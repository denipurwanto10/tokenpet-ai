"""Asisten lokal TokenPet. BUKAN LLM.

Alur: input -> IntentMatcher (keyword/regex) -> LocalIntelligenceEngine
-> template jawaban deterministik. Pertanyaan di luar daftar dijawab dengan
UNSUPPORTED; data kurang dijawab dengan INSUFFICIENT. Tidak ada jaringan.
"""

import re

from local_intel import (ESTIMATE, FACT, INSUFFICIENT, RECOMMENDATION,
                         UNSUPPORTED, fmt_dur, fmt_tok)

# intent -> daftar (regex, bobot). Skor tertinggi menang; < MIN = unknown.
PATTERNS = {
    "most_used_model": [
        (r"\bmodel\b.*\b(paling|terbanyak|sering)\b", 3),
        (r"\b(paling|terbanyak)\b.*\bmodel\b", 3),
        (r"\bmodel apa\b", 1), (r"\b(banyak|sering) (dipakai|digunakan)\b", 2)],
    "total_tokens": [
        (r"\btotal token\b", 4), (r"\bberapa token\b", 4),
        (r"\bjumlah token\b", 4), (r"\btoken saya\b", 1)],
    "total_requests": [
        (r"\b(berapa|jumlah|total) request\b", 5), (r"\brequest saya\b", 2)],
    "avg_tokens": [
        (r"\brata[- ]?rata\b", 3), (r"\btoken (per|/|tiap) request\b", 4),
        (r"\bper request\b", 2)],
    "session_usage": [(r"\b(sesi|session)\b", 5)],
    "usage_trend": [
        (r"\b(meningkat|naik|turun|menurun|tren|trend)\b", 3),
        (r"\bdibandingkan\b", 4), (r"\bsebelumnya\b", 3),
        (r"\bpenggunaan\b", 1)],
    "quota_status": [
        (r"\b(quota|kuota)\b", 3), (r"\bsisa\b", 1), (r"\bkondisi\b", 1)],
    "quota_prediction": [
        (r"\bkapan\b", 2), (r"\bdiperkirakan\b", 3), (r"\bprediksi\b", 4),
        (r"\b(habis|mencapai batas|batas)\b", 2), (r"\bestimasi\b", 3)],
    "anomaly_status": [
        (r"\b(tidak biasa|anomali|aneh|lonjakan|janggal)\b", 5),
        (r"\baktivitas\b", 1)],
    "model_efficiency": [
        (r"\b(efisien|hemat|rekomendasi|rekomendasikan|irit)\b", 5)],
    "provider_status": [
        (r"\b(koneksi|provider|9router|online|offline|terhubung)\b", 4),
        (r"\bstatus\b", 1)],
    "help": [(r"\b(bantuan|help|bisa apa|menu)\b", 5)],
}
MIN_SCORE = 3

SUGGESTIONS = (
    "Model apa yang paling banyak digunakan hari ini?",
    "Berapa total token saya?",
    "Berapa request saya hari ini?",
    "Apakah penggunaan saya meningkat?",
    "Model mana yang paling efisien?",
    "Apakah ada aktivitas tidak biasa?",
    "Berapa rata-rata token per request?",
    "Bagaimana kondisi quota?",
    "Kapan quota diperkirakan mencapai batas?",
)


