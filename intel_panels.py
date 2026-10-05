"""Panel terpisah TokenPet Intelligence (jendela sendiri, tidak memenuhi widget).

Tab: Assistant, Insights, Anomali, Sesi, Progres, Provider, Pengaturan.
Hanya tkinter bawaan. Analisis dihitung di thread latar; UI hanya diubah di
main thread (root.after). Semua error panel ditangkap supaya tidak
mengganggu widget utama.
"""

import threading
import time
import tkinter as tk
from tkinter import messagebox

import local_intel as li
from local_assistant import SUGGESTIONS, LocalAssistant, prediction_lines

TABS = (("assistant", "Assistant"), ("insights", "Insights"),
        ("anomaly", "Anomali"), ("session", "Sesi"),
        ("progress", "Progres"), ("health", "Provider"),
        ("settings", "Pengaturan"))
TAG_COL = {li.FACT: "fact", li.ESTIMATE: "est", li.RECOMMENDATION: "rec"}


def _dur(sec):
    return li.fmt_dur(sec)


def _ts(t):
    return time.strftime("%d/%m %H:%M", time.localtime(t)) if t else "-"


class IntelWindow:
    REFRESH_MS = 5000

    def __init__(self, app, colors, start_tab="assistant"):
        self.app, self.eng, self.C = app, app.intel, colors
        self.assistant = LocalAssistant(self.eng)
        self.tab, self.closed, self._job, self._busy = start_tab, False, None, False
        self.top = tk.Toplevel(app.root)
        t = self.top
        t.title("TokenPet · Local Intelligence")
        t.configure(bg=colors["BG"])
        w = int(560 * app.dpi)
        h = int(520 * app.dpi)
        try:
            t.geometry("%dx%d+%d+%d" % (w, h, app.root.winfo_x() + 20,
                                        app.root.winfo_y() + 60))
            t.minsize(int(420 * app.dpi), int(360 * app.dpi))
            t.attributes("-topmost", bool(app.always_on_top))
        except tk.TclError:
            pass
        t.protocol("WM_DELETE_WINDOW", self.close)
        self.f = lambda sz=10, b=False: app.ft(sz, b)
        bar = tk.Frame(t, bg=colors["BG"])
        bar.pack(fill="x", padx=8, pady=(8, 4))
        self.btns = {}
        for key, label in TABS:
            b = tk.Button(bar, text=label, relief="flat", bd=0, padx=8, pady=3,
                          font=self.f(9), cursor="hand2",
                          command=lambda k=key: self.show(k))
            b.pack(side="left", padx=2)
            self.btns[key] = b
        self.body = tk.Frame(t, bg=colors["BG"])
        self.body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.show(start_tab)
        self._loop()

    # ---------- umum ----------
    def alive(self):
        if self.closed:
            return False
        try:
            return bool(self.top.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        self.closed = True
        if self._job:
            try:
                self.top.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        self.app._intel_win = None

    def focus(self, tab=None):
        try:
            self.top.deiconify()
            self.top.lift()
            self.top.focus_force()
        except tk.TclError:
            pass
        if tab:
            self.show(tab)

    def _loop(self):
        if not self.alive():
            return
        if self.tab != "assistant":
            self.refresh()
        self._job = self.top.after(self.REFRESH_MS, self._loop)

    def refresh(self):
        """Hitung di thread latar, gambar di main thread."""
        if self._busy or not self.alive():
            return
        self._busy = True

        def work():
            try:
                a = self.eng.analyze(force=True)
            except Exception:
                a = None
            try:
                self.top.after(0, lambda: self._render_safe(a))
            except Exception:
                self._busy = False
        threading.Thread(target=work, daemon=True).start()

    def _render_safe(self, a):
        self._busy = False
        if a is None or not self.alive() or self.tab == "assistant":
            return
        try:
            getattr(self, "_r_" + self.tab)(a)
        except Exception:
            try:
                self.app._intel_log("intel-panel")
            except Exception:
                pass

    def show(self, key):
        self.tab = key
        C = self.C
        for k, b in self.btns.items():
            on = (k == key)
            b.configure(bg=C["MINT"] if on else C["BTN"],
                        fg=C["ON_ACCENT"] if on else C["FG"],
                        activebackground=C["MINT"],
                        activeforeground=C["ON_ACCENT"])
        for w in self.body.winfo_children():
            w.destroy()
        if key == "assistant":
            self._build_assistant()
            return
        if key == "settings":
            self._build_settings()
            return
        self._reset_btn, self._emb = None, []
        self.text = self._text(self.body)
        self.text.pack(fill="both", expand=True)
        self.refresh()

    def _text(self, parent, height=None):
        C = self.C
        tx = tk.Text(parent, wrap="word", bg=C["SURFACE"], fg=C["FG"],
                     bd=0, highlightthickness=0, padx=10, pady=8,
                     font=self.f(10), cursor="arrow", relief="flat",
                     **({"height": height} if height else {}))
        tx.tag_configure("h", font=self.f(11, True), foreground=C["MINT"],
                         spacing1=6, spacing3=3)
        tx.tag_configure("fact", foreground=C["FG"])
        tx.tag_configure("est", foreground=C["YELLOW"])
        tx.tag_configure("rec", foreground=C["MINT"])
        tx.tag_configure("mut", foreground=C["MUTED"])
        tx.tag_configure("bad", foreground=C["RED"])
        tx.tag_configure("me", foreground=C["MINT"], font=self.f(10, True))
        tx.configure(state="disabled")
        return tx

    def _put(self, lines, tx=None):
        """lines: [(tag, teks)] - ganti seluruh isi Text."""
        tx = tx or self.text
        for w in getattr(self, "_emb", []):
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._emb = []
        y = tx.yview()
        tx.configure(state="normal")
        tx.delete("1.0", "end")
        for tag, s in lines:
            tx.insert("end", s + "\n", tag)
        tx.configure(state="disabled")
        tx.yview_moveto(y[0])

    @staticmethod
    def _tagged(s):
        """'[FACT] teks' -> (tag, teks)."""
        for k, tag in TAG_COL.items():
            if s.startswith("[%s]" % k):
                return tag, s
        return "fact", s

    # ---------- Assistant ----------
    def _build_assistant(self):
        C = self.C
        self.chat = self._text(self.body)
        self.chat.pack(fill="both", expand=True)
        sug = tk.Frame(self.body, bg=C["BG"])
        sug.pack(fill="x", pady=(6, 0))
        for q in SUGGESTIONS[:6]:
            tk.Button(sug, text=q, relief="flat", bd=0, padx=6, pady=2,
                      bg=C["BTN"], fg=C["FG"], font=self.f(8), cursor="hand2",
                      activebackground=C["MINT"], activeforeground=C["ON_ACCENT"],
                      command=lambda t=q: self._ask(t)).pack(
                          side="left", padx=2, pady=1)
        row = tk.Frame(self.body, bg=C["BG"])
        row.pack(fill="x", pady=(6, 0))
        self.entry = tk.Entry(row, bg=C["SURFACE"], fg=C["FG"],
                              insertbackground=C["FG"], relief="flat",
                              font=self.f(10), highlightthickness=1,
                              highlightbackground=C["LINE"],
                              highlightcolor=C["MINT"])
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda _e: self._ask())
        tk.Button(row, text="Kirim", relief="flat", bd=0, padx=10, pady=3,
                  bg=C["MINT"], fg=C["ON_ACCENT"], font=self.f(9, True),
                  command=self._ask, cursor="hand2").pack(side="left", padx=(6, 0))
        self._chat_add("tokenpet", "Halo! Saya asisten lokal TokenPet — bukan "
                       "AI. Saya menjawab dari data penggunaan di komputer ini "
                       "(ketik 'bantuan' untuk contoh).")
        self.entry.focus_set()

    def _chat_add(self, who, text):
        tx = self.chat
        tx.configure(state="normal")
        tx.insert("end", ("Anda" if who == "me" else "TokenPet") + "\n",
                  "me" if who == "me" else "h")
        for line in text.split("\n"):
            tag, s = self._tagged(line)
            tx.insert("end", s + "\n", tag)
        tx.insert("end", "\n")
        tx.configure(state="disabled")
        tx.see("end")

    def _ask(self, text=None):
        q = (text if text is not None else self.entry.get()).strip()
        if not q:
            return
        self.entry.delete(0, "end")
        self._chat_add("me", q)
        try:
            intent, ans = self.assistant.ask(q)
        except Exception:
            ans = li.UNSUPPORTED
            intent = "unknown"
        self._chat_add("tokenpet", ans)
        if intent in ("total_tokens", "total_requests", "most_used_model",
                      "avg_tokens", "usage_trend", "quota_status"):
            self.app._intel_game("usage")

    # ---------- Insights ----------
    def _r_insights(self, a):
        L = []
        L.append(("h", "Pemakaian teramati"))
        L.append(("fact", "[FACT] Mood pet: %s" % a["mood"]))
        if not a["has_data"]:
            L.append(("mut", li.INSUFFICIENT))
        for lab, k in (("Hari ini", "today"), ("24 jam", "last24h"),
                       ("7 hari", "week")):
            w = a[k]
            L.append(("fact", "[FACT] %s: %s token, %d request%s" % (
                lab, li.fmt_tok(w["tokens"]), w["requests"],
                ", rata-rata %s/request" % li.fmt_tok(w["avg"])
                if w["avg"] else "")))
        t = a["trend"]
        if t["ok"] and t["change_pct"] is not None:
            L.append(("est", "[ESTIMATE] Laju 24 jam terakhir %+.0f%% "
                      "dibanding 24 jam sebelumnya." % t["change_pct"]))
        else:
            L.append(("mut", "Tren: " + li.INSUFFICIENT))
        L.append(("h", "Prediksi"))
        for ln in prediction_lines(a).split("\n"):
            L.append(self._tagged(ln) if ln.startswith("[") else ("mut", ln))
        L.append(("h", "Rekomendasi model (hanya konsumsi token)"))
        ad = a["advice"]
        if not ad["ok"]:
            L.append(("mut", li.INSUFFICIENT))
        else:
            for r in ad["ranking"][:6]:
                L.append(("fact", "[FACT] %s — %s token/request (%d request)"
                          % (r["model"], li.fmt_tok(r["avg"]), r["requests"])))
            if ad.get("best"):
                L.append(("rec", "[RECOMMENDATION] %s paling hemat token per "
                          "request (%.0f%% di bawah rata-rata). Bukan penilaian "
                          "kualitas/kecepatan/harga; model tidak diganti "
                          "otomatis." % (ad["best"]["model"], ad["lower_pct"])))
            for n in ad["notes"]:
                L.append(("fact", "[FACT] " + n))
        L.append(("h", "Riwayat notifikasi"))
        for n in a.get("notifications") or []:
            L.append(("mut", "%s · %s · %s" % (
                _ts(n["t"]), li.CATEGORY_LABEL.get(n["cat"], n["cat"]),
                n["text"][:120])))
        if not a.get("notifications"):
            L.append(("mut", "Belum ada."))
        self._put(L)

    # ---------- Anomali ----------
    def _r_anomaly(self, a):
        an = a["anomalies"]
        L = [("h", "Anomali (sensitivitas: %s)" %
              self.eng.settings["anomaly_sensitivity"])]
        if not an["enabled"]:
            L.append(("mut", "Deteksi anomali dimatikan di Pengaturan."))
        elif an["state"] == "insufficient" and not an["all"]:
            L.append(("mut", li.INSUFFICIENT))
        elif not an["all"]:
            L.append(("fact", "[FACT] Tidak ada aktivitas tidak biasa "
                      "terhadap baseline 7 hari."))
        self._put(L)
        # tombol per anomali baru (dibangun ulang tiap refresh)
        tx = self.text
        tx.configure(state="normal")
        for x in an["all"][:15]:
            st = x["status"]
            tx.insert("end", "\n%s · %s\n" % (_ts(x["last_at"]), st.upper()),
                      "mut")
            tx.insert("end", x["text"] + "\n", "bad" if st == "new" else "mut")
            if st == "new":
                row = tk.Frame(tx, bg=self.C["SURFACE"])
                for label, status in (("Tutup", "dismissed"),
                                      ("Sudah ditinjau", "reviewed"),
                                      ("Abaikan jenis ini", "ignored")):
                    tk.Button(row, text=label, relief="flat", bd=0, padx=6,
                              pady=2, bg=self.C["BTN"], fg=self.C["FG"],
                              font=self.f(8), cursor="hand2",
                              command=lambda i=x["id"], s=status:
                              self._anomaly_act(i, s)).pack(side="left", padx=2)
                tx.window_create("end", window=row)
                self._emb.append(row)
                tx.insert("end", "\n")
        tx.configure(state="disabled")

    def _anomaly_act(self, aid, status):
        self.app._intel_anomaly_action(aid, status)
        self.refresh()

    # ---------- Sesi ----------
    def _r_session(self, a):
        s = a["session"]
        L = [("h", "Sesi berjalan")]
        c = s["current"]
        if c:
            L.append(("fact", "[FACT] mulai %s · durasi %s · %d request · %s "
                      "token (input %s / output %s)%s" % (
                          _ts(c["start"]), _dur(c["duration"]), c["requests"],
                          li.fmt_tok(c["tokens"]), li.fmt_tok(c["prompt"]),
                          li.fmt_tok(c["completion"]),
                          " · rata-rata %s/request" % li.fmt_tok(
                              c["avg_per_request"]) if c["avg_per_request"]
                          else "")))
            L.append(("fact", "model: " + ", ".join(c["models"][:4])))
        else:
            L.append(("mut", "Tidak ada sesi berjalan (menunggu aktivitas)."))
        L.append(("h", "Sesi terakhir"))
        last = s["last"]
        L.append(("fact", "[FACT] %s · %s · %d request · %s token" % (
            _ts(last["start"]), _dur(last["duration"]), last["requests"],
            li.fmt_tok(last["tokens"])) if last else
            "Belum ada sesi yang selesai."))
        L.append(("h", "Riwayat (maks 20)"))
        for h in s["history"]:
            L.append(("mut", "%s · %s · %d req · %s token · %s" % (
                _ts(h["start"]), _dur(h["duration"]), h["requests"],
                li.fmt_tok(h["tokens"]), ", ".join(h["models"][:2]))))
        L.append(("mut", "\nSesi = aktivitas + idle timeout (%d menit, atur di "
                  "Pengaturan). Data lama tidak dihitung sebagai pemakaian baru."
                  % self.eng.settings["idle_timeout_minutes"]))
        self._put(L)
        if self._reset_btn is None or not self._reset_btn.winfo_exists():
            self._reset_btn = tk.Button(
                self.body, text="Reset sesi berjalan", relief="flat", bd=0,
                padx=8, pady=3, bg=self.C["BTN"], fg=self.C["FG"],
                font=self.f(9), cursor="hand2", command=self._reset_session)
            self._reset_btn.pack(anchor="e", pady=(6, 0))

    def _reset_session(self):
        if messagebox.askyesno(
                "Reset sesi", "Buang sesi yang sedang berjalan?\n"
                "Riwayat sesi yang sudah selesai tetap tersimpan.",
                parent=self.top):
            self.eng.reset_session()
            self.refresh()

    # ---------- Progres ----------
    def _r_progress(self, a):
        g = a["game"]
        L = [("h", "Level %d · %d / %d XP · streak %d hari" % (
            g["level"], g["xp"], g["need"], g["streak"]))]
        if not self.eng.settings["gamification_enabled"]:
            L.append(("mut", "Gamifikasi dimatikan di Pengaturan."))
        else:
            bar = int(round(20 * g["xp"] / max(1, g["need"])))
            L.append(("rec", "[" + "█" * bar + "·" * (20 - bar) + "]"))
            L.append(("h", "Misi harian"))
            for _k, lab, done in g["missions"]:
                L.append(("fact" if done else "mut",
                          ("☑ " if done else "☐ ") + lab))
            L.append(("h", "Pencapaian"))
            for _k, lab, d in g["achievements"] or []:
                L.append(("fact", "★ %s (%s)" % (lab, d)))
            if not g["achievements"]:
                L.append(("mut", "Belum ada."))
            if g["unlocked"]:
                L.append(("h", "Aksesoris ditandai terbuka"))
                L.append(("fact", ", ".join(g["unlocked"])))
            L.append(("mut", "\nXP hanya dari misi dan pencapaian — bukan dari "
                      "jumlah token atau request."))
        self._put(L)

    # ---------- Provider ----------
    def _r_health(self, a):
        h = a["health"]
        bad = h["status"] in ("OFFLINE", "AUTH ERROR")
        L = [("h", "Status 9Router"),
             ("bad" if bad else "fact", "[FACT] " + h["status"])]
        L.append(("fact", "[FACT] Koneksi sukses terakhir: " + (
            "%s lalu" % _dur(a["now"] - h["last_success"])
            if h["last_success"] else "belum ada")))
        if h["latency"] is not None:
            L.append(("fact", "[FACT] Waktu respons poll terakhir: %.0f ms "
                      "(rata-rata %.0f ms)" % (h["latency"] * 1000,
                                               (h["latency_avg"] or 0) * 1000)))
        if h["fails"]:
            L.append(("est", "Gagal beruntun: %d (%s: %s). OFFLINE dinyatakan "
                      "setelah %d kegagalan berturut-turut." % (
                          h["fails"], h["last_error_kind"], h["last_error"],
                          li.ProviderHealth.FAIL_N)))
        L.append(("h", "Kuota resmi"))
        off = a["quota"]["official"]
        for o in off:
            L.append(("fact", "[FACT] %s · %s: terpakai %.0f%%%s" % (
                o["provider"], o["name"], o["used"],
                " · reset %s" % _dur(o["reset_in"])
                if o.get("reset_in") is not None else "")))
        if not off:
            L.append(("mut", "Tidak ada data kuota resmi (pilih pet layanan "
                      "yang punya kuota)."))
        L.append(("mut", "\nStatus memakai hasil polling yang sudah berjalan; "
                  "tidak ada request tambahan."))
        self._put(L)

    # ---------- Pengaturan ----------
    def _build_settings(self):
        C, e = self.C, self.eng
        fr = tk.Frame(self.body, bg=C["SURFACE"])
        fr.pack(fill="both", expand=True)
        pad = dict(anchor="w", padx=12, pady=2)

        def check(label, key, value, cb=None):
            v = tk.BooleanVar(master=self.top, value=bool(value))

            def go():
                e.set_setting(key, v.get())
                if cb:
                    cb()
            tk.Checkbutton(fr, text=label, variable=v, command=go,
                           bg=C["SURFACE"], fg=C["FG"], selectcolor=C["DARK"],
                           activebackground=C["SURFACE"],
                           activeforeground=C["FG"], font=self.f(10)
                           ).pack(**pad)

        def head(t):
            tk.Label(fr, text=t, bg=C["SURFACE"], fg=C["MINT"],
                     font=self.f(10, True)).pack(anchor="w", padx=12,
                                                 pady=(10, 2))
        s = e.settings
        head("Intelligence")
        check("Enable Usage Prediction", "prediction_enabled",
              s["prediction_enabled"])
        check("Enable Anomaly Detection", "anomaly_enabled",
              s["anomaly_enabled"])
        check("Enable Gamification", "gamification_enabled",
              s["gamification_enabled"])
        row = tk.Frame(fr, bg=C["SURFACE"])
        row.pack(**pad)
        tk.Label(row, text="Sensitivitas anomali:", bg=C["SURFACE"],
                 fg=C["FG"], font=self.f(10)).pack(side="left")
        sv = tk.StringVar(master=self.top, value=s["anomaly_sensitivity"])
        om = tk.OptionMenu(row, sv, "low", "medium", "high",
                           command=lambda v: e.set_setting(
                               "anomaly_sensitivity", v))
        om.configure(bg=C["BTN"], fg=C["FG"], relief="flat", bd=0,
                     highlightthickness=0, font=self.f(9),
                     activebackground=C["MINT"])
        om.pack(side="left", padx=6)
        row2 = tk.Frame(fr, bg=C["SURFACE"])
        row2.pack(**pad)
        tk.Label(row2, text="Idle timeout sesi (menit):", bg=C["SURFACE"],
                 fg=C["FG"], font=self.f(10)).pack(side="left")
        iv = tk.StringVar(master=self.top,
                          value=str(int(s["idle_timeout_minutes"])))
        sp = tk.Spinbox(row2, from_=1, to=120, width=4, textvariable=iv,
                        bg=C["DARK"], fg=C["FG"], buttonbackground=C["BTN"],
                        relief="flat", font=self.f(10),
                        command=lambda: self._set_idle(iv))
        sp.pack(side="left", padx=6)
        sp.bind("<FocusOut>", lambda _e: self._set_idle(iv))
        sp.bind("<Return>", lambda _e: self._set_idle(iv))
        head("Notifikasi per kategori")
        for cat in li.CATEGORIES:
            check(li.CATEGORY_LABEL[cat], "notify." + cat,
                  s["notify"].get(cat, True))
        tk.Label(fr, text="Semua analisis berjalan lokal. Tidak ada AI/LLM "
                 "eksternal, API key, atau pengiriman data.", bg=C["SURFACE"],
                 fg=C["MUTED"], font=self.f(8), wraplength=int(480 * self.app.dpi),
                 justify="left").pack(anchor="w", padx=12, pady=(12, 4))

    def _set_idle(self, var):
        try:
            v = max(1, min(120, int(float(var.get()))))
        except (ValueError, TypeError):
            return
        var.set(str(v))
        self.eng.set_setting("idle_timeout_minutes", v)
