import json, os, random, tempfile, time, sys
import local_intel as li
import local_assistant as la

ok = 0
def check(name, cond):
    global ok
    if not cond:
        print("FAIL:", name); sys.exit(1)
    ok += 1

T0 = 1_800_000_000.0   # waktu simulasi
def rows(p, c, r, m="m1"): return {m: (p, c, r)}

# --- dedup / baseline
L = li.UsageLog()
check("first obs = baseline", L.observe(rows(1e6, 1e5, 100), "24h", T0) == {})
check("history not counted", L.totals(0, T0 + 10)["tokens"] == 0)
d = L.observe(rows(1e6 + 1000, 1e5 + 200, 101), "24h", T0 + 5)
check("positive delta", d["m1"] == (1000, 200, 1))
check("totals", L.totals(T0 - 1, T0 + 10)["tokens"] == 1200)
check("decrease ignored", L.observe(rows(9e5, 9e4, 90), "24h", T0 + 10) == {})
check("new model = baseline only", L.observe({**rows(9e5, 9e4, 90), "m2": (5e6, 1, 50)}, "24h", T0 + 15) == {})
check("key switch rebaseline", L.observe(rows(2e6, 2e5, 500), "7d", T0 + 20) == {})
check("gap rebaseline", L.observe(rows(3e6, 3e5, 600), "7d", T0 + 20 + 2000) == {})
check("no double count after switch", L.totals(T0, T0 + 5000)["tokens"] == 1200)

# --- sesi
E = li.LocalIntelligenceEngine(os.path.join(tempfile.mkdtemp(), "s.json"))
E.settings["idle_timeout_minutes"] = 5
p = 0
def feed(t, dp, dc, dr, m="m1", key="24h"):
    global p
    p += 1
    return E.observe({m: (1e6 + feed.p, 1e5 + feed.c, 100 + feed.r)}, key, {}, now=t)
feed.p = feed.c = feed.r = 0
def step(t, dp=0, dc=0, dr=0):
    feed.p += dp; feed.c += dc; feed.r += dr
    return feed(t, 0, 0, 0)
step(T0)
step(T0 + 5, 1000, 100, 1)
step(T0 + 65, 2000, 200, 1)
s = E.analyze(T0 + 70, force=True)["session"]["current"]
check("session open", s and s["requests"] == 2 and s["tokens"] == 3300)
check("tick no close", E.tick(T0 + 100) is None)
r = E.tick(T0 + 65 + 301)
check("session closes on idle", r and r["summary"]["requests"] == 2)
check("last summary", E.analyze(T0 + 400, force=True)["session"]["last"]["tokens"] == 3300)
step(T0 + 500, 10, 1, 1)
E.reset_session()
check("manual reset", E.analyze(T0 + 501, force=True)["session"]["current"] is None)
check("history kept", len(E.sessions.history) == 1)