def normalize(text):
    t = re.sub(r"[^\w\s/-]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def match_intent(text):
    t = normalize(text)
    if not t:
        return "unknown", 0
    scores = {}
    for intent, pats in PATTERNS.items():
        sc = sum(w for rx, w in pats if re.search(rx, t))
        if sc:
            scores[intent] = sc
    if not scores:
        return "unknown", 0
    # "kapan quota ..." harus menang atas quota_status
    if "quota_prediction" in scores and "quota_status" in scores and \
            scores["quota_prediction"] >= 3:
        scores["quota_prediction"] += 2
    best = max(scores, key=lambda k: (scores[k], k))
    return (best, scores[best]) if scores[best] >= MIN_SCORE \
        else ("unknown", scores[best])


def _scope(text):
    t = normalize(text)
    if re.search(r"\b(24 jam|kemarin)\b", t):
        return "last24h", "24 jam terakhir"
    if re.search(r"\b(minggu|7 hari|seminggu)\b", t):
        return "week", "7 hari terakhir"
    return "today", "hari ini"


def _line(tag, text):
    return "[%s] %s" % (tag, text)


def _need(a, scope):
    w = a.get(scope) or {}
    return not a.get("has_data") or w.get("observed", 0) < 300


def _models(a, scope):
    if scope == "today":
        return a["models_today"]
    if scope == "last24h":
        return a["models_24h"]
    return {}


def answer(intent, analysis, text=""):
    """Template deterministik. analysis = engine.analyze()."""
    a = analysis
    scope, label = _scope(text)
    if intent == "help":
        return "Contoh pertanyaan yang saya pahami:\n- " + "\n- ".join(SUGGESTIONS)
    if intent == "unknown":
        return UNSUPPORTED
    if intent in ("most_used_model", "total_tokens", "total_requests",
                  "avg_tokens"):
        if _need(a, scope):
            return INSUFFICIENT
        w = a[scope]
        if intent == "most_used_model":
            bm = _models(a, scope) or a["models_24h"]
            if not bm:
                return INSUFFICIENT
            top = max(bm.items(), key=lambda kv: kv[1]["tokens"])
            tot = sum(v["tokens"] for v in bm.values())
            return _line(FACT, "Model terbanyak %s: %s dengan %s token (%d%% "
                         "dari total teramati) dan %d request." % (
                             label, top[0], fmt_tok(top[1]["tokens"]),
                             round(top[1]["tokens"] / tot * 100) if tot else 0,
                             top[1]["requests"]))
        if intent == "total_tokens":
            return _line(FACT, "Total token %s: %s (input %s, output %s)." % (
                label, fmt_tok(w["tokens"]), fmt_tok(w["prompt"]),
                fmt_tok(w["completion"]))) + \
                "\nHanya mencakup pemakaian yang teramati TokenPet."
        if intent == "total_requests":
            return _line(FACT, "Total request %s: %d." % (label, w["requests"]))
        if w["avg"] is None:
            return INSUFFICIENT
        return _line(FACT, "Rata-rata %s token per request %s (dari %d "
                     "request)." % (fmt_tok(w["avg"]), label, w["requests"]))
    if intent == "session_usage":
        s = a["session"]
        cur, last = s["current"], s["last"]
        if not cur and not last:
            return INSUFFICIENT
        out = []
        for name, x in (("Sesi berjalan", cur), ("Sesi terakhir", last)):
            if x:
                out.append(_line(FACT, "%s: %s, %d request, %s token%s." % (
                    name, fmt_dur(x["duration"]), x["requests"],
                    fmt_tok(x["tokens"]),
                    (", rata-rata %s/request" % fmt_tok(x["avg_per_request"])
                     if x["avg_per_request"] else ""))))
        return "\n".join(out)
    if intent == "usage_trend":
        t = a["trend"]
        if not t["ok"] or t["change_pct"] is None:
            return INSUFFICIENT
        ch = t["change_pct"]
        word = "naik" if ch > 5 else "turun" if ch < -5 else "relatif sama"
        return (_line(FACT, "24 jam terakhir: %s token; 24 jam sebelumnya: %s "
                      "token." % (fmt_tok(t["recent"]), fmt_tok(t["prev"]))) +
                "\n" + _line(ESTIMATE, "Laju per jam teramati %s (%+.0f%%)."
                             % (word, ch)))
    if intent == "quota_status":
        q = a["quota"]
        out = []
        if q["left_pct"] is not None and q["budget"]:
            out.append(_line(FACT, "Batas token TokenPet (%s): terpakai %s dari "
                         "%s, sisa %.0f%%. Ini batas yang ditetapkan TokenPet, "
                         "bukan kuota resmi 9Router." % (
                             q["period"], fmt_tok(q["used"] or 0),
                             fmt_tok(q["budget"]), q["left_pct"])))
        if q["budget"] is None and q.get("bsrc") == "auto":
            out.append(_line(FACT, "Batas token TokenPet memakai mode otomatis "
                         "(mengikuti puncak pemakaian), jadi bukan batas tetap "
                         "dan tidak ada sisa/prediksi yang bermakna. Isi batas "
                         "manual untuk mengaktifkan prediksi."))
        for o in q["official"]:
            out.append(_line(FACT, "Kuota resmi %s (%s): terpakai %.0f%%%s." % (
                o["provider"], o["name"], o["used"],
                ", reset %s" % fmt_dur(o["reset_in"])
                if o.get("reset_in") is not None else "")))
        return "\n".join(out) or INSUFFICIENT
    if intent == "quota_prediction":
        return _predict_text(a)
    if intent == "anomaly_status":
        an = a["anomalies"]
        if not an["enabled"]:
            return "Deteksi anomali dimatikan di pengaturan."
        if an["state"] == "insufficient":
            return INSUFFICIENT
        act = an["active"]
        if not act:
            return _line(FACT, "Tidak ada aktivitas tidak biasa terdeteksi "
                         "terhadap baseline 7 hari.")
        return "\n".join(_line(FACT, x["text"]) for x in act[:3])
    if intent == "model_efficiency":
        ad = a["advice"]
        if not ad["ok"]:
            return INSUFFICIENT
        if not ad["compare"]:
            r = ad["ranking"][0]
            return (_line(FACT, "Hanya %s yang punya data cukup: rata-rata %s "
                          "token/request." % (r["model"], fmt_tok(r["avg"]))) +
                    "\nBelum ada model lain untuk dibandingkan.")
        b = ad["best"]
        return (_line(FACT, "%s rata-rata %s token/request (%d request, %d hari "
                      "terakhir); rata-rata semua model %s." % (
                          b["model"], fmt_tok(b["avg"]), b["requests"],
                          ad["days"], fmt_tok(ad["overall_avg"]))) + "\n" +
                _line(RECOMMENDATION, "Dari sisi hemat token per request, %s "
                      "terendah (%.0f%% di bawah rata-rata). Ini bukan "
                      "penilaian kualitas, kecepatan, atau harga." % (
                          b["model"], ad["lower_pct"])))
    if intent == "provider_status":
        h = a["health"]
        out = [_line(FACT, "Status 9Router: %s." % h["status"])]
        if h["last_success"]:
            out.append(_line(FACT, "Koneksi sukses terakhir %s lalu." %
                             fmt_dur(a["now"] - h["last_success"])))
        if h["latency"] is not None:
            out.append(_line(FACT, "Waktu respons poll terakhir %.0f ms." %
                             (h["latency"] * 1000)))
        if h["last_error"] and h["fails"]:
            out.append(_line(FACT, "Galat terakhir (%s): %s" % (
                h["last_error_kind"], h["last_error"])))
        return "\n".join(out)
    return UNSUPPORTED


def _eta_txt(r):
    lo, mid, hi = r["eta_fast"], r["eta_mid"], r["eta_slow"]
    rng = "%s - %s" % (fmt_dur(lo), fmt_dur(hi) if hi else "tak terbatas")
    return "~%s (rentang %s, keyakinan %s)" % (fmt_dur(mid), rng,
                                              r["confidence"])


def _hits_txt(r):
    return {"ya": " Pada laju ini kemungkinan habis sebelum reset.",
            "mungkin": " Bisa habis sebelum reset, tergantung laju.",
            "tidak": " Pada laju ini diperkirakan tidak habis sebelum reset."
            }.get(r.get("hits"), "")


def _predict_text(a):
    p = a["prediction"]
    if not p["enabled"]:
        return "Prediksi penggunaan dimatikan di pengaturan."
    out = []
    for o in p["official"]:
        r = o["result"]
        if r["ok"] and not r.get("idle"):
            out.append(_line(ESTIMATE, "Kuota resmi %s (%s) terpakai %.0f%%, "
                             "laju %.1f%%/jam; habis dalam %s.%s" % (
                                 o["provider"], o["name"], r["used"],
                                 r["pct_per_hour"], _eta_txt(r),
                                 _hits_txt(r))))
        elif r["ok"]:
            out.append(_line(FACT, "Kuota resmi %s (%s): tidak ada kenaikan "
                             "terobservasi, tidak ada prediksi habis." % (
                                 o["provider"], o["name"])))
    b = p["budget"]
    if b and b["ok"] and not b.get("idle"):
        out.append(_line(ESTIMATE, "Batas token TokenPet: laju ~%s token/menit; "
                         "tercapai dalam %s.%s Ini bukan kuota resmi." % (
                             fmt_tok(b["rate_per_min"]), _eta_txt(b),
                             _hits_txt(b))))
    elif b and b["ok"]:
        out.append(_line(FACT, "Tidak ada pemakaian token terobservasi dalam "
                         "1 jam terakhir; tidak ada prediksi habis."))
    return "\n".join(out) or INSUFFICIENT


def prediction_lines(a):
    """Dipakai panel Smart Insights."""
    return _predict_text(a)


class LocalAssistant:
    def __init__(self, engine):
        self.engine = engine

    def ask(self, text):
        intent, _score = match_intent(text)
        if intent in ("unknown", "help"):
            a = None
            return intent, answer(intent, a, text)
        return intent, answer(intent, self.engine.analyze(), text)
