"""TokenPet Local Intelligence Engine.

100% lokal: hanya modul bawaan Python. Tidak ada koneksi jaringan, tidak ada
AI/LLM, tidak ada API key. Semua analisis memakai statistik sederhana atas
data 9Router yang SUDAH dibaca TokenPet (selisih kumulatif per model).

Setiap hasil dibedakan: FACT (angka teramati), ESTIMATE (perkiraan statistik),
RECOMMENDATION (saran informasi, tidak pernah mengubah apa pun otomatis).
Jika data kurang -> INSUFFICIENT, bukan karangan.
"""

import datetime
import json
import math
import os
import threading
import time

SCHEMA = 1
FACT, ESTIMATE, RECOMMENDATION = "FACT", "ESTIMATE", "RECOMMENDATION"
INSUFFICIENT = "Data tidak mencukupi untuk membuat analisis yang dapat dipercaya."
UNSUPPORTED = ("Saya belum dapat menjawab pertanyaan tersebut\n"
               "berdasarkan data yang tersedia di TokenPet.")

MOODS = ("ERROR", "DISCONNECTED", "CRITICAL", "WORRIED", "SURPRISED",
         "THINKING", "EFFICIENT", "HAPPY", "IDLE", "SLEEPING")  # urut prioritas
CATEGORIES = ("quota_warning", "quota_prediction", "anomaly",
              "provider_connection", "session_summary",
              "smart_recommendation", "achievement")
CATEGORY_LABEL = {
    "quota_warning": "Peringatan kuota", "quota_prediction": "Prediksi kuota",
    "anomaly": "Anomali", "provider_connection": "Koneksi provider",
    "session_summary": "Ringkasan sesi",
    "smart_recommendation": "Rekomendasi pintar", "achievement": "Pencapaian"}

DEFAULT_SETTINGS = {
    "prediction_enabled": True,
    "anomaly_enabled": True,
    "anomaly_sensitivity": "medium",      # low | medium | high
    "idle_timeout_minutes": 10,
    "gamification_enabled": True,
    "notify": {c: True for c in CATEGORIES},
}


# ---------------------------------------------------------------- statistik
def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return 0.0
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def stdev(xs):
    xs = list(xs)
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def percentile(xs, p):
    xs = sorted(xs)
    if not xs:
        return 0.0
    i = (len(xs) - 1) * p / 100.0
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def mad(xs):
    xs = list(xs)
    if not xs:
        return 0.0
    m = median(xs)
    return median([abs(x - m) for x in xs])


def pct_change(new, old):
    return None if not old or old <= 0 else (new - old) / old * 100.0


def weighted_avg(pairs):
    """pairs: [(value, weight)] -> weighted average atau None."""
    tw = sum(w for _v, w in pairs)
    return None if tw <= 0 else sum(v * w for v, w in pairs) / tw


def linreg(points):
    """Regresi linear sederhana -> (slope, intercept, se_slope) atau None."""
    n = len(points)
    if n < 3:
        return None
    mx = mean(p[0] for p in points)
    my = mean(p[1] for p in points)
    sxx = sum((p[0] - mx) ** 2 for p in points)
    if sxx <= 0:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in points) / sxx
    icpt = my - slope * mx
    sse = sum((p[1] - (icpt + slope * p[0])) ** 2 for p in points)
    se = math.sqrt(max(0.0, sse / (n - 2)) / sxx)
    return slope, icpt, se


def fmt_tok(n):
    n = float(n or 0)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= lim:
            return ("%.1f%s" % (n / lim, suf)).replace(".0" + suf, suf)
    return "%d" % round(n)


def fmt_dur(sec):
    if sec is None:
        return "-"
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return "%dh %dj" % (d, h)
    if h:
        return "%dj %dm" % (h, m)
    if m:
        return "%dm" % m
    return "%ds" % sec


def day_start(now):
    d = datetime.datetime.fromtimestamp(now)
    return d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def today_key(now=None):
    return time.strftime("%Y-%m-%d", time.localtime(now or time.time()))