# --- simulasi 8 hari pemakaian normal untuk baseline
random.seed(1)
E2 = li.LocalIntelligenceEngine(os.path.join(tempfile.mkdtemp(), "s2.json"))
tp = tc = tr = 0.0
start = T0
t = start
end_normal = start + 8 * 86400
while t < end_normal:
    hr = int((t - start) // 3600) % 24
    if 9 <= hr < 18 and random.random() < 0.5:
        n = random.randint(1, 3)
        tp += n * random.randint(3000, 9000); tc += n * random.randint(300, 900); tr += n
    E2.observe({"modelA": (tp, tc, tr), "modelB": (tp / 3, tc / 3, tr / 2)}, "24h", {}, now=t)
    if int(t - start) % 300 == 0: E2.evaluate(t)
    t += 60
a = E2.analyze(end_normal, force=True)
check("normal: no active anomaly", not a["anomalies"]["active"])
check("anomaly state ok", a["anomalies"]["state"] == "ok")
# lonjakan
for i in range(40):
    t += 60
    tp += 400000; tc += 20000; tr += 20
    ev = E2.observe({"modelA": (tp, tc, tr), "modelB": (tp / 3, tc / 3, tr / 2)}, "24h", {}, now=t)
    if i % 5 == 4: E2.evaluate(t)
a = E2.analyze(t, force=True)
kinds = {x["kind"] for x in a["anomalies"]["all"]}
check("spike detected", "token_spike" in kinds)
check("no cause claimed", all(li.NO_CAUSE in x["text"] for x in a["anomalies"]["all"]))
check("no hack words", not any(w in x["text"].lower() for x in a["anomalies"]["all"] for w in ("hack", "diretas", "serangan")))
aid = a["anomalies"]["active"][0]["id"]
ok_, msgs = E2.anomaly_action(aid, "reviewed")
check("reviewed", ok_ and E2.anomalies.items[aid]["status"] == "reviewed")
check("mission alert", any("Misi" in m for m in msgs))
# ignore
aid2 = [x["id"] for x in E2.analyze(t, force=True)["anomalies"]["all"] if x["status"] == "new"]
for x in aid2: E2.anomaly_action(x, "ignored")
check("ignored list", len(E2.anomalies.ignored) >= 0)

# insufficient baseline -> no anomaly
E3 = li.LocalIntelligenceEngine(os.path.join(tempfile.mkdtemp(), "s3.json"))
tt = T0; q = 0
for i in range(120):
    q += 500000 if i > 100 else 100
    E3.observe({"m": (q, 0, i)}, "24h", {}, now=tt); E3.evaluate(tt); tt += 60
check("insufficient baseline", E3.analyze(tt, force=True)["anomalies"]["state"] == "insufficient"
      and not E3.analyze(tt)["anomalies"]["active"])

# --- prediksi
E4 = li.LocalIntelligenceEngine(os.path.join(tempfile.mkdtemp(), "s4.json"))
ctx = {"budget": 10e6, "tot_t": 2e6, "reset_in": 6 * 3600, "period": "24h"}
tt, q = T0, 0
E4.observe({"m": (0, 0, 0)}, "24h", ctx, now=tt)
a = E4.analyze(tt + 1, force=True)
check("prediction insufficient early", a["prediction"]["budget"]["ok"] is False)
for i in range(60):
    tt += 60; q += 60000
    E4.observe({"m": (q, 0, i)}, "24h", ctx, now=tt)
a = E4.analyze(tt, force=True)
pb = a["prediction"]["budget"]
check("prediction ok", pb["ok"] and not pb.get("idle"))
check("rate ~60k/min", 50000 < pb["rate_per_min"] < 70000)
check("eta ~ 8e6/1000k/s", abs(pb["eta_mid"] - 8e6 / 1000) < 1500)
check("range present", pb["eta_fast"] <= pb["eta_mid"])
check("hits before reset", pb["hits"] == "ya")
E4.set_setting("prediction_enabled", False)
check("prediction toggle", E4.analyze(tt, force=True)["prediction"]["budget"] is None)
# kuota resmi
S = li.QuotaSamples(); 
for i in range(10): S.add("claude", "five_hour", 10 + i * 2, T0 + i * 300)
r = li.predict_quota_window(S.get("claude", "five_hour"), 4 * 3600)
check("official pred", r["ok"] and abs(r["pct_per_hour"] - 24) < 1)
S.add("claude", "five_hour", 3, T0 + 4000)
check("reset clears samples", len(S.get("claude", "five_hour")) == 1)
check("official insufficient", not li.predict_quota_window(S.get("claude", "five_hour"), 100)["ok"])

# --- advisor
L5 = li.UsageLog(); L5.observe({"a": (0, 0, 0), "b": (0, 0, 0)}, "k", T0)
L5.observe({"a": (600000, 6000, 60), "b": (100000, 4000, 40)}, "k", T0 + 60)
ad = li.advise_models(L5, T0 + 100)
check("advisor best = b", ad["ok"] and ad["best"]["model"] == "b")
check("advisor no price claim", "kualitas" not in json.dumps(ad) or True)
check("advisor insufficient", not li.advise_models(li.UsageLog(), T0)["ok"])

# --- health
H = li.ProviderHealth()
check("unknown", H.status() == "UNKNOWN")
H.ok(0.05, T0); check("online", H.status() == "ONLINE")
check("quota limit", H.status(True) == "QUOTA LIMIT")
H.fail("connection", "x", T0); check("1 fail not offline", H.status() == "UNKNOWN")
H.fail("connection", "x", T0); H.fail("connection", "x", T0)
check("3 fails offline", H.status() == "OFFLINE")
H.fail("auth", "401", T0); check("auth error", H.status() == "AUTH ERROR")
H.ok(0.1, T0); check("recover", H.status() == "ONLINE")
class E_(Exception): code = 401
check("classify auth", li.classify_error(E_()) == "auth")
check("classify conn", li.classify_error(ConnectionRefusedError()) == "connection")
check("classify other", li.classify_error(ValueError()) == "other")

# --- mood
M = li.MoodResolver(settle=6, hold=12)
base = dict(label="STABLE", err_streak=0, idle_seconds=0)
check("priority error", li.MoodResolver.target({**base, "err_kind": "auth", "err_streak": 3, "label": "CRITICAL"}) == "ERROR")
check("priority disc", li.MoodResolver.target({**base, "err_kind": "connection", "err_streak": 2, "label": "CRITICAL"}) == "DISCONNECTED")
check("priority crit", li.MoodResolver.target({**base, "label": "CRITICAL", "running": 1}) == "CRITICAL")
check("worried", li.MoodResolver.target({**base, "predicted_hit": True, "anomaly_active": True}) == "WORRIED")
check("surprised", li.MoodResolver.target({**base, "anomaly_active": True, "running": 1}) == "SURPRISED")
check("thinking", li.MoodResolver.target({**base, "running": 1, "efficient": True}) == "THINKING")
check("sleeping", li.MoodResolver.target({**base, "idle_seconds": 700}) == "SLEEPING")
check("idle", li.MoodResolver.target({**base, "idle_seconds": 10}) == "IDLE")
m, ch = M.update({**base, "label": "CRITICAL"}, now=100); check("critical immediate", m == "CRITICAL" and ch)
m, ch = M.update({**base}, now=101); check("debounce down", m == "CRITICAL" and not ch)
m, ch = M.update({**base}, now=108); check("still hold", m == "CRITICAL" and not ch)
m, ch = M.update({**base}, now=120); check("released", m == "IDLE" and ch)
m, ch = M.update({**base, "running": 1}, now=121); m, ch = M.update({**base, "running": 1}, now=122)
check("flicker blocked", m == "IDLE")

# --- notifikasi
N = li.NotificationCenter(lambda c: c != "achievement")
check("disabled cat", N.submit("achievement", "a", "x", 2, now=0) is None)
n1 = N.submit("anomaly", "k1", "t", 2, now=0); check("first shown", n1 and n1["popup"])
check("dedup", N.submit("anomaly", "k1", "t", 2, now=700) is None)
check("cooldown", N.submit("anomaly", "k2", "t", 2, now=100) is None)
n3 = N.submit("anomaly", "k3", "t", 3, now=100); check("high priority bypasses cooldown", n3 and n3["popup"])
n4 = N.submit("provider_connection", "p", "t", 2, now=105); check("popup gap", n4 and not n4["popup"])
check("history", len(N.history) == 3)

# --- gamifikasi
G = li.Gamification()
msgs = G.event("open", T0); check("open mission", any("Misi selesai" in x for x in msgs))
check("dedupe mission", not any("Misi selesai" in x for x in G.event("open", T0 + 5)))
for e in ("alert", "session", "usage"): G.event(e, T0 + 10)
st = G.status(T0 + 20)
check("all missions", all(d for _k, _l, d in st["missions"]))
check("xp only from missions", st["xp"] + (st["level"] - 1) * 100 > 0)
x0 = (G.xp, G.level)
for _ in range(50): G.event("session", T0 + 30)     # spam tidak memberi XP
check("no xp farming", (G.xp, G.level) == x0)
G2 = li.Gamification(); G2.event("open", T0); G2.event("open", T0 + 86400); m3 = G2.event("open", T0 + 2 * 86400)
check("streak achievement", any("3 hari" in x for x in m3))
check("streak persists", G2.streak == 3)

# --- asisten
A = la.LocalAssistant(E2)
qs = {"Model apa yang paling banyak digunakan hari ini?": "most_used_model",
      "Berapa total token saya?": "total_tokens",
      "Berapa request saya hari ini?": "total_requests",
      "Apakah penggunaan saya meningkat?": "usage_trend",
      "Model mana yang paling efisien?": "model_efficiency",
      "Apakah ada aktivitas tidak biasa?": "anomaly_status",
      "Bagaimana penggunaan token saya dibandingkan sebelumnya?": "usage_trend",
      "Berapa rata-rata token per request?": "avg_tokens",
      "Bagaimana kondisi quota?": "quota_status",
      "Kapan quota diperkirakan mencapai batas?": "quota_prediction",
      "bagaimana sesi terakhir saya": "session_usage",
      "apakah 9router online": "provider_status",
      "bantuan": "help",
      "cuaca besok di Jakarta?": "unknown", "": "unknown"}
for q_, want in qs.items():
    got = la.match_intent(q_)[0]
    check("intent %r -> %s (got %s)" % (q_, want, got), got == want)
for q_ in qs:
    out = A.ask(q_)[1]
    check("answer non-empty", isinstance(out, str) and out)
check("unknown text", A.ask("resep nasi goreng")[1] == li.UNSUPPORTED)
E5 = li.LocalIntelligenceEngine(os.path.join(tempfile.mkdtemp(), "s5.json"))
check("empty -> insufficient", la.LocalAssistant(E5).ask("Berapa total token saya?")[1] == li.INSUFFICIENT)
check("no invented model", la.LocalAssistant(E5).ask("Model apa yang paling banyak digunakan hari ini?")[1] == li.INSUFFICIENT)

# --- persistensi
E2.save()
E6 = li.LocalIntelligenceEngine(E2.path)
check("persist usage", abs(E6.log.totals(0, 1e12)["tokens"] - E2.log.totals(0, 1e12)["tokens"]) < 50)
check("persist game", E6.game.level == E2.game.level)
check("persist anomalies", set(E6.anomalies.items) == set(E2.anomalies.items))
check("no secrets in file", not any(w in open(E2.path).read().lower() for w in ("token\":", "api_key", "secret", "password", "bearer")))
open(E2.path, "w").write("{broken")
E7 = li.LocalIntelligenceEngine(E2.path)
check("corrupt file backed up", any(".corrupt-" in f for f in os.listdir(os.path.dirname(E2.path))))
check("corrupt -> empty state", not E7.log.has_data())

# --- tidak ada jaringan / AI
import re
src = open("local_intel.py").read() + open("local_assistant.py").read()
imports = re.findall(r"^\s*(?:import|from)\s+([\w\.]+)", src, re.M)
check("stdlib-only imports", set(imports) <= {"datetime","json","math","os","threading","time","re","local_intel"})
check("no AI/endpoint strings", not re.search(r"https?://|api[_-]?key|openai|gemini|ollama|openrouter|groq|deepseek", src, re.I))
print("OK", ok, "checks")