# ------------------------------------------------------------ log pemakaian
class UsageLog:
    """Selisih pemakaian per model per bucket 5 menit.

    Deduplikasi: pembacaan pertama hanya menjadi BASELINE (angka kumulatif
    lama tidak pernah dihitung sebagai pemakaian baru). Hanya kenaikan positif
    antar-poll yang dicatat. Baseline di-reset bila periode/metrik berganti,
    jeda poll terlalu lama (aplikasi tertutup), atau jam mundur. Model yang
    baru muncul juga hanya jadi baseline. Catatan: bila jendela 9Router
    bergulir (24h) dan angka lama keluar bersamaan dengan pemakaian baru,
    kenaikan bersih yang terlihat bisa lebih kecil dari yang sebenarnya.
    """
    BUCKET, KEEP, MAX_GAP = 300, 35 * 86400, 900

    def __init__(self):
        self.b = {}      # bucket_ts -> {model: [prompt, completion, requests]}
        self.obs = {}    # hour_ts -> detik teramati (poll berhasil beruntun)
        self._base = None
        self.latest = None   # waktu pengamatan terakhir (jam berjalan belum penuh)
        self.dirty = False

    def observe(self, rows, key, now):
        """rows: {model: (prompt, completion, requests)} -> {model: delta}."""
        out, base = {}, self._base
        cur = {m: tuple(float(x or 0) for x in v) for m, v in rows.items()}
        if (base is None or base["key"] != key or now < base["t"]
                or now - base["t"] > self.MAX_GAP):
            self._base = {"key": key, "t": now, "m": cur}
            return out
        self._add_obs(base["t"], now)
        self.latest = now
        k = int(now // self.BUCKET) * self.BUCKET
        for m, v in cur.items():
            prev = base["m"].get(m)
            if prev is None:
                continue
            d = tuple(max(0.0, a - b) for a, b in zip(v, prev))
            if any(d):
                out[m] = d
                rec = self.b.setdefault(k, {}).setdefault(m, [0.0, 0.0, 0.0])
                for i in range(3):
                    rec[i] += d[i]
                self.dirty = True
        self._base = {"key": key, "t": now, "m": cur}
        return out

    def _add_obs(self, t0, t1):
        t = t0
        while t < t1:
            h = int(t // 3600) * 3600
            seg = min(t1, h + 3600) - t
            self.obs[h] = self.obs.get(h, 0.0) + seg
            t += seg
        self.dirty = True

    def prune(self, now):
        cut = now - self.KEEP
        for k in [k for k in self.b if k < cut]:
            del self.b[k]
        for k in [k for k in self.obs if k < cut]:
            del self.obs[k]

    # --- query ---
    def _rows(self, start, end):
        for k, mods in self.b.items():
            if start <= k < end:
                yield k, mods

    def totals(self, start, end, model=None):
        p = c = r = 0.0
        for _k, mods in self._rows(start, end):
            for m, v in mods.items():
                if model is None or m == model:
                    p, c, r = p + v[0], c + v[1], r + v[2]
        return {"prompt": p, "completion": c, "tokens": p + c, "requests": r}

    def by_model(self, start, end):
        out = {}
        for _k, mods in self._rows(start, end):
            for m, v in mods.items():
                o = out.setdefault(m, {"prompt": 0.0, "completion": 0.0,
                                       "requests": 0.0})
                o["prompt"] += v[0]
                o["completion"] += v[1]
                o["requests"] += v[2]
        for o in out.values():
            o["tokens"] = o["prompt"] + o["completion"]
        return out

    def observed(self, start, end):
        tot = 0.0
        for h, sec in self.obs.items():
            h_end = h + 3600
            if self.latest is not None and h <= self.latest < h_end:
                h_end = max(self.latest, h + 1.0)   # jam berjalan: baru sampai sini
            lo, hi = max(h, start), min(h_end, end)
            if hi > lo:
                tot += min(sec, h_end - h) * (hi - lo) / (h_end - h)
        return tot

    def hourly(self, start, end):
        """[(jam_ts, tokens, requests, observed_sec)] per jam, urut waktu."""
        h0 = int(start // 3600) * 3600
        agg = {}
        for k, mods in self.b.items():
            if start <= k < end:
                h = int(k // 3600) * 3600
                a = agg.setdefault(h, [0.0, 0.0])
                for v in mods.values():
                    a[0] += v[0] + v[1]
                    a[1] += v[2]
        out, h = [], h0
        while h < end:
            a = agg.get(h, (0.0, 0.0))
            out.append((h, a[0], a[1], min(self.obs.get(h, 0.0), 3600.0)))
            h += 3600
        return out

    def active_buckets(self, start, end):
        return sum(1 for _k, m in self._rows(start, end)
                   if any(v[0] + v[1] > 0 for v in m.values()))

    def has_data(self):
        return bool(self.b)

    def to_json(self):
        return {"b": {str(k): {m: [round(x, 1) for x in v]
                               for m, v in mods.items()}
                      for k, mods in self.b.items()},
                "obs": {str(k): round(v, 1) for k, v in self.obs.items()}}

    def load(self, d, now):
        try:
            for k, mods in (d.get("b") or {}).items():
                for m, v in mods.items():
                    self.b.setdefault(int(k), {})[str(m)] = [
                        max(0.0, float(x)) for x in v[:3]]
            for k, v in (d.get("obs") or {}).items():
                self.obs[int(k)] = max(0.0, float(v))
        except (ValueError, TypeError, AttributeError):
            self.b, self.obs = {}, {}
        self.prune(now)


# -------------------------------------------------------------------- sesi
class SessionTracker:
    """Sesi = aktivitas + idle timeout. Memakai selisih dari UsageLog."""
    KEEP = 60

    def __init__(self, idle_fn):
        self.idle_fn = idle_fn
        self.cur = None
        self.history = []

    @staticmethod
    def _new(now):
        return {"start": now, "last": now, "requests": 0.0, "prompt": 0.0,
                "completion": 0.0, "models": {}}

    def on_activity(self, deltas, now):
        """deltas: {model: (dp, dc, dr)} -> sesi yang baru ditutup atau None."""
        closed = self.tick(now)
        if not deltas:
            return closed
        if self.cur is None:
            self.cur = self._new(now)
        s = self.cur
        for m, (dp, dc, dr) in deltas.items():
            s["prompt"] += dp
            s["completion"] += dc
            s["requests"] += dr
            mm = s["models"].setdefault(m, {"tokens": 0.0, "requests": 0.0})
            mm["tokens"] += dp + dc
            mm["requests"] += dr
        s["last"] = now
        return closed

    def tick(self, now):
        s = self.cur
        if s and now - s["last"] >= self.idle_fn():
            self.cur = None
            self.history.append(s)
            self.history = self.history[-self.KEEP:]
            return s
        return None

    def reset(self):
        """Reset manual: buang sesi berjalan (riwayat tetap)."""
        self.cur = None

    @staticmethod
    def summary(s, now=None):
        if not s:
            return None
        end = s["last"]
        toks = s["prompt"] + s["completion"]
        top = sorted(s["models"].items(), key=lambda kv: -kv[1]["tokens"])
        return {"start": s["start"], "end": end,
                "duration": max(0.0, end - s["start"]),
                "requests": s["requests"], "tokens": toks,
                "prompt": s["prompt"], "completion": s["completion"],
                "avg_per_request": (toks / s["requests"]
                                    if s["requests"] > 0 else None),
                "models": [m for m, _v in top]}

    def to_json(self):
        return {"cur": self.cur, "history": self.history}

    def load(self, d):
        try:
            if isinstance(d.get("cur"), dict):
                self.cur = d["cur"]
            self.history = [h for h in (d.get("history") or [])
                            if isinstance(h, dict) and "start" in h][-self.KEEP:]
        except (TypeError, AttributeError):
            self.cur, self.history = None, []


# ----------------------------------------------------------------- prediksi
class QuotaSamples:
    """Sampel % terpakai kuota RESMI (di memori) untuk regresi laju."""
    KEEP = 3 * 3600

    def __init__(self):
        self.s = {}

    def add(self, provider, wkey, used, now):
        lst = self.s.setdefault((provider, wkey), [])
        if lst and used < lst[-1][1] - 1.0:      # kuota reset -> mulai ulang
            lst.clear()
        if lst and used == lst[-1][1] and now - lst[-1][0] < 60:
            return
        lst.append((now, float(used)))
        cut = now - self.KEEP
        self.s[(provider, wkey)] = [x for x in lst if x[0] >= cut]

    def get(self, provider, wkey):
        return list(self.s.get((provider, wkey), []))


def predict_budget(log, remaining, reset_in, now, min_obs=900.0):
    """ESTIMASI kapan batas token (angka TokenPet, bukan kuota resmi) tercapai."""
    if remaining is None:
        return {"ok": False, "reason": "batas token tidak diketahui"}
    obs_h = log.observed(now - 3600, now)
    if obs_h < min_obs:
        return {"ok": False, "reason": INSUFFICIENT}
    rates, wl = [], []
    for w, wt in ((600, 3.0), (1800, 2.0), (3600, 1.0)):
        o = log.observed(now - w, now)
        if o >= min(w * 0.5, 300.0):
            rates.append(log.totals(now - w, now)["tokens"] / o)
            wl.append(wt)
    if not rates:
        return {"ok": False, "reason": INSUFFICIENT}
    rate = weighted_avg(list(zip(rates, wl)))
    if log.totals(now - 3600, now)["tokens"] <= 0 or rate <= 0:
        return {"ok": True, "idle": True, "rate_per_min": 0.0,
                "remaining": remaining}
    if log.active_buckets(now - 3600, now) < 2:
        return {"ok": False, "reason": INSUFFICIENT}
    hi, lo = max(rates), min(rates)
    eta_mid = remaining / rate
    eta_fast = remaining / hi
    eta_slow = remaining / lo if lo > 0 else None
    hits = None
    if reset_in is not None and reset_in > 0:
        if eta_slow is not None and eta_slow < reset_in:
            hits = "ya"
        elif eta_fast >= reset_in:
            hits = "tidak"
        else:
            hits = "mungkin"
    spread = hi / lo if lo > 0 else 99.0
    conf = ("tinggi" if obs_h >= 2700 and spread <= 2.5
            else "sedang" if obs_h >= 1500 and spread <= 6 else "rendah")
    return {"ok": True, "idle": False, "basis": "estimasi batas TokenPet",
            "rate_per_min": rate * 60.0, "remaining": remaining,
            "eta_mid": eta_mid, "eta_fast": eta_fast, "eta_slow": eta_slow,
            "reset_in": reset_in, "hits": hits, "confidence": conf}


def predict_quota_window(samples, reset_in):
    """ESTIMASI habis kuota RESMI satu jendela dari tren % terpakai."""
    if len(samples) < 4 or samples[-1][0] - samples[0][0] < 600:
        return {"ok": False, "reason": INSUFFICIENT}
    t0 = samples[0][0]
    fit = linreg([(t - t0, u) for t, u in samples])
    if not fit:
        return {"ok": False, "reason": INSUFFICIENT}
    slope, _i, se = fit
    last = samples[-1][1]
    if slope <= 1e-9:
        return {"ok": True, "idle": True, "used": last}
    if se / slope > 1.0:
        return {"ok": False, "reason": INSUFFICIENT}
    left = max(0.0, 100.0 - last)
    eta_mid = left / slope
    eta_fast = left / (slope + se)
    eta_slow = left / (slope - se) if slope - se > 1e-9 else None
    hits = None
    if reset_in is not None and reset_in > 0:
        if eta_slow is not None and eta_slow < reset_in:
            hits = "ya"
        elif eta_fast >= reset_in:
            hits = "tidak"
        else:
            hits = "mungkin"
    r = se / slope
    conf = "tinggi" if len(samples) >= 8 and r < 0.25 else \
        "sedang" if r < 0.5 else "rendah"
    return {"ok": True, "idle": False, "used": last,
            "pct_per_hour": slope * 3600.0, "eta_mid": eta_mid,
            "eta_fast": eta_fast, "eta_slow": eta_slow, "reset_in": reset_in,
            "hits": hits, "confidence": conf}


# ------------------------------------------------------------------ anomali
SENS = {"low": dict(z=6.0, ratio=5.0, mratio=4.0, floor=100000.0),
        "medium": dict(z=4.0, ratio=3.0, mratio=2.5, floor=50000.0),
        "high": dict(z=3.0, ratio=2.0, mratio=1.8, floor=20000.0)}
NO_CAUSE = "Penyebab tidak dapat ditentukan dari data lokal."


class AnomalyDetector:
    """Bandingkan jendela terkini dengan baseline historis (7 hari)."""
    WIN, BASE_DAYS, MIN_BASE_HOURS, CONFIRM = 900, 7, 24, 2
    COOLDOWN, EXPIRE, KEEP = 3600, 6 * 3600, 100

    def __init__(self):
        self.items = {}       # id -> dict
        self.ignored = []     # ["kind|model"]
        self._hits = {}
        self.mode = None

    @staticmethod
    def _key(kind, model):
        return "%s|%s" % (kind, model or "")

    def active(self):
        return [a for a in self.items.values() if a["status"] == "new"]

    @staticmethod
    def _hod(ts):
        return time.localtime(ts).tm_hour

    def baseline(self, log, now):
        """Baseline per 1 jam: jam-dalam-sehari yang sama (+-2 jam) bila ada
        >= 6 sampel; jika tidak, hanya jam yang aktif. Jam sepi (malam) tidak
        dicampur dengan jam kerja supaya pemakaian normal tidak dianggap
        lonjakan. -> (list[(tokens, requests)], mode) atau ([], None)."""
        hrs = [(h, t, r) for h, t, r, o in
               log.hourly(now - self.BASE_DAYS * 86400, now - 3600)
               if o >= 600.0]
        if len(hrs) < self.MIN_BASE_HOURS:
            return [], None
        cur = self._hod(now)
        same = [(t, r) for h, t, r in hrs
                if min((self._hod(h) - cur) % 24, (cur - self._hod(h)) % 24) <= 2]
        if len(same) >= 6:
            return same, "jam-sama"
        active = [(t, r) for _h, t, r in hrs if t > 0]
        if len(active) >= 8:
            return active, "jam-aktif"
        return [], None

    def evaluate(self, log, now, sensitivity="medium"):
        """-> (anomali baru, status) ; status 'ok' | 'insufficient'."""
        sens = SENS.get(sensitivity, SENS["medium"])
        for a in self.items.values():
            if a["status"] == "new" and now - a["last_at"] > self.EXPIRE:
                a["status"] = "expired"
        hrs, self.mode = self.baseline(log, now)
        if not hrs:
            return [], "insufficient"
        raised, seen = [], set()
        tok = [t / 4.0 for t, _r in hrs]     # per 15 menit
        req = [r / 4.0 for _t, r in hrs]
        cur = log.totals(now - self.WIN, now)
        obs = log.observed(now - self.WIN, now)
        if obs >= 300.0:
            scale = self.WIN / obs
            for kind, val, base, floor, unit in (
                    ("token_spike", cur["tokens"] * scale, tok,
                     sens["floor"], "token/15 menit"),
                    ("request_spike", cur["requests"] * scale, req,
                     max(5.0, sens["floor"] / 10000.0), "request/15 menit")):
                m, sd = mean(base), stdev(base)
                md = max(median(base), percentile(base, 75))   # tahan batas jam
                spread = max(1.4826 * mad(base), 0.5 * sd, 0.25 * m, 1.0)
                thr = max(md + sens["z"] * spread,
                          sens["ratio"] * max(md, 0.5 * m), floor)
                hit = val >= thr
                ev = self._confirm(kind, None, hit, now)
                seen.add(self._key(kind, None))
                if ev:
                    a = self._raise(kind, None, now, val, md, unit)
                    if a:
                        raised.append(a)
        bs, be = now - self.BASE_DAYS * 86400, now - 3600
        base_m, rec_m = log.by_model(bs, be), log.by_model(now - 3600, now)
        for m, rv in rec_m.items():
            bv = base_m.get(m)
            if not bv or bv["requests"] < 20 or rv["requests"] < 3:
                continue
            ab, ar = bv["tokens"] / bv["requests"], rv["tokens"] / rv["requests"]
            hit = ar >= sens["mratio"] * ab and ar - ab >= 2000
            seen.add(self._key("model_spike", m))
            if self._confirm("model_spike", m, hit, now):
                a = self._raise("model_spike", m, now, ar, ab,
                                "token/request")
                if a:
                    raised.append(a)
        o1 = log.observed(now - 3600, now)
        if o1 >= 1800 and not any(
                x["kind"] == "token_spike" for x in self.active()):
            base1h = [t for t, _r in hrs]            # per jam, baseline sama
            r1 = log.totals(now - 3600, now)["tokens"] / o1 * 3600
            m1, sd1 = mean(base1h), stdev(base1h)
            md1 = max(median(base1h), percentile(base1h, 75))
            spread = max(1.4826 * mad(base1h), 0.5 * sd1, 0.25 * m1, 1.0)
            up = (r1 >= md1 + sens["z"] * spread and
                  r1 >= sens["ratio"] * max(md1, 0.5 * m1) and
                  r1 >= 4 * sens["floor"])
            seen.add(self._key("rate_shift", None))
            if self._confirm("rate_shift", None, up, now):
                x = self._raise("rate_shift", None, now, r1, md1,
                                "token/jam")
                if x:
                    raised.append(x)
        for k in list(self._hits):
            if k not in seen:
                self._hits[k] = 0
        if len(self.items) > self.KEEP:
            old = sorted(self.items.values(), key=lambda a: a["last_at"])
            for a in old[:len(self.items) - self.KEEP]:
                self.items.pop(a["id"], None)
        return raised, "ok"

    def _confirm(self, kind, model, hit, now):
        k = self._key(kind, model)
        self._hits[k] = self._hits.get(k, 0) + 1 if hit else 0
        return hit and self._hits[k] >= self.CONFIRM

    def _raise(self, kind, model, now, val, base, unit):
        if self._key(kind, model) in self.ignored:
            return None
        for a in self.items.values():
            if (a["kind"], a["model"]) == (kind, model) and \
                    now - a["last_at"] < self.COOLDOWN:
                a["last_at"] = now
                return None
        aid = "%s-%d" % (self._key(kind, model), int(now))
        what = {"token_spike": "Pemakaian token jauh di atas biasanya",
                "request_spike": "Jumlah request jauh di atas biasanya",
                "model_spike": "Token per request model ini jauh di atas biasanya",
                "rate_shift": "Laju pemakaian 1 jam terakhir naik tajam"}[kind]
        a = {"id": aid, "kind": kind, "model": model, "first_at": now,
             "last_at": now, "status": "new", "value": val, "baseline": base,
             "unit": unit,
             "text": "%s%s: %s vs baseline %s %s. %s" % (
                 what, " (%s)" % model if model else "", fmt_tok(val),
                 fmt_tok(base), unit, NO_CAUSE)}
        self.items[aid] = a
        return a

    def set_status(self, aid, status):
        a = self.items.get(aid)
        if not a:
            return False
        if status == "ignored":
            k = self._key(a["kind"], a["model"])
            if k not in self.ignored:
                self.ignored.append(k)
        a["status"] = status
        return True

    def to_json(self):
        return {"items": self.items, "ignored": self.ignored}

    def load(self, d):
        try:
            self.items = {k: v for k, v in (d.get("items") or {}).items()
                          if isinstance(v, dict) and "kind" in v}
            self.ignored = [str(x) for x in (d.get("ignored") or [])]
        except (TypeError, AttributeError):
            self.items, self.ignored = {}, []


# ------------------------------------------------------- rekomendasi model
def advise_models(log, now, days=7, min_req=5):
    """Perbandingan konsumsi token per request. Bukan klaim kualitas/harga."""
    bm = log.by_model(now - days * 86400, now)
    ok = {m: v for m, v in bm.items() if v["requests"] >= min_req}
    if not ok:
        return {"ok": False, "reason": INSUFFICIENT}
    rank = sorted(({"model": m, "avg": v["tokens"] / v["requests"],
                    "requests": v["requests"], "tokens": v["tokens"],
                    "prompt_share": (v["prompt"] / v["tokens"]
                                     if v["tokens"] > 0 else 0.0)}
                   for m, v in ok.items()), key=lambda r: r["avg"])
    all_req = sum(v["requests"] for v in ok.values())
    all_avg = sum(v["tokens"] for v in ok.values()) / all_req
    out = {"ok": True, "ranking": rank, "overall_avg": all_avg, "days": days,
           "compare": len(rank) >= 2, "notes": []}
    if len(rank) >= 2:
        b = rank[0]
        out["best"] = b
        out["lower_pct"] = (all_avg - b["avg"]) / all_avg * 100.0
    for r in rank:
        if r["prompt_share"] >= 0.95 and r["avg"] >= 20000:
            out["notes"].append(
                "%s: %.0f%% token adalah prompt (rata-rata %s token/request)."
                % (r["model"], r["prompt_share"] * 100, fmt_tok(r["avg"])))
    return out


# ---------------------------------------------------------- kesehatan koneksi
class ProviderHealth:
    """ONLINE | OFFLINE | AUTH ERROR | QUOTA LIMIT | UNKNOWN.

    Memakai hasil polling yang SUDAH ada (tanpa request tambahan). Satu
    kegagalan tidak pernah dinyatakan 'down'.
    """
    FAIL_N = 3

    def __init__(self):
        self.last_success = None
        self.last_error = None
        self.last_error_kind = None
        self.latency = None       # detik, poll terakhir yang sukses
        self.latency_avg = None
        self.fails = 0
        self.auth_fail = 0
        self.attempts = 0

    def ok(self, latency, now):
        self.attempts += 1
        self.last_success, self.fails, self.auth_fail = now, 0, 0
        if latency is not None and latency >= 0:
            self.latency = latency
            self.latency_avg = (latency if self.latency_avg is None
                                else 0.8 * self.latency_avg + 0.2 * latency)

    def fail(self, kind, msg, now):
        self.attempts += 1
        self.fails += 1
        self.last_error, self.last_error_kind = str(msg)[:80], kind
        self.auth_fail = self.auth_fail + 1 if kind == "auth" else 0

    def status(self, quota_limit=False):
        if self.attempts == 0:
            return "UNKNOWN"
        if self.auth_fail >= 1:
            return "AUTH ERROR"
        if self.fails >= self.FAIL_N:
            return "OFFLINE"
        if self.fails > 0:
            return "UNKNOWN"          # belum cukup bukti
        return "QUOTA LIMIT" if quota_limit else "ONLINE"


def classify_error(exc):
    """Kelompokkan exception polling -> auth | connection | other."""
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return "auth"
    name = type(exc).__name__
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)) or \
            name in ("URLError", "timeout", "RemoteDisconnected"):
        return "connection"
    return "other"


# --------------------------------------------------------------------- mood
class MoodResolver:
    """Pilih mood berdasar prioritas dengan debounce (tanpa animasi baru)."""
    UP_NOW = ("ERROR", "DISCONNECTED", "CRITICAL")

    def __init__(self, settle=6.0, hold=12.0):
        self.cur, self.pending = "IDLE", "IDLE"
        self.pending_at = self.changed_at = 0.0
        self.settle, self.hold = settle, hold

    @staticmethod
    def target(s, sleep_after=600.0):
        if s.get("err_kind") in ("auth", "other") and s.get("err_streak", 0) >= 3:
            return "ERROR"
        if s.get("err_kind") == "connection" and s.get("err_streak", 0) >= 2:
            return "DISCONNECTED"
        if s.get("label") == "CRITICAL":
            return "CRITICAL"
        if s.get("label") == "HOT" or s.get("predicted_hit"):
            return "WORRIED"
        if s.get("anomaly_active"):
            return "SURPRISED"
        if s.get("running", 0) > 0 or s.get("busy"):
            return "THINKING"
        if s.get("efficient"):
            return "EFFICIENT"
        if s.get("happy"):
            return "HAPPY"
        return "SLEEPING" if s.get("idle_seconds", 0) >= sleep_after else "IDLE"

    def update(self, s, now=None, sleep_after=600.0):
        now = time.time() if now is None else now
        t = self.target(s, sleep_after)
        if t == self.cur:
            self.pending, self.pending_at = t, now
            return self.cur, False
        if t in self.UP_NOW and MOODS.index(t) < MOODS.index(self.cur):
            self.cur, self.pending, self.pending_at = t, t, now
            self.changed_at = now
            return self.cur, True
        if t != self.pending:
            self.pending, self.pending_at = t, now
            return self.cur, False
        if now - self.pending_at < self.settle or \
                now - self.changed_at < self.hold:
            return self.cur, False
        self.cur, self.changed_at = t, now
        return self.cur, True


# ----------------------------------------------------------------- notifikasi
class NotificationCenter:
    """Kategori, prioritas, cooldown, dedup, riwayat. Tidak spam popup."""
    COOLDOWN = {"quota_warning": 600, "quota_prediction": 1800,
                "anomaly": 600, "provider_connection": 300,
                "session_summary": 120, "smart_recommendation": 6 * 3600,
                "achievement": 0}
    DEDUP, KEEP, POPUP_GAP = 3600, 100, 20

    def __init__(self, enabled_fn):
        self.enabled_fn = enabled_fn
        self.history = []
        self._cat_at, self._key_at, self._popup_at = {}, {}, -1e9

    def submit(self, cat, key, text, priority=2, now=None):
        """-> dict(popup: bool, ...) atau None bila ditekan."""
        now = time.time() if now is None else now
        if cat not in CATEGORIES or not self.enabled_fn(cat):
            return None
        if now - self._key_at.get((cat, key), -1e9) < self.DEDUP:
            return None
        if priority < 3 and now - self._cat_at.get(cat, -1e9) < \
                self.COOLDOWN.get(cat, 600):
            return None
        self._key_at[(cat, key)] = self._cat_at[cat] = now
        popup = priority >= 2 and (priority >= 3 or
                                   now - self._popup_at >= self.POPUP_GAP)
        if popup:
            self._popup_at = now
        n = {"t": now, "cat": cat, "key": key, "text": text,
             "priority": priority, "popup": popup}
        self.history.append(n)
        self.history = self.history[-self.KEEP:]
        return n

    def record(self, cat, text, now=None):
        """Catat ke riwayat tanpa popup (mis. alert sistem lama)."""
        self.history.append({"t": time.time() if now is None else now,
                             "cat": cat, "key": "", "text": text,
                             "priority": 2, "popup": False})
        self.history = self.history[-self.KEEP:]

    def to_json(self):
        return {"history": self.history}

    def load(self, d):
        try:
            self.history = [h for h in (d.get("history") or [])
                            if isinstance(h, dict) and "text" in h][-self.KEEP:]
        except (TypeError, AttributeError):
            self.history = []


# ------------------------------------------------------------ gamifikasi
MISSIONS = (("open", "Buka TokenPet"),
            ("alert", "Tinjau satu peringatan penting"),
            ("session", "Selesaikan satu sesi penggunaan AI"),
            ("usage", "Cek pemakaian hari ini"))
MISSION_XP, ACH_XP = 20, 50
# Level -> aksesoris yang ditandai terbuka (hanya penanda; aksesoris lama
# tetap bebas dipakai, sistem aksesoris tidak diubah).
UNLOCKS = {2: ("hat", "cap"), 3: ("eyes", "round"), 4: ("neck", "bow"),
           5: ("other", "badge"), 7: ("hat", "crown"), 10: ("back", "cape")}
ACHIEVEMENTS = {
    "first_day": "Hari pertama bersama TokenPet",
    "streak3": "3 hari berturut-turut membuka TokenPet",
    "streak7": "7 hari berturut-turut membuka TokenPet",
    "reviewer5": "Meninjau 5 peringatan",
    "all_missions": "Menyelesaikan semua misi dalam sehari",
    "level5": "Mencapai level 5",
}


class Gamification:
    """XP hanya dari misi/pencapaian — TIDAK dari jumlah token/request."""

    def __init__(self):
        self.xp, self.level = 0, 1
        self.day, self.done = "", {}
        self.streak, self.last_open = 0, ""
        self.counters = {"alerts": 0}
        self.ach, self.unlocked = {}, []

    @staticmethod
    def need(level):
        return 100 + 40 * (level - 1)

    def _roll(self, now):
        d = today_key(now)
        if d != self.day:
            self.day, self.done = d, {}

    def _gain(self, n, msgs):
        self.xp += n
        while self.xp >= self.need(self.level):
            self.xp -= self.need(self.level)
            self.level += 1
            msgs.append("Naik ke level %d!" % self.level)
            if self.level in UNLOCKS:
                slot, key = UNLOCKS[self.level]
                self.unlocked.append("%s:%s" % (slot, key))
                msgs.append("Aksesoris ditandai terbuka: %s/%s" % (slot, key))
            if self.level == 5:
                self._award("level5", msgs)

    def _award(self, aid, msgs):
        if aid not in self.ach:
            self.ach[aid] = today_key()
            msgs.append("Pencapaian: %s" % ACHIEVEMENTS[aid])
            self._gain(ACH_XP, msgs)

    def event(self, name, now=None):
        """name: open | alert | session | usage -> daftar pesan."""
        now = time.time() if now is None else now
        self._roll(now)
        msgs = []
        if name == "alert":
            self.counters["alerts"] = self.counters.get("alerts", 0) + 1
            if self.counters["alerts"] >= 5:
                self._award("reviewer5", msgs)
        if name == "open" and self.last_open != self.day:
            yest = today_key(now - 86400)
            self.streak = self.streak + 1 if self.last_open == yest else 1
            self.last_open = self.day
            self._award("first_day", msgs)
            if self.streak >= 3:
                self._award("streak3", msgs)
            if self.streak >= 7:
                self._award("streak7", msgs)
        if name in dict(MISSIONS) and not self.done.get(name):
            self.done[name] = True
            msgs.append("Misi selesai: %s (+%d XP)" % (
                dict(MISSIONS)[name], MISSION_XP))
            self._gain(MISSION_XP, msgs)
            if all(self.done.get(k) for k, _l in MISSIONS):
                self._award("all_missions", msgs)
        return msgs

    def status(self, now=None):
        self._roll(time.time() if now is None else now)
        return {"xp": self.xp, "need": self.need(self.level),
                "level": self.level, "streak": self.streak,
                "missions": [(k, l, bool(self.done.get(k)))
                             for k, l in MISSIONS],
                "achievements": [(k, ACHIEVEMENTS[k], d)
                                 for k, d in self.ach.items()
                                 if k in ACHIEVEMENTS],
                "unlocked": list(self.unlocked)}

    def to_json(self):
        return {"xp": self.xp, "level": self.level, "day": self.day,
                "done": self.done, "streak": self.streak,
                "last_open": self.last_open, "counters": self.counters,
                "ach": self.ach, "unlocked": self.unlocked}

    def load(self, d):
        try:
            self.xp = max(0, int(d.get("xp", 0)))
            self.level = max(1, int(d.get("level", 1)))
            self.day = str(d.get("day", ""))
            self.done = dict(d.get("done") or {})
            self.streak = max(0, int(d.get("streak", 0)))
            self.last_open = str(d.get("last_open", ""))
            self.counters = dict(d.get("counters") or {"alerts": 0})
            self.ach = dict(d.get("ach") or {})
            self.unlocked = list(d.get("unlocked") or [])
        except (TypeError, ValueError, AttributeError):
            self.__init__()


# ------------------------------------------------------------------- engine
class LocalIntelligenceEngine:
    """Pusat analisis lokal TokenPet. Aman dipanggil dari thread mana pun."""
    EVAL_EVERY = 60.0

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.log = UsageLog()
        self.sessions = SessionTracker(
            lambda: max(60.0, float(self.settings["idle_timeout_minutes"]) * 60))
        self.qsamples = QuotaSamples()
        self.anomalies = AnomalyDetector()
        self.health = ProviderHealth()
        self.mood = MoodResolver()
        self.notes = NotificationCenter(
            lambda c: bool(self.settings["notify"].get(c, True)))
        self.game = Gamification()
        self.ctx = {}                 # konteks terbaru dari TokenPet
        self.anomaly_state = "insufficient"
        self._eval_at = 0.0
        self._cache, self._cache_at = None, 0.0
        self.last_activity = None
        self.load()

    # --- persistensi (tanpa secret; hanya angka dan nama model) ---
    def load(self):
        now = time.time()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("root")
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError):
            try:
                os.replace(self.path, "%s.corrupt-%s" % (
                    self.path, time.strftime("%Y%m%d-%H%M%S")))
            except OSError:
                pass
            return
        with self.lock:
            st = d.get("settings")
            if isinstance(st, dict):
                for k, v in st.items():
                    if k == "notify" and isinstance(v, dict):
                        self.settings["notify"].update(
                            {c: bool(v.get(c, True)) for c in CATEGORIES})
                    elif k in DEFAULT_SETTINGS and k != "notify":
                        self.settings[k] = v
            self.log.load(d.get("usage") or {}, now)
            self.sessions.load(d.get("sessions") or {})
            self.anomalies.load(d.get("anomalies") or {})
            self.notes.load(d.get("notifications") or {})
            self.game.load(d.get("game") or {})
            self.last_activity = d.get("last_activity")

    def save(self):
        with self.lock:
            self.log.prune(time.time())
            data = {"schema_version": SCHEMA, "settings": self.settings,
                    "usage": self.log.to_json(),
                    "sessions": self.sessions.to_json(),
                    "anomalies": self.anomalies.to_json(),
                    "notifications": self.notes.to_json(),
                    "game": self.game.to_json(),
                    "last_activity": self.last_activity}
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.path)
            self.log.dirty = False
        except OSError:
            pass

    def set_setting(self, key, value):
        with self.lock:
            if key.startswith("notify."):
                self.settings["notify"][key[7:]] = bool(value)
            elif key in DEFAULT_SETTINGS and key != "notify":
                self.settings[key] = value
            self._cache = None

    # --- input dari TokenPet ---
    def observe(self, rows, key, ctx=None, now=None):
        """Dipanggil tiap poll sukses. -> dict event untuk integrasi UI."""
        now = time.time() if now is None else now
        ev = {"mission": [], "closed": None}
        with self.lock:
            if ctx is not None:
                self.ctx = ctx
            deltas = self.log.observe(rows, key, now)
            if deltas:
                self.last_activity = now
            closed = self.sessions.on_activity(deltas, now)
            if closed:
                ev["closed"] = self.sessions.summary(closed)
                ev["mission"] += self._game("session", now)
            self._cache = None
        return ev

    def evaluate(self, now=None):
        """Deteksi anomali (dijalankan di thread latar, tiap ~EVAL_EVERY dtk).
        -> anomali baru. Tidak menyentuh Tk."""
        now = time.time() if now is None else now
        with self.lock:
            if not self.settings["anomaly_enabled"]:
                return []
            self._eval_at = now
            new, self.anomaly_state = self.anomalies.evaluate(
                self.log, now, self.settings["anomaly_sensitivity"])
            self._cache = None
            return new

    def observe_quota(self, provider, snap, now=None):
        now = time.time() if now is None else now
        with self.lock:
            for w in (snap or {}).get("windows", []) or []:
                try:
                    self.qsamples.add(provider, w.get("key", ""),
                                      float(w["used"]), now)
                except (KeyError, TypeError, ValueError):
                    continue

    def poll_ok(self, latency, now=None):
        with self.lock:
            self.health.ok(latency, time.time() if now is None else now)

    def poll_fail(self, kind, msg, now=None):
        with self.lock:
            self.health.fail(kind, msg, time.time() if now is None else now)

    def tick(self, now=None):
        """Panggil berkala: menutup sesi yang idle. -> ringkasan atau None."""
        now = time.time() if now is None else now
        with self.lock:
            closed = self.sessions.tick(now)
            if not closed:
                return None
            self._cache = None
            return {"summary": self.sessions.summary(closed),
                    "mission": self._game("session", now)}

    def _game(self, name, now):
        return self.game.event(name, now) if \
            self.settings["gamification_enabled"] else []

    def notify(self, cat, key, text, priority=2, now=None):
        with self.lock:
            return self.notes.submit(cat, key, text, priority, now)

    def record_notification(self, cat, text, now=None):
        with self.lock:
            self.notes.record(cat, text, now)

    def game_event(self, name, now=None):
        with self.lock:
            return self._game(name, time.time() if now is None else now)

    def anomaly_action(self, aid, status):
        with self.lock:
            ok = self.anomalies.set_status(aid, status)
            self._cache = None
            msgs = self._game("alert", time.time()) \
                if ok and status in ("reviewed", "dismissed", "ignored") else []
            return ok, msgs

    def reset_session(self):
        with self.lock:
            self.sessions.reset()
            self._cache = None

    def mood_state(self, inputs, now=None):
        now = time.time() if now is None else now
        with self.lock:
            inp = dict(inputs)
            inp["anomaly_active"] = bool(self.anomalies.active())
            inp["idle_seconds"] = (now - self.last_activity
                                   if self.last_activity else 1e9)
            inp["efficient"] = self._efficient(now)
            return self.mood.update(inp, now)

    def _efficient(self, now):
        rec = self.log.totals(now - 3600, now)
        base = self.log.totals(now - 7 * 86400, now - 3600)
        if rec["requests"] < 5 or base["requests"] < 30:
            return False
        return (rec["tokens"] / rec["requests"] <=
                0.7 * base["tokens"] / base["requests"])

    # --- analisis (hasil di-cache 15 dtk) ---
    def analyze(self, now=None, force=False):
        now = time.time() if now is None else now
        with self.lock:
            if not force and self._cache and now - self._cache_at < 15:
                return self._cache
            a = self._analyze(now)
            self._cache, self._cache_at = a, now
            return a

    def _window(self, start, end):
        t = self.log.totals(start, end)
        return {**t, "avg": (t["tokens"] / t["requests"]
                             if t["requests"] > 0 else None),
                "observed": self.log.observed(start, end)}

    def _analyze(self, now):
        ds = day_start(now)
        s = self.settings
        a = {"now": now, "has_data": self.log.has_data(),
             "today": self._window(ds, now),
             "last24h": self._window(now - 86400, now),
             "week": self._window(now - 7 * 86400, now),
             "models_today": self.log.by_model(ds, now),
             "models_24h": self.log.by_model(now - 86400, now)}
        cur, prev = a["last24h"], self._window(now - 2 * 86400, now - 86400)
        a["trend"] = {"ok": False}
        if cur["observed"] >= 6 * 3600 and prev["observed"] >= 6 * 3600:
            rc = cur["tokens"] / cur["observed"] * 3600
            rp = prev["tokens"] / prev["observed"] * 3600
            a["trend"] = {"ok": True, "recent_rate": rc, "prev_rate": rp,
                          "change_pct": pct_change(rc, rp),
                          "recent": cur["tokens"], "prev": prev["tokens"]}
        ctx = self.ctx or {}
        a["quota"] = {"budget": ctx.get("budget"), "bsrc": ctx.get("bsrc"),
                      "used": ctx.get("tot_t"),
                      "left_pct": ctx.get("left_pct"),
                      "reset_in": ctx.get("reset_in"),
                      "period": ctx.get("period"),
                      "official": ctx.get("official") or []}
        a["prediction"] = {"enabled": bool(s["prediction_enabled"]),
                           "budget": None, "official": []}
        if s["prediction_enabled"]:
            b, u = ctx.get("budget"), ctx.get("tot_t")
            if b and u is not None and b > 0:
                a["prediction"]["budget"] = predict_budget(
                    self.log, max(0.0, b - u), ctx.get("reset_in"), now)
            for o in ctx.get("official") or []:
                p = predict_quota_window(
                    self.qsamples.get(o["provider"], o["key"]),
                    o.get("reset_in"))
                a["prediction"]["official"].append({**o, "result": p})
        a["anomalies"] = {"enabled": bool(s["anomaly_enabled"]),
                          "state": self.anomaly_state,
                          "active": self.anomalies.active(),
                          "all": sorted(self.anomalies.items.values(),
                                        key=lambda x: -x["last_at"])[:30]}
        a["advice"] = advise_models(self.log, now)
        a["session"] = {"current": self.sessions.summary(self.sessions.cur),
                        "last": self.sessions.summary(
                            self.sessions.history[-1]
                            if self.sessions.history else None),
                        "history": [self.sessions.summary(h) for h in
                                    reversed(self.sessions.history[-20:])]}
        ql = bool(ctx.get("quota_limit"))
        h = self.health
        a["health"] = {"status": h.status(ql), "last_success": h.last_success,
                       "latency": h.latency, "latency_avg": h.latency_avg,
                       "fails": h.fails, "last_error": h.last_error,
                       "last_error_kind": h.last_error_kind}
        a["game"] = self.game.status(now)
        a["notifications"] = list(reversed(self.notes.history[-15:]))
        a["mood"] = self.mood.cur
        return a
