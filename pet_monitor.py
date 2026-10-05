"""Widget desktop pemantau token 9router dengan pet pixel-art.

Hanya modul bawaan Python (tkinter + urllib + threading + json).
Jalankan:  python pet_monitor.py
Tanpa konsol (Windows): jalankan pet_monitor.pyw
Uji otomatis: python pet_monitor.py --selftest

Data (live):
- Daftar model dibaca OTOMATIS dari combo 9router (/api/combos).
- Token per-model dibaca dari /api/usage/stats (byModel). Tiap baris stats
  dicocokkan ke SATU model combo saja (tidak dobel hitung); stats yang tak
  cocok ke combo mana pun dihitung terpisah sebagai "di luar combo".
- 9router tidak memberi limit per-model, jadi % model = pangsa dari total
  token combo. Isi `model_budgets` bila ingin % = terpakai / batas.
- Total besar di header = angka RESMI 9router (totalPromptTokens +
  totalCompletionTokens), bukan jumlah model combo, supaya selalu sama
  dengan kartu dashboard. Rincian per-model tetap dibatasi combo terpilih;
  selisihnya ditampilkan sebagai "di luar combo".
- 9router tak punya limit TOKEN total, jadi batas token tetap dari
  `combo_budget`/ketikan user/auto. Tapi sisa % bisa memakai kuota ASLI
  per koneksi (/api/usage/<id> -> quotas {used, total,
  remainingPercentage, resetAt}) untuk provider yang melayani combo.
"""

import json
import math
import os
import re
import sys
import time
import random
import threading
import urllib.request
import urllib.error
import urllib.parse
import base64
import datetime
import hashlib
import secrets
import webbrowser
import http.server

from secure_store import SecureCredentialStore, SecureStorageError

# Local Intelligence (opsional & 100% lokal). Bila file modulnya hilang atau
# rusak, TokenPet tetap berjalan seperti semula tanpa fitur intelligence.
try:
    from local_intel import (LocalIntelligenceEngine, classify_error,
                             fmt_dur as intel_dur, fmt_tok as intel_tok)
    from intel_panels import IntelWindow
    INTEL_ERR = None
except Exception as _intel_exc:          # pragma: no cover
    LocalIntelligenceEngine = IntelWindow = None
    classify_error = lambda _e: "other"
    intel_dur = intel_tok = str
    INTEL_ERR = repr(_intel_exc)

try:
    import tkinter as tk
    from tkinter import font as tkfont
except ImportError:
    print("Tkinter tidak ditemukan. Di Windows ia sudah bawaan Python resmi.")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
POS_PATH = os.path.join(BASE_DIR, "window_pos.json")
HIST_PATH = os.path.join(BASE_DIR, "history.json")
LOG_PATH = os.path.join(BASE_DIR, "tokenpet.log")
LOG_MAX = 200 * 1024       # rotasi sederhana: maks ~200 KB
LOCK_PATH = os.path.join(BASE_DIR, "tokenpet.lock")
AI_PATH = os.path.join(BASE_DIR, "ai_accounts.json")
CREDENTIAL_PATH = os.path.join(BASE_DIR, "tokenpet_credentials.dat")
INTEL_PATH = os.path.join(BASE_DIR, "intel_state.json")
INTEL_DEMO_PATH = os.path.join(BASE_DIR, "intel_state_demo.json")
CONFIG_SCHEMA_VERSION = 2
STATE_SCHEMA_VERSION = 2

# Akun AI di halaman settings: (key, label, pet default index).
# Index pet mengikuti PETS: 0 Robo (9router), 1 Claude, 2 ChatGPT,
# 3 Antigravity, 4 Cursor, 5 Codex. Tiap layanan punya pet sendiri.
AI_PROVIDERS = (
    ("antigravity", "Antigravity", 3),
    ("claude", "Claude", 1),
    ("chatgpt", "ChatGPT + Codex", 2),     # satu akun OpenAI untuk keduanya
    ("cursor", "Cursor", 4),
)
# Pet yang ikut akun lain: pet Codex = tampilan lain dari akun ChatGPT.
PET_OWNER = {"codex": "chatgpt"}
AI_PET_VER = 2        # naik bila urutan PETS berubah (reset pet akun lama)

# Halaman login web tiap layanan yang punya tombol "Continue with Google".
# Login Google sendiri terjadi di browser (halaman resmi layanan itu);
# widget tidak pernah melihat password / sesi / cookie-nya.
GOOGLE_LOGIN_URLS = {
    "claude": "https://claude.ai/login",
    "chatgpt": "https://chatgpt.com/auth/login",
}
# Portal resmi yang dibuka dari kartu OpenAI. Login tetap dilakukan di
# browser/desktop app resmi; TokenPet hanya membaca kredensial lokal Codex
# untuk menampilkan status dan kuota, tidak pernah membaca password/cookie.
CHATGPT_PORTAL_URL = "https://chatgpt.com/"
CODEX_PORTAL_URL = "https://chatgpt.com/codex/open-app?app_brand=chatgpt&source=login"
GOOGLE_ENDPOINTS = {
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
}

# --- Tema "coklat gelap + lime" (mengikuti header referensi) ---
BG = "#2B1611"
BG_EMPTY = "#4D3027"
BORDER = "#5E3B2E"
FG = "#F5EBE6"
MUTED = "#B79B8F"
ORANGE = "#F4845F"
YELLOW_TXT = "#F2E04A"
MINT = "#B5E61D"
RED = "#F0443A"
YELLOW = "#FFC857"
GREEN = "#B5E61D"
ALERT_BG = "#4D1A1A"
BTN = "#43302A"
GROUND = "#B9976A"
GROUND_HI = "#E3D0A4"
GROUND_LO = "#7A5A3E"
GROUND_DOT = "#3B2A1E"
GROUND_TUFT = "#EFE4C6"
CACTUS = "#5BA384"
DECOR = "cactus"
DECOR_COL = "#5BA384"
DECOR_COL2 = "#FFFFFF"
FX_CFG = None      # efek cuaca header (diisi apply_theme)
SCENE = None       # adegan latar header (diisi apply_theme)
SYM = "~"          # simbol melayang di dekat pet (diisi apply_theme)
BRIGHT = "#FFFFFF"   # angka besar / sorotan
SPARK = "#FFD35A"    # kilau kecil di pojok header
SHADOW = "#1B0E0A"   # bayangan pet melayang
ON_ACCENT = "#17121F"   # teks di atas warna aksen (tombol aktif, badge)
ON_WARN = "#17121F"
ON_BAD = "#FFFFFF"
SURFACE = "#37231D"      # kartu / panel dalam (turunan BG)
SURFACE_HI = "#42291F"
DARK = "#170B07"         # track bar kosong, isi lencana
LINE = "#4A322A"         # garis tipis pemisah / tepi kartu
FONT = "Segoe UI"          # diganti otomatis oleh pick_fonts() sesuai font terpasang
FONT_SEMI = None           # varian semibold (mis. "Segoe UI Semibold") kalau ada
FONT_SCALE = 0.86          # skala global ukuran huruf (lebih kecil = lebih ringan)
FONT_CANDIDATES = ("Segoe UI", "Segoe UI Variable Text", "Inter", "SF Pro Text",
                   "Helvetica Neue", "Noto Sans", "Open Sans", "Roboto",
                   "DejaVu Sans", "Liberation Sans", "Arial")
MODEL_COLORS = ["#FFB547", "#4FD1C5", "#FF7AA2", "#9F8CFF",
                "#7CF2A2", "#F6E05E", "#63B3ED", "#F78F5C"]
OTHER_COLOR = "#6B5A8A"

BASE_W = 480           # lebar acuan; semua ukuran diskalakan terhadap ini
MIN_W, MAX_W = 360, 900
PERIOD_SECS = {"today": 86400, "24h": 86400, "7d": 604800,
               "30d": 2592000, "60d": 5184000, "all": 2592000}
DEFAULT_BUDGET = {"24h": 100e6, "7d": 500e6, "today": 100e6, "all": 1e9}
# Periode yang angkanya di 9router sudah berupa JENDELA GESER, jadi batas
# otomatis ikut turun sendiri saat jendela bergeser. Yang kumulatif (7d,
# all) hanya bertambah, jadi batasnya ikut naik dan tak pernah turun.
AUTO_WINDOWED = ("24h", "today", "30d", "60d")
DEFAULT_ALIASES = {"oc": "opencode", "ag": "antigravity"}
DEFAULT_ALERTS = {"enabled": True, "sound": True, "levels": [20, 10, 5],
                  "hot": True, "cooldown_seconds": 600,
                  "banner_seconds": 12}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MOOD = {"CRITICAL": "butuh perhatian sekarang!", "HOT": "ngebut banget, awas habis!",
        "WARM": "lumayan kenceng nih", "CHILL": "santai aja~",
        "STABLE": "lagi nunggu token..."}
SPEECH = {
    "STABLE": ("Semuanya aman.", "Aku jagain tokennya."),
    "CHILL": ("Lagi santai dulu...", "Zzz... panggil kalau perlu."),
    "WARM": ("Mulai ramai nih.", "Aku tetap pantau ya."),
    "HOT": ("Wah, tokennya banyak dipakai!", "Lagi sibuk nih."),
    "CRITICAL": ("Hati-hati! Quota hampir habis!", "Butuh perhatian sekarang!"),
    "DISCONNECTED": ("Eh... servernya ke mana?",),
    "CONNECTED": ("Kita online lagi!",),
    "ERROR": ("Ada sedikit masalah...",),
    "RESET": ("Quota sudah reset, yay!",),
}

# ---------------------------------------------------------------------
# Pet vektor halus (bukan blok piksel lagi). Tiap pet digambar dari
# bentuk dasar dalam kotak 48 x 44 satuan:
#   ("o", cx, cy, rx, ry, warna)             oval
#   ("r", x0, y0, x1, y1, radius, warna)     kotak membulat
#   ("p", [x, y, ...], warna)                poligon (sudut dibulatkan)
# "body" ikut diberi kontur gelap; "deco" ditimpa di atasnya (kilau, lampu).
# Wajah (mata, alis, pipi, mulut) digambar terpisah supaya bisa berkedip,
# melirik kursor, dan berganti ekspresi.
# ---------------------------------------------------------------------
PET_W, PET_H = 48.0, 44.0
HDR_BAR_Y0, HDR_BAR_H = 30, 16      # bar status header (satuan s())
PET_SCALE = 1.1       # pet sedikit lebih besar di header (ekspresi terbaca)


def _o(cx, cy, rx, ry, k):
    return ("o", cx, cy, rx, ry, k)


def _r(x0, y0, x1, y1, rad, k):
    return ("r", x0, y0, x1, y1, rad, k)


def _p(pts, k):
    return ("p", pts, k)


def _b_nova(fr):                      # astronot: helm putih + visor gelap
    a = 1.0 if fr else 0.0
    body = [
        _r(22.7, 0.8, 24.5, 5.8, 0.9, "S"),                 # antena
        _o(23.6, 1.9, 2.0, 2.0, "V"),
        _o(11.0, 34.5 - a, 3.3, 4.4, "S"),                  # tangan
        _o(36.2, 33.5 + a, 3.3, 4.4, "S"),
        _r(14.5, 29.0, 33.5, 41.0, 6.5, "W"),               # badan
        _o(19.6, 41.6 - 0.9 * a, 5.2, 2.4, "S"),            # kaki
        _o(28.6, 41.6 - 0.9 * (1 - a), 5.2, 2.4, "S"),
        _o(25.0, 18.6, 16.6, 15.4, "S"),                    # bayangan helm
        _o(23.6, 17.4, 16.2, 14.6, "W"),                    # helm
        _o(7.3, 18.0, 2.7, 4.3, "V"),                       # telinga helm
        _o(40.0, 18.0, 2.7, 4.3, "V"),
    ]
    deco = [
        _o(23.6, 18.4, 12.0, 9.6, "N"),                     # visor
        _o(18.0, 13.8, 3.8, 1.4, "g"),                      # kilau visor
        _o(23.6, 35.2, 2.0, 1.5, "V"),                      # lampu dada
    ]
    return body, deco


def _b_obi(fr):                     # gurita pink: topi kuning + headphone
    w = (0.0, 1.0, 1.0, 0.0) if fr == 0 else (1.0, 0.0, 0.0, 1.0)
    tx = (11.6, 19.7, 28.3, 36.4)
    body = [_o(tx[i], 36.2 + w[i], 4.4, 5.4, "P") for i in range(4)]
    body += [
        _o(24.0, 20.6, 16.8, 14.8, "P"),                    # kepala
        _r(4.9, 11.5, 7.5, 22.0, 1.1, "B"),                 # tangkai headphone
        _r(40.5, 11.5, 43.1, 22.0, 1.1, "B"),
        _o(7.0, 22.8, 3.9, 6.2, "B"),                       # bantalan telinga
        _o(41.0, 22.8, 3.9, 6.2, "B"),
        _o(24.0, 11.4, 14.8, 8.2, "H"),                     # topi
        _r(8.6, 14.4, 39.4, 19.6, 2.6, "h"),
        _o(24.0, 3.6, 3.0, 3.0, "h"),                       # pompom
    ]
    deco = [
        _o(17.2, 9.2, 3.6, 1.4, "Hh"),
        _o(7.0, 22.8, 1.7, 3.3, "Bh"),
        _o(41.0, 22.8, 1.7, 3.3, "Bh"),
    ]
    return body, deco


def _b_piko(fr):                    # helm indigo + pelat wajah putih
    a = 1.0 if fr else 0.0
    body = [
        _r(15.2, 38.0 - a, 22.2, 43.8 - a, 2.6, "D"),       # kaki
        _r(25.8, 38.0 - (1 - a), 32.8, 43.8 - (1 - a), 2.6, "D"),
        _r(22.9, 2.6, 25.1, 6.0, 1.0, "L"),                 # antena
        _o(24.0, 2.3, 2.0, 2.0, "E"),
        _o(24.0, 20.4, 18.2, 17.0, "D"),                    # helm
        _o(5.6, 22.6, 3.7, 6.0, "L"),                       # bantalan telinga
        _o(42.4, 22.6, 3.7, 6.0, "L"),
    ]
    deco = [
        _r(10.4, 12.4, 37.6, 34.0, 10.0, "W"),              # pelat wajah
        _o(17.0, 8.4, 5.4, 1.5, "Dh"),                      # kilau helm
    ]
    return body, deco


def _b_kubo(fr):                     # kubus 3D bersudut bulat
    a = 1.0 if fr else 0.0
    body = [
        _r(9.5, 39.0 - a, 17.5, 43.6 - a, 2.4, "D"),        # kaki
        _r(21.0, 39.0 - (1 - a), 29.0, 43.6 - (1 - a), 2.4, "D"),
        _p([31.5, 15.5, 41.5, 7.0, 41.5, 31.5, 31.5, 40.0], "S"),   # sisi kanan
        _p([5.5, 15.5, 15.5, 7.0, 41.5, 7.0, 31.5, 15.5], "T"),     # atas
        _r(5.5, 15.5, 31.5, 40.0, 5.0, "F"),                # depan
    ]
    deco = [
        _r(8.2, 18.4, 11.2, 30.0, 1.5, "Fh"),
        _o(26.0, 11.2, 6.0, 1.1, "Th"),
    ]
    return body, deco


def _b_zuzu(fr):                # UFO melayang + api roket
    flame = ([18.8, 34.5, 29.2, 34.5, 24.0, 42.8] if fr == 0 else
             [18.0, 34.5, 30.0, 34.5, 24.0, 44.0])
    inner = ([21.2, 35.4, 26.8, 35.4, 24.0, 39.8] if fr == 0 else
             [20.6, 35.4, 27.4, 35.4, 24.0, 41.0])
    body = [
        _p(flame, "F"),
        _o(24.0, 32.4, 11.0, 4.6, "D"),                     # perut
        _o(24.0, 16.2, 12.4, 12.4, "G"),                    # kubah kaca
        _o(24.0, 27.4, 22.4, 8.2, "I"),                     # piring
    ]
    deco = [
        _p(inner, "f"),
        _o(18.2, 8.6, 3.8, 1.6, "Gh"),                      # kilau kaca
        _o(24.0, 22.2, 18.6, 1.1, "Ih"),                    # tepi piring
        _o(9.0, 28.8, 2.3, 1.6, "Y"), _o(16.6, 31.4, 2.3, 1.6, "Y"),
        _o(24.0, 32.4, 2.3, 1.6, "Y"), _o(31.4, 31.4, 2.3, 1.6, "Y"),
        _o(39.0, 28.8, 2.3, 1.6, "Y"),
    ]
    return body, deco


def _b_robo(fr):
    """Robo: robot pendamping generasi baru dengan visor LED lebar.

    Mata, mulut, dan alis TIDAK digambar di sini (tidak ada glyph statis di
    layar) -- semuanya digambar oleh PetMonitor._draw_led_face supaya bisa
    berkedip, melirik kursor, dan berganti ekspresi."""
    a = 1.0 if fr else 0.0
    body = [
        _r(22.8, 1.6, 25.2, 8.8, 1.0, "AN"),                # antena
        _o(24.0, 1.9, 2.5, 2.5, "AL"),                      # lampu antena
        _o(9.7, 36.3 - a, 3.4, 4.2, "P"),                   # bahu/lengan
        _o(38.3, 35.5 + a, 3.4, 4.2, "P"),
        _r(12.8, 29.2, 35.2, 41.3, 6.0, "W"),               # torso berlapis
        _o(18.5, 41.6 - a, 5.1, 2.5, "D"),                  # kaki magnetik
        _o(29.5, 41.6 - (1 - a), 5.1, 2.5, "D"),
        _r(5.0, 8.0, 43.0, 33.6, 10.5, "W"),                # kepala
        _o(4.6, 21.1, 2.7, 5.5, "P"),                       # ear pod
        _o(43.4, 21.1, 2.7, 5.5, "P"),
    ]
    deco = [
        _r(8.4, 11.1, 39.6, 30.7, 7.8, "D"),                # frame visor
        _r(10.2, 13.0, 37.8, 28.8, 6.2, "K"),               # layar gelap
        _o(15.0, 14.8, 4.1, 0.9, "Gh"),                     # kilau kaca layar
        _p([8.2, 14.0, 10.0, 11.1, 10.0, 29.2, 8.2, 26.7], "Ph"),
        _p([39.8, 14.0, 38.0, 11.1, 38.0, 29.2, 39.8, 26.7], "Ph"),
        _r(17.1, 32.1, 30.9, 38.6, 2.7, "P"),               # panel dada
        _r(18.7, 33.4, 29.3, 37.2, 1.6, "D"),
        _o(24.0, 35.3, 1.2, 1.2, "E"),                      # inti cahaya
        _o(32.5, 33.8, 0.7, 0.7, "E"),
    ]
    return body, deco


def _b_claude(fr):
    """Claude: gumpalan terakota hangat, pelat wajah krem, kilau 4 titik."""
    a = 1.0 if fr else 0.0
    body = [
        _p([24.0, 0.3, 25.3, 3.5, 28.6, 4.8, 25.3, 6.1,
            24.0, 9.3, 22.7, 6.1, 19.4, 4.8, 22.7, 3.5], "SP"),   # kilau
        _o(7.6, 31.4 - a, 3.0, 3.7, "c"),                          # tangan
        _o(40.4, 30.4 + a, 3.0, 3.7, "c"),
        _o(18.4, 41.4 - 0.9 * a, 4.6, 2.4, "c"),                   # kaki
        _o(29.6, 41.4 - 0.9 * (1 - a), 4.6, 2.4, "c"),
        _r(5.5, 8.0, 42.5, 38.5, 15.0, "C"),                       # badan
        _o(11.2, 11.6, 3.6, 3.6, "C"),                             # telinga
        _o(36.8, 11.6, 3.6, 3.6, "C"),
    ]
    deco = [
        _o(24.0, 23.4, 15.4, 11.2, "F"),                           # pelat wajah
        _o(24.0, 36.0, 5.0, 1.6, "c"),                             # perut
    ]
    return body, deco


def _b_chatgpt(fr):
    """ChatGPT: gelembung ucapan hijau-toska dengan ekor + tiga titik ketik."""
    a = 1.0 if fr else 0.0
    body = [
        _p([9.0, 30.0, 7.4, 41.6, 21.5, 34.4], "G"),               # ekor
        _o(4.4, 21.5, 2.7, 4.0, "g"),                              # sisi
        _o(43.6, 21.5, 2.7, 4.0, "g"),
        _o(25.6, 40.6 - 0.9 * a, 4.2, 2.4, "g"),                   # kaki
        _o(35.0, 40.6 - 0.9 * (1 - a), 4.2, 2.4, "g"),
        _r(5.0, 6.0, 43.0, 36.0, 13.0, "G"),                       # gelembung
    ]
    deco = [
        _r(9.0, 10.0, 39.0, 31.6, 10.0, "W"),                      # pelat wajah
        _o(20.2, 7.9, 0.95, 0.95, "DT"),                           # titik ketik
        _o(24.0, 7.9, 0.95, 0.95, "DT"),
        _o(27.8, 7.9, 0.95, 0.95, "DT"),
    ]
    return body, deco


def _b_antigravity(fr):
    """Antigravity: roh kubah ungu melayang, cincin orbit, api kecil di bawah."""
    a = 1.0 if fr else 0.0
    body = [
        _o(24.0, 33.6, 22.4, 4.6, "R"),                            # cincin orbit
        _o(3.4, 12.0 + a, 2.1, 2.1, "R"),                          # satelit
        _o(44.6, 29.0 - a, 1.7, 1.7, "R"),
        _o(24.0, 41.3, 2.6 + 0.8 * a, 2.0 + 0.8 * a, "F"),         # api
        _p([18.5, 33.0, 29.5, 33.0, 27.0, 39.0, 21.0, 39.0], "b"),  # nozel
        _o(6.4, 21.0, 2.7, 4.8, "b"),                              # pod samping
        _o(41.6, 21.0, 2.7, 4.8, "b"),
        _r(7.5, 4.5, 40.5, 36.0, 16.0, "B"),                       # kubah
    ]
    deco = [
        _r(11.0, 11.0, 37.0, 30.0, 9.0, "N"),                      # visor
        _o(17.0, 14.2, 3.6, 1.1, "g"),                             # kilau
    ]
    return body, deco


def _b_cursor(fr):
    """Cursor: kotak grafit dengan pelat wajah terang + panah kursor putih."""
    a = 1.0 if fr else 0.0
    body = [
        _p([29.0, 0.8, 29.0, 10.6, 31.6, 8.4, 33.6, 12.4,
            35.8, 11.4, 33.8, 7.4, 37.4, 7.4], "AR"),              # panah kursor
        _o(8.0, 34.4 - a, 3.0, 3.8, "K"),                          # tangan
        _o(40.0, 33.4 + a, 3.0, 3.8, "K"),
        _r(14.0, 31.0, 34.0, 41.2, 4.5, "K"),                      # badan
        _o(19.0, 41.4 - 0.9 * a, 4.6, 2.4, "k"),                   # kaki
        _o(29.0, 41.4 - 0.9 * (1 - a), 4.6, 2.4, "k"),
        _r(6.0, 9.0, 42.0, 34.0, 8.0, "K"),                        # kepala
    ]
    deco = [
        _r(9.4, 12.4, 38.6, 31.0, 5.0, "P"),                       # pelat wajah
        _o(24.0, 37.0, 1.1, 1.1, "A"),                             # lampu dada
    ]
    return body, deco


def _b_codex(fr):
    """Codex: awan lavender dengan layar terminal gelap + prompt >_ di dada."""
    a = 1.0 if fr else 0.0
    body = [
        _o(4.6, 31.0, 2.6, 3.2, "v"),                              # tangan
        _o(43.4, 31.0, 2.6, 3.2, "v"),
        _o(19.0, 41.2 - 0.9 * a, 4.4, 2.4, "v"),                   # kaki
        _o(29.0, 41.2 - 0.9 * (1 - a), 4.4, 2.4, "v"),
        _o(24.0, 24.0, 17.0, 12.0, "W"),                           # awan
        _o(10.8, 27.0, 7.6, 7.0, "W"),
        _o(37.2, 27.0, 7.6, 7.0, "W"),
        _o(16.8, 15.6, 8.2, 7.8, "W"),
        _o(31.2, 14.6, 9.0, 8.4, "W"),
        _r(10.0, 29.0, 38.0, 37.2, 3.5, "W"),
    ]
    deco = [
        _r(10.6, 14.6, 37.4, 31.8, 6.0, "N"),                      # layar
        _o(16.0, 17.2, 3.4, 1.0, "g"),                             # kilau
        _p([20.8, 33.3, 22.8, 34.7, 20.8, 36.1], "V"),             # ">"
        _r(24.2, 35.4, 28.0, 36.3, 0.4, "V"),                      # "_"
    ]
    return body, deco


def _pet(name, build, colors, face, hover=False):
    return {"name": name, "build": build, "colors": colors, "face": face,
            "hover": hover}


# face: eyes = pusat mata, er = (rx, ry), ink = warna mata/mulut, mouth =
# (x, y), mw = lebar mulut, blush = warna pipi (None = tanpa pipi), base =
# warna kulit di bawah pipi, glow = mata menyala di visor gelap.
PETS = [
    _pet("Robo", _b_robo,
         {"W": "#F4F8FC", "D": "#172333", "Dh": "#344A65", "L": "#8EA8C4",
          "P": "#607D9B", "Ph": "#A8D8F2", "E": "#8BE7FF", "K": "#08121F",
          "G": "#D8F7FF", "Gh": "#1C2B42",
          "AN": "#8EA8C4", "AL": "#8BE7FF"},
         # led=True -> wajah layar LED (lihat _draw_led_face). base="K" =
         # warna layar, jadi aksesoris wajah tahu latarnya gelap.
         dict(eyes=((18.0, 20.2), (30.0, 20.2)), er=(2.5, 3.0), ink="E",
              mouth=(24.0, 25.9), mw=5.6, blush="#FF7AA8", base="K",
              glint="G", led=True, screen=(10.9, 13.9, 37.1, 28.3),
              antenna=(24.0, 2.1), lamp=(24.0, 35.9), sweat=45.6)),
    _pet("Claude", _b_claude,
         {"C": "#E07B5A", "c": "#B85A3D", "F": "#FBEBDD", "SP": "#FFD9A8",
          "E": "#2B1710", "G": "#FFFFFF"},
         dict(eyes=((17.6, 22.0), (30.4, 22.0)), er=(2.0, 2.7), ink="E",
              mouth=(24.0, 28.0), mw=6.0, blush="#FF8A7A", base="F",
              glint="G", sweat=41.0)),
    _pet("ChatGPT", _b_chatgpt,
         {"G": "#10A37F", "g": "#0A7C60", "W": "#F4FFFB", "DT": "#D9FFF1",
          "E": "#0B2B24", "GL": "#FFFFFF"},
         dict(eyes=((17.8, 19.6), (30.2, 19.6)), er=(2.0, 2.7), ink="E",
              mouth=(24.0, 25.6), mw=5.8, blush="#FF9DB0", base="W",
              glint="GL", sweat=41.0)),
    _pet("Antigravity", _b_antigravity,
         {"B": "#6C63F2", "b": "#4A42C8", "N": "#0F1030", "g": "#2B2C66",
          "R": "#FF6FD8", "F": "#7DF9FF", "E": "#8CF5FF", "G": "#FFFFFF"},
         dict(eyes=((18.4, 20.6), (29.6, 20.6)), er=(2.1, 2.7), ink="E",
              mouth=(24.0, 26.0), mw=5.0, blush="#FF6FD8", base="N",
              glint="G", glow=True, visor=(24.0, 20.6), sweat=38.0),
         hover=True),
    _pet("Cursor", _b_cursor,
         {"K": "#262932", "k": "#3A3E49", "P": "#ECEDF2", "AR": "#FFFFFF",
          "A": "#8AB4FF", "E": "#14161B", "G": "#FFFFFF"},
         dict(eyes=((18.0, 20.8), (30.0, 20.8)), er=(2.0, 2.7), ink="E",
              mouth=(24.0, 26.6), mw=5.2, blush="#FF9AA2", base="P",
              glint="G", sweat=40.0)),
    _pet("Codex", _b_codex,
         {"W": "#F3F0FF", "v": "#6A5CF0", "V": "#7B6CFF", "N": "#171340",
          "g": "#2C2766", "E": "#B7ABFF", "G": "#FFFFFF"},
         dict(eyes=((18.4, 22.4), (29.6, 22.4)), er=(2.1, 2.7), ink="E",
              mouth=(24.0, 27.8), mw=5.0, blush="#FF8FD0", base="N",
              glint="G", glow=True, visor=(24.0, 22.4), sweat=38.0)),
]
DEFAULT_PET = 0   # Robo

EMOTIONS = ("smile",)          # hover: senyum saja (+ efek lagu)
TONGUE = "#E85D75"
MONO = "Consolas"              # glyph terminal >_ di visor Nova
DEFAULT_PET = 0   # Robo

# Tema per pet: warna UI + tanah + hiasan mengikuti warna pet.
# Kunci = nama pet (huruf kecil). Tambah pet baru -> tambah tema di sini
# (kalau tidak ada, dipakai tema Obi/gurun).
THEME_KEYS = ("BG", "BG_EMPTY", "BORDER", "FG", "MUTED", "ORANGE",
              "YELLOW_TXT", "MINT", "BTN", "GROUND", "GROUND_HI",
              "GROUND_LO", "GROUND_DOT", "GROUND_TUFT", "DECOR",
              "DECOR_COL", "DECOR_COL2")
THEMES = {
    "obi": {          # Gurun: coklat gelap + pasir + kaktus
        "SYM": "~",
        "SCENE": {"kind": "sunset", "sky": ("#21100C", "#7A3C1C"),
                  "far": "#5A2E1A", "near": "#432111",
                  "rings": ["#6F3718", "#A35A27", "#E19445", "#FFD991"]},
        "label": "Gurun",
        "WARN": "#FFC857", "BAD": "#F0443A", "BRIGHT": "#FFFFFF",
        "SPARK": "#FFD35A", "OTHER": "#6B5A8A",
        "MODELS": ["#FFB547", "#4FD1C5", "#FF7AA2", "#9F8CFF",
                   "#7CF2A2", "#F6E05E", "#63B3ED", "#F78F5C"],
        "FX": {"kind": "sand", "n": 28,
               "cols": ["#D9BE8A", "#E8D5A8", "#A8855A"]},
        "BG": "#2B1611", "BG_EMPTY": "#4D3027", "BORDER": "#5E3B2E",
        "FG": "#F5EBE6", "MUTED": "#B79B8F", "ORANGE": "#F4845F",
        "YELLOW_TXT": "#F2E04A", "MINT": "#B5E61D", "BTN": "#43302A",
        "GROUND": "#B9976A", "GROUND_HI": "#E3D0A4", "GROUND_LO": "#7A5A3E",
        "GROUND_DOT": "#3B2A1E", "GROUND_TUFT": "#EFE4C6",
        "DECOR": "cactus", "DECOR_COL": "#5BA384", "DECOR_COL2": "#FFFFFF"},
    "nova": {           # Salju: indigo malam + salju putih + pohon cemara
        "SYM": "\u266a",
        "SCENE": {"kind": "snownight", "sky": ("#13123A", "#2B2A6E"),
                  "far": "#3A3988", "near": "#2A2965",
                  "moon": "#F1EFFF"},
        "label": "Salju",
        "WARN": "#8FD3FF", "BAD": "#FF6B8A", "BRIGHT": "#FFFFFF",
        "SPARK": "#DDE3FF", "OTHER": "#6E6AA8",
        "MODELS": ["#A99BFF", "#7FD0FF", "#F1EFFF", "#FF9EC4",
                   "#8FE3C8", "#FFD27A", "#6B8CFF", "#C9B8FF"],
        "FX": {"kind": "snow", "n": 30,
               "cols": ["#FFFFFF", "#DDE3F7", "#B9C2E8"]},
        "BG": "#1C1B3A", "BG_EMPTY": "#34335C", "BORDER": "#4A4880",
        "FG": "#F1EFFF", "MUTED": "#A9A6D6", "ORANGE": "#B8B2EE",
        "YELLOW_TXT": "#E4E0FF", "MINT": "#A99BFF", "BTN": "#2C2A52",
        "GROUND": "#E6EAF7", "GROUND_HI": "#FFFFFF", "GROUND_LO": "#AEB6D6",
        "GROUND_DOT": "#C5CCE6", "GROUND_TUFT": "#FFFFFF",
        "DECOR": "pine", "DECOR_COL": "#3F8F7A", "DECOR_COL2": "#FFFFFF"},
    "piko": {         # Samudra: biru laut + dasar laut + rumput laut
        "SYM": "~",
        "SCENE": {"kind": "ocean", "sky": ("#0B1C52", "#1E56B0"),
                  "far": "#17409A", "near": "#102F78", "ray": "#7FB8FF"},
        "label": "Samudra",
        "WARN": "#A9A0FF", "BAD": "#FF6B6B", "BRIGHT": "#F4F8FF",
        "SPARK": "#CFE0FF", "OTHER": "#4A5F9C",
        "MODELS": ["#7FD0FF", "#4FD1C5", "#FFB3C7", "#A9C0F5",
                   "#7CF2A2", "#F6E05E", "#5B8CFF", "#FF9A7A"],
        "FX": {"kind": "bubble", "n": 12,
               "cols": ["#7FD0FF", "#A9C0F5", "#CFE0FF"]},
        "BG": "#0F1B3D", "BG_EMPTY": "#233768", "BORDER": "#33509A",
        "FG": "#EAF1FF", "MUTED": "#8FA3D6", "ORANGE": "#7FD0FF",
        "YELLOW_TXT": "#9FE3FF", "MINT": "#7FD0FF", "BTN": "#1C2C5C",
        "GROUND": "#6C8FD8", "GROUND_HI": "#A9C0F5", "GROUND_LO": "#3E5DA8",
        "GROUND_DOT": "#2A4585", "GROUND_TUFT": "#CFE0FF",
        "DECOR": "seaweed", "DECOR_COL": "#4FD1C5", "DECOR_COL2": "#FF7AA2"},
    "kubo": {          # Batu: abu-biru slate + kristal
        "SYM": "~",
        "SCENE": {"kind": "storm", "sky": ("#121622", "#2A3148"),
                  "far": "#222839", "near": "#191E2D", "cloud": "#313852"},
        "label": "Batu",
        "WARN": "#CDBDF2", "BAD": "#F2706B", "BRIGHT": "#F4F7FF",
        "SPARK": "#C9D4F4", "OTHER": "#5A6482",
        "MODELS": ["#9BB0E8", "#6FD3C8", "#C9D4F4", "#E0A6C8",
                   "#F2C26B", "#8FD694", "#7A8CC0", "#E08F78"],
        "FX": {"kind": "rain", "n": 26,
               "cols": ["#8FA3D6", "#6C84C0", "#B5C4E8"]},
        "BG": "#1A1F2E", "BG_EMPTY": "#323A55", "BORDER": "#46507A",
        "FG": "#E6ECFA", "MUTED": "#8F9AC0", "ORANGE": "#C9D4F4",
        "YELLOW_TXT": "#C9D4F4", "MINT": "#9BB0E8", "BTN": "#262D45",
        "GROUND": "#7C879F", "GROUND_HI": "#B5BED4", "GROUND_LO": "#505A74",
        "GROUND_DOT": "#3A4258", "GROUND_TUFT": "#D5DBEA",
        "DECOR": "crystal", "DECOR_COL": "#9BB0E8", "DECOR_COL2": "#E6ECFF"},
    "zuzu": {     # Luar angkasa: ruang hampa gelap + planet cincin + meteor
        "SYM": "z",
        "SCENE": {"kind": "space", "sky": ("#02040F", "#111D3F"),
                  "far": "#182A50", "near": "#0A142C", "neb": "#35569C",
                  "planet": "#FF8A5C", "ring": "#FFE27A"},
        "label": "Luar Angkasa",
        "WARN": "#C79BFF", "BAD": "#FF5C8A", "BRIGHT": "#FFFFFF",
        "SPARK": "#FFE27A", "OTHER": "#5B4FA8",
        "MODELS": ["#9BE3FF", "#FFE27A", "#FF8AD1", "#A99BFF",
                   "#7CF2C8", "#FFB36B", "#6B8CFF", "#E0A6FF"],
        "FX": {"kind": "meteor", "n": 11,
               "cols": ["#FFE27A", "#FF9E6D", "#9BE3FF"]},
        "BG": "#080C1B", "BG_EMPTY": "#182343", "BORDER": "#314C78",
        "FG": "#EEF5FF", "MUTED": "#93A7CB", "ORANGE": "#9BE3FF",
        "YELLOW_TXT": "#FFE27A", "MINT": "#6DCDFF", "BTN": "#121C33",
        "GROUND": "#263B64", "GROUND_HI": "#4D6D9E", "GROUND_LO": "#142443",
        "GROUND_DOT": "#0B152B", "GROUND_TUFT": "#88BCEB",
        "DECOR": "asteroid", "DECOR_COL": "#9FBCE7", "DECOR_COL2": "#FFB36B"},
}


def pick_fonts(root, wanted=None):
    """Pilih font proporsional yang enak dibaca dari yang terpasang."""
    global FONT, FONT_SEMI
    try:
        fams = {f.lower(): f for f in tkfont.families(root)}
    except tk.TclError:
        return
    for name in ([wanted] if wanted else []) + list(FONT_CANDIDATES):
        if name and str(name).lower() in fams:
            FONT = fams[str(name).lower()]
            break
    FONT_SEMI = fams.get((FONT + " Semibold").lower())


def rpts(x0, y0, x1, y1, r, n=6):
    """Titik poligon kotak bersudut membulat (r = radius sudut)."""
    r = max(0.0, min(float(r), (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    if r < 1.0:
        return [x0, y0, x1, y0, x1, y1, x0, y1]
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0),
                       (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


THEMES["robo"] = dict(THEMES["piko"])
THEMES["robo"].update({
    "label":"Perkotaan", "SCENE":{"kind":"city","sky":("#07111F","#243B57"),"far":"#14243A","near":"#0B1625","building":"#17283D","window":"#8BE7FF","road":"#111923","road_hi":"#2B3948","sun":"#38BDF8","moon":"#BFEFFF"},
    "BG":"#0B111A","BG_EMPTY":"#17212E","BORDER":"#2D4054","FG":"#EEF6FF","MUTED":"#91A6BA","ORANGE":"#00E5FF","YELLOW_TXT":"#7DD3FC","MINT":"#22D3EE","BTN":"#14202D",
    "GROUND":"#283746","GROUND_HI":"#435466","GROUND_LO":"#17222D","GROUND_DOT":"#0E151D","GROUND_TUFT":"#6B8093","DECOR":"city","DECOR_COL":"#22D3EE","DECOR_COL2":"#38BDF8",
    "WARN":"#38BDF8","BAD":"#FF6B6B","BRIGHT":"#FFFFFF","SPARK":"#67E8F9","OTHER":"#66819B","MODELS":["#8BE7FF","#B6F36B","#FFD76A","#A7B7FF","#FF8FB3","#7CF2C8","#7AA7FF","#F7A36A"],
    "FX":{"kind":"stars","n":12,"cols":["#FFFFFF","#67E8F9","#38BDF8"]},
})
def lum(hex_col):
    """Kecerahan relatif 0..1."""
    h = hex_col.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on_color(hex_col):
    """Warna teks yang terbaca di atas hex_col."""
    return "#17121F" if lum(hex_col) > 0.45 else "#FFFFFF"


def apply_theme(pet_name, follow=True):
    """Set semua warna global sesuai pet. follow=False -> tema gurun."""
    key = str(pet_name).lower() if follow else "obi"
    th = THEMES.get(key) or THEMES["obi"]
    g = globals()
    for k in THEME_KEYS:
        g[k] = th[k]
    g["CACTUS"] = th["DECOR_COL"]
    g["FX_CFG"] = th.get("FX")
    g["SCENE"] = th.get("SCENE")
    g["SYM"] = th.get("SYM", "~")
    # status: OK = aksen tema, warn/bad = versi yang serasi dengan tema
    g["GREEN"], g["YELLOW"], g["RED"] = th["MINT"], th["WARN"], th["BAD"]
    g["BRIGHT"], g["SPARK"] = th["BRIGHT"], th["SPARK"]
    g["MODEL_COLORS"], g["OTHER_COLOR"] = list(th["MODELS"]), th["OTHER"]
    # turunan otomatis
    g["ALERT_BG"] = mix(th["BG"], th["BAD"], 0.30)
    g["SHADOW"] = mix(th["BG"], "#000000", 0.55)
    g["ON_ACCENT"] = on_color(th["MINT"])
    g["ON_WARN"] = on_color(th["WARN"])
    g["ON_BAD"] = on_color(th["BAD"])
    g["SURFACE"] = mix(th["BG"], th["FG"], 0.06)
    g["SURFACE_HI"] = mix(th["BG"], th["FG"], 0.11)
    g["DARK"] = mix(th["BG"], "#000000", 0.45)
    g["LINE"] = mix(th["BG"], th["FG"], 0.15)
    return th.get("label", "")


def style_tk(root):
    """Warna widget Tk standar (menu, dialog budget) ikut tema."""
    for pat, val in (
            ("*Toplevel.background", BG), ("*Frame.background", BG),
            ("*Dialog.background", BG),
            ("*Label.background", BG), ("*Label.foreground", FG),
            ("*Entry.background", BG_EMPTY), ("*Entry.foreground", FG),
            ("*Entry.insertBackground", FG),
            ("*Entry.selectBackground", MINT),
            ("*Entry.selectForeground", ON_ACCENT),
            ("*Entry.highlightColor", MINT),
            ("*Entry.highlightBackground", BORDER),
            ("*Button.background", BTN), ("*Button.foreground", FG),
            ("*Button.activeBackground", MINT),
            ("*Button.activeForeground", ON_ACCENT),
            ("*Button.highlightBackground", BG),
            ("*Menu.background", BTN), ("*Menu.foreground", FG),
            ("*Menu.activeBackground", MINT),
            ("*Menu.activeForeground", ON_ACCENT),
            ("*Menu.selectColor", MINT)):
        root.option_add(pat, val, 80)


# =====================================================================
# Util
# =====================================================================
def _backup_corrupt_json(path):
    """Keep a recoverable copy of malformed state without blocking startup."""
    if not os.path.exists(path):
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = "%s.corrupt-%s" % (path, stamp)
    try:
        os.replace(path, dst)
        return dst
    except OSError:
        return None


def _safe_json(path, default, write_default=False):
    """Read a JSON object; malformed files are backed up and never crash UI."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("JSON root must be an object")
        return data
    except FileNotFoundError:
        return dict(default)
    except (OSError, ValueError, TypeError):
        _backup_corrupt_json(path)
        data = dict(default)
        if write_default:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except OSError:
                pass
        return data


DEFAULT_CONFIG_STATE = {
    "schema_version": CONFIG_SCHEMA_VERSION,
    "combos_url": "http://localhost:20128/api/combos",
    "stats_url": "http://localhost:20128/api/usage/stats?period=24h",
    "auth": {},
}


def load_config():
    cfg = _safe_json(CONFIG_PATH, DEFAULT_CONFIG_STATE, write_default=True)
    # Old config files remain valid. The version is only a migration marker;
    # unknown keys are retained untouched by TokenPet.
    cfg.setdefault("schema_version", CONFIG_SCHEMA_VERSION)
    cfg.setdefault("combos_url", DEFAULT_CONFIG_STATE["combos_url"])
    cfg.setdefault("stats_url", DEFAULT_CONFIG_STATE["stats_url"])
    cfg.setdefault("auth", {})
    return cfg


def migrate_legacy_credentials(cfg, store):
    """Move TokenPet-owned plaintext config fields into Windows DPAPI once.

    Environment variables and credentials managed by external CLIs are never
    copied.  If DPAPI is unavailable, the existing setting is kept so a
    working 9Router installation is not silently disconnected.
    """
    specs = (("auth", "password", "9router"),
             ("chatgpt_quota", "access_token", "chatgpt"),
             ("google_oauth", "client_secret", "google_oauth"))
    changed = False
    for group, field, key in specs:
        part = cfg.get(group)
        if not isinstance(part, dict):
            continue
        value = str(part.get(field) or "").strip()
        if not value:
            continue
        try:
            store.save(key, value)
        except SecureStorageError:
            continue
        part[field] = ""
        changed = True
    if not changed:
        return False
    cfg["schema_version"] = CONFIG_SCHEMA_VERSION
    try:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, CONFIG_PATH)
        return True
    except OSError:
        return False


def shade(hex_col, f):
    """f>0 -> lebih terang, f<0 -> lebih gelap."""
    h = hex_col.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    if f >= 0:
        rgb = [int(v + (255 - v) * f) for v in rgb]
    else:
        rgb = [int(v * (1 + f)) for v in rgb]
    return "#%02X%02X%02X" % tuple(rgb)


def mix(c1, c2, t):
    """Campur dua warna hex: t=0 -> c1, t=1 -> c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(int(round(x + (y - x) * t))
                                   for x, y in zip(a, b))


def _mk_theme(base, label, bg, fg, accent, title, scene, fx, decor, dcol,
              dcol2, models, ground, sym="~", warn=None, bad="#FF6B6B",
              spark=None):
    """Tema turunan: warna panel/tanah dihitung dari beberapa warna kunci."""
    th = dict(THEMES[base])
    th.update(
        label=label, SYM=sym, SCENE=scene, FX=fx, DECOR=decor,
        DECOR_COL=dcol, DECOR_COL2=dcol2, BG=bg, FG=fg,
        BG_EMPTY=mix(bg, fg, 0.12), BORDER=mix(bg, accent, 0.38),
        MUTED=mix(fg, bg, 0.45), ORANGE=title, YELLOW_TXT=mix(fg, accent, 0.3),
        MINT=accent, BTN=mix(bg, fg, 0.09), GROUND=ground,
        GROUND_HI=mix(ground, "#FFFFFF", 0.22),
        GROUND_LO=mix(ground, "#000000", 0.35),
        GROUND_DOT=mix(ground, "#000000", 0.5),
        GROUND_TUFT=mix(ground, "#FFFFFF", 0.4), WARN=warn or accent, BAD=bad,
        BRIGHT="#FFFFFF", SPARK=spark or accent, OTHER=mix(bg, fg, 0.35),
        MODELS=list(models))
    return th


THEMES["claude"] = _mk_theme(
    "obi", "Senja", "#23142E", "#FFF2E9", "#F49A72", "#E77B62",
    {"kind": "twilight", "sky": ("#25163D", "#D86E67"), "far": "#5B3158",
     "near": "#2D1A3B", "moon": "#FFE1A8", "lamp": "#FFD27A"},
    {"kind": "petal", "n": 18, "cols": ["#FFD1C5", "#FF9DB0", "#F6C177"]},
    "lantern", "#FFD27A", "#E9916E",
    ["#E9916E", "#FFD9A8", "#9FD8CB", "#C8A2FF", "#F6C177", "#7FB7FF",
     "#FF8FA3", "#B5E3A0"], "#4A2E38", sym="*", warn="#FFC857")
THEMES["chatgpt"] = _mk_theme(
    "piko", "Laguna", "#08201B", "#EAFBF5", "#19C39B", "#10A37F",
    {"kind": "ocean", "sky": ("#04201B", "#0E6B57"), "far": "#0A4F42",
     "near": "#073A31", "ray": "#6FE7C8"},
    {"kind": "bubble", "n": 18, "cols": ["#BFFFEA", "#6FE7C8", "#FFFFFF"]},
    "seaweed", "#19C39B", "#7CF0D0",
    ["#19C39B", "#7CF0D0", "#FFD76A", "#8FB8FF", "#FF9DB0", "#C8F36B",
     "#B6A2FF", "#FFB070"], "#1E5C4E", warn="#FFD76A")
THEMES["antigravity"] = _mk_theme(
    "zuzu", "Gravitasi Nol", "#120D29", "#F4F0FF", "#A78BFA", "#FF6FD8",
    {"kind": "antigravity", "sky": ("#170C3D", "#532A8F"), "far": "#34216E",
     "near": "#1A1648", "grid": "#7DF9FF", "orb": "#FF6FD8",
     "island": "#6C63F2"},
    {"kind": "firefly", "n": 18, "cols": ["#FF9DE6", "#7DF9FF", "#C9B8FF"]},
    "holo", "#FF9DE6", "#7DF9FF",
    ["#8C84FF", "#7DF9FF", "#FF6FD8", "#FFE27A", "#7CF2C8", "#FFB36B",
     "#6B8CFF", "#E0A6FF"], "#382B84", sym="z", warn="#FFE27A")
THEMES["cursor"] = _mk_theme(
    "kubo", "Editor", "#101216", "#F1F2F6", "#9DB8FF", "#E8EAF0",
    {"kind": "storm", "sky": ("#0E1014", "#2A2E38"), "far": "#1C1F27",
     "near": "#14161C", "cloud": "#3B404C"},
    {"kind": "rain", "n": 22, "cols": ["#8A93A6", "#B8C0D0", "#5E6678"]},
    "city", "#9DB8FF", "#E8EAF0",
    ["#9DB8FF", "#E8EAF0", "#FFD76A", "#7CF2C8", "#FF9DB0", "#C8A2FF",
     "#7FD0FF", "#F6A36A"], "#2F333D", warn="#FFD76A")
THEMES["codex"] = _mk_theme(
    "nova", "Awan Kode", "#17163F", "#F1EFFF", "#8F82FF", "#B9B0FF",
    {"kind": "snownight", "sky": ("#12113A", "#322F8A"), "far": "#4540A8",
     "near": "#2F2B80", "moon": "#F1EFFF"},
    {"kind": "snow", "n": 28, "cols": ["#FFFFFF", "#DDE3F7", "#B9C2E8"]},
    "crystal", "#8F82FF", "#D9D4FF",
    ["#8F82FF", "#7FD0FF", "#F1EFFF", "#FF9EC4", "#8FE3C8", "#FFD27A",
     "#6B8CFF", "#C9B8FF"], "#D9D8F4", sym="\u266a", warn="#8FD3FF")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


KEY_COLOR = "#010203"      # warna kunci: piksel ini transparan (celah)


def gap_color():
    """Warna celah di antara header dan panel; dibuat transparan oleh
    -transparentcolor (Windows) sehingga kedua kartu tampak terpisah."""
    return KEY_COLOR


def ease_io(p):
    """Easing halus (cubic in-out) untuk animasi buka/tutup."""
    p = clamp(p, 0.0, 1.0)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2.0


def sanitize_log_message(message):
    """Remove common credential/header forms before any message reaches disk."""
    text = str(message or "")
    patterns = (
        # JSON / query-string / Python-dict fields.
        r'(?i)("?(?:access[_-]?token|refresh[_-]?token|session[_-]?token|'
        r'auth[_-]?token|api[_-]?key|client[_-]?secret|password|cookie)"?'
        r'\s*[:=]\s*["\']?)([^\s,;\}\]\"\']+)',
        # HTTP Authorization header and bare bearer token.
        r'(?i)(authorization\s*[:=]\s*)([^\r\n]+)',
        r'(?i)(bearer\s+)([A-Za-z0-9._~+\-/=]{8,})',
    )
    for pat in patterns:
        text = re.sub(pat, lambda m: m.group(1) + "[REDACTED]", text)
    return text


def log_exc(msg=""):
    """Tulis exception tak tertangani ke tokenpet.log (rotasi ~200 KB).

    Penting karena .pyw tidak punya konsol. Tak pernah raise.
    """
    try:
        if os.path.exists(LOG_PATH) and \
                os.path.getsize(LOG_PATH) > LOG_MAX:
            try:
                os.replace(LOG_PATH, LOG_PATH + ".1")
            except OSError:
                pass
        import traceback
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n%s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"),
                sanitize_log_message(msg),
                sanitize_log_message(traceback.format_exc())))
    except Exception:
        pass


def mask_secret(text):
    """Samarkan password/cookie untuk output --debug-stats."""
    s = str(text or "")
    if len(s) <= 4:
        return "****"
    return s[:2] + "****" + s[-2:]


class SingleInstance:
    """Satu instance saja: named mutex Windows, fallback file lock.

    Di Windows pakai CreateMutexW (otomatis lepas saat proses mati).
    Di OS lain pakai file lock eksklusif (fcntl bila ada).
    .acquire() -> True bila instance pertama, False bila sudah berjalan.
    """

    def __init__(self, name="TokenPetSingleInstance"):
        self.name, self._mutex, self._fh = name, None, None

    def acquire(self):
        if os.name == "nt":
            try:
                import ctypes
                m = ctypes.windll.kernel32.CreateMutexW(None, False,
                                                        "Global\\" + self.name)
                if not m:
                    return self._fallback()
                if ctypes.windll.kernel32.GetLastError() == 183:
                    ctypes.windll.kernel32.CloseHandle(m)
                    return False
                self._mutex = m
                return True
            except Exception:
                log_exc("single-instance mutex")
                return self._fallback()
        return self._fallback()

    def _fallback(self):
        try:
            self._fh = open(LOCK_PATH, "w")
            try:
                import fcntl
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (ImportError, OSError):
                pass
            self._fh.write(str(os.getpid()))
            self._fh.flush()
            return True
        except OSError:
            log_exc("single-instance lock")
            return False

    def release(self):
        try:
            if self._mutex:
                import ctypes
                ctypes.windll.kernel32.ReleaseMutex(self._mutex)
                ctypes.windll.kernel32.CloseHandle(self._mutex)
                self._mutex = None
        except Exception:
            pass
        try:
            if self._fh:
                try:
                    import fcntl
                    fcntl.flock(self._fh, fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass
                self._fh.close()
                self._fh = None
        except Exception:
            pass


def visible_rect():
    """Area layar terlihat (virtual screen, dukung multi-monitor).

    Return (x, y, w, h) atau None bila gagal.
    """
    try:
        import ctypes
        u = ctypes.windll.user32
        x = u.GetSystemMetrics(76)    # SM_XVIRTUALSCREEN
        y = u.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN
        w = u.GetSystemMetrics(78)    # SM_CXVIRTUALSCREEN
        h = u.GetSystemMetrics(79)    # SM_CYVIRTUALSCREEN
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    return None


def clamp_to_visible(x, y, w=100, h=60):
    """Pindahkan (x, y) agar jendela w x h tetap terlihat."""
    r = visible_rect()
    if r is None:
        return x, y
    vx, vy, vw, vh = r
    x = clamp(x, vx, vx + vw - min(w, vw) + 40)
    y = clamp(y, vy, vy + vh - min(h, vh))
    return x, y


def fmt_countdown(secs):
    if secs is None or secs < 0:
        return "--"
    secs = int(secs)
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m, s = divmod(secs, 60)
    if d > 0:
        return "%dd %dh" % (d, h)
    if h > 0:
        return "%dh %dm" % (h, m)
    if m > 0:
        return "%dm %ds" % (m, s)
    return "%ds" % s


def fmt_ago(secs):
    if secs is None:
        return "never"
    if secs < 5:
        return "just now"
    if secs < 3600:
        return "%ds ago" % int(secs)
    return "%dh %dm ago" % (int(secs // 3600), int((secs % 3600) // 60))


def fmt_tokens(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "--"
    if n < 1000:
        return "%d" % int(n)
    if n < 999950:
        return "%.1fK" % (n / 1e3)
    if n < 999.95e6:
        return "%.1fM" % (n / 1e6)
    return "%.2fB" % (n / 1e9)


def fmt_pct(p):
    """Persen 1 desimal; nilai > 0 tapi sangat kecil tampil '<0.1%'."""
    if p is None:
        return "--%"
    if 0 < p < 0.05:
        return "<0.1%"
    return "%.1f%%" % min(999.9, p)


def fmt_left(p):
    """Sisa kuota: <10% pakai 1 desimal supaya tak tampil '0%' palsu."""
    if p < 10:
        return "%.1f%%" % p
    return "%d%%" % int(round(p))


def smooth_color(pct_left, warn_mid=50.0, warn_low=20.0):
    """Warna status yang bergradasi halus: hijau -> kuning -> merah."""
    if pct_left is None:
        return BG_EMPTY
    p = clamp(float(pct_left), 0.0, 100.0)
    low = clamp(float(warn_low), 1.0, 99.0)
    mid = clamp(float(warn_mid), low + 1.0, 99.0)
    hi = min(100.0, mid + 20.0)
    pts = [(0.0, RED), (low, mix(RED, YELLOW, 0.4)), (mid, YELLOW),
           (hi, GREEN)]
    for (p0, c0), (p1, c1) in zip(pts, pts[1:]):
        if p <= p1:
            return mix(c0, c1, clamp((p - p0) / (p1 - p0), 0.0, 1.0))
    return GREEN


def bar_color(pct_left, warn_mid=50.0, warn_low=20.0):
    if pct_left is None:
        return BG_EMPTY
    if pct_left < warn_low:
        return RED
    if pct_left < warn_mid:
        return YELLOW
    return GREEN


def parse_amount(text):
    """'100M' / '2.5b' / '750k' / '1500000' -> float token, None bila salah."""
    m = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([kKmMbB]?)\s*$",
                 str(text or ""))
    if not m:
        return None
    mult = {"": 1.0, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2).lower()]
    return float(m.group(1).replace(",", ".")) * mult


def next_alert_level(left, levels, prev, hysteresis=2.0):
    """Level peringatan sisa budget. Return (level_baru, harus_bunyi).

    levels mis. [20, 10, 5]; bunyi hanya saat level MEMBURUK. Level baru
    turun (pulih) hanya bila sisa sudah > ambang + hysteresis, supaya tidak
    bunyi berulang saat angka naik-turun di sekitar ambang.
    """
    lvl = sum(1 for t in levels if left < t)
    if prev is None:
        return lvl, lvl > 0
    if lvl < prev:
        lvl = min(prev, sum(1 for t in levels if left < t + hysteresis))
    return lvl, lvl > prev


def enable_dpi_awareness():
    """Windows: tajam di layar 125%/150% (tanpa ini jadi buram)."""
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def autostart_command():
    exe = sys.executable
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pw):
        exe = pw
    return '"%s" "%s"' % (exe, os.path.join(BASE_DIR, "pet_monitor.pyw"))


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "TokenPet")
        return True
    except (ImportError, OSError):
        return False


def set_autostart(on):
    try:
        import winreg
    except ImportError:
        raise OSError("hanya Windows")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "TokenPet", 0, winreg.REG_SZ,
                              autostart_command())
        else:
            try:
                winreg.DeleteValue(k, "TokenPet")
            except FileNotFoundError:
                pass


class History:
    """Riwayat nyata yang direkam widget, tanpa mengarang data yang hilang."""
    BUCKET, KEEP = 300, 35 * 86400
    FIELDS = ("tokens", "prompt", "completion", "cached", "requests")

    def __init__(self, path):
        self.path, self.dirty, self.last, self.b = path, False, {}, {}
        raw = _safe_json(path, {"buckets": {}}, write_default=False).get(
            "buckets", {})
        cut = time.time() - self.KEEP
        try:
            for k, val in raw.items():
                if int(k) < cut:
                    continue
                # v1 stored a number; retain it as the observed token total.
                src = val if isinstance(val, dict) else {"tokens": val}
                self.b[int(k)] = {f: max(0.0, float(src.get(f, 0) or 0))
                                  for f in self.FIELDS}
        except (ValueError, TypeError, AttributeError):
            _backup_corrupt_json(path)
            self.b = {}

    def feed(self, period, total, now=None, replace=False, components=None,
             requests=None):
        """Store only positive observed deltas from cumulative 9Router data."""
        now = time.time() if now is None else now
        components = components or {}
        cur = {"tokens": float(total or 0),
               "prompt": float(components.get("prompt", 0) or 0),
               "completion": float(components.get("completion", 0) or 0),
               "cached": float(components.get("cached", 0) or 0),
               "requests": float(requests or 0)}
        prev = self.last.get(period)
        inc = {f: 0.0 for f in self.FIELDS}
        if prev and not replace:
            for f in self.FIELDS:
                if cur[f] > prev.get(f, 0.0):
                    inc[f] = cur[f] - prev[f]
        self.last[period] = cur
        if any(inc.values()):
            k = int(now // self.BUCKET) * self.BUCKET
            dest = self.b.setdefault(k, {f: 0.0 for f in self.FIELDS})
            for f in self.FIELDS:
                dest[f] += inc[f]
            self.dirty = True
        return inc["tokens"]

    def reset(self):
        self.last = {}

    @staticmethod
    def _shape(period, now, earliest=None):
        if period in ("today", "24h"):
            return 24, 3600, (int(now // 3600) + 1) * 3600 - 24 * 3600
        if period == "7d":
            return 28, 6 * 3600, (int(now // (6 * 3600)) + 1) * 6 * 3600 - 28 * 6 * 3600
        if period == "30d":
            return 30, 86400, (int(now // 86400) + 1) * 86400 - 30 * 86400
        step = 86400
        start = int((earliest if earliest is not None else now) // step) * step
        n = max(1, min(35, int((now - start) // step) + 1))
        return n, step, start

    def series(self, period, now=None, field="tokens"):
        """Observed bucket values, oldest first. Empty fields remain zero."""
        now = time.time() if now is None else now
        field = field if field in self.FIELDS else "tokens"
        earliest = min(self.b) if self.b else None
        n, step, start = self._shape(period, now, earliest)
        out = [0.0] * n
        for k, val in self.b.items():
            i = int((k - start) // step)
            if 0 <= i < n:
                out[i] += float(val.get(field, 0.0) or 0)
        return out, step

    def totals(self, period, now=None):
        now = time.time() if now is None else now
        earliest = min(self.b) if self.b else None
        n, step, start = self._shape(period, now, earliest)
        end = start + n * step
        total = {f: 0.0 for f in self.FIELDS}
        for k, val in self.b.items():
            if start <= k < end:
                for f in self.FIELDS:
                    total[f] += float(val.get(f, 0.0) or 0)
        return total

    def save(self):
        if not self.dirty:
            return
        cut = time.time() - self.KEEP
        self.b = {k: v for k, v in self.b.items() if k >= cut}
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"schema_version": STATE_SCHEMA_VERSION,
                           "buckets": {str(k): {a: round(b, 3) for a, b in v.items()}
                                       for k, v in self.b.items()}}, f)
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            pass


# =====================================================================
# Model combo <-> statistik byModel
# =====================================================================
def model_keys(entry):
    """Varian kunci satu entri combo (lowercase) - dipakai utk model_budgets."""
    e = str(entry).strip().lower()
    out = [e]
    if "/" in e:
        out.append(e.split("/", 1)[1])
        out.append(e.rsplit("/", 1)[-1])
    out.append(out[-1].split(":")[0])
    seen, uniq = set(), []
    for k in out:
        if k and k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq


def short_model(entry, width=28):
    s = str(entry)
    s = s.split("/", 1)[1] if "/" in s else s
    return s if len(s) <= width else s[:width - 1] + ".."


def metric_value(vals, metric="io"):
    """Total token dari komponen input/cached/output sesuai metrik.

    Dashboard 9router hanya menampilkan tiga kartu terpisah (Total Input
    Tokens / Cached Tokens / Output Tokens) - tidak ada kartu "total".
    Supaya angka widget bisa dibandingkan 1:1 dengan kartu mana pun, widget
    menjumlahkan komponen yang sama:

    - `io`              : input + output (semua token yang ditransfer)
    - `input`           : input saja       (= kartu "Total Input Tokens")
    - `output`          : output saja      (= kartu "Output Tokens")
    - `input_noncached` : input - cached   (prompt yang tak di-cache)
    """
    p = float(vals.get("prompt") or 0)
    c = float(vals.get("cached") or 0)
    o = float(vals.get("completion") or 0)
    if metric == "input":
        return p
    if metric == "output":
        return o
    if metric == "input_noncached":
        return max(0.0, p - c)
    return p + o


# Kartu dashboard 9router -> field yang dipakai. Dipakai breakdown supaya
# label di layar selalu cocok dengan angka dashboard yang dibandingkan.
DASH_CARDS = (("input", "prompt"), ("cached", "cached"), ("output", "completion"))


def card_value(vals, key):
    """Nilai satu kartu dashboard (input / cached / output) dari dict."""
    return float(vals.get(key) or 0)


METRICS = ("io", "input", "output", "input_noncached")
METRIC_LABEL = {"io": "", "input": "input saja",
                "output": "output saja",
                "input_noncached": "input–cached"}

def parse_model_stats(st, metric="io"):
    """stats JSON -> list entri unik per model.

    Fields: name, raw, provider, requests (mentah), prompt, cached,
    completion, tokens (jumlah sesuai `metric`).
    """
    out = []
    for key, val in ((st or {}).get("byModel") or {}).items():
        if not isinstance(val, dict):
            continue
        try:
            comp = {"prompt": float(val.get("promptTokens") or 0),
                    "cached": float(val.get("cachedTokens") or 0),
                    "completion": float(val.get("completionTokens") or 0)}
            tok = metric_value(comp, metric)
            if tok == 0 and not any(comp.values()):
                tok = float(val.get("totalTokens") or val.get("tokens") or 0)
            req = int(val.get("requests") or 0)
        except (TypeError, ValueError):
            continue
        k = str(key).strip()
        name, provider = k, ""
        if k.endswith(")") and " (" in k:
            name, provider = k.rsplit(" (", 1)
            provider = provider[:-1]
        raw = str(val.get("rawModel") or "").strip().lower() or \
            name.strip().lower()
        provider = str(val.get("provider") or provider).strip().lower()
        out.append({"name": name.strip().lower(), "raw": raw,
                    "provider": provider, "tokens": tok, "requests": req,
                    "prompt": comp["prompt"], "cached": comp["cached"],
                    "completion": comp["completion"]})
    return out


def parse_stats_components(st):
    """Tiga angka resmi 9router: input / cached / output (semua trafik).

    Dipakai buat cross-check visual: kartu dashboard menampilkan persis
    tiga angka ini, jadi widget bisa dicocokkan kolom per kolom.
    """
    if not isinstance(st, dict):
        return None
    try:
        p = st.get("totalPromptTokens")
        c = st.get("totalCompletionTokens")
        if p is None and c is None:
            return None
        return {"prompt": float(p or 0),
                "cached": float(st.get("totalCachedTokens") or 0),
                "completion": float(c or 0)}
    except (TypeError, ValueError):
        return None


def parse_stats_running(st):
    """Jumlah request yang SEDANG berjalan di 9router (model lagi dipakai).

    9router mengirim `pending.byModel` ({"model (provider)": n}) dan
    `activeRequests` ([{model, provider, account, count}]) di
    /api/usage/stats; server membersihkannya sendiri bila request macet
    (60 dtk). Mengembalikan None bila server tidak mengirim infonya
    (9router lama), supaya widget memakai cara lama (token naik)."""
    if not isinstance(st, dict):
        return None
    seen, by_model, active = False, 0, 0
    pend = st.get("pending")
    if isinstance(pend, dict) and isinstance(pend.get("byModel"), dict):
        seen = True
        for v in pend["byModel"].values():
            try:
                by_model += max(0, int(v))
            except (TypeError, ValueError):
                pass
    act = st.get("activeRequests")
    if isinstance(act, list):
        seen = True
        for a in act:
            try:
                active += max(0, int(a.get("count", 1))) \
                    if isinstance(a, dict) else 0
            except (TypeError, ValueError):
                pass
    return max(by_model, active) if seen else None


def parse_stats_totals(st, metric="io"):
    """Total resmi dari 9router (bila ada) utk cross-check byModel."""
    if not isinstance(st, dict):
        return None
    try:
        pt = st.get("totalPromptTokens")
        ct = st.get("totalCompletionTokens")
        if pt is None and ct is None:
            return None
        return {"tokens": metric_value({"prompt": float(pt or 0),
                                        "cached": float(
                                            st.get("totalCachedTokens") or 0),
                                        "completion": float(ct or 0)},
                                       metric),
                "requests": int(st.get("totalRequests") or 0)}
    except (TypeError, ValueError):
        return None


def quota_reset_in(s):
    """Detik sampai reset kuota 9router (ISO '...Z'); None bila tak tahu."""
    if not s or not isinstance(s, str):
        return None
    try:
        t = s.strip()
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return max(0.0, dt.timestamp() - time.time())
    except (ValueError, OverflowError):
        return None


def fmt_count(n):
    """Angka cacah (bukan token): '1.000' gaya Indonesia."""
    try:
        return "{:,}".format(int(n)).replace(",", ".")
    except (TypeError, ValueError):
        return "--"


def parse_nr_quotas(payload):
    """GET /api/usage/<connection-id> -> list kuota per koneksi 9router.

    Tiap item: {key, name, used, total, left (sisa %), reset (detik /
    None)}. Kuota `unlimited` dilewati (tak ada batas). Satuan kuota ini
    CACAH (request/saldo), bukan token - jadi ditampilkan apa adanya,
    tidak dicampur ke budget token.
    """
    out = []
    quotas = (payload or {}).get("quotas") \
        if isinstance(payload, dict) else None
    if not isinstance(quotas, dict):
        return out
    for key, v in quotas.items():
        if not isinstance(v, dict) or v.get("unlimited"):
            continue
        try:
            used = float(v.get("used") or 0)
            total = float(v.get("total") or 0)
        except (TypeError, ValueError):
            continue
        left = v.get("remainingPercentage")
        if left is None and v.get("remaining") is not None and total > 0:
            try:
                left = float(v.get("remaining")) / total * 100.0
            except (TypeError, ValueError):
                left = None
        if left is None:
            left = max(0.0, (total - used) / total * 100.0) \
                if total > 0 else 0.0
        try:
            left = max(0.0, min(100.0, float(left)))
        except (TypeError, ValueError):
            left = 0.0
        out.append({"key": str(key),
                    "name": str(v.get("displayName") or key),
                    "used": used, "total": total, "left": left,
                    "reset": quota_reset_in(v.get("resetAt"))})
    return out


def expand_combos(items, names):
    """Daftar model dari combo terpilih; combo bersarang (combo di dalam
    combo) diurai rekursif supaya token model aslinya ikut terhitung."""
    by_name = {c.get("name"): c for c in items if isinstance(c, dict)}
    out, found = [], False

    def walk(combo, seen):
        for m in combo.get("models", []):
            m = str(m).strip()
            if not m:
                continue
            sub = by_name.get(m)
            if sub is not None and m not in seen:
                walk(sub, seen | {m})
            elif sub is None and m not in out:
                out.append(m)

    for c in items:
        if not isinstance(c, dict):
            continue
        if "*" in names or c.get("name") in names:
            found = True
            walk(c, {c.get("name")})
    return out, found


def _provider_ok(prefix, provider, aliases):
    a = (aliases or {}).get(prefix)
    if a:
        return a in provider or provider in a
    return provider.startswith(prefix)


def match_score(entry, s, aliases=None, known=None, strict=True):
    """Skor kecocokan entri combo vs satu baris stats. 0 = tak cocok.

    Provider dipakai bila prefix combo (mis. 'oc') bisa dipetakan ke salah
    satu provider yang muncul di stats (`known`): provider yang beda berarti
    model itu dipakai lewat jalur LAIN (di luar combo). Bila prefix tak bisa
    dipetakan, provider diabaikan (tak ada bukti beda).
    Return negatif-bebas: skor, atau -skor bila cocok-nama tapi provider beda
    dan strict=False (dipakai sebagai penanda 'tak pasti').
    """
    e = str(entry).strip().lower()
    prefix = e.split("/", 1)[0] if "/" in e else ""
    rest = e.split("/", 1)[1] if "/" in e else e
    tail = e.rsplit("/", 1)[-1]
    names = {s["name"], s["raw"]} - {""}
    tails = {n.rsplit("/", 1)[-1] for n in names}
    if e in names or rest in names:
        sc = 100
    elif tail in tails:
        sc = 80
    elif tail.split(":")[0] in {t.split(":")[0] for t in tails}:
        sc = 50
    else:
        return 0
    if prefix and s["provider"]:
        if _provider_ok(prefix, s["provider"], aliases):
            return sc + 5
        known = known or set()
        if any(_provider_ok(prefix, kp, aliases) for kp in known if kp):
            # prefix terpetakan ke provider lain -> jalur berbeda
            return 0 if strict else -(sc - 20)
    return sc


def assign_usage(models, entries, aliases=None, strict=True):
    """Tiap baris stats ke SATU model combo (skor tertinggi) -> tak dobel.

    Return ({model: {tokens, requests, prompt, cached, completion}},
            {tokens, requests, maybe, prompt, cached, completion})
    Bagian kedua = di luar combo; `maybe` = token yang dihitung ke combo
    meski provider-nya beda (hanya saat strict=False). Komponen
    prompt/cached/completion ikut dijumlahkan supaya tiap metrik bisa
    dihitung tanpa fetch ulang.
    """
    def blank():
        return {"tokens": 0.0, "requests": 0, "prompt": 0.0, "cached": 0.0,
                "completion": 0.0}

    per = {m: blank() for m in models}
    other = blank()
    other["maybe"] = 0.0
    known = {s["provider"] for s in entries if s["provider"]}
    for s in entries:
        best, best_sc, best_abs = None, 0, 0
        for m in models:
            sc = match_score(m, s, aliases, known, strict)
            if abs(sc) > best_abs:
                best, best_sc, best_abs = m, sc, abs(sc)
        if best is None:
            other["tokens"] += s["tokens"]
            other["requests"] += s["requests"]
            for f in ("prompt", "cached", "completion"):
                other[f] += s.get(f, 0.0)
            continue
        per[best]["tokens"] += s["tokens"]
        per[best]["requests"] += s["requests"]
        for f in ("prompt", "cached", "completion"):
            per[best][f] += s.get(f, 0.0)
        if best_sc < 0:
            other["maybe"] += s["tokens"]
    return per, other


def extract_auth_cookie(set_cookie_headers):
    for h in set_cookie_headers or []:
        if h and "auth_token=" in h:
            return h.split("auth_token=", 1)[1].split(";")[0].strip()
    return None


class AuthSession:
    """Login otomatis dashboard 9router, cookie auth_token di memori."""

    def __init__(self, cfg, timeout, credential_store=None):
        a = cfg.get("auth", {}) or {}
        self.login_url = a.get("login_url",
                               "http://localhost:20128/api/auth/login")
        env = a.get("password_env", "TOKENPET_PASSWORD")
        # Environment wins. The legacy config field is only a compatibility
        # fallback; normal persistence uses the per-user DPAPI store.
        secret = None
        if credential_store:
            try:
                secret = credential_store.get("9router")
            except SecureStorageError:
                secret = None
        self.password = os.environ.get(env, "") or secret or a.get("password", "")
        self.logout_url = a.get("logout_url") or re.sub(
            r"/login/?$", "/logout", self.login_url)
        self.timeout = timeout
        self.cookie = None
        self._lock = threading.Lock()

    def enabled(self):
        return bool(self.password)

    def login(self):
        if not self.password:
            raise ValueError("password 9Router belum tersedia")
        body = json.dumps({"password": self.password}).encode("utf-8")
        req = urllib.request.Request(
            self.login_url, data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if hasattr(resp.headers, "get_all"):
                    headers = resp.headers.get_all("Set-Cookie") or []
                elif resp.headers.get("Set-Cookie"):
                    headers = [resp.headers.get("Set-Cookie")]
                else:
                    headers = []
                tok = extract_auth_cookie(headers)
                try:
                    data = json.loads(resp.read().decode("utf-8", "replace")
                                      or "{}")
                except ValueError:
                    data = {}
                if not tok:
                    if not data.get("success"):
                        raise ValueError("login gagal (password salah?)")
                    raise ValueError("login tanpa cookie auth_token")
                with self._lock:
                    self.cookie = "auth_token=" + tok
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ValueError("login gagal (password salah?)")
            raise

    def logout(self):
        """Hapus cookie di memori + beri tahu server (best effort)."""
        with self._lock:
            ck, self.cookie = self.cookie, None
        url = self.logout_url
        if not (ck and url):
            return

        def _go():
            try:
                req = urllib.request.Request(
                    url, data=b"{}", method="POST",
                    headers={"Content-Type": "application/json",
                             "Cookie": ck})
                urllib.request.urlopen(req, timeout=self.timeout).close()
            except Exception:
                pass
        threading.Thread(target=_go, daemon=True).start()

    def get(self, url, headers, timeout):
        for attempt in (0, 1):
            h = dict(headers or {})
            with self._lock:
                ck = self.cookie
            if ck:
                h["Cookie"] = ck
            req = urllib.request.Request(url, headers=h)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                if e.code == 401 and self.enabled() and attempt == 0:
                    self.login()
                    continue
                raise
        raise ValueError("gagal ambil %s" % url)


# =====================================================================
# Simulasi (demo tanpa 9router) - memakai bentuk byModel asli
# =====================================================================
# =====================================================================
# Login Google (OAuth 2.0 + PKCE, penerima di 127.0.0.1)
# =====================================================================
class GoogleLoginError(Exception):
    pass


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwt_claims(token):
    """Isi (payload) id_token. Token diterima langsung dari endpoint token
    lewat HTTPS, jadi tanda tangan tidak perlu diperiksa ulang di sini."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part.encode("ascii")))
    except (IndexError, ValueError, AttributeError):
        return {}


def google_oauth_login(gcfg, opener=None, timeout=180.0):
    """Masuk dengan Google: buka browser, tunggu callback lokal, tukar kode.

    gcfg: {client_id, client_secret?, auth_url?, token_url?, userinfo_url?}
    Mengembalikan {"email", "name"}. Tidak ada token yang disimpan.
    `opener(url)` = fungsi pembuka browser (diganti saat uji)."""
    cid = str((gcfg or {}).get("client_id") or "").strip()
    if not cid:
        raise GoogleLoginError("client_id Google belum diisi")
    ep = dict(GOOGLE_ENDPOINTS)
    ep.update({k: v for k, v in (gcfg or {}).items()
               if k in ep and isinstance(v, str) and v})
    opener = opener or webbrowser.open
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = _b64url(secrets.token_bytes(16))
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" not in q and "error" not in q:
                self.send_response(404)
                self.end_headers()
                return
            got["q"] = {k: v[0] for k, v in q.items()}
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<html><body style='font-family:sans-serif;"
                             "text-align:center;padding:48px'><h3>TokenPet: "
                             "login Google selesai.</h3><p>Boleh tutup tab "
                             "ini.</p></body></html>".encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    srv.timeout = 0.5
    redirect = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        url = ep["auth_url"] + "?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect,
            "response_type": "code", "scope": "openid email profile",
            "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "prompt": "select_account"})
        opener(url)
        end = time.time() + float(timeout)
        while "q" not in got and time.time() < end:
            srv.handle_request()
    finally:
        srv.server_close()
    q = got.get("q")
    if not q:
        raise GoogleLoginError("waktu habis menunggu login Google")
    if q.get("error"):
        raise GoogleLoginError("Google menolak: %s" % q["error"])
    if q.get("state") != state:
        raise GoogleLoginError("state tidak cocok (dibatalkan demi keamanan)")
    form = {"code": q["code"], "client_id": cid, "redirect_uri": redirect,
            "grant_type": "authorization_code", "code_verifier": verifier}
    if gcfg.get("client_secret"):
        form["client_secret"] = str(gcfg["client_secret"])
    try:
        req = urllib.request.Request(
            ep["token_url"], urllib.parse.urlencode(form).encode("utf-8"),
            {"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as r:
            tok = json.loads(r.read().decode("utf-8"))
        info = _jwt_claims(tok.get("id_token") or "")
        if not info.get("email") and tok.get("access_token"):
            rq = urllib.request.Request(
                ep["userinfo_url"],
                headers={"Authorization": "Bearer " + tok["access_token"]})
            with urllib.request.urlopen(rq, timeout=15) as r:
                info = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise GoogleLoginError("tukar kode gagal: %s" % str(e)[:60])
    if not info.get("email"):
        raise GoogleLoginError("Google tidak mengirim email")
    return {"email": str(info["email"]), "name": str(info.get("name") or "")}



# =====================================================================
# Kuota ChatGPT (tampil saat pet ChatGPT aktif, menggantikan daftar model)
# =====================================================================
# Sumber: endpoint internal ChatGPT yang juga dipakai Codex CLI. TIDAK
# terdokumentasi resmi, jadi bisa berubah sewaktu-waktu; gagal = tampil
# pesan, widget tetap jalan. Token hanya dikirim ke URL ini dan tidak
# pernah ditulis ke log / file.
CHATGPT_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


class QuotaError(Exception):
    """kind: nocred | auth | net | http | format | other"""

    def __init__(self, kind, msg):
        Exception.__init__(self, msg)
        self.kind, self.msg = kind, msg


def _win_name(sec):
    try:
        h = float(sec) / 3600.0
    except (TypeError, ValueError):
        return "Kuota", "KUOTA"
    if abs(h - 5) < 0.6:
        return "5 jam", "5J"
    if abs(h - 168) < 2:
        return "Mingguan", "MGG"
    if h >= 24 and abs(h / 24 - round(h / 24)) < 0.05:
        d = int(round(h / 24))
        return "%d hari" % d, "%dH" % d
    return "%g jam" % round(h, 1), "%gJ" % round(h, 1)


def parse_chatgpt_usage(body, now=None):
    """Respons /wham/usage -> {plan, windows[], credits, limit_reached, t}.

    windows: [{key, name, tab, used (0..100), reset_at, reset_s, limit_s}]
    `secondary_window` bisa null (mis. paket yang hanya punya batas mingguan)."""
    now = time.time() if now is None else now
    try:
        d = json.loads(body) if isinstance(body, (str, bytes)) else body
    except ValueError:
        raise QuotaError("format", "respons bukan JSON")
    rl = d.get("rate_limit") if isinstance(d, dict) else None
    if not isinstance(rl, dict):
        raise QuotaError("format", "respons tak berisi rate_limit")
    wins = []
    for key in ("primary_window", "secondary_window"):
        w = rl.get(key)
        if not isinstance(w, dict):
            continue
        try:
            used = clamp(float(w["used_percent"]), 0.0, 100.0)
        except (KeyError, TypeError, ValueError):
            continue
        reset_at, reset_s = w.get("reset_at"), w.get("reset_after_seconds")
        try:
            if reset_s is None and reset_at is not None:
                reset_s = max(0.0, float(reset_at) - now)
            if reset_at is None and reset_s is not None:
                reset_at = now + float(reset_s)
        except (TypeError, ValueError):
            reset_at = reset_s = None
        name, tab = _win_name(w.get("limit_window_seconds"))
        wins.append({"key": key, "name": name, "tab": tab, "used": used,
                     "reset_at": reset_at, "reset_s": reset_s,
                     "limit_s": w.get("limit_window_seconds")})
    if not wins:
        raise QuotaError("format", "tak ada jendela kuota di respons")
    bal = None
    cr = d.get("credits")
    if isinstance(cr, dict) and cr.get("balance") is not None:
        try:
            bal = float(cr["balance"])
        except (TypeError, ValueError):
            bal = None
    return {"plan": str(d.get("plan_type") or "").capitalize(),
            "windows": wins, "credits": bal,
            "limit_reached": bool(rl.get("limit_reached")), "t": now}


def chatgpt_credentials(qcfg):
    """(access_token, account_id, sumber). Urutan: secure store > env > Codex.

    Codex CLI menyimpan token login di ~/.codex/auth.json (atau $CODEX_HOME).
    File itu hanya DIBACA; widget tidak menulis / me-refresh token."""
    tok = str(qcfg.get("_secure_access_token") or qcfg.get("access_token") or
              os.environ.get("TOKENPET_CHATGPT_TOKEN") or "").strip()
    acct = str(qcfg.get("account_id") or
               os.environ.get("TOKENPET_CHATGPT_ACCOUNT") or "").strip()
    if tok:
        return tok, acct, "config"
    if qcfg.get("use_codex_auth", True):
        home = os.environ.get("CODEX_HOME") or \
            os.path.join(os.path.expanduser("~"), ".codex")
        path = str(qcfg.get("auth_file") or os.path.join(home, "auth.json"))
        try:
            with open(path, "r", encoding="utf-8") as f:
                t = (json.load(f) or {}).get("tokens") or {}
            tok = str(t.get("access_token") or "").strip()
            acct = acct or str(t.get("account_id") or "").strip()
        except (OSError, ValueError, AttributeError):
            tok = ""
        if tok:
            return tok, acct, "codex"
    raise QuotaError("nocred", "token ChatGPT belum ada")


def fetch_chatgpt_usage(qcfg, urlopen=None, timeout=10):
    tok, acct, _src = chatgpt_credentials(qcfg)
    url = str(qcfg.get("url") or CHATGPT_USAGE_URL)
    if not url.lower().startswith("https://"):
        raise QuotaError("other", "url kuota harus https")
    hdr = {"Authorization": "Bearer " + tok, "User-Agent": "codex-cli",
           "Accept": "application/json"}
    if acct:
        hdr["ChatGPT-Account-Id"] = acct
    try:
        with (urlopen or urllib.request.urlopen)(
                urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise QuotaError("auth", "token ditolak (kedaluwarsa?)")
        raise QuotaError("http", "server menjawab HTTP %d" % e.code)
    except (urllib.error.URLError, OSError):
        raise QuotaError("net", "ChatGPT tak terjangkau")
    return parse_chatgpt_usage(body)


# ---------------------------------------------------------------------
# Deteksi login otomatis (tanpa browser) + kuota Claude
# ---------------------------------------------------------------------
# Token dibaca dari file login CLI masing-masing layanan (hanya DIBACA,
# tidak ditulis / di-refresh, tidak disimpan ke ai_accounts.json):
#   Claude         -> ~/.claude/.credentials.json  ($CLAUDE_CONFIG_DIR)
#   ChatGPT, Codex -> ~/.codex/auth.json           ($CODEX_HOME)
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
AUTO_DETECT_KEYS = ("claude", "chatgpt")


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or \
        os.path.join(os.path.expanduser("~"), ".claude")


def claude_credentials(qcfg=None):
    """(access_token, expires_ms|None, plan, email). QuotaError bila belum login."""
    qcfg = qcfg or {}
    base = _claude_dir()
    path = str(qcfg.get("auth_file") or os.path.join(base, ".credentials.json"))
    d = _read_json_file(path) or {}
    o = d.get("claudeAiOauth") if isinstance(d.get("claudeAiOauth"), dict) else {}
    tok = str(o.get("accessToken") or os.environ.get("TOKENPET_CLAUDE_TOKEN")
              or "").strip()
    if not tok:
        raise QuotaError("nocred", "Claude belum login")
    exp = o.get("expiresAt")
    try:
        exp = float(exp) if exp is not None else None
    except (TypeError, ValueError):
        exp = None
    email = ""
    for cand in (os.path.join(os.path.dirname(base.rstrip("\\/")) or base,
                              ".claude.json"),
                 os.path.join(os.path.expanduser("~"), ".claude.json")):
        oa = (_read_json_file(cand) or {}).get("oauthAccount")
        if isinstance(oa, dict) and oa.get("emailAddress"):
            email = str(oa["emailAddress"])
            break
    return tok, exp, str(o.get("subscriptionType") or "").capitalize(), email


def codex_credentials_info(qcfg=None):
    """(access_token, account_id, plan, email) dari ~/.codex/auth.json."""
    qcfg = qcfg or {}
    home = os.environ.get("CODEX_HOME") or \
        os.path.join(os.path.expanduser("~"), ".codex")
    path = str(qcfg.get("auth_file") or os.path.join(home, "auth.json"))
    t = (_read_json_file(path) or {}).get("tokens")
    t = t if isinstance(t, dict) else {}
    tok = str(t.get("access_token") or "").strip()
    if not tok:
        raise QuotaError("nocred", "Codex/ChatGPT belum login")
    cl = _jwt_claims(str(t.get("id_token") or ""))
    auth = cl.get("https://api.openai.com/auth") \
        if isinstance(cl.get("https://api.openai.com/auth"), dict) else {}
    return (tok, str(t.get("account_id") or auth.get("chatgpt_account_id") or ""),
            str(auth.get("chatgpt_plan_type") or "").capitalize(),
            str(cl.get("email") or ""))


def detect_local_accounts(cfg=None):
    """{kunci: {email, plan}} untuk layanan yang token lokalnya ditemukan."""
    cfg = cfg or {}
    out = {}
    try:
        _t, _e, plan, email = claude_credentials(cfg.get("claude_quota"))
        out["claude"] = {"email": email or "Claude Code", "plan": plan}
    except QuotaError:
        pass
    gpts = list_chatgpt_accounts(cfg)
    if gpts:
        out["chatgpt"] = {"email": gpts[0]["email"], "plan": gpts[0]["plan"]}
    return out


def list_chatgpt_accounts(cfg=None):
    """Semua akun ChatGPT/Codex yang sedang login di komputer ini.

    Sumber (hanya file login CLI, TIDAK membaca cookie/sesi browser):
      $CODEX_HOME, ~/.codex, setiap folder ~/.codex*/ (mis. ~/.codex-kerja
      untuk akun ke-2), dan chatgpt_quota.auth_file / auth_files di config.
    Akun yang sama di dua file hanya dihitung sekali."""
    import glob
    qc = (cfg or {}).get("chatgpt_quota") or {}
    if not qc.get("use_codex_auth", True):
        return []
    home = os.path.expanduser("~")
    cands = []
    if os.environ.get("CODEX_HOME"):
        cands.append(os.path.join(os.environ["CODEX_HOME"], "auth.json"))
    if qc.get("auth_file"):
        cands.append(str(qc["auth_file"]))
    if isinstance(qc.get("auth_files"), list):
        cands += [str(x) for x in qc["auth_files"]]
    cands.append(os.path.join(home, ".codex", "auth.json"))
    cands += sorted(glob.glob(os.path.join(home, ".codex*", "auth.json")))
    seen, out = set(), []
    for path in cands:
        path = os.path.expanduser(path)
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        try:
            _t, acct, plan, email = codex_credentials_info({"auth_file": path})
        except QuotaError:
            continue
        aid = "%s|%s" % (acct, email)
        if any(o["id"] == aid for o in out):
            continue
        out.append({"id": aid, "email": email or "akun ChatGPT",
                    "plan": plan, "path": path,
                    "folder": os.path.basename(os.path.dirname(path))})
    return out


def _iso_epoch(v):
    """'2026-10-05T10:00:00.123+00:00' / 'Z' -> epoch detik (None bila gagal)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) / (1000.0 if v > 1e11 else 1.0)
    try:
        import datetime as _dt
        t = str(v).strip().replace("Z", "+00:00")
        t = re.sub(r"(\.\d{1,6})\d*", r"\1", t)
        return _dt.datetime.fromisoformat(t).timestamp()
    except (ValueError, TypeError):
        return None


def parse_claude_usage(body, now=None, plan=""):
    """Respons /api/oauth/usage -> snapshot yang sama dengan parse_chatgpt_usage."""
    now = time.time() if now is None else now
    try:
        d = json.loads(body) if isinstance(body, (str, bytes)) else body
    except ValueError:
        raise QuotaError("format", "respons bukan JSON")
    if not isinstance(d, dict):
        raise QuotaError("format", "respons Claude tak dikenal")
    spec = (("five_hour", "5 jam", "5J", 5 * 3600),
            ("seven_day", "Mingguan", "MGG", 7 * 86400),
            ("seven_day_opus", "Opus mingguan", "OPUS", 7 * 86400),
            ("seven_day_sonnet", "Sonnet mingguan", "SON", 7 * 86400))
    wins = []
    for key, name, tab, lim in spec:
        w = d.get(key)
        if not isinstance(w, dict):
            continue
        try:
            used = clamp(float(w["utilization"]), 0.0, 100.0)
        except (KeyError, TypeError, ValueError):
            continue
        reset_at = _iso_epoch(w.get("resets_at"))
        wins.append({"key": key, "name": name, "tab": tab, "used": used,
                     "reset_at": reset_at,
                     "reset_s": max(0.0, reset_at - now) if reset_at else None,
                     "limit_s": lim})
    if not wins:
        raise QuotaError("format", "tak ada jendela kuota di respons")
    return {"plan": plan, "windows": wins[:3], "credits": None,
            "limit_reached": any(w["used"] >= 100 for w in wins[:2]), "t": now}


def fetch_claude_usage(qcfg=None, urlopen=None, timeout=10):
    qcfg = qcfg or {}
    tok, exp, plan, _email = claude_credentials(qcfg)
    if exp and exp / 1000.0 < time.time():
        raise QuotaError("auth", "token Claude kedaluwarsa")
    url = str(qcfg.get("url") or CLAUDE_USAGE_URL)
    if not url.lower().startswith("https://"):
        raise QuotaError("other", "url kuota harus https")
    hdr = {"Authorization": "Bearer " + tok, "Accept": "application/json",
           "anthropic-beta": "oauth-2025-04-20", "User-Agent": "claude-code/2.0"}
    try:
        with (urlopen or urllib.request.urlopen)(
                urllib.request.Request(url, headers=hdr), timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise QuotaError("auth", "token ditolak (kedaluwarsa?)")
        raise QuotaError("http", "server menjawab HTTP %d" % e.code)
    except (urllib.error.URLError, OSError):
        raise QuotaError("net", "Claude tak terjangkau")
    return parse_claude_usage(body, plan=plan)


# kunci pet -> (nama tampil, fungsi ambil kuota)
QUOTA_PROVIDERS = {"chatgpt": "ChatGPT", "codex": "Codex", "claude": "Claude"}


class DemoQuota:
    """Simulasi respons /wham/usage (mode demo): 5 jam + mingguan + kredit."""

    def __init__(self):
        self.t0 = time.time()

    def get(self):
        now = time.time()
        el = now - self.t0
        body = {"plan_type": "plus", "credits": {"balance": "18.79"},
                "rate_limit": {
                    "allowed": True, "limit_reached": False,
                    "primary_window": {
                        "used_percent": min(100.0, 38.0 + el * 0.08),
                        "limit_window_seconds": 18000,
                        "reset_after_seconds": int(6198 - el),
                        "reset_at": int(now + 6198 - el)},
                    "secondary_window": {
                        "used_percent": 27,
                        "limit_window_seconds": 604800,
                        "reset_after_seconds": int(212000 - el),
                        "reset_at": int(now + 212000 - el)}}}
        return parse_chatgpt_usage(body, now)


def fmt_reset_in(sec):
    """Sisa waktu reset: '3 hari 4j', '2j 10m', '45m', '30d' (detik)."""
    if sec is None:
        return "--"
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return "%d hari %dj" % (d, h)
    if h:
        return "%dj %dm" % (h, m)
    return "%dm" % m if sec >= 60 else "%dd" % sec


def fmt_reset_hms(sec):
    """Hitung mundur reset lengkap sampai detik: '1j 43m 18d',
    '3 hari 22j 10m 05d' (j = jam, m = menit, d = detik)."""
    if sec is None:
        return "--"
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, sc = divmod(r, 60)
    if d:
        return "%d hari %dj %02dm %02dd" % (d, h, m, sc)
    if h:
        return "%dj %02dm %02dd" % (h, m, sc)
    if m:
        return "%dm %02dd" % (m, sc)
    return "%dd" % sc



DEMO_MODELS = [
    "oc/muse-spark-1.3-contributor-free",
    "oc/big-pickle",
    "openrouter/deepseek/deepseek-v4-pro-0813",
    "tokenharbor/qwen3.8-flash:free",
    "tokenharbor/deepseek-v4.1-flash:free",
    "oc/space-bunny-free",
    "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
    "ag/claude-opus-4-6-thinking",
    "ag/claude-sonnet-4-6",
]


def _demo_row(raw, prompt, comp, req):
    return {"promptTokens": prompt, "completionTokens": comp,
            "requests": req, "rawModel": raw}


class DemoSim:
    def __init__(self):
        self.models = list(DEMO_MODELS)
        self.t0 = time.time()
        self.by = {
            "muse-spark-1.3-contributor-free (opencode)": _demo_row(
                "muse-spark-1.3-contributor-free", 47.0e6, 1.6e6, 634),
            "big-pickle (opencode)": _demo_row("big-pickle", 100000, 2731, 1),
            "deepseek/deepseek-v4-pro-0813 (openrouter)": _demo_row(
                "deepseek/deepseek-v4-pro-0813", 100, 24, 1),
            "qwen3.8-flash:free (tokenharbor)": _demo_row(
                "qwen3.8-flash:free", 62, 55, 1),
            "space-bunny-free (opencode)": _demo_row(
                "space-bunny-free", 100000, 11109, 2),
            "nvidia/nemotron-3-ultra-550b-a55b (nvidia)": _demo_row(
                "nvidia/nemotron-3-ultra-550b-a55b", 120000, 4335, 2),
            "some-other-model (elsewhere)": _demo_row(
                "some-other-model", 30000, 2000, 3),
        }

    def poll(self, metric="io"):
        m = self.by["muse-spark-1.3-contributor-free (opencode)"]
        m["promptTokens"] += random.uniform(700, 2000)
        m["completionTokens"] += random.uniform(50, 400)
        m["requests"] += random.choice([0, 0, 1])
        # simulasi `pending` 9router: tiap 20 dtk ada request aktif ~9 dtk
        run = 1 if (time.time() - self.t0) % 20.0 < 9.0 else 0
        pend = {"byModel": {"muse-spark-1.3-contributor-free (opencode)": run}
                if run else {}}
        st = {"byModel": self.by,
              "totalPromptTokens": sum(float(r.get("promptTokens") or 0)
                                       for r in self.by.values()),
              "totalCompletionTokens": sum(float(r.get("completionTokens") or 0)
                                           for r in self.by.values()),
              "totalCachedTokens": 0,
              "totalRequests": sum(int(r.get("requests") or 0)
                                   for r in self.by.values())}
        return {"models": list(self.models),
                "usage": parse_model_stats({"byModel": self.by}, metric),
                "totals": parse_stats_totals(st, metric),
                "raw_totals": parse_stats_components(st),
                "running": parse_stats_running({"pending": pend})}


# =====================================================================
# Pace: laju dari PENAMBAHAN token (tahan terhadap jendela 24h/7d bergulir)
# =====================================================================
class PaceTracker:
    MIN_SPAN = 30.0   # detik pengamatan minimal sebelum laju dipercaya

    def __init__(self, window=600):
        self.window = float(window)
        self.events = []      # (waktu, tambahan token)
        self.last = None      # total terakhir
        self.first = None

    def add(self, total):
        now = time.time()
        total = float(total)
        if self.first is None:
            self.first = now
        if self.last is not None and total > self.last:
            self.events.append((now, total - self.last))
        # turun = token lama keluar dari jendela -> bukan pemakaian, abaikan
        self.last = total
        cut = now - self.window
        self.events = [e for e in self.events if e[0] >= cut]

    def reset(self):
        """Buang laju lama (metrik/tab berubah -> total tak comparable)."""
        self.events = []
        self.last = None
        self.first = None

    def rate(self):
        """token/detik, atau None bila belum cukup lama diamati."""
        if self.first is None:
            return None
        span = min(self.window, time.time() - self.first)
        if span < self.MIN_SPAN:
            return None
        return sum(e[1] for e in self.events) / span

    def decide(self, remaining, reset_in, hot_ratio=0.5):
        r = self.rate()
        if r is None:
            return "STABLE", "mengukur pace..."
        if r <= 0 or remaining is None:
            return "STABLE", "pace stable"
        if remaining <= 0:
            return "HOT", "batas token sudah habis"
        eta = remaining / r
        txt = "~%s to limit at this pace" % fmt_countdown(eta)
        if reset_in is None or reset_in <= 0:
            return "CHILL", txt
        if eta < hot_ratio * reset_in:
            return "HOT", txt
        if eta < reset_in:
            return "WARM", txt
        return "CHILL", txt


class MoodController:
    """Small state machine that prevents polling noise from jerking the pet."""
    ORDER = ("STABLE", "CHILL", "WARM", "HOT", "CRITICAL")

    def __init__(self, initial="STABLE", settle_seconds=8.0,
                 recover_seconds=20.0):
        self.current = initial if initial in self.ORDER else "STABLE"
        self.pending, self.pending_at = self.current, time.time()
        self.changed_at = time.time()
        self.settle_seconds = max(2.0, float(settle_seconds))
        self.recover_seconds = max(self.settle_seconds, float(recover_seconds))

    def update(self, target, now=None, urgent=False):
        now = time.time() if now is None else now
        target = target if target in self.ORDER else "STABLE"
        cur_i, tar_i = self.ORDER.index(self.current), self.ORDER.index(target)
        if target == self.current:
            self.pending, self.pending_at = target, now
            return self.current, False
        if urgent or target == "CRITICAL":
            self.current = target
            self.pending, self.pending_at, self.changed_at = target, now, now
            return self.current, True
        if target != self.pending:
            self.pending, self.pending_at = target, now
            return self.current, False
        wait = self.settle_seconds if tar_i > cur_i else self.recover_seconds
        if now - self.pending_at < wait:
            return self.current, False
        # Recover in single steps so a one-off quiet poll cannot jump HOT->STABLE.
        if tar_i < cur_i:
            target = self.ORDER[cur_i - 1]
        self.current = target
        self.pending, self.pending_at, self.changed_at = target, now, now
        return self.current, True


# =====================================================================
# Widget
# =====================================================================
# =====================================================================
# Aksesoris pet (topi, kacamata, kumis, dasi, sayap, ...)
# Tiap pet punya titik jangkar (satuan pet 48 x 44) supaya aksesoris
# pas di kepala / mata / mulut / leher masing-masing pet:
#   hx, by, hw = tengah, garis dasar topi, setengah lebar topi
#   ty         = puncak kepala asli   ear = (x kiri, x kanan, y) telinga
#   nk, nw     = titik & lebar leher  bk = titik punggung (sayap/jubah)
# ---------------------------------------------------------------------
ACC_ANCHOR = {
    "nova": dict(hx=23.6, by=5.0, hw=10.5, ty=2.8, ear=(7.3, 40.0, 18.0),
                  nk=(23.6, 31.0), nw=7.0, bk=(24.0, 31.0)),
    "obi": dict(hx=24.0, by=9.0, hw=11.5, ty=5.8, ear=(7.0, 41.0, 22.8),
                   nk=(24.0, 35.0), nw=9.0, bk=(24.0, 30.0)),
    "piko": dict(hx=24.0, by=8.0, hw=12.0, ty=3.4, ear=(5.6, 42.4, 22.6),
                    nk=(24.0, 37.0), nw=9.0, bk=(24.0, 30.0)),
    "kubo": dict(hx=23.5, by=10.0, hw=11.0, ty=7.0, ear=(5.5, 41.0, 25.0),
                   nk=(18.5, 38.4), nw=8.0, bk=(23.5, 30.0)),
    "zuzu": dict(hx=24.0, by=7.0, hw=8.5, ty=3.8,
                        ear=(11.6, 36.4, 16.5), nk=(24.0, 26.5), nw=8.0,
                        bk=(24.0, 26.0)),
    # Robo: kepala kotak membulat (atas datar di y=9, lebar 6..42)
    "robo": dict(hx=24.0, by=11.0, hw=10.4, ty=9.0, ear=(5.2, 42.8, 21.0),
                 nk=(24.0, 33.2), nw=7.5, bk=(24.0, 35.0)),
    "claude": dict(hx=24.0, by=9.6, hw=10.2, ty=8.0, ear=(7.0, 41.0, 21.0),
                   nk=(24.0, 34.6), nw=7.0, bk=(24.0, 33.0)),
    "chatgpt": dict(hx=24.0, by=7.6, hw=10.2, ty=6.0, ear=(4.4, 43.6, 21.5),
                    nk=(24.0, 34.2), nw=7.0, bk=(24.0, 33.0)),
    "antigravity": dict(hx=24.0, by=6.2, hw=9.6, ty=4.5, ear=(6.4, 41.6, 21.0),
                        nk=(24.0, 35.0), nw=6.5, bk=(24.0, 33.0)),
    "cursor": dict(hx=24.0, by=10.4, hw=10.2, ty=9.0, ear=(6.0, 42.0, 21.5),
                   nk=(24.0, 33.4), nw=7.0, bk=(24.0, 34.5)),
    "codex": dict(hx=24.0, by=8.2, hw=9.8, ty=6.4, ear=(6.0, 42.0, 22.0),
                  nk=(24.0, 35.0), nw=7.0, bk=(24.0, 34.0)),
}
# topi bawaan Obi (kuning) disembunyikan bila user memilih topi lain
# antena Robo juga disembunyikan bila memakai topi (tidak tembus topi)
HAT_KEYS = {"obi": ("H", "h", "Hh"), "robo": ("AN", "AL"),
            "claude": ("SP",), "chatgpt": ("DT",), "cursor": ("AR",)}

ACC_SLOTS = [
    ("hat", "Topi", [
        ("cap", "Topi baseball"), ("tophat", "Topi tinggi"),
        ("santa", "Topi Santa"), ("wizard", "Topi penyihir"),
        ("party", "Topi ulang tahun"), ("crown", "Mahkota"),
        ("beanie", "Kupluk"), ("cowboy", "Topi koboi"),
        ("chef", "Topi koki"), ("propeller", "Topi baling-baling"),
        ("grad", "Topi wisuda"), ("bunny", "Kuping kelinci"),
        ("cat", "Kuping kucing"), ("horns", "Tanduk setan"),
        ("halo", "Halo malaikat"), ("flower", "Mahkota bunga"),
        ("cybercap", "Topi cyber")]),
    ("eyes", "Kacamata", [
        ("round", "Kacamata bulat"), ("sun", "Kacamata hitam"),
        ("nerd", "Kacamata kotak"), ("heart", "Kacamata hati"),
        ("star", "Kacamata bintang"), ("d3", "Kacamata 3D"),
        ("monocle", "Monokel"), ("patch", "Penutup mata bajak laut"),
        ("ar", "Visor AR")]),
    ("face", "Wajah", [
        ("mustache", "Kumis"), ("handle", "Kumis melengkung"),
        ("beard", "Jenggot"), ("whisk", "Kumis kucing"),
        ("mask", "Masker"), ("clown", "Hidung badut"),
        ("plaster", "Plester"), ("freckle", "Bintik-bintik")]),
    ("neck", "Leher", [
        ("bow", "Dasi kupu-kupu"), ("tie", "Dasi"), ("scarf", "Syal"),
        ("chain", "Kalung emas"), ("bandana", "Bandana"),
        ("bell", "Kalung lonceng")]),
    ("back", "Punggung", [
        ("cape", "Jubah"), ("wings", "Sayap malaikat"),
        ("bat", "Sayap kelelawar"), ("jetpack", "Jetpack mini")]),
    ("other", "Lainnya", [
        ("phones", "Headphone"), ("earflower", "Bunga di telinga"),
        ("ribbon", "Pita"), ("sparkle", "Kilau bintang"),
        ("badge", "Lencana AI")]),
]
ACC_VALID = {k: {i for i, _l in items} | {"none"} for k, _t, items in ACC_SLOTS}


def clean_acc(raw):
    """Buang slot/aksesoris yang tak dikenal dari data tersimpan."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for pet, sel in raw.items():
        if not isinstance(sel, dict):
            continue
        ok = {k: v for k, v in sel.items()
              if k in ACC_VALID and v in ACC_VALID[k]}
        if ok:
            out[str(pet).lower()] = ok
    return out


class AccPainter:
    """Menggambar aksesoris di canvas memakai satuan pet."""

    def __init__(self, c, ox, oy, u, A, face, colors, edge, dark_face, t):
        self.c, self.ox, self.oy, self.u = c, ox, oy, u
        self.A, self.f, self.col = A, face, colors
        self.edge, self.t = edge, t
        self.ow = max(1, round(1.5 * u))
        # warna bingkai kacamata: gelap di kulit terang, terang di visor gelap
        self.fr = "#F4F1FF" if dark_face else "#1B1620"
        self.hx, self.by = A["hx"], A["by"]
        self.s = A["hw"] / 10.0

    # ---- primitif (satuan pet) ----
    def X(self, v):
        return self.ox + v * self.u

    def Y(self, v):
        return self.oy + v * self.u

    def _flat(self, pts):
        out = []
        for x, y in pts:
            out += [self.X(x), self.Y(y)]
        return out

    def poly(self, pts, fill, out=None, w=None, smooth=False):
        out = self.edge if out is None else out
        w = self.ow if w is None else w
        self.c.create_polygon(*self._flat(pts), fill=fill, outline=out,
                              width=w, joinstyle="round", smooth=smooth,
                              tags="pet")

    def oval(self, cx, cy, rx, ry, fill, out=None, w=None):
        out = self.edge if out is None else out
        w = self.ow if w is None else w
        if not out:
            w = 0
        self.c.create_oval(self.X(cx - rx), self.Y(cy - ry), self.X(cx + rx),
                           self.Y(cy + ry), fill=fill, outline=out, width=w,
                           tags="pet")

    def line(self, pts, color, w=1.5, smooth=False):
        self.c.create_line(*self._flat(pts), fill=color, smooth=smooth,
                           width=max(1, round(w * self.u)), capstyle="round",
                           joinstyle="round", tags="pet")

    def star(self, cx, cy, ro, fill, out=None, w=None, ri=None):
        ri = ro * 0.46 if ri is None else ri
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = ro if i % 2 == 0 else ri
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.poly(pts, fill, out, w)

    def heart(self, cx, cy, r, fill, out=None, w=None):
        pts = [(0, 0.95), (-0.95, 0.0), (-1.0, -0.6), (-0.5, -1.0),
               (0, -0.55), (0.5, -1.0), (1.0, -0.6), (0.95, 0.0)]
        self.poly([(cx + x * r, cy + y * r) for x, y in pts], fill, out, w,
                  smooth=True)

    def rrect(self, cx, cy, hw, hh, fill, out=None, w=None):
        k = min(hw, hh) * 0.55
        pts = [(cx - hw + k, cy - hh), (cx + hw - k, cy - hh),
               (cx + hw, cy - hh + k), (cx + hw, cy + hh - k),
               (cx + hw - k, cy + hh), (cx - hw + k, cy + hh),
               (cx - hw, cy + hh - k), (cx - hw, cy - hh + k)]
        self.poly(pts, fill, out, w, smooth=False)

    # ---- relatif terhadap kepala (skala mengikuti lebar kepala) ----
    def r(self, pts):
        return [(self.hx + dx * self.s, self.by + dy * self.s)
                for dx, dy in pts]

    def ro(self, dx, dy, rx, ry, fill, out=None, w=None):
        self.oval(self.hx + dx * self.s, self.by + dy * self.s,
                  rx * self.s, ry * self.s, fill, out, w)

    # ==== TOPI ====
    def h_cap(self):
        self.poly(self.r([(-9, .5), (-9.5, -5), (-6, -9.5), (0, -11),
                          (6, -9.5), (9.5, -5), (9, .5)]), "#E5484D",
                  smooth=True)
        self.ro(0, 1, 12, 2.3, "#B8333A")
        self.ro(0, -11, 1.3, 1.3, "#B8333A")
        self.ro(-3.5, -7, 2.6, 1.1, "#F27A7E", "")

    def h_tophat(self):
        self.poly(self.r([(-7, 0), (-7, -13), (7, -13), (7, 0)]), "#23202B")
        self.ro(0, -13, 7, 2, "#3A3646")
        self.poly(self.r([(-7, -4.5), (7, -4.5), (7, -1.8), (-7, -1.8)]),
                  "#E5484D", "")
        self.ro(0, .5, 12.5, 2.4, "#23202B")

    def h_santa(self):
        self.poly(self.r([(-10, 0), (-8.5, -7), (-3, -12), (4, -14),
                          (10, -11), (13, -6), (14.5, -2.5), (11, -3.5),
                          (10, 0)]), "#E5484D", smooth=True)
        self.ro(0, 0, 11, 2.5, "#FFFFFF")
        self.ro(14.5, -2, 2.6, 2.6, "#FFFFFF")

    def h_wizard(self):
        self.poly(self.r([(-11, 0), (-6, -8), (-1, -17), (3, -21),
                          (4.5, -15), (8, -7), (11, 0)]), "#6B4FD0")
        self.ro(0, .6, 13.5, 2.5, "#4F38A8")
        self.poly(self.r([(-9.5, -2.2), (9.5, -2.2), (9.3, -0.2),
                          (-9.3, -0.2)]), "#F7C948", "")
        self.star(self.hx - 1 * self.s, self.by - 8 * self.s, 2.4 * self.s,
                  "#FFE27A", "")

    def h_party(self):
        self.poly(self.r([(-7, 0), (0, -17), (7, 0)]), "#FF6FA8")
        self.line(self.r([(-4.2, -5), (4.2, -5)]), "#FFE27A", 1.4)
        self.line(self.r([(-2.2, -10), (2.2, -10)]), "#7FD0FF", 1.4)
        self.ro(0, -17.3, 2.2, 2.2, "#FFE27A")

    def h_crown(self):
        self.poly(self.r([(-8, 0), (-9.5, -10), (-4.5, -5.5), (0, -12),
                          (4.5, -5.5), (9.5, -10), (8, 0)]), "#F7C948")
        self.ro(0, -3, 1.4, 1.4, "#E5484D", "")
        self.ro(-4.8, -2.6, 1.0, 1.0, "#4FA3FF", "")
        self.ro(4.8, -2.6, 1.0, 1.0, "#4FD1A5", "")

    def h_beanie(self):
        self.poly(self.r([(-10, 0), (-10, -5), (-6, -10), (0, -12),
                          (6, -10), (10, -5), (10, 0)]), "#3E78E0",
                  smooth=True)
        self.poly(self.r([(-10.5, -3.8), (10.5, -3.8), (10.5, .8),
                          (-10.5, .8)]), "#2E5CB5")
        self.ro(0, -13, 3, 3, "#FFFFFF")

    def h_cowboy(self):
        self.poly(self.r([(-7, 0), (-7.5, -8), (-3.5, -9.5), (0, -7),
                          (3.5, -9.5), (7.5, -8), (7, 0)]), "#B5753C",
                  smooth=True)
        self.poly(self.r([(-7.2, -3.2), (7.2, -3.2), (7.2, -.8),
                          (-7.2, -.8)]), "#6B3F1D", "")
        self.poly(self.r([(-16, -4), (-11, 1), (0, 2.8), (11, 1), (16, -4),
                          (12, -.4), (0, .8), (-12, -.4)]), "#8C5527",
                  smooth=True)

    def h_chef(self):
        for dx, dy, r in ((-5.2, -9, 5), (5.2, -9, 5), (0, -12.5, 5.6)):
            self.ro(dx, dy, r, r, "#FFFFFF")
        self.poly(self.r([(-7, -6), (7, -6), (7, 0), (-7, 0)]), "#FFFFFF",
                  "")
        self.line(self.r([(-7, 0), (7, 0)]), self.edge, 1.5)

    def h_propeller(self):
        self.poly(self.r([(-8, 0), (-8, -3), (-4, -7), (0, -8), (4, -7),
                          (8, -3), (8, 0)]), "#4FA3FF", smooth=True)
        self.poly(self.r([(-8, -3.4), (8, -3.4), (8, 0), (-8, 0)]), "#E5484D",
                  "")
        self.line(self.r([(0, -8), (0, -11)]), self.edge, 1.4)
        sp = abs(math.cos(self.t * 9))
        self.ro(0, -11.5, 9 * max(0.12, sp), 1.2, "#F7C948")
        self.ro(0, -11.5, 1.2, 1.2, self.edge, "")

    def h_grad(self):
        self.poly(self.r([(-7, -4), (-7, 0), (0, 1.5), (7, 0), (7, -4)]),
                  "#2A2733")
        self.poly(self.r([(-13, -5.5), (0, -10), (13, -5.5), (0, -1.5)]),
                  "#1E1B26")
        self.line(self.r([(11, -5.8), (11.5, 0)]), "#F7C948", 1.2)
        self.ro(11.6, .8, 1.1, 1.8, "#F7C948", "")

    def h_bunny(self):
        for sg in (-1, 1):
            self.ro(sg * 4.8, -13, 3.0, 8.5, "#F6F0F2")
            self.ro(sg * 4.8, -12.5, 1.5, 6.0, "#FFB3C7", "")

    def h_cat(self):
        for sg in (-1, 1):
            self.poly(self.r([(sg * 9.5, .5), (sg * 9.5, -10),
                              (sg * 1.5, -2.5)]), "#F2A65A")
            self.poly(self.r([(sg * 8.2, -1), (sg * 8.2, -7),
                              (sg * 3.6, -2.5)]), "#FFB3C7", "")

    def h_horns(self):
        for sg in (-1, 1):
            self.poly(self.r([(sg * 9, 0), (sg * 11, -7), (sg * 8, -13),
                              (sg * 4.5, -5), (sg * 4, -1.5)]), "#E5484D",
                      smooth=False)

    def h_halo(self):
        bob = math.sin(self.t * 3) * 0.8
        self.oval(self.hx, self.by - 7 * self.s + bob, 8 * self.s,
                  2.4 * self.s, "", "#F7C948", max(2, round(2.3 * self.u)))

    def h_flower(self):
        cols = ("#FF7AA2", "#FFE27A", "#FFFFFF", "#FF9A7A", "#B58CFF")
        for i in range(5):
            a = math.radians(-72 + i * 36)
            dx, dy = 10.2 * math.sin(a), -2.6 - 5.5 * math.cos(a) + 5.2
            self.ro(dx, dy - 2.4, 2.6, 2.6, cols[i])
            self.ro(dx, dy - 2.4, 1.0, 1.0, "#F7C948" if i != 1 else "#E5484D",
                    "")

    def h_cybercap(self):
        """Topi panel datar dengan garis cahaya; cocok untuk Robo/Codex."""
        self.poly(self.r([(-10, .4), (-9, -4.5), (-5, -8.5), (6, -8.5),
                          (10, -4.0), (10, .4)]), "#253552", smooth=True)
        self.poly(self.r([(-10.5, -1.0), (10.5, -1.0), (9.5, 1.4),
                          (-9.5, 1.4)]), "#172238", "")
        self.line(self.r([(-6.5, -4.0), (5.5, -4.0)]), "#7DF9FF", 1.2)
        self.ro(7.2, -4.0, 1.1, 1.1, "#FF6FD8", "")

    # ==== KACAMATA ====
    def _eyes(self):
        (x1, y1), (x2, y2) = self.f["eyes"]
        rx, ry = self.f["er"]
        return x1, y1, x2, y2, max(rx, ry) + 1.9

    def _temples(self, x1, y1, x2, y2, r, color):
        self.line([(x1 - r, y1 - .4), (x1 - r - 3.5, y1 - 1.6)], color, 1.4)
        self.line([(x2 + r, y2 - .4), (x2 + r + 3.5, y2 - 1.6)], color, 1.4)

    def e_round(self):
        x1, y1, x2, y2, r = self._eyes()
        self.line([(x1 + r, y1 - .6), (x2 - r, y2 - .6)], self.fr, 1.4)
        for x, y in ((x1, y1), (x2, y2)):
            self.oval(x, y, r, r, "", self.fr, max(2, round(1.6 * self.u)))
        self._temples(x1, y1, x2, y2, r, self.fr)

    def e_nerd(self):
        x1, y1, x2, y2, r = self._eyes()
        self.line([(x1 + r, y1 - 1), (x2 - r, y2 - 1)], self.fr, 1.5)
        for x, y in ((x1, y1), (x2, y2)):
            self.rrect(x, y, r, r * .85, "", self.fr, max(2, round(1.9 * self.u)))
        self._temples(x1, y1, x2, y2, r, self.fr)
        self.line([(x1 + r * .2, y1 + r * .5), (x1 + r * .5, y1 + r * .8)],
                  "#FFFFFF", 1.0)

    def e_sun(self):
        x1, y1, x2, y2, r = self._eyes()
        r += .5
        self.line([(x1 + r, y1 - .8), (x2 - r, y2 - .8)], "#14121A", 1.8)
        for x, y in ((x1, y1), (x2, y2)):
            self.rrect(x, y, r, r * .8, "#14121A", self.fr, max(1, round(1.1 * self.u)))
            self.line([(x - r * .55, y - r * .35), (x - r * .1, y - r * .6)],
                      "#8A86A0", 1.1)
        self._temples(x1, y1, x2, y2, r, "#14121A")

    def e_heart(self):
        x1, y1, x2, y2, r = self._eyes()
        r += .9
        self.line([(x1 + r * .6, y1 - .6), (x2 - r * .6, y2 - .6)], self.fr, 1.3)
        for x, y in ((x1, y1), (x2, y2)):
            self.heart(x, y + .3, r, "#FF5C8A")
            self.oval(x - r * .45, y - r * .4, r * .22, r * .14, "#FFD3E0", "")

    def e_star(self):
        x1, y1, x2, y2, r = self._eyes()
        r += 1.0
        self.line([(x1 + r * .5, y1), (x2 - r * .5, y2)], self.fr, 1.3)
        for x, y in ((x1, y1), (x2, y2)):
            self.star(x, y + .2, r * 1.15, "#FFD84A")

    def e_d3(self):
        x1, y1, x2, y2, r = self._eyes()
        self.line([(x1 + r, y1 - .6), (x2 - r, y2 - .6)], "#FFFFFF", 1.5)
        self.rrect(x1, y1, r, r * .85, "#FF4D5E", "#FFFFFF",
                   max(1, round(1.4 * self.u)))
        self.rrect(x2, y2, r, r * .85, "#3FC8FF", "#FFFFFF",
                   max(1, round(1.4 * self.u)))
        self._temples(x1, y1, x2, y2, r, "#FFFFFF")

    def e_monocle(self):
        x1, y1, x2, y2, r = self._eyes()
        self.oval(x2, y2, r + .4, r + .4, "", "#F7C948",
                  max(2, round(1.7 * self.u)))
        self.line([(x2 + r * .6, y2 + r), (x2 + 3.5, y2 + 8),
                   (x2 + 1.5, y2 + 15)], "#F7C948", 1.0, True)

    def e_patch(self):
        x1, y1, x2, y2, r = self._eyes()
        self.line([(x1 - r - 3, y1 - 3), (x1, y1 - 1), (x2 + r + 3, y2 - 5)],
                  "#14121A", 1.3)
        self.oval(x1, y1 + .2, r, r * .9, "#14121A", self.fr,
                  max(1, round(1.1 * self.u)))

    def e_ar(self):
        """Dua lensa transparan-stilis dengan konektor neon."""
        x1, y1, x2, y2, r = self._eyes()
        r += .65
        col = "#7DF9FF" if self.fr.startswith("#F") else "#25344F"
        self.line([(x1 + r, y1 - .7), (x2 - r, y2 - .7)], col, 1.45)
        for x, y in ((x1, y1), (x2, y2)):
            self.rrect(x, y, r, r * .82, "", col, max(2, round(1.45 * self.u)))
            self.line([(x - r * .55, y + r * .15), (x + r * .48, y + r * .15)],
                      "#FF6FD8", .8)
        self._temples(x1, y1, x2, y2, r, col)

    # ==== WAJAH ====
    def _hair(self, dark_col):
        """Warna kumis: dibuat lebih terang bila latar wajah gelap (layar LED)."""
        if self.fr.startswith("#F"):
            return "#D9A066"
        return dark_col

    def f_mustache(self):
        mx, my = self.f["mouth"]
        k = self.f["mw"] * .5
        yy = my - 2.1
        for sg in (-1, 1):
            self.poly([(mx, yy), (mx + sg * .5 * k, yy - .55 * k),
                       (mx + sg * 1.3 * k, yy - .15 * k),
                       (mx + sg * 1.75 * k, yy + .7 * k),
                       (mx + sg * 1.15 * k, yy + .55 * k),
                       (mx + sg * .55 * k, yy + .5 * k),
                       (mx, yy + .75 * k)], self._hair("#4A2A18"),
                      out=self._hair("") or None, smooth=True)

    def f_handle(self):
        mx, my = self.f["mouth"]
        k = self.f["mw"] * .5
        yy = my - 2.0
        for sg in (-1, 1):
            self.poly([(mx, yy), (mx + sg * .6 * k, yy - .5 * k),
                       (mx + sg * 1.5 * k, yy - .1 * k),
                       (mx + sg * 2.2 * k, yy - .5 * k),
                       (mx + sg * 2.5 * k, yy - 1.2 * k),
                       (mx + sg * 2.05 * k, yy - .8 * k),
                       (mx + sg * 1.5 * k, yy + .55 * k),
                       (mx + sg * .6 * k, yy + .55 * k),
                       (mx, yy + .75 * k)], self._hair("#2B1A12"),
                      out=self._hair("") or None, smooth=True)

    def f_beard(self):
        mx, my = self.f["mouth"]
        w = self.f["mw"]
        self.poly([(mx - w * .95, my + .6), (mx - w * .75, my + 4.5),
                   (mx, my + 8), (mx + w * .75, my + 4.5),
                   (mx + w * .95, my + .6), (mx + w * .4, my + 2.2),
                   (mx, my + 1.4), (mx - w * .4, my + 2.2)], "#5A3A24",
                  smooth=True)

    def f_whisk(self):
        mx, my = self.f["mouth"]
        w = self.f["mw"]
        col = "#2B2530" if lum(self.col[self.f["base"]]) > .45 else "#F1EFFF"
        for sg in (-1, 1):
            for dy in (-1.8, 0, 1.8):
                self.line([(mx + sg * (w * .5), my - 1.8 + dy * .3),
                           (mx + sg * (w * .5 + 5.5), my - 1.8 + dy * 1.5)],
                          col, 1.0)

    def f_mask(self):
        mx, my = self.f["mouth"]
        w = self.f["mw"] * 1.35
        self.line([(mx - w, my - 1), (mx - w - 3.8, my - 3.5)], "#E8F4FA", 1.0)
        self.line([(mx + w, my - 1), (mx + w + 3.8, my - 3.5)], "#E8F4FA", 1.0)
        self.poly([(mx - w, my - 3.4), (mx + w, my - 3.4), (mx + w + .6, my + 1),
                   (mx + w * .6, my + 4.6), (mx - w * .6, my + 4.6),
                   (mx - w - .6, my + 1)], "#CDEBF7", smooth=True)
        for dy in (-1.4, .6, 2.6):
            self.line([(mx - w * .7, my + dy), (mx + w * .7, my + dy)],
                      "#8CC4DD", 0.8)

    def f_clown(self):
        (x1, y1, _x2, _y2, _r) = self._eyes()
        mx, my = self.f["mouth"]
        ny = (y1 + my) / 2.0 + .3
        self.oval(mx, ny, 2.5, 2.5, "#F0443A")
        self.oval(mx - .8, ny - .8, .8, .6, "#FFB3AC", "")

    def f_plaster(self):
        (_x1, _y1, x2, y2, _r) = self._eyes()
        cx, cy = x2 + 3.2, y2 + 5.2
        a = math.radians(-35)
        ca, sa = math.cos(a), math.sin(a)
        pts = [(-4, -1.5), (4, -1.5), (4, 1.5), (-4, 1.5)]
        pts = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]
        self.poly(pts, "#F2D3A8")
        for x in (-1.2, 1.2):
            p0 = (cx + x * ca, cy + x * sa)
            self.oval(p0[0], p0[1], .35, .35, "#C99A66", "")

    def f_freckle(self):
        (x1, y1, x2, y2, _r) = self._eyes()
        for x, y, sg in ((x1, y1, -1), (x2, y2, 1)):
            for ddx, ddy in ((0.0, 4.6), (2.0, 5.6), (-1.6, 5.6)):
                self.oval(x + ddx * (-sg), y + ddy, .55, .55, "#B5603A", "")

    # ==== LEHER ====
    def n_bow(self):
        x, y = self.A["nk"]
        for sg in (-1, 1):
            self.poly([(x, y), (x + sg * 5.2, y - 2.6), (x + sg * 5.2, y + 2.6)],
                      "#E5484D")
        self.oval(x, y, 1.5, 1.7, "#B8333A")

    def n_tie(self):
        x, y = self.A["nk"]
        self.poly([(x - 1.4, y + 1), (x + 1.4, y + 1), (x + 2.6, y + 7),
                   (x, y + 9), (x - 2.6, y + 7)], "#3E78E0")
        self.poly([(x - 2, y - 1.4), (x + 2, y - 1.4), (x + 1.4, y + 1.2),
                   (x - 1.4, y + 1.2)], "#2E5CB5")

    def n_scarf(self):
        x, y = self.A["nk"]
        w = self.A["nw"]
        self.poly([(x + w * .35, y + .5), (x + w * .75, y + 9),
                   (x + w * .25, y + 10.5), (x - w * .05, y + 2)], "#E5484D")
        self.poly([(x - w, y - 1.6), (x + w, y - 1.6), (x + w, y + 2.4),
                   (x - w, y + 2.4)], "#E5484D", smooth=True)
        for i in (-.5, 0, .5):
            self.line([(x + i * w, y - 1.2), (x + i * w, y + 2.0)], "#FFD3D0",
                      1.0)

    def n_chain(self):
        x, y = self.A["nk"]
        w = self.A["nw"]
        self.line([(x - w * .9, y - 1.5), (x - w * .5, y + 2.6),
                   (x, y + 4.2), (x + w * .5, y + 2.6), (x + w * .9, y - 1.5)],
                  "#F7C948", 1.2, True)
        self.oval(x, y + 5.6, 1.8, 1.8, "#F7C948")

    def n_bandana(self):
        x, y = self.A["nk"]
        w = self.A["nw"]
        self.poly([(x - w * 1.05, y - 1.5), (x + w * 1.05, y - 1.5),
                   (x, y + 8.5)], "#E5484D")
        for dx, dy in ((-3, 1.2), (3, 1.2), (0, 4), (0, 0.3)):
            self.oval(x + dx, y + dy, .6, .6, "#FFFFFF", "")

    def n_bell(self):
        x, y = self.A["nk"]
        w = self.A["nw"]
        self.poly([(x - w, y - 1.2), (x + w, y - 1.2), (x + w, y + 1.2),
                   (x - w, y + 1.2)], "#E5484D", smooth=True)
        self.oval(x, y + 3.2, 2.2, 2.2, "#F7C948")
        self.oval(x, y + 3.8, .6, .6, self.edge, "")

    # ==== PUNGGUNG (digambar di belakang badan) ====
    def b_cape(self):
        x, y = self.A["bk"]
        sw = math.sin(self.t * 3) * 0.8
        self.poly([(x - 8, y - 3), (x + 8, y - 3), (x + 18 + sw, y + 12),
                   (x + 8, y + 14.5), (x, y + 12.5), (x - 8, y + 14.5),
                   (x - 18 - sw, y + 12)], "#C9302C", smooth=True)

    def b_wings(self):
        x, y = self.A["bk"]
        fl = math.sin(self.t * 5) * 2.2
        for sg in (-1, 1):
            self.poly([(x + sg * 6, y), (x + sg * 14, y - 9 + fl),
                       (x + sg * 22, y - 8 + fl * 1.3),
                       (x + sg * 21, y - 2 + fl), (x + sg * 23, y + 4 + fl * .6),
                       (x + sg * 16, y + 5), (x + sg * 8, y + 4)], "#FFFFFF",
                      smooth=True)

    def b_bat(self):
        x, y = self.A["bk"]
        fl = math.sin(self.t * 6) * 2.5
        for sg in (-1, 1):
            self.poly([(x + sg * 6, y - 2), (x + sg * 14, y - 12 + fl),
                       (x + sg * 22, y - 6 + fl), (x + sg * 18, y - 2 + fl * .6),
                       (x + sg * 20, y + 5), (x + sg * 14, y + 1),
                       (x + sg * 10, y + 6), (x + sg * 7, y + 2)], "#3B2A55")

    def b_jetpack(self):
        x, y = self.A["bk"]
        pulse = .55 + .45 * math.sin(self.t * 7)
        for sg in (-1, 1):
            self.rrect(x + sg * 7.3, y + 1.0, 3.5, 6.2, "#34445C")
            self.rrect(x + sg * 7.3, y + 1.3, 2.0, 4.3, "#8EA8C4", "")
            self.poly([(x + sg * 5.6, y + 6), (x + sg * 9.0, y + 6),
                       (x + sg * 7.3, y + 11 + pulse * 2)], "#7DF9FF", "")
        self.rrect(x, y + .5, 4.6, 4.5, "#1A2230")
        self.oval(x, y + .3, 1.1, 1.1, "#FF6FD8", "")

    # ==== LAINNYA ====
    def o_phones(self):
        xl, xr, ey = self.A["ear"]
        ty = self.A["ty"]
        cx = (xl + xr) / 2.0
        self.line([(xl - .2, ey - 1), (xl - .2, ty + 4), (cx, ty - 2.2),
                   (xr + .2, ty + 4), (xr + .2, ey - 1)], "#2B2733", 2.0, True)
        for x in (xl, xr):
            self.rrect(x, ey, 2.7, 4.4, "#E5484D")

    def o_earflower(self):
        xl, xr, ey = self.A["ear"]
        x, y = xr - 1.2, ey - 5.0
        for i in range(5):
            a = math.radians(i * 72 - 90)
            self.oval(x + 2.1 * math.cos(a), y + 2.1 * math.sin(a), 1.6, 1.6,
                      "#FF7AA2", "")
        self.oval(x, y, 1.4, 1.4, "#FFE27A", self.edge, 1)

    def o_ribbon(self):
        x = self.hx + self.A["hw"] * 0.85
        y = self.by + 1.0
        for sg in (-1, 1):
            self.poly([(x, y), (x + sg * 5.5, y - 3.2), (x + sg * 5.5, y + 3.2)],
                      "#FF6FA8")
        self.oval(x, y, 1.4, 1.6, "#D94A85")

    def o_sparkle(self):
        for k, (dx, dy, r) in enumerate(((-3.5, 5.5, 2.6), (4.0, -2.5, 1.8))):
            ph = 0.65 + 0.35 * math.sin(self.t * 4 + k * 2)
            self.star(self.A["ear"][1] + dx + 3, self.A["ty"] + 4 + dy,
                      r * ph, "#FFE27A", "")

    def o_badge(self):
        x, y = self.A["nk"]
        self.oval(x + self.A["nw"] * .55, y + 2.8, 2.5, 2.5, "#2E5CB5")
        self.star(x + self.A["nw"] * .55, y + 2.8, 1.5, "#7DF9FF", "")


def draw_accessories(layer, c, ox, oy, u, pet, sel, edge, t):
    """layer: 'back' (sebelum badan) atau 'front' (setelah wajah)."""
    name = pet["name"].lower()
    A = ACC_ANCHOR.get(name)
    if not A or not sel:
        return
    f, col = pet["face"], pet["colors"]
    dark = lum(col[f["base"]]) < 0.4
    p = AccPainter(c, ox, oy, u, A, f, col, edge, dark, t)
    order = ("back",) if layer == "back" else (
        "neck", "other", "face", "eyes", "hat")
    pre = {"back": "b_", "neck": "n_", "other": "o_", "face": "f_",
           "eyes": "e_", "hat": "h_"}
    for slot in order:
        v = sel.get(slot)
        if not v or v == "none":
            continue
        fn = getattr(p, pre[slot] + v, None)
        if fn:
            fn()


WEATHER_PRESETS = {
    "sand": {"kind": "sand", "n": 28,
             "cols": ["#D9BE8A", "#E8D5A8", "#A8855A"]},
    "snow": {"kind": "snow", "n": 30,
             "cols": ["#FFFFFF", "#DDE3F7", "#B9C2E8"]},
    "rain": {"kind": "rain", "n": 26,
             "cols": ["#8FA3D6", "#6C84C0", "#B5C4E8"]},
    "bubble": {"kind": "bubble", "n": 12,
               "cols": ["#7FD0FF", "#A9C0F5", "#CFE0FF"]},
    "stars": {"kind": "stars", "n": 18,
              "cols": ["#FFE27A", "#9BE3FF", "#FFFFFF"]},
    "petal": {"kind": "petal", "n": 18,
              "cols": ["#FFB3C7", "#FF8FB0", "#FFD6E2"]},
    "leaf": {"kind": "petal", "n": 16,
             "cols": ["#E8A33D", "#C9702A", "#9CBF4A", "#D9822B"]},
    "firefly": {"kind": "firefly", "n": 14,
                "cols": ["#FFF3A0", "#C8FF8A", "#FFE27A"]},
    "meteor": {"kind": "meteor", "n": 11,
               "cols": ["#FFE27A", "#FF9E6D", "#9BE3FF"]},
}
WEATHER_MENU = [("auto", "Otomatis (ikut tema pet)"), ("sand", "Angin pasir"),
                ("snow", "Salju"), ("rain", "Hujan"),
                ("bubble", "Gelembung"), ("stars", "Bintang berkedip"),
                ("petal", "Kelopak sakura"), ("leaf", "Daun gugur"),
                ("firefly", "Kunang-kunang"), ("meteor", "Hujan meteor"),
                ("none", "Tanpa cuaca")]
DECOR_MENU = [("none", "Tanpa dekorasi"),
              ("lights", "Lampu natal (warna-warni)"),
              ("warm", "Lampu kuning hangat"),
              ("garland", "Untaian cemara + lampu"), ("neon", "Lampu neon"),
              ("lanterns", "Lampion"), ("bunting", "Bendera segitiga"),
              ("stars", "Bintang gantung"), ("hologram", "Hologram data"),
              ("orbit", "Orbit kosmik")]

THEME_MENU = [("robo", "Perkotaan / Robo"), ("claude", "Senja / Claude"),
              ("chatgpt", "Laguna / ChatGPT"),
              ("antigravity", "Gravitasi Nol / Antigravity"),
              ("cursor", "Editor / Cursor"), ("codex", "Awan Kode / Codex"),
              ("obi", "Gurun"), ("nova", "Salju"), ("kubo", "Batu"),
              ("zuzu", "Luar Angkasa")]
BULB_COLS = ["#FF5C5C", "#FFD84A", "#5CE08A", "#5CC8FF", "#FF8AD1"]


class PetMonitor:
    def __init__(self, root, cfg):
        self.root, self.cfg = root, cfg
        self.demo = bool(cfg.get("demo", False))
        self.interval = max(1, int(cfg.get("poll_interval_seconds", 5)))
        self.timeout = max(1, int(cfg.get("request_timeout_seconds", 3)))
        self.combo_name = cfg.get("combo_name", "*")
        self.max_rows = max(3, int(cfg.get("max_model_rows", 10)))
        self.collapsed_rows = max(2, int(cfg.get("collapsed_rows", 4)))
        self.bar_style = str(cfg.get("bar_style", "segmented")).lower()
        self.strict_provider = bool(cfg.get("strict_provider", True))
        self.theme_follow = bool(cfg.get("theme_follows_pet", True))
        self.fx_on = bool(cfg.get("weather_effects", True))
        self._fx, self._fx_splash, self._shoot = [], [], None
        self._fx_job = None
        self._sc, self._sc_job = [], None
        self._fx_t = self._sc_t = time.time()
        self._fx_m = self._sc_dt = 1.0
        self.expanded_breakdown = True
        # animasi dropdown: _prog 0 = tertutup .. 1 = terbuka penuh
        self.anim_ms = max(0, int(cfg.get("animation_ms", 240)))
        self._prog, self._full_h = 0.0, 0
        self._anim, self._anim_job = None, None
        self.alert_cfg = {**DEFAULT_ALERTS, **(cfg.get("alerts") or {})}
        self.alert_levels = sorted(
            {float(x) for x in self.alert_cfg.get("levels", [])},
            reverse=True)
        self.aliases = {**DEFAULT_ALIASES,
                        **{str(k).lower(): str(v).lower() for k, v in
                           (cfg.get("provider_aliases") or {}).items()}}
        self.budgets = {str(k).strip().lower(): float(v)
                        for k, v in (cfg.get("model_budgets") or {}).items()}
        self.combo_budget = {**DEFAULT_BUDGET,
                             **{str(k): float(v) for k, v in
                                (cfg.get("combo_budget") or {}).items()}}
        # batas token = combo_budget per periode, atau angka yang diketik
        # user (klik caption "batas ..."). 9router tak punya limit.
        self.manual_budget = {}
        # batas otomatis: ikut naik mengikuti pemakaian (lihat _auto_cap)
        self.auto_budget = bool(cfg.get("auto_budget", True))
        self.auto_headroom = max(1.0, float(cfg.get("auto_headroom", 25)))
        self.auto_floor = max(0.0, float(cfg.get("auto_floor", 1e6)))
        # _auto_peak = pemakaian tertinggi per periode; _auto_cap_seen =
        # batas terakhir yg sudah ditulis (batas tak pernah turun);
        # _auto_seen = kapan terakhir dipakai, buat buang yang basi.
        self._auto_peak = {str(k): float(v) for k, v in
                           (cfg.get("auto_peak") or {}).items() if float(v) > 0}
        self._auto_cap_seen = {str(k): float(v) for k, v in
                               (cfg.get("auto_cap_seen") or {}).items()
                               if float(v) > 0}
        self._auto_seen = {}
        th = cfg.get("thresholds", {})
        self.warn_mid = float(th.get("warn_mid", 50))
        self.warn_low = float(th.get("warn_low", 20))
        self.hot_ratio = float(th.get("hot_ratio", 0.5))
        self.pace_window = cfg.get("pace_window_seconds", 600)
        self.tabs = [("24H", "24h"), ("7D", "7d"), ("TODAY", "today"),
                     ("ALL", "all")]
        # nilai ?period= yang dikirim ke 9router (bisa diubah lewat config)
        self.period_api = {"24h": "24h", "7d": "7d", "today": "today",
                           "all": "all",
                           **{str(k): str(v) for k, v in
                              (cfg.get("period_api") or {}).items()}}
        self.tab_i, self.period = 0, "24h"
        self.models, self.usage = [], []
        # Daftar combo berubah jauh lebih jarang daripada statistik token.
        # Cache ini menghindari request /combos pada hampir setiap polling.
        try:
            self.combo_refresh = max(15.0, float(
                cfg.get("combo_refresh_seconds", 75)))
        except (TypeError, ValueError):
            self.combo_refresh = 75.0
        self._combo_cache, self._combo_cached_at = None, 0.0
        self._per = []
        self._other = {"tokens": 0.0, "requests": 0, "maybe": 0.0,
                       "prompt": 0.0, "cached": 0.0, "completion": 0.0}
        self.selected, self.last_ok, self.error = None, None, None
        self.expanded, self.fetching = False, False
        self.show_all, self.list_off = False, 0
        self.sort_tokens, self.pet_i = True, DEFAULT_PET
        self.metric = self._pick_metric(cfg.get("token_metric", "io"))
        self._have, self.reported, self._stale_drawn = False, None, False
        self._tot_parts = {"prompt": 0.0, "cached": 0.0, "completion": 0.0}
        self._pet_var = tk.IntVar(master=root, value=DEFAULT_PET)
        self._pet_imgs = []
        self.acc = {}                  # {pet: {slot: aksesoris}}
        self.weather, self.decor = "auto", "none"
        self.scene_theme = "robo"
        self._bulbs = []
        self.logged_out = False
        self.sim = DemoSim() if self.demo else None
        self.secure_store = SecureCredentialStore(CREDENTIAL_PATH)
        self._secure_migrated = migrate_legacy_credentials(cfg, self.secure_store)
        self.auth = AuthSession(cfg, self.timeout, self.secure_store)
        self.tracker = PaceTracker(self.pace_window)
        self.frame, self.tick_n, self.blink_on = 0, 0, False
        self._rst_items = []              # teks hitung mundur reset (per detik)
        self._period_anchor = {}          # awal jendela per periode (utk reset)
        self._label, self._low, self._job = "STABLE", False, None
        self.pet_x, self.hits, self._drag, self._resize = 0, [], None, None
        self._cfg_job, self._status_id, self._cursor = None, None, ""
        self._tick_job = None
        self._ptr, self._hov_key, self._hov_item = None, None, None
        # _ptr dipakai khusus untuk hover UI, sedangkan _eye_ptr selalu
        # menyimpan posisi pointer terakhir agar mata tetap melirik walau
        # kursor sudah keluar dari area canvas.
        self._eye_ptr, self._eye_job = None, None
        self._pet_eye_center = None
        self._emo, self._emo_t0, self._emo_until = None, 0.0, 0.0
        self._emo_last, self._emo_job, self._on_pet = None, None, False
        self._busy_until, self._busy_t0 = 0.0, 0.0
        self._running = 0            # jumlah request aktif di 9router
        qc = cfg.get("chatgpt_quota")
        self.qcfg = dict(qc) if isinstance(qc, dict) else {}
        try:
            self.q_poll = max(20, int(self.qcfg.get("poll_seconds", 60)))
        except (TypeError, ValueError):
            self.q_poll = 60
        cq = cfg.get("claude_quota")
        self.ccfg = dict(cq) if isinstance(cq, dict) else {}
        self._qd = {}                # kuota per layanan (claude/chatgpt/codex)
        self._ai_scan_at = 0.0
        self._gpt_n, self._gpt_path = 0, ""   # akun ChatGPT terdeteksi / dipilih
        self.q_i = 0                 # jendela kuota yang tampil di header
        self._demo_q = DemoQuota()
        self._ant_hidden = False
        self._blink_until, self._blink_job = 0.0, None
        self._look_q, self._look_t = (0.0, 0.0), 0.0
        # Nilai bar tampilan dianimasikan menuju data baru, bukan melompat.
        self._bar_values, self._bar_anim, self._bar_anim_job = {}, None, None
        self.view = "main"  # main | settings
        self.ai = {"active": None, "nine_pet": None, "accounts": {}}
        self.busy_secs = max(0, float(cfg.get("busy_seconds", 15)))
        self._fonts = {}
        global FONT_SCALE
        pick_fonts(root, cfg.get("font"))
        FONT_SCALE = clamp(float(cfg.get("font_scale", FONT_SCALE)), 0.6, 1.4)
        self.dpi = clamp(root.winfo_fpixels("1i") / 96.0, 1.0, 3.0)
        self.base_w = BASE_W * self.dpi
        self.min_w, self.max_w = int(MIN_W * self.dpi), int(MAX_W * self.dpi)
        self.W, self.k = int(self.base_w), 1.0
        self.hist = History(HIST_PATH)
        self._alert_lvl, self._alert_at, self._was_hot = {}, {}, False
        self.alert_msg, self.alert_until, self._alert_shown = "", 0.0, False
        self.flash_msg, self.flash_until = "", 0.0
        self.autostart = autostart_enabled()
        self.lock_position, self.always_on_top = False, True
        self._dialog_open = False  # dialog sementara matikan topmost
        self.stats_period, self.selected_provider = "24h", None
        self._hud = None
        self._speech, self._speech_until, self._speech_last = "", 0.0, 0.0
        self._idle_job, self._idle_action, self._idle_until, self._idle_t0 = None, None, 0.0, 0.0
        self._reaction, self._reaction_until, self._reaction_t0 = None, 0.0, 0.0
        self._event_at, self._last_total, self._err_streak = {}, None, 0
        self._router_was_offline, self._last_activity_at = False, time.time()
        self._mood = MoodController(
            settle_seconds=cfg.get("mood_settle_seconds", 8),
            recover_seconds=cfg.get("mood_recover_seconds", 20))
        self.mood_enabled = bool(cfg.get("mood_enabled", True))
        self._intel_init()

        r = root
        r.title("9Router Pet Monitor")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        self._load_pos()
        self._load_ai()
        self._ai_restore_gpt()
        self._fix_hidden_pet()
        self._sync_theme_to_pet()
        self._prog = 1.0 if self.expanded else 0.0
        apply_theme(self.scene_theme)
        style_tk(r)
        r.configure(bg=gap_color())
        try:                       # Windows: celah antar kartu tembus pandang
            r.attributes("-transparentcolor", KEY_COLOR)
        except tk.TclError:
            pass
        self.k = clamp(self.W / self.base_w, 0.75, 1.9)
        r.geometry("%dx%d" % (self.W, self.s(68)))
        self.c = tk.Canvas(r, bg=gap_color(), highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        self.c.bind("<ButtonPress-1>", self._press)
        self.c.bind("<B1-Motion>", self._move)
        self.c.bind("<ButtonRelease-1>", self._release)
        self.c.bind("<Double-Button-1>", self._double_click_header)
        self.c.bind("<Button-3>", self._context_menu)
        self.c.bind("<Motion>", self._hover)
        self.c.bind("<Leave>", self._leave)
        self.c.bind("<MouseWheel>", self._wheel)
        self.c.bind("<Button-4>", self._wheel)
        self.c.bind("<Button-5>", self._wheel)
        self.c.bind("<Configure>", self._on_cfg)
        r.bind_all("<KeyPress>", self._shortcut, add="+")
        r.bind("<FocusOut>", self._on_focus_out, add="+")
        try:
            r.attributes("-topmost", self.always_on_top)
        except tk.TclError:
            pass
        # Injecting this in memory keeps a migrated legacy config compatible
        # while no secret is written back to JSON.
        try:
            self.qcfg["_secure_access_token"] = self.secure_store.get("chatgpt") or ""
        except SecureStorageError:
            self.qcfg["_secure_access_token"] = ""
        self._fx_build()
        self.draw_all()
        self._blink_job = self.root.after(2200, self._blink_loop)
        self._eye_job = self.root.after(45, self._eye_track)
        self._tick()
        self._fx_step()
        self._sc_step()
        self._idle_job = self.root.after(random.randint(2800, 5200), self._idle_step)
        self._schedule_poll(80)

    # ---------- skala / font ----------
    def s(self, v):
        return int(round(v * self.k * self.dpi))

    def fz(self, size):
        return max(7, int(round(size * self.k * FONT_SCALE)))

    def ft(self, size, bold=False):
        """Tuple font Tk: ukuran lewat fz(); tebal = semibold bila tersedia."""
        sz = self.fz(size)
        if bold:
            return (FONT_SEMI, sz) if FONT_SEMI else (FONT, sz, "bold")
        return (FONT, sz)

    def _font(self, size, bold=False):
        key = (size, bold)
        f = self._fonts.get(key)
        if f is None:
            if bold and FONT_SEMI:
                f = tkfont.Font(family=FONT_SEMI, size=size, weight="normal")
            else:
                f = tkfont.Font(family=FONT, size=size,
                                weight="bold" if bold else "normal")
            self._fonts[key] = f
        return f

    def measure(self, text, size, bold=False):
        return self._font(self.fz(size), bold).measure(text)

    def fit(self, text, px, size, bold=False):
        """Potong teks sesuai lebar piksel nyata (bukan jumlah huruf)."""
        if px <= 0:
            return ""
        if self.measure(text, size, bold) <= px:
            return text
        while len(text) > 1 and self.measure(text + "..", size, bold) > px:
            text = text[:-1]
        return text + ".."

    # ---------- posisi / ukuran / mouse ----------
    def _load_pos(self):
        x, y = 100, 100
        p = _safe_json(POS_PATH, {"schema_version": STATE_SCHEMA_VERSION},
                       write_default=True)
        try:
            self.W = clamp(int(round(float(p.get("w", BASE_W)) * self.dpi)),
                           self.min_w, self.max_w)
            pv = p.get("pet")
            old = {"copilot": "robo"}      # Copilot dihapus -> Robo
            if isinstance(pv, str):
                pv = old.get(pv.lower(), pv)
            names = [pt["name"].lower() for pt in PETS]
            if isinstance(pv, str) and pv.lower() in names:
                self.pet_i = names.index(pv.lower())
            self.expanded = bool(p.get("expanded", False))
            self.acc = clean_acc({old.get(str(k).lower(), k): v for k, v in
                                  (p.get("acc") or {}).items()})
            if p.get("weather") in {k for k, _l in WEATHER_MENU}:
                self.weather = p["weather"]
            if p.get("decor") in {k for k, _l in DECOR_MENU}:
                self.decor = p["decor"]
            if p.get("scene_theme") in {k for k, _l in THEME_MENU}:
                self.scene_theme = p["scene_theme"]
            # Migrasi file lama: tema nyangkut di dalam "budgets"
            # (bug _save_pos lama) -> angkat ke tempatnya, lalu buang.
            _bud = p.get("budgets") or {}
            if not isinstance(_bud, dict):
                _bud = {}
            if self.scene_theme == "robo" and \
                    _bud.get("scene_theme") in {k for k, _l in THEME_MENU}:
                self.scene_theme = _bud["scene_theme"]
            if "theme_follow" in p:
                self.theme_follow = bool(p["theme_follow"])
            elif "theme_follow" in _bud:
                self.theme_follow = bool(_bud["theme_follow"])
            self.show_all = False         # selalu mulai ringkas (4 model)
            self.expanded_breakdown = bool(p.get("expanded_breakdown", True))
            self.sort_tokens = bool(p.get("sort", True))
            self.lock_position = bool(p.get("lock_position", False))
            self.always_on_top = bool(p.get("always_on_top", True))
            self.alert_cfg["enabled"] = bool(p.get(
                "notifications_enabled", self.alert_cfg.get("enabled", True)))
            if p.get("stats_period") in ("today", "24h", "7d", "30d", "all"):
                self.stats_period = p["stats_period"]
            if p.get("selected_provider") in {"9router"} | {
                    k for k, _l, _d in AI_PROVIDERS}:
                self.selected_provider = p["selected_provider"]
            if p.get("view") in ("main", "settings", "statistics", "account"):
                self.view = p["view"]
            self.selected = p.get("selected") or None
            self.metric = self._pick_metric(p.get("metric"))
            ti = int(p.get("tab", 0))
            if 0 <= ti < len(self.tabs):
                self.tab_i, self.period = ti, self.tabs[ti][1]
            for k2, v in (p.get("budgets") or {}).items():
                try:
                    if float(v) > 0 and str(k2) in self.combo_budget:
                        self.combo_budget[str(k2)] = float(v)
                except (ValueError, TypeError):
                    continue
            for k2, v in (p.get("manual_budgets") or {}).items():
                try:
                    if float(v) > 0:
                        self.manual_budget[str(k2)] = float(v)
                except (ValueError, TypeError):
                    continue
            # batas otomatis ikut nyimpen puncaknya, jadi restart tak
            # bikin batas jatuh balik ke config
            for src, dst in (("auto_peak", self._auto_peak),
                             ("auto_cap_seen", self._auto_cap_seen)):
                for k2, v in (p.get(src) or {}).items():
                    try:
                        if float(v) > 0:
                            dst[str(k2)] = float(v)
                    except (ValueError, TypeError):
                        continue
            x = max(0, min(int(p.get("x", 100)),
                           self.root.winfo_screenwidth() - 100))
            y = max(0, min(int(p.get("y", 100)),
                           self.root.winfo_screenheight() - 60))
        except (ValueError, TypeError):
            pass
        x, y = clamp_to_visible(x, y, self.W, 120)
        self.root.geometry("+%d+%d" % (x, y))

    # ---------- akun AI (ai_accounts.json, lokal saja) ----------
    def _load_ai(self):
        d = _safe_json(AI_PATH, {"schema_version": STATE_SCHEMA_VERSION,
                                  "accounts": {}}, write_default=True)
        acc = {}
        migrated = False
        known = {k: dp for k, _l, dp in AI_PROVIDERS}   # Copilot dll. dibuang
        fresh = d.get("pet_ver") != AI_PET_VER          # urutan pet berubah
        for k, v in (d.get("accounts") or {}).items():
            if isinstance(v, dict) and str(k) in known:
                try:
                    pet = known[str(k)] % len(PETS) if fresh \
                        else int(v.get("pet", 0)) % len(PETS)
                except (ValueError, TypeError):
                    pet = known[str(k)] % len(PETS)
                if v.get("via") == "auto":     # versi lama: tersambung sendiri
                    v = dict(v, connected=False, email="", via="")
                # ai_accounts.json v1 could contain a plaintext `token`.
                # Migrate it once, then only keep non-secret metadata here.
                legacy = str(v.get("token") or "")
                if legacy:
                    try:
                        self.secure_store.save(str(k), legacy)
                        migrated = True
                    except SecureStorageError:
                        pass
                acc[str(k)] = {"connected": bool(v.get("connected")),
                               "email": str(v.get("email") or ""),
                               "via": str(v.get("via") or ""),
                               "sel": str(v.get("sel") or ""),
                               "pet": pet,
                               "last_sync": float(v.get("last_sync") or 0),
                               "last_error": sanitize_log_message(
                                   str(v.get("last_error") or ""))[:120],
                               "credential_source": str(
                                   v.get("credential_source") or
                                   ("secure" if legacy else ""))}
        self.ai = {"active": None, "nine_pet": self.pet_i, "accounts": acc}
        try:
            np_ = int(d.get("nine_pet", self.pet_i))
        except (ValueError, TypeError):
            np_ = self.pet_i
        if 0 <= np_ < len(PETS):
            self.ai["nine_pet"] = np_
        a = d.get("active")
        if isinstance(a, str) and a in acc and acc[a]["connected"]:
            self.ai["active"] = a
            self.pet_i = acc[a]["pet"]
        if migrated:
            self._save_ai()

    def _ai_restore_gpt(self):
        """Pulihkan akun ChatGPT terpilih (tanpa menyambungkan apa pun)."""
        gacc = self._ai_acc("chatgpt")
        if not gacc.get("connected"):
            return
        gpts = list_chatgpt_accounts(self.cfg)
        self._gpt_n = len(gpts)
        sel = next((a for a in gpts if a["id"] == gacc.get("sel")), None)
        if sel:
            self._gpt_path = sel["path"]

    def _claude_detect(self, label):
        """Dipanggil HANYA saat pengguna mengetuk: cek login Claude Code."""
        try:
            _t, _e, plan, email = claude_credentials(self.ccfg)
        except QuotaError:
            self.flash("%s belum login - jalankan `claude` sekali, lalu "
                       "ketuk OFF lagi" % label, 8)
            return
        acc = self._ai_acc("claude")
        acc.update(connected=True, via="detected", credential_source="external",
                   email=(email or "Claude Code") +
                   (" \u00b7 " + plan if plan else ""))
        self._qd.pop("claude", None)
        self._save_ai()
        self.flash("%s terdeteksi - ketuk ON untuk mengaktifkan" % label, 6)
        self.draw_all()

    def _pet_visible(self, i):
        """Pet milik layanan AI (Claude, ChatGPT, Codex, dst.) hanya
        tampil setelah akun layanan itu login."""
        key = PETS[i % len(PETS)]["name"].lower()
        key = PET_OWNER.get(key, key)
        if key not in {k for k, _l, _d in AI_PROVIDERS}:
            return True
        a = (getattr(self, "ai", None) or {}).get("accounts", {}).get(key)
        return bool(isinstance(a, dict) and a.get("connected"))

    def _visible_pets(self):
        return [i for i in range(len(PETS)) if self._pet_visible(i)]

    def _fix_hidden_pet(self):
        """Pet terpilih milik akun yang belum login -> kembali ke pet 9router."""
        if self._pet_visible(self.pet_i):
            return
        nine = self.ai.get("nine_pet")
        if not isinstance(nine, int) or not (0 <= nine < len(PETS)) \
                or not self._pet_visible(nine):
            nine = (self._visible_pets() or [0])[0]
        self.pet_i = nine
        self.ai["nine_pet"] = nine

    def _save_ai(self):
        try:
            accounts = {}
            for key, value in self.ai.get("accounts", {}).items():
                if not isinstance(value, dict):
                    continue
                accounts[str(key)] = {k: v for k, v in value.items()
                                      if k not in ("token", "credential", "secret",
                                                   "access_token", "api_key")}
            with open(AI_PATH, "w", encoding="utf-8") as f:
                # Deliberately serialize metadata only: no token/API key.
                json.dump({"schema_version": STATE_SCHEMA_VERSION,
                           "pet_ver": AI_PET_VER,
                           "active": self.ai.get("active"),
                           "nine_pet": self.ai.get("nine_pet", self.pet_i),
                           "accounts": accounts}, f)
        except OSError:
            pass

    def _ai_acc(self, key, defp=None):
        if defp is None:                   # pet default = pet milik layanan itu
            defp = {k: d for k, _l, d in AI_PROVIDERS}.get(key, 0)
        accs = self.ai.setdefault("accounts", {})
        a = accs.get(key)
        if not isinstance(a, dict):
            a = {"connected": False, "email": "", "pet": defp % len(PETS),
                 "via": "", "sel": "", "last_sync": 0.0,
                 "last_error": "", "credential_source": ""}
            accs[key] = a
        try:
            a["pet"] = int(a.get("pet", defp)) % len(PETS)
        except (ValueError, TypeError):
            a["pet"] = defp % len(PETS)
        return a

    def ai_toggle(self, key, label):
        """Ketuk pil status: login -> aktifkan -> kembali ke 9router."""
        acc = self._ai_acc(key)
        if not acc.get("connected"):
            self.ai_connect(key, label)
        elif self.ai.get("active") == key:
            self.ai_deactivate()
        else:
            if self.ai.get("active") is None:
                self.ai["nine_pet"] = self.pet_i
            self.ai["active"] = key
            self._save_ai()
            self.set_pet(acc["pet"])
            self.flash("%s aktif - pet %s"
                       % (label, PETS[self.pet_i]["name"]))

    def ai_deactivate(self):
        if self.ai.get("active") is None:
            return
        self.ai["active"] = None
        nine = self.ai.get("nine_pet", self.pet_i)
        if not isinstance(nine, int) or not (0 <= nine < len(PETS)):
            nine = self.pet_i
        self._save_ai()
        self.set_pet(nine)
        self.flash("kembali ke 9router - pet %s"
                   % PETS[self.pet_i]["name"])

    def ai_cycle_pet(self, key, label):
        """Ketuk chip pet: ganti pet khusus akun itu."""
        acc = self._ai_acc(key)
        if not acc.get("connected"):
            self.flash("login %s dulu" % label)
            return
        vis = self._visible_pets() or [acc["pet"]]
        nxt = [i for i in vis if i > acc["pet"]]
        acc["pet"] = nxt[0] if nxt else vis[0]
        self._save_ai()
        if self.ai.get("active") == key:
            self.set_pet(acc["pet"])
        else:
            self.flash("pet %s = %s" % (label, PETS[acc["pet"]]["name"]))
            self.draw_all()

    def chatgpt_detect(self):
        """Tombol DETEKSI: cari akun ChatGPT/Codex yang sedang login.
        Satu akun -> langsung dipakai; beberapa -> menu pilih."""
        gpts = list_chatgpt_accounts(self.cfg)
        self._gpt_n = len(gpts)
        if not gpts:
            self.flash("belum ada akun ChatGPT login - jalankan `codex login` "
                       "sekali (akun ke-2: set CODEX_HOME dulu)", 9)
            return
        if len(gpts) == 1:
            self._chatgpt_choose(gpts[0])
            return
        cur = self._ai_acc("chatgpt").get("sel")
        m = tk.Menu(self.root, tearoff=0, font=self.ft(10), bg=BTN, fg=FG,
                    activebackground=MINT, activeforeground=ON_ACCENT, bd=1,
                    relief="solid")
        m.add_command(label="Pilih akun ChatGPT + Codex:", state="disabled")
        for a in gpts:
            lab = "%s %s%s%s" % ("\u25cf" if a["id"] == cur else "\u25cb",
                                 a["email"],
                                 " \u00b7 " + a["plan"] if a["plan"] else "",
                                 " (%s)" % a["folder"]
                                 if a["folder"] != ".codex" else "")
            m.add_command(label=lab,
                          command=lambda a=a: self._chatgpt_choose(a))
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def _chatgpt_choose(self, a):
        acc = self._ai_acc("chatgpt")
        acc.update(connected=True, via="detected", credential_source="external", sel=a["id"],
                   email=a["email"] + (" \u00b7 " + a["plan"] if a["plan"]
                                       else ""))
        self._gpt_path = a["path"]
        self._qd.pop("chatgpt", None)     # kuota akun lama dibuang
        self._qd.pop("codex", None)
        self._save_ai()
        self.flash("ChatGPT + Codex: %s - pilih ruang kerja untuk mengaktifkan"
                   % a["email"], 6)
        self._quota_kick(True)
        self.draw_all()

    def _open_openai_space(self, space):
        """Aktifkan persona yang tepat lalu buka portal resminya.

        ChatGPT dan Codex menggunakan sesi OpenAI yang sama. Memisahkan dua
        tombol di UI membuat tujuannya jelas tanpa menggandakan token atau
        menyimpan kredensial tambahan.
        """
        acc = self._ai_acc("chatgpt")
        if not acc.get("connected"):
            # Tetap beri jalan masuk yang berguna untuk akun baru. Setelah
            # login di portal/CLI, pengguna memilih DETEKSI untuk mengaitkan
            # akun lokal ke widget dan membaca kuotanya.
            name = "Codex" if space == "codex" else "ChatGPT"
            try:
                webbrowser.open(CODEX_PORTAL_URL if space == "codex"
                                else CHATGPT_PORTAL_URL, new=1)
                self.flash("login %s dulu, lalu ketuk DETEKSI di TokenPet" % name,
                           8)
            except Exception:
                self.flash("buka %s lalu ketuk DETEKSI untuk menyambungkan" % name,
                           8)
            return
        name = "Codex" if space == "codex" else "ChatGPT"
        pet_i = next((i for i, p in enumerate(PETS) if p["name"] == name),
                     5 if space == "codex" else 2)
        if self.ai.get("active") is None:
            self.ai["nine_pet"] = self.pet_i
        self.ai["active"] = "chatgpt"
        acc["pet"] = pet_i
        self._save_ai()
        self.set_pet(pet_i)
        try:
            webbrowser.open(CODEX_PORTAL_URL if space == "codex"
                            else CHATGPT_PORTAL_URL, new=1)
            self.flash("membuka %s dengan akun OpenAI yang tersambung" % name,
                       6)
        except Exception:
            self.flash("%s aktif di TokenPet; portal gagal dibuka" % name, 7)

    def open_chatgpt(self):
        self._open_openai_space("chatgpt")

    def open_codex(self):
        self._open_openai_space("codex")

    def ai_connect(self, key, label):
        if key == "chatgpt":
            self.chatgpt_detect()
            return
        if key == "claude":               # deteksi token lokal, tanpa browser
            self._claude_detect(label)
            return
        self._ai_connect_manual(key, label)

    def _ai_mark_connected(self, key, label, email, via=""):
        acc = self._ai_acc(key)
        acc["connected"] = True
        acc["email"] = email
        acc["via"] = via
        self._save_ai()
        self.flash("%s tersambung (%s)" % (label, via or "lokal"))
        self.draw_all()

    def google_connect(self, key, label):
        """Login Claude / ChatGPT lewat Google.

        - Bila config punya google_oauth.client_id: Google OAuth lokal
          memverifikasi email, lalu halaman login layanan dibuka di browser.
        - Bila tidak: halaman login layanan dibuka (di sana ada tombol
          "Continue with Google"); setelah selesai, ketuk konfirmasi."""
        url = GOOGLE_LOGIN_URLS[key]
        gcfg = dict(self.cfg.get("google_oauth") or {})
        try:
            gcfg["client_secret"] = self.secure_store.get("google_oauth") or ""
        except SecureStorageError:
            pass
        if str(gcfg.get("client_id") or "").strip():
            if getattr(self, "_g_busy", False):
                self.flash("login Google masih berjalan...")
                return
            self._g_busy = True
            self.flash("pilih akun Google di browser...", 8)

            def work():
                try:
                    info = google_oauth_login(gcfg)
                    err = None
                except GoogleLoginError as e:
                    info, err = None, str(e)
                except Exception as e:
                    log_exc("google-login")
                    info, err = None, type(e).__name__

                def done():
                    self._g_busy = False
                    if err:
                        self.flash("Google: " + err, 8)
                        return
                    self._ai_mark_connected(key, label, info["email"], "Google")
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass
                self._ui(done)
            threading.Thread(target=work, daemon=True).start()
            return
        try:
            webbrowser.open(url)
        except Exception:
            self.flash("gagal membuka browser: " + url, 8)
            return
        self._with_dialog(lambda: self._google_confirm(key, label))

    def _with_dialog(self, fn):
        self._dialog_open = True
        try:
            self.root.attributes("-topmost", False)
            fn()
        except Exception:
            log_exc("dialog")
        finally:
            self._dialog_open = False
            try:
                self.root.attributes("-topmost", self.always_on_top)
            except tk.TclError:
                pass

    def _google_confirm(self, key, label):
        from tkinter import messagebox, simpledialog
        if not messagebox.askyesno(
                "Login %s" % label,
                "Browser dibuka ke halaman login %s.\n\nPilih \"Continue "
                "with Google\" di sana. Sudah selesai login?" % label,
                parent=self.root):
            return
        email = simpledialog.askstring(
            "Login %s" % label,
            "Email Google yang dipakai (boleh kosong):", parent=self.root)
        self._ai_mark_connected(key, label, (email or "").strip()
                                or "akun Google", "Google")

    def _ai_connect_manual(self, key, label):
        self._dialog_open = True
        try:
            from tkinter import simpledialog
            self.root.attributes("-topmost", False)
            email = simpledialog.askstring(
                "Login " + label, "Email akun %s:" % label,
                parent=self.root)
            if not (email or "").strip():
                return
            token = simpledialog.askstring(
                "Login " + label,
                "API key / token %s:\n(disimpan terenkripsi di Windows)" % label,
                show="*", parent=self.root)
        except Exception:
            return
        finally:
            self._dialog_open = False
            try:
                self.root.attributes("-topmost", self.always_on_top)
            except tk.TclError:
                pass
        acc = self._ai_acc(key)
        if token:
            try:
                self.secure_store.save(key, token)
            except SecureStorageError:
                self.flash("credential tidak bisa diamankan; akun tidak disimpan", 7)
                return
        acc["connected"] = True
        acc["email"] = email.strip()
        acc["credential_source"] = "secure" if token else ""
        acc["last_error"] = ""
        self._save_ai()
        self.flash("%s tersambung (credential terenkripsi)" % label)
        self.draw_all()

    def ai_disconnect(self, key, label):
        acc = self._ai_acc(key)
        was_active = self.ai.get("active") == key
        acc["connected"] = False
        acc["via"] = ""
        if was_active:
            self.ai["active"] = None
        self._save_ai()
        if was_active:
            nine = self.ai.get("nine_pet", self.pet_i)
            if not isinstance(nine, int) or not (0 <= nine < len(PETS)):
                nine = self.pet_i
            self.set_pet(nine)
        elif not self._pet_visible(self.pet_i):
            self._fix_hidden_pet()
            self.set_pet(self.pet_i)
        else:
            self.draw_all()
        self.flash("%s diputus (credential lokal tetap terenkripsi)" % label)

    def ai_delete_credential(self, key, label):
        from tkinter import messagebox
        if not messagebox.askyesno(
                "Hapus credential",
                "Credential %s yang disimpan TokenPet akan dihapus dari Windows.\n\nLanjutkan?" % label,
                parent=self.root):
            return
        try:
            self.secure_store.delete(key)
        except SecureStorageError:
            self.flash("credential %s tidak bisa dihapus" % label, 6)
            return
        acc = self._ai_acc(key)
        acc["credential_source"] = ""
        acc["connected"] = False
        self._save_ai()
        self.flash("credential %s dihapus" % label)
        self.draw_all()

    def ai_reveal_credential(self, key, label):
        from tkinter import messagebox
        if not messagebox.askyesno(
                "Tampilkan credential",
                "Tampilkan credential %s sementara di layar?" % label,
                parent=self.root):
            return
        try:
            value = self.secure_store.get(key)
        except SecureStorageError:
            value = None
        if not value:
            self.flash("credential %s tidak disimpan oleh TokenPet" % label, 6)
            return
        pop = tk.Toplevel(self.root)
        pop.title("Credential " + label)
        pop.configure(bg=BG)
        pop.transient(self.root)
        pop.attributes("-topmost", self.always_on_top)
        tk.Label(pop, text="Credential akan disembunyikan otomatis.",
                 bg=BG, fg=MUTED, font=self.ft(9)).pack(padx=14, pady=(12, 4))
        shown = tk.StringVar(value=value)
        ent = tk.Entry(pop, textvariable=shown, width=42, show="", font=self.ft(10),
                       bg=BG_EMPTY, fg=FG, insertbackground=FG)
        ent.pack(padx=14, pady=4)
        ent.select_range(0, "end")
        def copy_value():
            try:
                pop.clipboard_clear(); pop.clipboard_append(value)
                self.flash("credential disalin; clipboard tidak dikelola TokenPet")
            except tk.TclError:
                pass
        tk.Button(pop, text="Copy", command=copy_value).pack(pady=(3, 12))
        pop.after(15000, lambda: pop.destroy() if pop.winfo_exists() else None)
        try:
            pop.grab_set()
        except tk.TclError:
            pass

    def logout_all(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
                "Logout All",
                "Semua credential AI yang disimpan TokenPet secara lokal akan dihapus.\n\nLanjutkan?",
                icon="warning", parent=self.root):
            return
        try:
            self.secure_store.delete_all()
        except SecureStorageError:
            self.flash("tidak semua credential dapat dihapus", 7)
            return
        self.auth.password, self.auth.cookie = "", None
        self.qcfg["_secure_access_token"] = ""
        for acc in self.ai.get("accounts", {}).values():
            if isinstance(acc, dict):
                acc.update(connected=False, credential_source="", via="")
        self.ai["active"] = None
        self._save_ai()
        self._fix_hidden_pet()
        self.set_pet(self.ai.get("nine_pet", 0))
        self.flash("credential TokenPet dihapus; login CLI eksternal tidak diubah", 8)

    def toggle_theme_follow(self):
        self.theme_follow = not self.theme_follow
        self._sync_theme_to_pet()
        self._save_pos()
        apply_theme(self.scene_theme)
        self.root.configure(bg=gap_color())
        self.c.configure(bg=gap_color())
        style_tk(self.root)
        self._fx_build()
        self.flash("tema ikut pet " + ("ON" if self.theme_follow else "OFF"))
        self.draw_all()

    def toggle_fx(self):
        self.fx_on = not self.fx_on
        self._fx_build()
        self.flash("efek cuaca " + ("ON" if self.fx_on else "OFF"))
        self.draw_all()

    def _footer_end_x(self):
        """Tepi kanan bar ikon footer (agar teks status tak menimpanya)."""
        s = self.s
        step = getattr(self, "_footer_step", None) or s(34)
        n = getattr(self, "_footer_n", 7)
        return s(20) + (n - 1) * step + s(21)

    def _footer_status_avail(self):
        """Ruang nyata teks status: dari ujung bar ikon sampai tombol QUIT."""
        s = self.s
        right = self.W - s(18) - s(56) - s(10)   # sejajar teks status
        return max(0, right - self._footer_end_x() - s(8))

    def _draw_footer(self, y, pnl, top, pad):
        """Footer dipakai ulang oleh panel utama & panel settings."""
        s, c, W = self.s, self.c, self.W
        c.create_line(pad, y - s(21), W - pad, y - s(21), fill=LINE,
                      width=max(1, int(self.dpi)), tags="ui")
        footer_icons = [
            ("settings", self.toggle_view),
            ("bars", self.toggle_sort),
            ("sun", self.theme_menu),
            ("weather", self.weather_menu),
            ("bulb", self.decor_menu),
            ("hat", self.acc_menu),
            ("gear", self.open_config),
        ]
        step = s(36)
        for i, (kind, fn) in enumerate(footer_icons):
            ixc = s(20) + i * step
            active = kind == "settings" and getattr(
                self, "view", "main") == "settings"
            self._button_surface(
                ixc - s(4), y - s(13), ixc + s(20), y + s(13),
                fill=mix(SURFACE, MINT, 0.24) if active else SURFACE,
                outline=MINT if active else LINE)
            self._icon(kind, ixc, y - s(8), fn)
        self._footer_n = len(footer_icons)
        self._footer_step = step
        lw = s(56)
        lx1 = W - s(18)
        self.box(lx1 - lw, y - s(13), lx1, y + s(13), "QUIT", self.quit,
                 fill=mix(BG, RED, 0.18), fg=RED,
                 outline=mix(BG, RED, 0.5), size=10)
        txt, col = self._status()
        self._status_id = self.tx(lx1 - lw - s(10), y, self._clip_status(txt),
                                  col, 10, False, "e")
        self.card_to(pnl, 1, top, W - 1, y + s(22), r=s(15))
        self._fit_window(y + s(26))

    def _draw_settings_panel(self, Hc, edge, bw2):
        """Halaman settings di kartu bawah header (mengganti panel utama)."""
        s, c, W = self.s, self.c, self.W
        top = Hc + s(12)
        pnl = self.card(1, top, W - 1, top + s(60), fill=BG, outline=edge,
                        r=s(15), bw=bw2)
        pad, ix = s(14), s(26)
        y = top + s(26)
        tid = self.tx(ix, y, "SETTINGS", FG, 15, True)
        name_x = c.bbox(tid)[2] + s(10)
        self.tx(name_x, y + s(2),
                self.fit("- akun AI & aplikasi",
                         W - s(120) - name_x - s(8), 10), MUTED, 10)
        bwb = self.measure("KEMBALI", 9, True) + s(16)
        bx = W - s(18) - bwb
        self.box(bx, y - s(10), bx + bwb, y + s(10), "KEMBALI",
                 self.close_settings_view, fill=SURFACE, outline=LINE,
                 size=9)
        y += s(40)
        self.card_to(pnl, 1, top, W - 1, y + s(14), r=s(15))
        ct = y + s(6)
        cid = self.card(pad, ct, W - pad, ct + s(60), r=s(12), outline=LINE)
        y2 = ct + s(24)
        self.tx(ix, y2, "AKUN AI", MUTED, 9, True)
        y2 += s(18)
        self.tx(ix, y2, self.fit(
            "Tiap akun punya pet sendiri - pet 9router tidak ketimpa.",
            W - 2 * ix, 8), MUTED, 8)
        y2 += s(24)

        def pill(xr, yc, label, mode, fn):
            pw = self.measure(label, 9, True) + s(14)
            x0 = xr - pw
            y0 = yc - s(9)
            if mode == "aktif":
                fill, fg, ol = MINT, ON_ACCENT, MINT
            elif mode == "on":
                fill, fg, ol = SURFACE_HI, FG, LINE
            else:
                fill, fg, ol = mix(BG, FG, 0.035), MUTED, mix(LINE, BG, 0.35)
            self._button_surface(x0, y0, x0 + pw, y0 + s(18), fill=fill,
                                 outline=ol)
            self.tx(x0 + pw / 2, y0 + 9, label, fg, 9, True, "center")
            self.hits.append((x0, y0, x0 + pw, y0 + s(18), fn))
            return x0

        def chip(xr, yc, label, fn):
            cw = self.measure(label, 9, True) + s(16)
            x0 = xr - cw
            y0 = yc - s(9)
            self._button_surface(x0, y0, x0 + cw, y0 + s(18),
                                 fill=SURFACE_HI, outline=LINE)
            self.tx(x0 + cw / 2, y0 + 9, label, FG, 9, True, "center")
            self.hits.append((x0, y0, x0 + cw, y0 + s(18), fn))
            return x0

        # --- baris 9Router (utama) ---
        nine = self.ai.get("nine_pet", self.pet_i)
        if not isinstance(nine, int) or not (0 <= nine < len(PETS)):
            nine = self.pet_i
        self.tx(ix, y2, "9Router (utama)", FG, 10, True)
        self.tx(ix, y2 + s(13),
                self.fit("pet: " + PETS[nine]["name"], W - 2 * ix, 8),
                MUTED, 8)
        if self.ai.get("active") is None:
            x = pill(W - ix, y2 + s(6), "AKTIF", "aktif",
                     lambda: self.flash("sudah di 9router"))
            chip(x - s(8), y2 + s(6), PETS[nine]["name"], self.pet_menu)
        else:
            x = pill(W - ix, y2 + s(6), "PAKAI", "on", self.ai_deactivate)
            chip(x - s(8), y2 + s(6), PETS[nine]["name"],
                 lambda: self.flash("kembali dulu via PAKAI"))
        y2 += s(42)

        # --- baris tiap provider AI ---
        for key, label, defp in AI_PROVIDERS:
            acc = self._ai_acc(key, defp)
            self.tx(ix, y2, label, FG, 10, True)
            sub = acc["email"] if acc["connected"] else (
                "belum aktif - ketuk OFF untuk deteksi login"
                if key in AUTO_DETECT_KEYS else "belum login - ketuk OFF")
            if key == "chatgpt" and acc["connected"] and self._gpt_n > 1:
                sub += "  (%d akun)" % self._gpt_n
            self.tx(ix, y2 + s(13), self.fit(
                sub, W - 2 * ix - (s(190) if key == "chatgpt" else 0), 8),
                MUTED, 8)
            if self.ai.get("active") == key:
                mode, plab = "aktif", "AKTIF"
            elif acc["connected"]:
                mode, plab = "on", "ON"
            else:
                mode, plab = "off", "OFF"
            x = pill(W - ix, y2 + s(6), plab, mode,
                     lambda k=key, lb=label: self.ai_toggle(k, lb))
            if key == "chatgpt":
                x = chip(x - s(8), y2 + s(6), "DETEKSI", self.chatgpt_detect)
            if acc["connected"]:
                # pet hanya tampil setelah akun login
                x = chip(x - s(8), y2 + s(6), PETS[acc["pet"]]["name"],
                         lambda k=key, lb=label: self.ai_cycle_pet(k, lb))
                x0 = x - s(8) - s(20)
                y0 = y2 + s(6) - s(9)
                self._button_surface(x0, y0, x0 + s(20), y0 + s(18),
                                     fill=mix(BG, RED, 0.18),
                                     outline=mix(BG, RED, 0.5))
                self.tx(x0 + s(10), y0 + 9, "X", RED, 9, True, "center")
                self.hits.append(
                    (x0, y0, x0 + s(20), y0 + s(18),
                     lambda k=key, lb=label: self.ai_disconnect(k, lb)))
            if key == "chatgpt":
                # Satu akun OpenAI, dua titik masuk yang eksplisit. Tombol
                # juga memilih pet yang sesuai sebelum portal dibuka.
                app_y = y2 + s(31)
                self.tx(ix, app_y, self.fit("Satu akun · pilih ruang kerja",
                                            W - 2 * ix - s(132), 8), MUTED, 8)
                x = chip(W - ix, app_y, "CODEX", self.open_codex)
                chip(x - s(8), app_y, "CHATGPT", self.open_chatgpt)
                y2 += s(25)
            y2 += s(42)

        # --- bagian APP ---
        y2 += s(4)
        self.tx(ix, y2, "APP", MUTED, 9, True)
        y2 += s(20)
        for lab, plab, mode, fn in (
                ("Autostart", "ON" if self.autostart else "OFF",
                 "on" if self.autostart else "off", self.toggle_autostart),
                ("Tema ikut pet",
                 "ON" if self.theme_follow else "OFF",
                 "on" if self.theme_follow else "off",
                 self.toggle_theme_follow),
                ("Efek cuaca", "ON" if self.fx_on else "OFF",
                 "on" if self.fx_on else "off", self.toggle_fx),
                ("Cuaca header", self._weather_label(), "on",
                 self.weather_menu),
                ("Dekorasi header", self._decor_label(), "on",
                 self.decor_menu),
                ("Aksesori pet", "ATUR", "on", self.acc_menu)):
            self.tx(ix, y2, lab, FG, 10)
            pill(W - ix, y2, plab, mode, fn)
            y2 += s(28)
        y2 += s(6)
        aw = self.measure("ADVANCED", 9, True) + s(16)
        self.box(ix, y2 - s(10), ix + aw, y2 + s(10), "ADVANCED",
                 self.open_config, fill=SURFACE, outline=LINE, size=9)
        self.tx(ix + aw + s(8), y2, ">", MUTED, 9, True)
        self.tx(ix + aw + s(22), y2,
                self.fit("config.json, batas, combo", W - ix - aw - s(30),
                         9), MUTED, 9)
        y2 += s(28)
        self.tx(ix, y2, "TokenPet v1.0", MUTED, 9)
        self.card_to(cid, pad, ct, W - pad, y2 + s(14), r=s(12))
        yf = y2 + s(40)
        self._draw_footer(yf, pnl, top, pad)

    def _save_pos(self, _ev=None):
        budgets = {k: v for k, v in self.combo_budget.items()
                   if v != DEFAULT_BUDGET.get(k) or k in
                   (self.cfg.get("combo_budget") or {})}
        try:
            with open(POS_PATH, "w", encoding="utf-8") as f:
                json.dump({"schema_version": STATE_SCHEMA_VERSION,
                           "x": self.root.winfo_x(), "y": self.root.winfo_y(),
                           "w": round(self.W / self.dpi), "pet": PETS[self.pet_i]["name"],
                           "expanded": self.expanded,
                           "acc": self.acc,
                           "weather": self.weather,
                           "decor": self.decor,
                           "scene_theme": self.scene_theme,
                           "theme_follow": self.theme_follow,
                           "show_all": self.show_all,
                           "expanded_breakdown": self.expanded_breakdown,
                           "sort": self.sort_tokens,
                           "selected": self.selected,
                           "metric": self.metric,
                           "tab": self.tab_i, "budgets": budgets,
                           "auto_peak": self._auto_peak,
                           "auto_cap_seen": self._auto_cap_seen,
                           "manual_budgets": self.manual_budget,
                           "lock_position": self.lock_position,
                           "always_on_top": self.always_on_top,
                           "notifications_enabled": self.alert_cfg.get("enabled", True),
                           "stats_period": self.stats_period,
                           "selected_provider": self.selected_provider,
                           "view": self.view}, f)
        except OSError:
            pass

    def _on_edge(self, x):
        return x >= self.W - self.s(7)

    def _press(self, ev):
        if self._on_edge(ev.x):
            self._resize = (ev.x_root, self.W)
            return
        for x0, y0, x1, y1, fn in reversed(self.hits):
            if x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
                self._drag = None
                fn()
                return
        if self.lock_position:
            self.flash("posisi dikunci")
            return
        self._drag = (ev.x_root - self.root.winfo_x(),
                      ev.y_root - self.root.winfo_y())

    def _move(self, ev):
        if self._resize:
            x0, w0 = self._resize
            nw = clamp(w0 + ev.x_root - x0, self.min_w, self.max_w)
            if nw != self.W:
                self.root.geometry("%dx%d" % (nw, self.root.winfo_height()))
        elif self._drag:
            self.root.geometry("+%d+%d" % (ev.x_root - self._drag[0],
                                           ev.y_root - self._drag[1]))

    def _release(self, _ev=None):
        self._resize = None
        self._save_pos()

    def _double_click_header(self, ev):
        if ev.y <= self.s(68):
            self.toggle()
            return "break"
        return None

    def _context_menu(self, ev):
        menu = tk.Menu(self.root, tearoff=0, font=self.ft(10), bg=BTN, fg=FG,
                       activebackground=MINT, activeforeground=ON_ACCENT,
                       bd=1, relief="solid")
        menu.add_command(label="Refresh", command=self.refresh_now)
        menu.add_command(label="Statistics", command=self.open_statistics_view)
        if self.intel:
            sub = tk.Menu(menu, tearoff=0, font=self.ft(10), bg=BTN, fg=FG,
                          activebackground=MINT, activeforeground=ON_ACCENT,
                          bd=1, relief="solid")
            for key, label in (("assistant", "Local Assistant"),
                               ("insights", "Smart Insights"),
                               ("anomaly", "Anomaly Alerts"),
                               ("session", "Session History"),
                               ("progress", "Pet Progression"),
                               ("health", "Provider Health"),
                               ("settings", "Intelligence Settings")):
                sub.add_command(label=label,
                                command=lambda k=key: self.open_intel(k))
            menu.add_cascade(label="Local Intelligence", menu=sub)
        menu.add_command(label="Settings", command=self.open_settings_view)
        menu.add_command(label="Change Pet", command=self.pet_menu)
        menu.add_separator()
        menu.add_checkbutton(label="Lock Position", onvalue=True, offvalue=False,
                             variable=tk.BooleanVar(value=self.lock_position),
                             command=self.toggle_lock_position)
        menu.add_checkbutton(label="Always on Top", onvalue=True, offvalue=False,
                             variable=tk.BooleanVar(value=self.always_on_top),
                             command=self.toggle_always_on_top)
        menu.add_separator()
        menu.add_command(label="Exit", command=self.quit)
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _is_text_input(self):
        widget = self.root.focus_get()
        if not widget:
            return False
        try:
            return widget.winfo_class() in ("Entry", "TEntry", "Text", "Spinbox",
                                             "TCombobox")
        except tk.TclError:
            return False

    def _shortcut(self, ev):
        if self._is_text_input():
            return None
        key = (ev.keysym or "").lower()
        if key == "r":
            self.refresh_now()
        elif key == "s":
            self.open_settings_view()
        elif key == "h":
            self.open_statistics_view()
        elif key == "p":
            self.next_pet()
        elif key == "i" and self.intel:
            self.open_intel("assistant")
        elif key == "escape":
            if self.view != "main":
                self.view = "main"
                self.draw_all()
            elif self.expanded:
                self.toggle()
            else:
                return None
        else:
            return None
        return "break"

    def toggle_lock_position(self):
        self.lock_position = not self.lock_position
        self._save_pos()
        self.flash("posisi " + ("dikunci" if self.lock_position else "dibuka"))

    def _apply_topmost(self):
        try:
            self.root.attributes("-topmost", self.always_on_top)
        except tk.TclError:
            pass

    def _enforce_topmost(self):
        """Kembalikan -topmost bila user mau selalu di depan."""
        if self.always_on_top and not getattr(self, "_dialog_open", False):
            try:
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass

    def _on_focus_out(self, _ev=None):
        # Klik aplikasi lain -> Windows kadang melepas status topmost;
        # tegakkan lagi tanpa mencuri fokus (tanpa lift/focus_force).
        if self.always_on_top and not getattr(self, "_dialog_open", False):
            try:
                self.root.after(150, self._enforce_topmost)
            except tk.TclError:
                pass

    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self._apply_topmost()
        self._save_pos()
        self.flash("always on top " + ("ON" if self.always_on_top else "OFF"))

    def toggle_notifications(self):
        self.alert_cfg["enabled"] = not self.alert_cfg.get("enabled", True)
        self._save_pos()
        self.flash("notifikasi " + ("ON" if self.alert_cfg["enabled"] else "OFF"))
        self.draw_all()

    def _hit_at(self, x, y):
        for h in reversed(self.hits):
            if h[0] <= x <= h[2] and h[1] <= y <= h[3]:
                return h
        return None

    def _hover(self, ev):
        self._ptr = (ev.x, ev.y)
        self._eye_ptr = self._ptr
        now_t = time.time()
        if now_t - self._look_t > 0.09 and not self._cur_emo():
            lv = self._look_vec()
            if lv != self._look_q:
                self._look_q, self._look_t = lv, now_t
                self._draw_pet(self._label in ("HOT", "CRITICAL"))
        h = self._hit_at(ev.x, ev.y)
        if self._on_edge(ev.x):
            cur = "sb_h_double_arrow"
        elif h:
            cur = "hand2"
        else:
            cur = ""
        if cur != self._cursor:
            self._cursor = cur
            try:
                self.c.configure(cursor=cur)
            except tk.TclError:
                pass
        is_pet = bool(h) and h[4] in (self.pet_menu, self.toggle_pet_hud)
        if is_pet != self._on_pet:
            self._on_pet = is_pet
            if is_pet:
                self._emo_start()
            else:
                self._emo_until = time.time() + 0.9    # tahan sebentar
        key = None if (h is None or is_pet) else tuple(h[:4])
        if key != self._hov_key:
            self._hov_key = key
            self._hov_draw()

    def _leave(self, _ev=None):
        self._ptr, self._hov_key = None, None
        self._hov_draw()
        if self._on_pet:
            self._on_pet = False
            self._emo_until = time.time() + 0.9

    def _eye_track(self):
        """Perbarui lirikan dari posisi pointer global secara hemat.

        Event ``<Motion>`` Tk hanya dikirim selama kursor berada di atas
        canvas. Membaca posisi pointer dari root membuat pet tetap terasa
        hidup saat pengguna menggerakkan kursor ke aplikasi lain, tanpa
        menggambar ulang seluruh dashboard.
        """
        self._eye_job = None
        try:
            self._eye_ptr = (
                self.root.winfo_pointerx() - self.c.winfo_rootx(),
                self.root.winfo_pointery() - self.c.winfo_rooty())
            look = self._look_vec()
            if look != self._look_q:
                self._look_q = look
                # Ekspresi khusus (senyum, sibuk, peringatan) punya animasi
                # mata sendiri; arah terbaru akan dipakai saat ekspresi usai.
                if not self._cur_emo():
                    self._draw_pet(self._label in ("HOT", "CRITICAL"))
            self._eye_job = self.root.after(45, self._eye_track)
        except tk.TclError:
            # Root sudah ditutup; jangan menjadwalkan callback baru.
            return

    def _hov_clear(self):
        it = self._hov_item
        self._hov_item = None
        if it:
            try:
                self.c.itemconfigure(it[0], fill=it[1], outline=it[2])
                if len(it) > 3 and it[3]:
                    self.c.delete(it[3])
            except tk.TclError:
                pass

    def _hov_draw(self):
        """Sorotan hover yang jelas, tetapi tetap lembut pada kartu data."""
        self._hov_clear()
        k = self._hov_key
        if not k or self._drag or self._resize:
            return
        c = self.c
        cx, cy = (k[0] + k[2]) / 2.0, (k[1] + k[3]) / 2.0
        area = max(1.0, (k[2] - k[0]) * (k[3] - k[1]))
        best, best_a = None, 0.0
        for i in c.find_overlapping(cx, cy, cx, cy):
            tags = c.gettags(i)
            if c.type(i) not in ("polygon", "rectangle") or \
                    "ui" not in tags or "button-shadow" in tags or \
                    not c.itemcget(i, "fill"):
                continue
            x0, y0, x1, y1 = c.bbox(i)
            a2 = (x1 - x0) * (y1 - y0)
            if best_a < a2 <= area * 2.5:
                best, best_a = i, a2
        if best is None:
            return
        fill, out = c.itemcget(best, "fill"), c.itemcget(best, "outline")
        is_button = "button-face" in c.gettags(best)
        try:
            c.itemconfigure(
                best, fill=mix(fill, FG, 0.22 if is_button else 0.14),
                outline=mix(out, MINT if is_button else FG,
                            0.56 if is_button else 0.30) if out else out)
            glow = None
            if is_button:
                x0, y0, x1, y1 = c.bbox(best)
                glow = self.chamfer(
                    x0 + 1, y0 + 1, x1 - 1, y1 - 1,
                    min((x1 - x0) / 2.0, (y1 - y0) / 2.0, self.s(9)),
                    fill="", outline=mix(out or fill, MINT, 0.72),
                    width=max(1, int(self.dpi)), tags=("ui", "hover-glow"))
            self._hov_item = (best, fill, out, glow)
        except (tk.TclError, ValueError):
            self._hov_item = None

    def _hov_sync(self):
        """Setelah gambar ulang: cocokkan sorotan dengan posisi kursor."""
        key = None
        if self._ptr:
            h = self._hit_at(*self._ptr)
            if h and h[4] != self.pet_menu:
                key = tuple(h[:4])
        self._hov_key = key
        self._hov_draw()

    # ---------- ekspresi pet (hover) ----------
    def _cur_emo(self):
        now = time.time()
        if self._reaction and now < self._reaction_until:
            return self._reaction
        if self._emo:
            return self._emo
        if self._idle_action and now < self._idle_until:
            return self._idle_action
        if now < self._busy_until:
            return "busy"
        return None

    def _mood_target(self, S):
        """Derive a real-condition target before hysteresis is applied."""
        if not self.mood_enabled:
            return "STABLE", False
        now = time.time()
        critical_pct = float(self.cfg.get("critical_left_percent", 5))
        release_pct = max(critical_pct + 3, float(
            self.cfg.get("critical_recover_percent", 10)))
        left = S.get("left_pct")
        # Keep critical until there is meaningful recovery, not one noisy poll.
        low_limit = release_pct if self._mood.current == "CRITICAL" else critical_pct
        quota_critical = False
        for q in self._qd.values():
            snap = q.get("snap") if isinstance(q, dict) else None
            if not snap:
                continue
            if snap.get("limit_reached"):
                quota_critical = True
                break
            for win in snap.get("windows", []):
                if float(win.get("used", 0) or 0) >= 95.0:
                    quota_critical = True
                    break
        if quota_critical or self._err_streak >= 3 or \
                (left is not None and left <= low_limit):
            return "CRITICAL", quota_critical or self._err_streak >= 3
        raw = S.get("label", "STABLE")
        if raw == "HOT" or (left is not None and left < self.warn_low):
            return "HOT", False
        if raw == "WARM" or self._running > 0:
            return "WARM", False
        # Low activity means no observed token increase and no active request.
        if now - self._last_activity_at >= max(30.0, float(
                self.cfg.get("chill_after_seconds", 60))):
            return "CHILL", False
        return raw if raw in MoodController.ORDER else "STABLE", False

    def _update_mood(self, S):
        target, urgent = self._mood_target(S)
        label, changed = self._mood.update(target, urgent=urgent)
        if changed:
            if label == "CRITICAL":
                self._trigger_reaction("panic", 4.0, speech="CRITICAL", force=True)
            elif label == "HOT":
                self._trigger_reaction("nervous", 2.5)
            elif label == "WARM":
                self._trigger_reaction("bounce", 1.5)
            elif label == "CHILL":
                self._speak("CHILL")
        return label

    @staticmethod
    def _mood_color(label):
        return {"STABLE": GREEN, "CHILL": GREEN, "WARM": YELLOW,
                "HOT": RED, "CRITICAL": RED}.get(label, MUTED)

    @staticmethod
    def _mood_foreground(label):
        return ON_ACCENT if label in ("STABLE", "CHILL") else \
            (ON_WARN if label == "WARM" else ON_BAD)

    def _draw_speech_bubble(self, x0, x1):
        return  # bubble komen dimatikan
        if not self._speech or time.time() >= self._speech_until:
            return
        s = self.s
        y0, y1 = s(2), s(24)
        self.card(x0, y0, x1, y1, fill=SURFACE_HI, outline=MINT, r=s(8),
                  bw=max(1, int(self.dpi)))
        self.tx(x0 + s(9), (y0 + y1) / 2,
                self.fit(self._speech, max(1, x1 - x0 - s(18)), 9), FG, 9)

    def _speak(self, kind=None, force=False):
        now = time.time()
        cooldown = max(12.0, float(self.cfg.get("speech_cooldown_seconds", 30)))
        if not force and now - self._speech_last < cooldown:
            return False
        phrases = (self.cfg.get("speech") or {}).get(kind or self._label)
        if isinstance(phrases, str):
            phrases = [phrases]
        phrases = phrases or SPEECH.get(kind or self._label, ())
        if not phrases:
            return False
        self._speech = str(random.choice(tuple(phrases)))
        self._speech_until = now + max(3.5, min(8.0, len(self._speech) * 0.12))
        self._speech_last = now
        if not getattr(self, "_drawing", False):
            self.draw_all()
        return True

    def _trigger_reaction(self, action, seconds=2.0, speech=None, force=False):
        """Event-only reaction; callers own the event comparison/cooldown."""
        now = time.time()
        if not force and self._reaction and now < self._reaction_until:
            return
        self._reaction, self._reaction_t0 = action, now
        self._reaction_until = now + max(0.4, float(seconds))
        if speech:
            self._speak(speech, force=force)
        self._emo_ensure()

    def _idle_step(self):
        self._idle_job = None
        now, mood = time.time(), self._label
        choices = {
            "STABLE": (("look_left", 2.0), ("look_right", 2.0),
                       ("look_up", 1.5), ("smile", 2.0), ("status", 2.0)),
            "CHILL": (("yawn", 2.5), ("sleep", 6.0), ("stretch", 2.5),
                      ("look_left", 2.0)),
            "WARM": (("bounce", 1.8), ("smile", 2.0), ("look_right", 2.0),
                     ("status", 2.0)),
            "HOT": (("nervous", 2.5), ("status", 2.0), ("look_right", 1.7)),
            "CRITICAL": (("panic", 2.2),),
        }
        action, duration = random.choice(choices.get(mood, choices["STABLE"]))
        # Idle does not override a meaningful polling/reconnect reaction.
        if not (self._reaction and now < self._reaction_until):
            self._idle_action, self._idle_t0 = action, now
            self._idle_until = now + duration
            self._emo_ensure()
            if action == "status" or (mood == "CHILL" and random.random() < .35):
                self._speak(mood)
        ranges = {"STABLE": (4, 10), "CHILL": (7, 16), "WARM": (3, 8),
                  "HOT": (2, 5), "CRITICAL": (2, 4)}
        lo, hi = ranges.get(mood, (4, 10))
        self._idle_job = self.root.after(random.randint(lo * 1000, hi * 1000),
                                         self._idle_step)

    def _emo_ensure(self):
        if not self._emo_job:
            self._emo_job = self.root.after(90, self._emo_step)

    def _emo_start(self):
        self._emo = "smile"
        self._emo_t0 = time.time()
        self._emo_until = float("inf")
        self._emo_ensure()

    def _mark_busy(self, secs=None):
        """Model sedang jalan / token baru terpakai: pet pasang tampang serius."""
        secs = self.busy_secs if secs is None else secs
        if self.busy_secs <= 0 or secs <= 0:
            return
        now = time.time()
        if now >= self._busy_until:
            self._busy_t0 = now
        self._busy_until = max(self._busy_until, now + secs)
        self._emo_ensure()

    def _emo_step(self):
        self._emo_job = None
        if self._emo and not self._on_pet and time.time() > self._emo_until:
            self._emo = None
        if self._reaction and time.time() >= self._reaction_until:
            self._reaction = None
        if self._idle_action and time.time() >= self._idle_until:
            self._idle_action = None
        self._draw_pet(self._label in ("HOT", "CRITICAL"))
        if self._cur_emo():
            self._emo_job = self.root.after(90, self._emo_step)

    def _on_cfg(self, ev):
        # hanya lebar yang kita ikuti; tinggi diatur sendiri oleh isi
        if ev.width < 50 or ev.width == self.W:
            return
        self.W = ev.width
        if self._cfg_job:          # sudah ada gambar ulang terjadwal
            return
        self._cfg_job = self.root.after(12, self._cfg_redraw)

    def _cfg_redraw(self):
        self._cfg_job = None
        self.draw_all()

    def _wheel(self, ev):
        if not (self.expanded and (self.show_all or not self._collapsible())):
            return
        delta = getattr(ev, "delta", 0)
        up = delta > 0 if delta else getattr(ev, "num", 0) == 4
        cap = self._rows_cap()
        self.list_off = clamp(self.list_off + (-1 if up else 1), 0,
                              max(0, len(self._per) - cap))
        self.draw_all()

    def _fit_window(self, want):
        """Tinggi jendela = tinggi header + (tinggi panel penuh x progres)."""
        if self.expanded or self._anim:
            self._full_h = max(want, self.s(68))
            a = self._anim
            if a and self.expanded and not a.get("ydone"):
                a["ydone"] = True          # geser ke atas bila panel keluar layar
                sh = self.root.winfo_screenheight()
                a["y1"] = min(a["y0"], max(0, sh - self._full_h - 40))
        self._sync_h()

    def _sync_h(self):
        hc = self.s(68)
        full = self._full_h if (self.expanded or self._anim) else hc
        h = int(round(hc + (max(full, hc) - hc) * ease_io(self._prog)))
        a = self._anim
        if a:
            y = a["y0"]
            if a.get("y1") is not None:
                y = int(round(a["y0"] + (a["y1"] - a["y0"]) * ease_io(self._prog)))
            self.root.geometry("%dx%d+%d+%d" % (self.W, h, self.root.winfo_x(), y))
            return
        if self.root.winfo_height() == h:
            return
        geo = "%dx%d" % (self.W, h)
        if self.expanded:
            sh, y = self.root.winfo_screenheight(), self.root.winfo_y()
            if y + h > sh - 40:
                geo += "+%d+%d" % (self.root.winfo_x(), max(0, sh - h - 40))
        self.root.geometry(geo)

    def _anim_step(self):
        a = self._anim
        if not a:
            return
        t = clamp((time.time() - a["t0"]) / a["dur"], 0.0, 1.0)
        self._prog = a["p0"] + (a["p1"] - a["p0"]) * t
        self._sync_h()
        if t < 1.0:
            self._anim_job = self.root.after(15, self._anim_step)
            return
        self._anim, self._anim_job = None, None
        self._prog = a["p1"]
        self.draw_all()               # tertutup: buang isi panel; terbuka: pas

    # ---------- aksi tombol ----------
    def toggle(self):
        self.expanded = not self.expanded
        self._save_pos()
        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None
        p1 = 1.0 if self.expanded else 0.0
        if self.anim_ms <= 0:
            self._anim, self._prog = None, p1
            self.draw_all()
            return
        p0 = self._prog
        self._anim = {"p0": p0, "p1": p1, "y0": self.root.winfo_y(),
                      "y1": None, "t0": time.time(),
                      "dur": self.anim_ms / 1000.0 * max(0.25, abs(p1 - p0))}
        self.draw_all()               # panel digambar penuh, jendela baru membuka
        self._anim["t0"] = time.time()
        self._anim_job = self.root.after(15, self._anim_step)

    # def toggle_breakdown(self):
    #     self.expanded_breakdown = not self.expanded_breakdown
    #     self._save_pos()
    #     self.draw_all()

    def toggle_models(self):
        self.show_all = not self.show_all
        self.list_off = 0
        self._save_pos()
        self.draw_all()

    def quit(self):
        self._save_pos()
        self.hist.save()
        self._intel_shutdown()
        for job in (self._job, self._cfg_job, self._tick_job,
                    self._sc_job, self._fx_job, self._anim_job, self._emo_job,
                    self._eye_job, self._bar_anim_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except (tk.TclError, ValueError):
                    pass
        self._job = self._cfg_job = self._tick_job = None
        self._sc_job = self._fx_job = self._eye_job = self._bar_anim_job = None
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def flash(self, msg, secs=4):
        self.flash_msg, self.flash_until = msg, time.time() + secs
        self._refresh_status()

    def toggle_autostart(self):
        try:
            set_autostart(not self.autostart)
            self.autostart = autostart_enabled()
            self.flash("autostart " + ("ON" if self.autostart else "OFF"))
        except Exception as e:
            self.flash("autostart gagal: %s" % str(e)[:30], 6)
        self.draw_all()

    def budget_source(self):
        """Return (batas, 'manual' | 'auto' | 'config') utk periode tab aktif.

        Batas = BATAS token yang boleh dipakai, BUKAN jumlah yang sudah
        terpakai. Sisa = batas - terpakai, jadi batas wajib lebih besar dari
        pemakaian; menyamakan keduanya bikin sisa selalu ~0% dan alarm
        berbunyi terus.

        9router tidak mengirim field limit/quota di respons mana pun
        (/api/usage/stats hanya punya total*Token, by*, last10Minutes), jadi
        angka batas TIDAK bisa diambil dari API - tidak boleh dikarang.

        Tiga sumber, urut prioritas:
          manual - angka yang diketik user (klik caption "batas ...")
          auto   - batas ikut naik sendiri mengikuti pemakaian; angka
                   batas = puncak pemakaian (auto_peak) + cadangan
                   (auto_headroom). Dipakai kalau `auto_budget` nyala.
          config - `combo_budget` per periode di config

        Mode auto bukan batas tetap: begitu pemakaian tembus batas lama,
        batas naik ke puncak baru + cadangan, jadi widget tidak pernah
        merah/Merah karena batasnya basi. Ruang sisa = cadangan, bukan
        angka yang dikarang 9router.
        """
        m = self.manual_budget.get(self.period, 0.0)
        if m > 0:
            return m, "manual"
        if self.auto_budget and self._have:
            cap = self._auto_cap()
            if cap > 0:
                return cap, "auto"
        return max(0.0, self.combo_budget.get(self.period, 0.0)), "config"

    def _auto_cap(self):
        """Batas mode auto utk periode aktif = puncak pemakaian + cadangan.

        Untuk periode BERJALAN (24h, today) angka yang dilaporkan 9router
        sudah berupa window geser, jadi batas ikut turun sendiri begitu
        pemakaian lama keluar dari window - itulah cara window bekerja.

        Untuk periode KUMULATIF (7d, all) angka yang dilaporkan 9router
        hanya bertambah, jadi batas ikut naik dan tidak pernah turun.
        """
        peak = self._auto_peak.get(self.period, 0.0)
        if peak <= 0:
            # belum ada observasi -> angka config jadi titik awal
            return max(0.0, self.combo_budget.get(self.period, 0.0))
        head = max(float(self.auto_floor),
                   peak * self.auto_headroom / 100.0)
        cap = peak + head
        if self.period not in AUTO_WINDOWED:
            # kumulatif: jangan pernah turun
            cap = max(cap, float(self._auto_cap_seen.get(self.period, 0.0)))
        return cap

    def _track_auto(self, used):
        """Catat pemakaian utk batas auto (dipanggil tiap data baru masuk).

        Batas ikut mengikuti pemakaian: naik saat pemakaian naik, dan utk
        periode berjalan ikut turun lagi saat jendela bergeser. Cadangan
        di atas pemakaian terjamin, jadi sisa tak pernah 0% karena
        batasnya basi.
        """
        if not self.auto_budget or not self._have or used <= 0:
            return False
        per = self.period
        if per in AUTO_WINDOWED:
            # angka 9router sudah windowed -> ikut apa adanya
            new_peak = used
        else:
            new_peak = max(self._auto_peak.get(per, 0.0), used)
        self._auto_peak[per] = new_peak
        self._auto_seen[per] = time.time()
        cap = self._auto_cap()
        old = float(self._auto_cap_seen.get(per, 0.0))
        if abs(cap - old) > 0.5:
            self._auto_cap_seen[per] = cap
            self._save_pos()
            return True                # batas berubah -> caption perlu redraw
        return False

    def _prune_auto(self):
        """Buang catatan lama yang periodenya sudah tak relevan.

        Catatan 'today' Hanya berguna di hari yang sama, jadi begitu
        tengah malam berganti mau dibuang; 24h/7d dibuang setelah berminggu-
        minggu supaya tak jadi rekor abadi.
        """
        now = time.time()
        lt = time.localtime(now)
        same_day = (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec) < 86400
        for per in list(self._auto_peak):
            if per == "all":
                continue
            if per == "today" and same_day:
                continue
            if now - float(self._auto_seen.get(per, 0.0)) > 86400 * 8:
                self._auto_peak.pop(per, None)
                self._auto_cap_seen.pop(per, None)
                self._auto_seen.pop(per, None)

    def edit_budget(self):
        label = self.tabs[self.tab_i][0]
        cur = self.budget_source()[0]
        top = True
        try:
            from tkinter import simpledialog
            self.root.attributes("-topmost", False)
            ans = simpledialog.askstring(
                "Batas " + label,
                "Batas token %s (mis. 100M, 2.5B, 750k).\n"
                "Sisa = batas - terpakai, jadi batas harus\n"
                "lebih besar dari yang sudah terpakai.\n\n"
                "Ketik 'auto' = batas ikut naik sendiri\n"
                "sesuai pemakaian (+%d%% cadangan)."
                % (label, round(self.auto_headroom)),
                initialvalue=fmt_tokens(cur) if cur else "",
                parent=self.root)
        except Exception:
            ans = None
        finally:
            try:
                self.root.attributes("-topmost", top)
            except tk.TclError:
                pass
        if ans is None:
            return
        if ans.strip().lower() in ("auto", "otomatis", "a"):
            # auto: lepaskan batas manual, biarkan ikut naik sendiri
            self.manual_budget.pop(self.period, None)
            self._alert_lvl.pop(self.period, None)
            self._save_pos()
            self.flash("batas %s ikut naik sendiri (auto)" % label)
            self.draw_all()
            return
        v = parse_amount(ans)
        if not v or v <= 0:
            self.flash("angka batas tidak valid", 5)
            return
        self.manual_budget[self.period] = v
        self._alert_lvl.pop(self.period, None)
        self._save_pos()
        self.flash("batas %s = %s" % (label, fmt_tokens(v)))
        self.draw_all()

    def set_tab(self, i):
        if i == self.tab_i:
            return
        self.tab_i, self.period = i, self.tabs[i][1]
        self.usage = []
        self.reported, self._have = None, False
        self._derive()
        self.tracker = PaceTracker(self.pace_window)
        self.hist.reset()
        self._save_pos()
        self.draw_all()
        self._schedule_poll(50)

    def select_model(self, entry):
        self.selected = None if self.selected == entry else entry
        self._save_pos()
        self.draw_all()

    def open_config(self):
        try:
            os.startfile(CONFIG_PATH)  # Windows
        except (AttributeError, OSError):
            pass

    def toggle_view(self):
        self.view = "settings" if self.view == "main" else "main"
        if self.view == "settings" and not self.expanded:
            self.expanded = True
            self._prog = 1.0
            self._save_pos()
        self.draw_all()

    def open_settings_view(self):
        self.view = "settings"
        if not self.expanded:
            self.expanded = True
            self._prog = 1.0
            self._save_pos()
        self.draw_all()

    def close_settings_view(self):
        self.view = "main"
        self.draw_all()

    def toggle_sort(self):
        self.sort_tokens = not self.sort_tokens
        self._save_pos()
        self.draw_all()

    def refresh_now(self):
        if self.logged_out:
            self.flash("sudah logout - klik LOGIN dulu")
            return
        self._schedule_poll(50)

    def toggle_login(self):
        """Tombol di sebelah status: logout (jeda polling) / login lagi."""
        if self.logged_out:
            self.logged_out = False
            self.auth.cookie = None
            self.error = None
            self.flash("login...")
            self._schedule_poll(50)
        else:
            self.logged_out = True
            self.auth.logout()
            if self._job:
                try:
                    self.root.after_cancel(self._job)
                except (tk.TclError, ValueError):
                    pass
                self._job = None
            self.error = None
            self.flash("logout - polling dihentikan")
        self.draw_all()

    def _pick_metric(self, v):
        """Normalisasi nama metrik; None/aneh -> default widget (io)."""
        v = str(v or "").strip().lower()
        return v if v in METRICS else "io"

    def cycle_metric(self):
        """Ganti metrik hitung token; komponen sudah ada di memory."""
        self.metric = METRICS[(METRICS.index(self.metric) + 1) % len(METRICS)]
        self._save_pos()
        self._recompute()
        self.draw_all()

    def _recompute(self):
        """Turunkan ulang total per-model setelah metrik berubah."""
        self._derive()
        self.tracker.reset()
        self.tracker.add(self._tot_t)
        self.hist.feed(self.period, self._tot_t, replace=True)
        self._check_alerts(self._state())

    def acc_set(self, slot, val):
        name = PETS[self.pet_i]["name"].lower()
        sel = self.acc.setdefault(name, {})
        if val:
            sel[slot] = val
        else:
            sel.pop(slot, None)
        if not sel:
            self.acc.pop(name, None)
        self._save_pos()
        self._draw_pet(self._label in ("HOT", "CRITICAL"))

    def acc_clear(self):
        self.acc.pop(PETS[self.pet_i]["name"].lower(), None)
        self._save_pos()
        self._draw_pet(self._label in ("HOT", "CRITICAL"))

    def acc_random(self):
        sel = {}
        for slot, _t, items in ACC_SLOTS:
            if slot in ("hat", "eyes") or random.random() < 0.45:
                sel[slot] = random.choice(items)[0]
        self.acc[PETS[self.pet_i]["name"].lower()] = sel
        self._save_pos()
        self._draw_pet(self._label in ("HOT", "CRITICAL"))

    def acc_menu(self):
        """Dropdown aksesoris pet: topi, kacamata, wajah, leher, dll."""
        name = PETS[self.pet_i]["name"].lower()
        cur = self.acc.get(name, {})
        fnt = self.ft(10)
        kw = dict(font=fnt, bg=BTN, fg=FG, activebackground=MINT,
                  activeforeground=ON_ACCENT, selectcolor=MINT)
        m = tk.Menu(self.root, tearoff=0, bd=1, relief="solid", **kw)
        self._acc_vars = []
        for slot, title, items in ACC_SLOTS:
            sub = tk.Menu(m, tearoff=0, bd=1, relief="solid", **kw)
            var = tk.StringVar(master=self.root, value=cur.get(slot, ""))
            self._acc_vars.append(var)
            first = "Tanpa"
            if slot == "hat" and name in HAT_KEYS:
                first = "Bawaan"
            sub.add_radiobutton(label=first, variable=var, value="",
                                command=lambda s=slot: self.acc_set(s, ""))
            if slot == "hat" and name in HAT_KEYS:
                sub.add_radiobutton(label="Tanpa topi", variable=var,
                                    value="none",
                                    command=lambda: self.acc_set("hat", "none"))
            sub.add_separator()
            for aid, lab in items:
                sub.add_radiobutton(label=lab, variable=var, value=aid,
                                    command=lambda s=slot, a=aid:
                                    self.acc_set(s, a))
            on = " \u2022" if cur.get(slot) not in (None, "", "none") else ""
            m.add_cascade(label=title + on, menu=sub)
        m.add_separator()
        m.add_command(label="Acak aksesoris", command=self.acc_random)
        m.add_command(label="Lepas semua", command=self.acc_clear)
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def top_model(self):
        if self._per:
            best = max(self._per, key=lambda p: p[1]["tokens"])[0]
            self.selected = None if self.selected == best else best
            self._save_pos()
            self.draw_all()

    # ---------- efek cuaca header (pasir / salju / hujan / gelembung / bintang) ----------
    def _fx_cfg(self):
        """Cuaca aktif: pilihan user, atau bawaan tema pet (auto)."""
        if self.weather == "none":
            return None
        if self.weather == "auto":
            return FX_CFG if self.fx_on else None
        return WEATHER_PRESETS.get(self.weather)

    def set_weather(self, key):
        self.weather = key
        self._save_pos()
        self._fx_build()
        self.draw_all()

    def set_decor(self, key):
        self.decor = key
        self._save_pos()
        self.draw_all()

    def _pick_menu(self, items, cur, fn):
        kw = dict(font=self.ft(10), bg=BTN, fg=FG, activebackground=MINT,
                  activeforeground=ON_ACCENT, selectcolor=MINT)
        m = tk.Menu(self.root, tearoff=0, bd=1, relief="solid", **kw)
        var = tk.StringVar(master=self.root, value=cur)
        self._menu_var = var
        for key, lab in items:
            m.add_radiobutton(label=lab, variable=var, value=key,
                              command=lambda k=key: fn(k))
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def theme_menu(self):
        self._pick_menu(THEME_MENU, self.scene_theme, self.set_scene_theme)

    def set_scene_theme(self, key):
        if key not in {k for k, _l in THEME_MENU}: return
        self.scene_theme = key
        self.theme_follow = False
        apply_theme(self.scene_theme)
        self.root.configure(bg=gap_color())
        self.c.configure(bg=gap_color())
        style_tk(self.root)
        self._fx_build()
        self._save_pos()
        self.draw_all()
        self.flash(dict(THEME_MENU).get(key, key))

    def weather_menu(self):
        self._pick_menu(WEATHER_MENU, self.weather, self.set_weather)

    def _weather_label(self):
        """Nama pendek cuaca terpilih (untuk pil di Settings)."""
        lab = dict(WEATHER_MENU).get(self.weather, self.weather)
        return lab.split(" (")[0]

    def _decor_label(self):
        """Nama pendek dekorasi terpilih (untuk pil di Settings)."""
        return dict(DECOR_MENU).get(self.decor, self.decor).split(" (")[0]

    def decor_menu(self):
        self._pick_menu(DECOR_MENU, self.decor, self.set_decor)

    def _fx_build(self):
        """Buat ulang partikel sesuai cuaca aktif (tag canvas: fx)."""
        c = self.c
        c.delete("fx")
        self._fx, self._fx_splash, self._shoot = [], [], None
        cfg = self._fx_cfg()
        if not cfg:
            return
        sc = self.k * self.dpi
        W, gy = max(self.W, 60), max(10, self.s(58))
        kind, cols = cfg["kind"], cfg["cols"]
        rnd = random.random
        for i in range(int(cfg.get("n", 20))):
            col = cols[i % len(cols)]
            pt = {"x": rnd() * W, "y": rnd() * gy, "ph": rnd() * 6.28,
                  "col": col, "vx": 0.0, "vy": 0.0, "sz": 2}
            if kind == "sand":
                big = i % 5 == 0
                pt.update(vx=(3.0 + rnd() * 4.5) * sc, sz=3 if big else 2)
                if big:                       # gumpalan debu samar
                    pt["col"] = mix(BG, GROUND_HI, 0.22)
                    pt["sz"] = 5
                    pt["vx"] = (1.5 + rnd() * 2.0) * sc
                half = max(1, round(pt["sz"] * sc / 2.0))
                pt["id"] = c.create_rectangle(0, 0, 0, 0, fill=pt["col"],
                                              width=0, tags="fx")
                pt["h"] = half * 2
            elif kind == "snow":
                pt.update(vy=(0.9 + rnd() * 1.6) * sc, sz=3 if i % 4 == 0 else 2)
                pt["h"] = max(1, round(pt["sz"] * sc))
                pt["id"] = c.create_rectangle(0, 0, 0, 0, fill=col, width=0,
                                              tags="fx")
            elif kind == "rain":
                pt.update(vy=(6.5 + rnd() * 4.0) * sc)
                pt["id"] = c.create_line(0, 0, 0, 0, fill=col,
                                         width=max(1, int(sc)), tags="fx")
            elif kind == "bubble":
                pt.update(vy=-(0.6 + rnd() * 1.1) * sc)
                pt["h"] = max(3, round((3 + (i % 3)) * sc))
                pt["y"] = rnd() * gy
                pt["id"] = c.create_oval(0, 0, 0, 0, outline=col,
                                         width=max(1, int(sc)), tags="fx")
            elif kind == "petal":
                pt.update(vy=(0.7 + rnd() * 1.0) * sc)
                pt["h"] = max(3, round((3 + i % 3) * sc))
                pt["id"] = c.create_oval(0, 0, 0, 0, fill=col, width=0,
                                         tags="fx")
            elif kind == "firefly":
                pt["h"] = max(2, round((2 + i % 2) * sc))
                pt["y"] = rnd() * max(6, gy - self.s(12))
                pt["id"] = c.create_oval(0, 0, 0, 0, fill=col, width=0,
                                         tags="fx")
            elif kind == "meteor":
                pt.update(vx=-(5.5 + rnd() * 4.5) * sc,
                          vy=(2.0 + rnd() * 2.2) * sc,
                          y=rnd() * max(6, gy * .62), x=rnd() * W)
                pt["id"] = c.create_line(0, 0, 0, 0, fill=col,
                                         width=max(1, int(sc)), tags="fx")
            else:                             # stars
                pt["h"] = max(1, round((3 if i % 5 == 0 else 2) * sc))
                pt["y"] = rnd() * max(6, gy - self.s(20))
                pt["id"] = c.create_rectangle(0, 0, 0, 0, fill=col, width=0,
                                              tags="fx")
            self._fx.append(pt)
        if kind == "stars":
            self._shoot = {"id": c.create_line(0, 0, 0, 0, fill=BRIGHT,
                                               width=max(2, int(2 * sc)),
                                               state="hidden", tags="fx"),
                           "t": 0, "x": 0.0, "y": 0.0,
                           "next": time.time() + 2.0 + random.random() * 4}

    def _fx_step(self):
        now = time.time()
        self._fx_m = clamp((now - self._fx_t) / 0.08, 0.25, 3.0)
        self._fx_t = now
        try:
            if self._fx:
                self._fx_move()
        except Exception:                     # efek tak boleh merusak widget
            log_exc("fx")
            self._fx, self._shoot = [], None
        self._fx_job = self.root.after(33, self._fx_step)

    def _fx_move(self):
        c, rnd = self.c, random.random
        cfg = self._fx_cfg()
        if not cfg:
            return
        kind = cfg["kind"]
        sc = self.k * self.dpi
        W, gy = max(self.W, 60), max(10, self.s(58))
        now = time.time()
        # HOT -> angin/hujan/salju lebih kencang
        boost = (1.7 if self._label in ("HOT", "CRITICAL") else 1.0) * 1.35 * self._fx_m
        if kind == "sand":                    # embusan angin bergelombang
            boost *= 1.0 + 0.9 * max(0.0, math.sin(now * 0.9))
        for pt in self._fx:
            pt["ph"] += 0.25 * self._fx_m
            x, y, h = pt["x"], pt["y"], pt.get("h", 2)
            if kind == "sand":
                x += pt["vx"] * boost
                y += math.sin(pt["ph"]) * 0.7 * sc * self._fx_m
                if x > W + 6:
                    x, y = -6.0, rnd() * gy
                y = clamp(y, 1, gy - h)
                c.coords(pt["id"], x, y, x + h, y + max(1, h // 2 + 1))
            elif kind == "snow":
                y += pt["vy"] * boost
                x += math.sin(pt["ph"] * 0.6) * 0.9 * sc * self._fx_m
                if y > gy:
                    y, x = -4.0, rnd() * W
                x = x % W
                c.coords(pt["id"], x, y, x + h, y + h)
            elif kind == "rain":
                y += pt["vy"] * boost
                x -= 1.8 * sc * boost
                if y >= gy:
                    if len(self._fx_splash) < 10:
                        self._add_splash(x, gy)
                    y, x = -8.0 * sc, rnd() * (W + 20 * sc)
                if x < -4:
                    x += W + 8
                c.coords(pt["id"], x, y, x - 1.8 * sc, y - 6.0 * sc)
            elif kind == "bubble":
                y += pt["vy"] * boost
                x += math.sin(pt["ph"]) * 0.6 * sc * self._fx_m
                if y < -h:
                    y, x = float(gy), rnd() * W
                c.coords(pt["id"], x, y, x + h, y + h)
            elif kind == "petal":             # kelopak/daun melayang jatuh
                y += pt["vy"] * boost
                x += (math.sin(pt["ph"] * 0.5) * 1.3 - 0.4) * sc * self._fx_m
                if y > gy:
                    y, x = -6.0, rnd() * W
                x = x % W
                c.coords(pt["id"], x, y, x + h, y + max(2, h * 2 // 3))
            elif kind == "firefly":           # kunang-kunang berkelip
                x += math.cos(pt["ph"] * 0.7) * 0.6 * sc * self._fx_m
                y += math.sin(pt["ph"] * 0.5) * 0.45 * sc * self._fx_m
                x, y = x % W, clamp(y, 2, gy - self.s(10))
                ph = (math.sin(pt["ph"] * 0.8) + 1.0) / 2.0
                c.itemconfigure(pt["id"], fill=mix(BG, pt["col"],
                                                   0.15 + 0.85 * ph))
                c.coords(pt["id"], x, y, x + h, y + h)
            elif kind == "meteor":            # jejak meteor diagonal
                x += pt["vx"] * boost
                y += pt["vy"] * boost
                if x < -24 * sc or y > gy * .78:
                    x, y = W + rnd() * W * .25, rnd() * max(5, gy * .28)
                c.coords(pt["id"], x, y, x + 14.0 * sc, y - 5.0 * sc)
            else:                             # stars: berkedip
                ph = (math.sin(pt["ph"] * 0.55) + 1.0) / 2.0
                c.itemconfigure(pt["id"], fill=mix(BG, pt["col"],
                                                   0.25 + 0.75 * ph))
                c.coords(pt["id"], x, y, x + h, y + h)
            pt["x"], pt["y"] = x, y
        # percikan hujan di tanah
        for sp in self._fx_splash[:]:
            sp["life"] -= self._fx_m
            if sp["life"] <= 0:
                for i in sp["ids"]:
                    c.delete(i)
                self._fx_splash.remove(sp)
                continue
            d = (4 - sp["life"]) * sc * 1.6 + 1
            lift = (4 - sp["life"]) * sc * 0.8
            for sgn, i in zip((-1, 1), sp["ids"]):
                px_ = sp["x"] + sgn * d
                c.coords(i, px_, gy - 1 - lift, px_ + max(1, sc), gy - lift)
        # bintang jatuh
        sh = self._shoot
        if sh:
            if sh["t"] <= 0 and now >= sh["next"]:
                sh["t"] = 12
                sh["x"] = W * (0.35 + rnd() * 0.6)
                sh["y"] = 2 + rnd() * self.s(12)
                c.itemconfigure(sh["id"], state="normal")
            if sh["t"] > 0:
                sh["t"] -= self._fx_m
                sh["x"] -= 9.0 * sc * self._fx_m
                sh["y"] += 3.5 * sc * self._fx_m
                c.coords(sh["id"], sh["x"], sh["y"],
                         sh["x"] + 22.0 * sc, sh["y"] - 8.0 * sc)
                if sh["t"] <= 0 or sh["y"] > gy - 6:
                    sh["t"] = 0
                    c.itemconfigure(sh["id"], state="hidden")
                    sh["next"] = now + 5.0 + rnd() * 7

    def _add_splash(self, x, gy):
        col = mix(BG, FG, 0.55)
        ids = [self.c.create_rectangle(0, 0, 0, 0, fill=col, width=0,
                                       tags="fx") for _ in (0, 1)]
        self.c.tag_raise("fx", "bgrect")
        self._fx_splash.append({"x": x, "life": 4, "ids": ids})

    def next_pet(self):
        vis = self._visible_pets() or [0]
        nxt = [i for i in vis if i > self.pet_i]
        self.set_pet(nxt[0] if nxt else vis[0])

    def toggle_pet_hud(self):
        return  # popup HUD dimatikan
        if self._hud and self._hud.winfo_exists():
            self._hud.destroy()
            self._hud = None
            return
        hud = tk.Toplevel(self.root)
        self._hud = hud
        hud.overrideredirect(True)
        hud.configure(bg=BG)
        hud.attributes("-topmost", self.always_on_top)
        try:
            hud.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        frame = tk.Frame(hud, bg=SURFACE, highlightbackground=LINE,
                         highlightthickness=max(1, int(self.dpi)))
        frame.pack(padx=1, pady=1)
        labels = {}
        name = tk.Label(frame, text=PETS[self.pet_i]["name"].upper(), bg=SURFACE,
                        fg=BRIGHT, font=self.ft(11, True), anchor="w")
        name.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(9, 6))
        labels["name"] = name
        for row, (key, label) in enumerate((
                ("mood", "Mood"), ("tokens", "Tokens"), ("today", "Today"),
                ("router", "9Router")), start=1):
            tk.Label(frame, text=label, bg=SURFACE, fg=MUTED,
                     font=self.ft(9), anchor="w").grid(row=row, column=0,
                                                        sticky="w", padx=(12, 28), pady=1)
            value = tk.Label(frame, text="—", bg=SURFACE, fg=FG,
                             font=self.ft(9, True), anchor="e")
            value.grid(row=row, column=1, sticky="e", padx=(4, 12), pady=1)
            labels[key] = value
        tk.Label(frame, text="click to close", bg=SURFACE, fg=MUTED,
                 font=self.ft(8)).grid(row=5, column=0, columnspan=2, pady=(5, 8))
        self._hud_labels = labels
        hud.bind("<Button-1>", lambda _e: self.toggle_pet_hud())
        frame.bind("<Button-1>", lambda _e: self.toggle_pet_hud())
        self._refresh_pet_hud()
        hud.geometry("+%d+%d" % (self.root.winfo_x() + self.s(8),
                                  self.root.winfo_y() + self.s(76)))

    def _refresh_pet_hud(self):
        hud = self._hud
        if not hud or not hud.winfo_exists():
            return
        labels = getattr(self, "_hud_labels", {})
        today = self.hist.totals("today")
        q = self._quota_view()
        router = "Offline" if self.is_stale() else (
            "Connected" if self._have else "Connecting")
        vals = {"name": PETS[self.pet_i]["name"].upper(), "mood": self._label,
                "tokens": fmt_tokens(self._tot_t) if self._have else "—",
                "today": fmt_tokens(today["tokens"]) if today["tokens"] else "—",
                "router": ("Quota unavailable" if q and not q.get("snap") else router)}
        for key, value in vals.items():
            try:
                labels[key].configure(text=value, fg=(RED if key == "mood" and
                                                      value == "CRITICAL" else FG))
            except (KeyError, tk.TclError):
                pass

    # ---------- kuota per layanan (pet Claude / ChatGPT / Codex) ----------
    @property
    def _q(self):
        prov = self._quota_provider() or "-"
        q = self._qd.get(prov)
        if q is None:
            q = self._qd[prov] = {"snap": None, "err": None, "t": 0.0,
                                  "next": 0.0, "fetching": False}
        return q

    def _quota_provider(self):
        """Kunci layanan bila pet aktif punya kuota sendiri, else None."""
        key = PETS[self.pet_i]["name"].lower()
        return key if key in QUOTA_PROVIDERS else None

    def _quota_label(self):
        return QUOTA_PROVIDERS.get(self._quota_provider() or "", "")

    def _quota_kick(self, force=False):
        """Ambil kuota di thread terpisah (hanya saat pet ChatGPT tampil)."""
        if not self._quota_provider():
            return
        q, now = self._q, time.time()
        if q["fetching"] or (not force and now < q["next"]):
            return
        q["fetching"] = True
        prov = self._quota_provider()

        def work():
            try:
                if self.demo:
                    snap = self._demo_q.get()
                elif prov == "claude":
                    snap = fetch_claude_usage(self.ccfg)
                else:                    # chatgpt & codex: akun OpenAI terpilih
                    qc = dict(self.qcfg)
                    if self._gpt_path:
                        qc["auth_file"] = self._gpt_path
                    snap = fetch_chatgpt_usage(qc)
                err = None
            except QuotaError as e:
                snap, err = None, e
            except Exception as e:                 # jangan sampai thread mati
                log_exc("quota")
                snap, err = None, QuotaError("other", type(e).__name__)
            self._ui(lambda: self._apply_quota(snap, err, prov))
        threading.Thread(target=work, daemon=True).start()

    def _apply_quota(self, snap, err, prov=None):
        q, now = (self._qd.get(prov) if prov else None) or self._q, time.time()
        q["fetching"] = False
        q["next"] = now + (self.q_poll if snap else min(self.q_poll, 15))
        q["err"] = err
        if snap:
            self._intel_quota(prov or self._quota_provider() or "-", snap)
            old = q["snap"]
            if old and old["windows"] and snap["windows"] and \
                    snap["windows"][0]["used"] > old["windows"][0]["used"] + 0.01:
                self._mark_busy(8.0)           # pemakaian naik -> pet sibuk
            q["snap"], q["t"] = snap, now
        self._begin_bar_animation()
        self.draw_all()

    def _q_remaining(self, w):
        """Detik sampai reset (dihitung ulang tiap gambar, bukan saat poll)."""
        if w.get("reset_at") is not None:
            return max(0.0, float(w["reset_at"]) - time.time())
        if w.get("reset_s") is not None:
            return max(0.0, float(w["reset_s"]) - (time.time() - self._q["t"]))
        return None

    def _q_caption(self, w):
        """Teks kartu kuota: terpakai + hitung mundur reset (jam:menit:detik)."""
        rem = self._q_remaining(w)
        cap = "terpakai %s" % fmt_pct(w["used"])
        cap += " · reset %s" % fmt_reset_hms(rem)
        if w.get("reset_at"):
            fmt = "%H:%M" if rem is not None and rem < 20 * 3600 \
                else "%d/%m %H:%M"
            cap += " (%s)" % time.strftime(fmt, time.localtime(w["reset_at"]))
        return cap

    def _rst_update(self):
        """Segarkan teks hitung mundur tiap detik tanpa menggambar ulang."""
        for item, fn in self._rst_items:
            try:
                self.c.itemconfigure(item, text=fn())
            except (tk.TclError, TypeError, KeyError):
                pass

    def _period_reset_secs(self, period=None, now=None):
        """Detik sampai jendela periode berjalan berakhir (None = tanpa reset).

        today = sampai tengah malam lokal; 24h/7d = jendela sejak poll
        pertama periode itu (perkiraan, karena 9router tak mengirim info
        reset per-model di /api/usage/stats); all = kumulatif.
        """
        p = period or self.period
        t = now if now is not None else time.time()
        if p == "all":
            return None
        if p == "today":
            lt = time.localtime(t)
            return max(0.0, 86400 - (lt.tm_hour * 3600 + lt.tm_min * 60 +
                                     lt.tm_sec))
        window = PERIOD_SECS.get(p, 86400)
        anchor = self._period_anchor.get(p)
        if anchor is None:
            return float(window)
        rem = window - (t - anchor)
        if rem <= 0:
            self._period_anchor[p] = t      # jendela bergulir -> jangkar baru
            return float(window)
        return rem

    def _model_reset_label(self):
        p = self.period
        if p == "all":
            return "kumulatif - tanpa reset"
        if p == "today":
            return "reset " + fmt_reset_hms(self._period_reset_secs())
        # 24h/7d = jendela geser, bukan periode yang reset -> tanpa countdown
        return {"24h": "jendela 24 jam terakhir",
                "7d": "jendela 7 hari terakhir"}.get(
                    p, "jendela %s" % p)

    def _q_select(self, i):
        self.q_i = i
        self.draw_all()

    def _q_cycle(self):
        n = len((self._q["snap"] or {}).get("windows") or [])
        self.q_i = (self.q_i + 1) % n if n else 0
        self.draw_all()

    def _quota_view(self):
        """Data tampilan kuota (header + panel); None bila bukan pet ChatGPT."""
        if not self._quota_provider():
            return None
        q, now = self._q, time.time()
        snap, err = q["snap"], q["err"]
        wins = snap["windows"] if snap else []
        self.q_i = clamp(self.q_i, 0, max(0, len(wins) - 1))
        stale = bool(err) or (bool(q["t"]) and now - q["t"] > self.q_poll * 3)
        V = {"wins": wins, "snap": snap, "err": err, "stale": stale,
             "plan": snap["plan"] if snap else "", "left_pct": None,
             "tab": "KUOTA", "label": "CHILL", "low": False,
             "used_txt": "", "txt": "", "mood": ""}
        if wins:
            w = wins[self.q_i]
            used = 100.0 if snap["limit_reached"] else w["used"]
            left = 100.0 - used
            V.update(left_pct=left, tab=w["tab"],
                     label="HOT" if used >= 85 else ("WARM" if used >= 60
                                                     else "CHILL"),
                     low=left <= self.warn_low)
            rem = self._q_remaining(w)
            V["used_txt"] = "%s terpakai · reset %s" % (fmt_pct(used),
                                                       fmt_reset_hms(rem))
            V["mood"] = ("kuota %s habis - tunggu reset" % w["name"]
                         if snap["limit_reached"] else
                         "kuota %s tersisa %s" % (w["name"], fmt_left(left)))
            age = int(now - q["t"])
            V["txt"] = "diperbarui %s lalu · cek tiap %d dtk%s" % (
                fmt_reset_in(age), self.q_poll,
                " · GAGAL: " + err.msg if err else "")
        else:
            V["used_txt"] = err.msg if err else \
                "memuat kuota %s..." % self._quota_label()
            V["mood"] = V["used_txt"]
            V["txt"] = "kuota " + self._quota_label()
        return V

    def _draw_quota_panel(self, Q, top, pnl, edge, bw2):
        """Panel pet ChatGPT: kuota akun (5 jam / mingguan / kredit)."""
        c, s, W = self.c, self.s, self.W
        pad, ix = s(14), s(26)
        y = top + s(26)
        link = RED if Q["err"] else (MUTED if (Q["stale"] or not Q["snap"])
                                     else GREEN)
        c.create_oval(s(18), y - s(4), s(26), y + s(4), fill=link, width=0,
                      tags="ui")
        tid = self.tx(s(34), y, self._quota_label().upper(), ORANGE, 15, True)
        name_x = c.bbox(tid)[2] + s(10)
        self.tx(name_x, y, self.fit("· kuota akun" + (" " + Q["plan"]
                                                       if Q["plan"] else ""),
                                    W - s(142) - name_x - s(8), 10), MUTED, 10)
        tabs = [w["tab"] for w in Q["wins"][:3]] + ["\u21bb"]
        for i, lab in enumerate(tabs):
            x0 = W - s(130) + (i % 2) * s(60)
            yc = y - s(3) + (i // 2) * s(25)
            refresh = i == len(tabs) - 1
            on = (not refresh) and i == self.q_i
            self.box(x0, yc - s(10), x0 + s(54), yc + s(10), lab,
                     (lambda: self._quota_kick(True)) if refresh
                     else (lambda i=i: self._q_select(i)),
                     fill=MINT if on else SURFACE,
                     fg=ON_ACCENT if on else MUTED,
                     outline=MINT if on else LINE, size=9)
        # lencana + ucapan
        y += s(40)
        badge = Q["label"] if Q["label"] in MoodController.ORDER else "STABLE"
        bcol = self._mood_color(badge)
        bw = self.measure(badge, 10, True) + s(16)
        self.chamfer(s(18), y - s(10), s(18) + bw, y + s(10), s(10),
                     fill=bcol, width=0)
        self.tx(s(18) + bw / 2.0, y, badge, self._mood_foreground(badge), 10,
                True, "center")
        mx = s(18) + bw + s(12)
        self.tx(mx, y, self.fit('"%s"' % Q["mood"], W - mx - s(18), 10), FG, 10)
        y += s(20)
        self.tx(s(18), y, self.fit(Q["txt"], W - s(36), 9),
                RED if Q["err"] else MUTED, 9)
        self._card_n = max(10, int((W - 2 * ix) / (8.0 * self.k * self.dpi)))
        ct = y + s(14)
        for i, w in enumerate(Q["wins"][:3]):
            left = 0.0 if Q["snap"]["limit_reached"] else 100.0 - w["used"]
            col = self._col(left)
            on = i == self.q_i
            self.card(pad, ct, W - pad, ct + s(78), r=s(12),
                      outline=mix(LINE, col, 0.45) if on else LINE)
            yy = ct + s(24)
            self.tx(ix, yy, w["name"], BRIGHT, 12, True)
            self.tx(W - ix, yy - s(1), "sisa " + fmt_left(left), col, 13, True,
                    "e")
            self.seg(ix, yy + s(10), W - 2 * ix, s(10), left / 100.0, col,
                     self._card_n, rounded=True, empty=DARK,
                     key="quota:%s" % i)
            cap_w = W - 2 * ix
            cid = self.tx(ix, yy + s(34),
                          self.fit(self._q_caption(w), cap_w, 9), MUTED, 9)
            self._rst_items.append(
                (cid, lambda w=w, cw=cap_w: self.fit(self._q_caption(w), cw, 9)))
            self.hits.append((pad, ct, W - pad, ct + s(78),
                              (lambda i=i: self._q_select(i))))
            ct += s(88)
        if Q["snap"] and Q["snap"]["credits"] is not None:
            self.card(pad, ct, W - pad, ct + s(40), r=s(10))
            self.tx(ix, ct + s(20), "Kredit tersisa", FG, 10)
            self.tx(W - ix, ct + s(20), "%.2f" % Q["snap"]["credits"], BRIGHT,
                    11, True, "e")
            ct += s(50)
        if not Q["snap"]:                     # belum ada data: beri petunjuk
            k = Q["err"].kind if Q["err"] else ""
            lab = self._quota_label()
            if self._quota_provider() == "claude":
                cli, where = "claude", "~/.claude/.credentials.json"
            else:
                cli, where = "codex", "~/.codex/auth.json"
            lines = {
                "nocred": ("Kuota %s belum tersambung." % lab,
                           "Login sekali lewat CLI: jalankan `%s` (token di" % cli,
                           "%s), widget mendeteksinya otomatis." % where),
                "auth": ("Token %s ditolak / kedaluwarsa." % lab,
                         "Jalankan `%s` sekali agar token diperbarui," % cli,
                         "lalu ketuk \u21bb untuk coba lagi."),
            }.get(k, (Q["used_txt"], "Ketuk \u21bb untuk coba lagi.", ""))
            self.card(pad, ct, W - pad, ct + s(78), r=s(12),
                      outline=mix(LINE, RED, 0.4) if Q["err"] else LINE)
            for j, ln in enumerate(l for l in lines if l):
                self.tx(ix, ct + s(22) + j * s(18),
                        self.fit(ln, W - 2 * ix, 10 if j == 0 else 9),
                        FG if j == 0 else MUTED, 10 if j == 0 else 9, j == 0)
            ct += s(88)
        self._draw_footer(ct + s(15), pnl, top, pad)

    def _sync_theme_to_pet(self):
        """Tema ikut pet (bila 'Tema ikut pet' ON): tiap pet punya adegannya."""
        key = PETS[self.pet_i]["name"].lower()
        if self.theme_follow and key in THEMES:
            self.scene_theme = key

    def set_pet(self, i):
        self.pet_i = i % len(PETS)
        self._pet_var.set(self.pet_i)
        self._sync_theme_to_pet()
        label = apply_theme(self.scene_theme)
        self.root.configure(bg=gap_color())
        self.c.configure(bg=gap_color())
        style_tk(self.root)
        self._pet_imgs = []               # ikon menu dibuat ulang
        if getattr(self, "ai", None) is not None:
            # sinkron pet akun: pet akun aktif ikut header,
            # kalau tak ada akun aktif catat sebagai pet 9router.
            if self.ai.get("active") in self.ai.get("accounts", {}):
                self.ai["accounts"][self.ai["active"]]["pet"] = self.pet_i
            else:
                self.ai["nine_pet"] = self.pet_i
            self._save_ai()
        self._save_pos()
        self._fx_build()
        self._quota_kick(True)            # pet ChatGPT -> ambil kuota sekarang
        self.draw_all()
        if self.theme_follow and label:
            self.flash("Tema %s" % label)

    def pet_menu(self):
        """Dropdown pilih pet (klik pet di header)."""
        if not self._pet_imgs:
            self._pet_imgs = [self._pet_icon(i) for i in range(len(PETS))]
        self._pet_var.set(self.pet_i)
        m = tk.Menu(self.root, tearoff=0, font=self.ft(10), bg=BTN, fg=FG,
                    activebackground=MINT, activeforeground=ON_ACCENT,
                    selectcolor=MINT, bd=1, relief="solid")
        for i, pet in enumerate(PETS):
            if not self._pet_visible(i):
                continue
            m.add_radiobutton(label=" " + pet["name"], image=self._pet_imgs[i],
                              compound="left", variable=self._pet_var,
                              value=i, command=lambda i=i: self.set_pet(i))
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    # ---------- polling ----------
    def _schedule_poll(self, delay_ms=None):
        if self.logged_out:
            return
        if self._job:
            try:
                self.root.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
        self._job = self.root.after(
            self.interval * 1000 if delay_ms is None else delay_ms,
            self._poll)

    def _poll(self):
        if self.logged_out:
            return
        if self.fetching:
            self._schedule_poll()
            return
        self.fetching = True
        # Umpan balik langsung: footer berubah ke status memuat sebelum
        # request jaringan selesai, sehingga widget tidak terlihat macet.
        self._refresh_status()
        threading.Thread(target=self._fetch_all, daemon=True).start()

    def _stats_url(self):
        u = self.cfg.get("stats_url", "")
        api = self.period_api.get(self.period, self.period)
        if "period=" in u:
            return re.sub(r"period=[^&]*", "period=" + api, u)
        return u + ("&" if "?" in u else "?") + "period=" + api

    def _ui(self, fn):
        """Panggil fn via event loop Tk; log bila root sudah mati."""
        try:
            self.root.after(0, fn)
        except Exception:
            log_exc("ui-callback")

    def _fetch_all(self):
        period, metric = self.period, self.metric
        try:
            if self.demo:
                result = self.sim.poll(metric)
            else:
                if self.auth.enabled() and not self.auth.cookie:
                    self.auth.login()
                # /api/combos bersifat relatif statis. Saat cache masih segar
                # cukup ambil /usage/stats saja. Ketika cache perlu diperbarui,
                # kedua endpoint diambil paralel sehingga waktu tunggu awal
                # mengikuti endpoint yang paling lambat, bukan jumlah keduanya.
                now = time.time()
                due_combo = self._combo_cache is None or (
                    now - self._combo_cached_at >= self.combo_refresh)
                combo_box, combo_thread = {}, None
                if due_combo:
                    def get_combo():
                        try:
                            combo_box["models"] = self._fetch_combo()
                        except Exception as e:
                            combo_box["error"] = e
                    combo_thread = threading.Thread(target=get_combo,
                                                    daemon=True)
                    combo_thread.start()
                _t_req = time.time()
                st = self.auth.get(self._stats_url(),
                                   self.cfg.get("stats_headers"),
                                   self.timeout)
                self._last_latency = time.time() - _t_req
                if combo_thread:
                    combo_thread.join()
                    if "models" in combo_box:
                        self._combo_cache = list(combo_box["models"])
                        self._combo_cached_at = now
                    elif self._combo_cache is None:
                        raise combo_box.get("error", ValueError(
                            "gagal memuat daftar combo"))
                models = list(self._combo_cache or [])
                result = {"models": models,
                          "usage": parse_model_stats(st, metric),
                          "totals": parse_stats_totals(st, metric),
                          "raw_totals": parse_stats_components(st),
                          "running": parse_stats_running(st)}
            result["period"], result["metric"] = period, metric
            self._ui(lambda: self._apply_ok(result))
        except Exception as e:
            log_exc("polling")
            self._err_kind = classify_error(e)
            msg = str(e)[:80] or type(e).__name__
            self._ui(lambda: self._apply_err(msg))
        finally:
            self.fetching = False
            self._ui(lambda: (self._refresh_status(), self._schedule_poll()))

    def _providers_url(self):
        u = self.cfg.get("providers_url") or ""
        if not u:
            c = self.cfg.get("combos_url", "") or ""
            u = re.sub(r"/combos.*$", "/providers", c) if "/combos" in c \
                else "http://localhost:20128/api/providers"
        return u

    def _fetch_combo(self):
        """Model dari dashboard/combos. combo_name: nama, daftar, atau '*'."""
        data = self.auth.get(self.cfg["combos_url"],
                             self.cfg.get("combos_headers", {}), self.timeout)
        items = data.get("combos", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError("format combos tak dikenal")
        names = self.combo_name
        names = [names] if isinstance(names, str) else list(names)
        out, found = expand_combos(items, names)
        if not found:
            raise ValueError("combo '%s' tak ketemu" % ",".join(names))
        return out

    def _apply_ok(self, result):
        # hasil fetch periode/metrik lama (user keburu ganti tab) dibuang
        if self.logged_out or result.get("period") != self.period \
                or result.get("metric") != self.metric:
            return
        if result.get("models") is not None:
            self.models = list(result["models"])
        previous_total = self._last_total
        self.usage = result.get("usage") or []
        self.reported = result.get("totals")
        self._have = True
        self._derive()
        if self.selected and self.models and self.selected not in self.models:
            self.selected = None          # model sudah dihapus dari combo
        running = result.get("running")   # None = 9router tak mengirim infonya
        self._running = int(running or 0)
        now = time.time()
        delta = self._tot_t - previous_total if previous_total is not None else 0.0
        if running:                       # ada request berjalan -> pet sibuk
            self._mark_busy(self.interval * 1.6 + 1.0)
            self._last_activity_at = now
        elif delta > 0:
            # token baru terpakai: tanpa info `pending` sibuk selama
            # busy_seconds; dengan info itu cukup sebentar (request selesai)
            self._mark_busy(self.busy_secs if running is None
                            else min(self.busy_secs, 4.0))
            self._last_activity_at = now
            # Surprise is reserved for a genuinely large observed change and
            # is rate-limited independently from regular busy animation.
            big = max(50000.0, float(self.cfg.get("big_usage_delta", 250000)))
            if delta >= big and now - self._event_at.get("usage_jump", 0) >= 20:
                self._event_at["usage_jump"] = now
                self._trigger_reaction("wow", 2.2, speech="HOT")
        self.tracker.add(self._tot_t)
        self.hist.feed(self.period, self._tot_t, components=self._tot_parts,
                       requests=self._tot_r)
        self.last_ok, self.error = time.time(), None
        if self.period not in self._period_anchor:
            self._period_anchor[self.period] = now   # jangkar jendela reset
        self._last_total, self._err_streak = self._tot_t, 0
        if self._router_was_offline:
            self._router_was_offline = False
            self._trigger_reaction("laugh", 2.5, speech="CONNECTED", force=True)
        S_ok = self._state()
        self._intel_on_ok(S_ok, now)
        self._check_alerts(S_ok)
        self._begin_bar_animation()
        self.draw_all()
        self._refresh_pet_hud()

    def _beep(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            try:
                self.root.bell()
            except tk.TclError:
                pass

    def _notify(self, msg):
        self.alert_msg = msg
        self.alert_until = time.time() + float(
            self.alert_cfg.get("banner_seconds", 12))
        if self.alert_cfg.get("sound", True):
            self._beep()

    def _check_alerts(self, S):
        al = self.alert_cfg
        if not al.get("enabled", True):
            return
        now, msgs = time.time(), []
        if S["left_pct"] is not None and self.alert_levels:
            new, fired = next_alert_level(
                S["left_pct"], self.alert_levels,
                self._alert_lvl.get(self.period))
            self._alert_lvl[self.period] = new
            if fired:
                msgs.append("sisa token tinggal %s!" %
                            fmt_left(S["left_pct"]))
        if al.get("hot", True):
            hot = S["label"] == "HOT"
            if hot and not self._was_hot and now - self._alert_at.get(
                    "hot", 0) >= float(al.get("cooldown_seconds", 600)):
                msgs.append("pace HOT! " + S["txt"])
                self._alert_at["hot"] = now
            self._was_hot = hot
        if msgs:
            self._notify(" | ".join(msgs))
            self._intel_record("quota_warning", " | ".join(msgs))

    def _apply_err(self, msg):
        if self.logged_out:
            return
        self.error = sanitize_log_message(msg)
        self._err_streak += 1
        self._intel_on_err(self.error)
        if not self._router_was_offline:
            self._router_was_offline = True
            self._trigger_reaction("confused", 2.5, speech="DISCONNECTED", force=True)
        elif self._err_streak == 3:
            self._trigger_reaction("panic", 4.0, speech="ERROR", force=True)
        self.draw_all()
        self._refresh_pet_hud()

    # ---------- Local Intelligence (100% lokal, tanpa AI/jaringan) ----------
    # Semua metode _intel_* dibungkus try/except: kegagalan intelligence tidak
    # boleh mengganggu widget utama. Analisis berat berjalan di thread latar;
    # UI hanya disentuh lewat self._ui (main thread).
    def _intel_init(self):
        self.intel, self._intel_win = None, None
        self._err_kind, self._last_latency = None, None
        self._intel_a, self._intel_busy = None, False
        self._intel_eval_at = self._intel_an_at = 0.0
        self._intel_status = "UNKNOWN"
        self._intel_mood, self._intel_happy_until = "IDLE", 0.0
        icfg = self.cfg.get("intelligence")
        icfg = icfg if isinstance(icfg, dict) else {}
        if LocalIntelligenceEngine is None or not icfg.get("enabled", True):
            if INTEL_ERR:
                log_exc("intel-import " + INTEL_ERR)
            return
        try:
            self.intel = LocalIntelligenceEngine(
                INTEL_DEMO_PATH if self.demo else INTEL_PATH)
            self._intel_game("open")
        except Exception:
            log_exc("intel-init")
            self.intel = None

    def _intel_log(self, msg):
        log_exc(msg)

    def _intel_colors(self):
        g = globals()
        return {k: g[k] for k in ("BG", "SURFACE", "FG", "MUTED", "MINT",
                                  "YELLOW", "RED", "BTN", "ON_ACCENT", "LINE",
                                  "DARK")}

    def open_intel(self, tab="assistant"):
        if not self.intel or IntelWindow is None:
            self.flash("Local Intelligence tidak aktif")
            return
        try:
            w = self._intel_win
            if w and w.alive():
                w.focus(tab)
            else:
                self._intel_win = IntelWindow(self, self._intel_colors(), tab)
        except Exception:
            log_exc("intel-open")
            self._intel_win = None
            self.flash("gagal membuka panel intelligence")
            return
        if tab in ("insights", "session"):
            self._intel_game("usage")

    def open_statistics_view(self):
        """Menu/tombol 'Statistics' -> tab Smart Insights."""
        self.open_intel("insights")

    def _intel_ctx(self, S, now):
        official, qlimit = [], False
        for prov, q in self._qd.items():
            snap = q.get("snap") if isinstance(q, dict) else None
            if not snap:
                continue
            qlimit = qlimit or bool(snap.get("limit_reached"))
            for w in snap.get("windows", []) or []:
                ra = w.get("reset_at")
                official.append({
                    "provider": prov, "key": w.get("key", ""),
                    "name": w.get("name", ""),
                    "used": float(w.get("used", 0) or 0),
                    "reset_in": (max(0.0, float(ra) - now) if ra else None)})
        auto = S.get("bsrc") == "auto"      # batas auto = bukan batas tetap
        return {"budget": None if auto else S.get("budget"),
                "bsrc": S.get("bsrc"), "tot_t": S.get("tot_t"),
                "left_pct": S.get("left_pct"), "period": self.period,
                # hanya "today" yang benar-benar reset; 24h/7d jendela geser
                "reset_in": (self._period_reset_secs()
                             if self.period == "today" else None),
                "official": official, "quota_limit": qlimit}

    def _intel_on_ok(self, S, now):
        if not self.intel:
            return
        try:
            rows = {str(m): (u.get("prompt", 0), u.get("completion", 0),
                             u.get("requests", 0)) for m, u in self._per}
            o = self._other
            if o.get("tokens") or o.get("requests"):
                rows["(di luar combo)"] = (o.get("prompt", 0),
                                           o.get("completion", 0),
                                           o.get("requests", 0))
            ctx = self._intel_ctx(S, now)
            self.intel.poll_ok(0.0 if self.demo else self._last_latency, now)
            self._err_kind = None
            ev = self.intel.observe(rows, self.period, ctx, now)
            st = self.intel.health.status(ctx["quota_limit"])
            if st != self._intel_status:
                prev, self._intel_status = self._intel_status, st
                if prev in ("OFFLINE", "AUTH ERROR") and st in (
                        "ONLINE", "QUOTA LIMIT"):
                    self._intel_notify("provider_connection", "back",
                                       "9Router terhubung kembali.", 1)
                elif st == "QUOTA LIMIT":
                    self._intel_notify("provider_connection", st,
                                       "Kuota resmi mencapai batas.", 2)
            if ev.get("closed"):
                self._intel_session_closed(ev["closed"], ev["mission"])
            self._intel_schedule_analysis(now)
        except Exception:
            log_exc("intel-ok")

    def _intel_on_err(self, msg):
        if not self.intel:
            return
        try:
            self.intel.poll_fail(self._err_kind or "other", msg)
            st = self.intel.health.status()
            if st != self._intel_status:
                self._intel_status = st
                if st == "AUTH ERROR":
                    self._intel_notify(
                        "provider_connection", st,
                        "9Router menolak akses (auth error). Periksa login/"
                        "kredensial di dashboard 9Router.", 3)
                elif st == "OFFLINE":
                    self._intel_notify(
                        "provider_connection", st,
                        "9Router tidak terjangkau setelah beberapa percobaan "
                        "beruntun.", 2)
        except Exception:
            log_exc("intel-err")

    def _intel_quota(self, prov, snap):
        if self.intel:
            try:
                self.intel.observe_quota(prov, snap)
            except Exception:
                log_exc("intel-quota")

    def _intel_record(self, cat, text):
        if self.intel:
            try:
                self.intel.record_notification(cat, text)
            except Exception:
                log_exc("intel-record")

    def _intel_notify(self, cat, key, text, priority=2):
        """Notifikasi baru lewat NotificationCenter (cooldown/dedup/kategori)
        dan alert sistem lama (banner). Prioritas rendah hanya flash."""
        if not self.intel:
            return
        try:
            n = self.intel.notify(cat, key, text, priority)
        except Exception:
            log_exc("intel-notify")
            return
        if not n:
            return
        now = time.time()
        if n["popup"] and self.alert_cfg.get("enabled", True):
            if priority >= 3:
                self._notify(text)
            elif now >= self.alert_until:
                self.alert_msg = text
                self.alert_until = now + float(
                    self.alert_cfg.get("banner_seconds", 12))
            else:
                self.flash(text)
        else:
            self.flash(text)

    def _intel_game(self, name):
        if not self.intel:
            return
        try:
            self._intel_game_msgs(self.intel.game_event(name))
        except Exception:
            log_exc("intel-game")

    def _intel_game_msgs(self, msgs):
        if not msgs:
            return
        if any("level" in m.lower() or "Pencapaian" in m for m in msgs):
            self._intel_happy_until = time.time() + 20.0
        self._intel_notify("achievement", " | ".join(msgs), " · ".join(msgs), 1)

    def _intel_anomaly_action(self, aid, status):
        if not self.intel:
            return
        try:
            _ok, msgs = self.intel.anomaly_action(aid, status)
            self._intel_game_msgs(msgs)
        except Exception:
            log_exc("intel-anomaly")

    def _intel_session_closed(self, sm, mission_msgs):
        self._intel_notify(
            "session_summary", str(int(sm["start"])),
            "Sesi selesai: %s, %d request, %s token." % (
                intel_dur(sm["duration"]), sm["requests"],
                intel_tok(sm["tokens"])), 1)
        self._intel_game_msgs(mission_msgs)

    def _intel_schedule_analysis(self, now):
        if self._intel_busy or now - self._intel_an_at < 30.0:
            return
        self._intel_busy, self._intel_an_at = True, now
        run_eval = now - self._intel_eval_at >= 60.0
        if run_eval:
            self._intel_eval_at = now

        def work():
            new, a = [], None
            try:
                if run_eval:
                    new = self.intel.evaluate()
                a = self.intel.analyze(force=True)
            except Exception:
                log_exc("intel-analysis")
            self._ui(lambda: self._intel_after(new, a))
        threading.Thread(target=work, daemon=True).start()

    def _intel_after(self, new, a):
        self._intel_busy = False
        if a is None or not self.intel:
            return
        try:
            self._intel_a = a
            for x in new:
                self._intel_notify("anomaly", x["id"], x["text"][:140], 2)
            pr = a["prediction"]
            cands = []
            b = pr.get("budget")
            if b and b.get("ok") and not b.get("idle") and \
                    b.get("confidence") != "rendah" and (
                        b.get("hits") == "ya" or (
                            b.get("eta_slow") is not None and
                            b["eta_slow"] < 3600)):
                cands.append(("budget", "Estimasi: batas token TokenPet "
                              "tercapai ~%s lagi pada laju sekarang." %
                              intel_dur(b["eta_mid"])))
            for o in pr.get("official", []):
                r = o["result"]
                if r.get("ok") and not r.get("idle") and \
                        r.get("confidence") != "rendah" and \
                        r.get("hits") == "ya":
                    cands.append(("%s/%s" % (o["provider"], o["key"]),
                                  "Estimasi: kuota %s (%s) habis ~%s lagi, "
                                  "sebelum reset." % (
                                      o["provider"], o["name"],
                                      intel_dur(r["eta_mid"]))))
            if cands:
                self._intel_notify("quota_prediction", cands[0][0],
                                   cands[0][1], 2)
            ad = a["advice"]
            if ad.get("ok") and ad.get("best") and ad["lower_pct"] >= 25:
                self._intel_notify(
                    "smart_recommendation", ad["best"]["model"],
                    "Info: %s paling hemat token per request (%s). Bukan "
                    "penilaian kualitas." % (
                        ad["best"]["model"], intel_tok(ad["best"]["avg"])), 1)
            self._intel_mood_step()
            if self.alert_msg and time.time() < self.alert_until and \
                    not self._alert_shown:
                self.draw_all()
        except Exception:
            log_exc("intel-after")

    def _intel_predicted_hit(self):
        a = self._intel_a
        if not a:
            return False
        pr = a.get("prediction") or {}
        b = pr.get("budget")
        if b and b.get("ok") and b.get("hits") == "ya":
            return True
        return any(o["result"].get("ok") and o["result"].get("hits") == "ya"
                   for o in pr.get("official", []))

    def _intel_mood_step(self):
        """Mood cerdas (prioritas + debounce) -> reaksi animasi yang SUDAH ada."""
        if not self.intel or not self.mood_enabled:
            return
        now = time.time()
        inp = {"err_kind": self._err_kind if self.error else None,
               "err_streak": self._err_streak, "label": self._label,
               "running": self._running, "busy": now < self._busy_until,
               "predicted_hit": self._intel_predicted_hit(),
               "happy": now < self._intel_happy_until}
        mood, changed = self.intel.mood_state(inp, now)
        if not changed:
            return
        self._intel_mood = mood
        act = {"ERROR": ("panic", 3.0), "WORRIED": ("worried", 3.0),
               "SURPRISED": ("wow", 2.2), "EFFICIENT": ("smile", 2.5),
               "HAPPY": ("laugh", 2.0)}.get(mood)
        if act:
            self._trigger_reaction(act[0], act[1])
        elif mood == "SLEEPING" and not (
                self._reaction and now < self._reaction_until):
            self._idle_action, self._idle_t0 = "sleep", now
            self._idle_until = now + 10.0
            self._emo_ensure()

    def _intel_tick(self):
        if not self.intel:
            return
        try:
            n = self.tick_n
            if n % 5 == 0:
                self._intel_mood_step()
            if n % 25 == 0:
                r = self.intel.tick()
                if r:
                    self._intel_session_closed(r["summary"], r["mission"])
            if n % 1500 == 0:
                threading.Thread(target=self.intel.save, daemon=True).start()
        except Exception:
            log_exc("intel-tick")

    def _intel_shutdown(self):
        if not self.intel:
            return
        try:
            w = self._intel_win
            if w and w.alive():
                w.close()
        except Exception:
            pass
        try:
            self.intel.save()
        except Exception:
            log_exc("intel-save")

    # ---------- animasi transisi bar ----------
    def _begin_bar_animation(self):
        """Mulai transisi singkat dari nilai bar yang tampak ke data baru."""
        if self._bar_anim_job:
            try:
                self.root.after_cancel(self._bar_anim_job)
            except (tk.TclError, ValueError):
                pass
        self._bar_anim_job = None
        self._bar_anim = {"t0": time.time(), "dur": 0.30,
                          "from": dict(self._bar_values)}
        self._bar_anim_job = self.root.after(28, self._bar_anim_step)

    def _bar_fraction(self, key, target):
        """Nilai bar saat ini; target disimpan agar animasi dapat dilanjutkan."""
        target = clamp(float(target), 0.0, 1.0)
        anim = self._bar_anim
        if not key or not anim:
            if key:
                self._bar_values[key] = target
            return target
        p = clamp((time.time() - anim["t0"]) / anim["dur"], 0.0, 1.0)
        start = clamp(float(anim["from"].get(key, 0.0)), 0.0, 1.0)
        value = start + (target - start) * ease_io(p)
        self._bar_values[key] = value
        return value

    def _bar_anim_step(self):
        self._bar_anim_job = None
        anim = self._bar_anim
        if not anim:
            return
        done = time.time() - anim["t0"] >= anim["dur"]
        if done:
            self._bar_anim = None
        try:
            self.draw_all()
        except tk.TclError:
            return
        if not done:
            self._bar_anim_job = self.root.after(28, self._bar_anim_step)

    def is_stale(self):
        """Data header sudah tak segar (9router error / lama tak update)."""
        if self.demo or self.logged_out:
            return False
        if self.error:
            return True
        return bool(self.last_ok and
                    time.time() - self.last_ok > max(15, self.interval * 3))

    # ---------- turunan ----------
    def _derive(self):
        per_map, other = assign_usage(self.models, self.usage, self.aliases,
                                      self.strict_provider)
        m = self.metric
        for u in list(per_map.values()) + [other]:
            u["tokens"] = metric_value(u, m)
        self._per = [(m2, per_map[m2]) for m2 in self.models]
        self._other = other
        self._tot_parts = {"prompt": sum(u["prompt"] for _m2, u in self._per),
                           "cached": sum(u["cached"] for _m2, u in self._per),
                           "completion": sum(u["completion"]
                                             for _m2, u in self._per)}
        self._tot_t = sum(u["tokens"] for _m2, u in self._per)
        self._tot_r = sum(u["requests"] for _m2, u in self._per)

    _tot_t, _tot_r = 0.0, 0

    def _model_pct(self, entry, tokens, total):
        for k in model_keys(entry):
            if k in self.budgets and self.budgets[k] > 0:
                return tokens / self.budgets[k] * 100.0, "budget"
        if total > 0:
            return tokens / total * 100.0, "share"
        return 0.0, "share"

    def _state(self):
        per = list(self._per)
        if self.sort_tokens:
            per.sort(key=lambda p: -p[1]["tokens"])
        tot_t = self._tot_t
        # batas ikut naik sendiri mengikuti pemakaian (mode auto)
        self._prune_auto()
        self._track_auto(tot_t)
        budget, bsrc = self.budget_source()
        used_pct = (tot_t / budget * 100.0) \
            if (budget > 0 and self._have) else None   # belum ada data = "--%"
        left_pct = None if used_pct is None else max(0.0, 100.0 - used_pct)
        label, txt = "STABLE", "pace stable"
        if budget > 0 and self.last_ok and self._have:
            window = PERIOD_SECS.get(self.period, 86400)
            if self.period == "today":
                lt = time.localtime()
                window = max(60.0, 86400 - (lt.tm_hour * 3600 +
                                            lt.tm_min * 60 + lt.tm_sec))
            label, txt = self.tracker.decide(max(0.0, budget - tot_t), window,
                                             self.hot_ratio)
        low = left_pct is not None and left_pct < self.warn_low
        return dict(tot_t=tot_t, tot_r=self._tot_r, per=per, budget=budget, bsrc=bsrc,
                    left_pct=left_pct, label=label, txt=txt, low=low)

    def _collapsible(self):
        return len(self._per) > self.collapsed_rows

    def _rows_cap(self):
        avail = self.root.winfo_screenheight() - self.s(60) - self.s(340) - 60
        return min(self.max_rows, max(3, int(avail / float(self.s(56)))))

    def model_color(self, entry):
        try:
            i = self.models.index(entry)
        except ValueError:
            i = len(MODEL_COLORS)
        return MODEL_COLORS[i] if i < len(MODEL_COLORS) else OTHER_COLOR

    # ---------- primitif gambar ----------
    def tx(self, x, y, txt, fill=None, size=10, bold=False, anchor="w"):
        fill = FG if fill is None else fill      # baca tema saat ini
        return self.c.create_text(
            x, y, text=txt, fill=fill, anchor=anchor, tags="ui",
            font=self.ft(size, bold))

    def chamfer(self, x0, y0, x1, y1, r, **kw):
        """Kotak sudut terpotong (kesan piksel membulat)."""
        kw.setdefault("tags", "ui")
        kw.setdefault("joinstyle", "round")
        return self.c.create_polygon(*rpts(x0, y0, x1, y1, r), **kw)

    def seg(self, x, y, w, h, frac, col, n, bevel=False, rounded=False,
            empty=None, key=None):
        frac = self._bar_fraction(key, frac)
        if rounded:
            return self._pill(x, y, w, h, frac, col, n, empty)
        filled = int(round(n * frac))
        if frac > 0 and filled == 0:
            filled = 1
        gap = max(1, int(round((2 if w / float(n) > 6 * self.dpi else 1)
                               * self.dpi)))
        sw = (w - gap * (n - 1)) / float(n)
        hl = max(1, int(round(1.5 * self.dpi)))
        empty = DARK if empty is None else empty
        rr = max(1, int(round((3 if h > 10 * self.dpi else 2) * self.dpi)))
        for i in range(n):
            x0 = x + i * (sw + gap)
            c0 = col if i < filled else empty
            if rounded:
                xa = int(round(x0))
                xb = int(round(x + w)) if i == n - 1 else int(round(x0 + sw))
                self.c.create_rectangle(xa, y, xb, y + h, width=0, fill=c0,
                                        tags="ui")
                if i < filled:
                    self.c.create_rectangle(
                        xa, y, xb, y + hl, width=0,
                        fill=shade(c0, 0.35), tags="ui")
                continue
            self.c.create_rectangle(x0, y, x0 + sw, y + h, width=0,
                                    fill=c0, tags="ui")
            if bevel:
                self.c.create_rectangle(x0, y, x0 + sw, y + hl, width=0,
                                        fill=shade(c0, 0.3), tags="ui")
                self.c.create_rectangle(x0, y + h - hl, x0 + sw, y + h,
                                        width=0, fill=shade(c0, -0.3),
                                        tags="ui")

    def _pill(self, x, y, w, h, frac, col, n, empty=None):
        """Bar berujung bulat; segmen tipis hanya sebagai garis pemisah halus."""
        c = self.c
        empty = DARK if empty is None else empty
        r = h / 2.0
        c.create_polygon(*rpts(x, y, x + w, y + h, r, 5), fill=empty, width=0,
                         tags="ui")
        fw = 0.0
        if frac > 0:
            fw = max(h, w * frac)
            c.create_polygon(*rpts(x, y, x + fw, y + h, r, 5), fill=col,
                             width=0, tags="ui")
            if fw > h * 1.6:       # kilau tipis di sisi atas
                c.create_line(x + r, y + h * 0.3, x + fw - r, y + h * 0.3,
                              fill=shade(col, 0.32), capstyle="round",
                              width=max(1, int(round(h * 0.2))), tags="ui")
        if self.bar_style != "solid" and n > 1:
            gw = max(1, int(round(1.3 * self.dpi)))
            cut = shade(empty, 0.1)
            for i in range(1, n):
                gx = x + w * i / float(n)
                if gx < x + r or gx > x + w - r:
                    continue
                c.create_line(gx, y, gx, y + h, width=gw, tags="ui",
                              fill=empty if gx < x + fw else cut)

    def thin(self, x, y, w, h, frac, col, key=None):
        self._pill(x, y, w, h, self._bar_fraction(key, frac), col, 0,
                   BG_EMPTY)

    def bar(self, x, y, w, h, frac, col, n, key=None):
        if self.bar_style == "solid":
            self.thin(x, y, w, h, frac, col, key)
        else:
            self.seg(x, y, w, h, frac, col, n, rounded=True, empty=DARK,
                     key=key)

    def _button_surface(self, x0, y0, x1, y1, fill=None, outline=None,
                        radius=None):
        """Permukaan tombol yang tenang: radius besar, elevasi tipis, dan
        garis sorot halus. Semua tombol canvas memakai primitif ini agar
        terasa sebagai satu sistem, bukan kumpulan kotak terpisah."""
        fill = BTN if fill is None else fill
        outline = LINE if outline is None else outline
        h = max(1.0, y1 - y0)
        radius = min(h / 2.0, self.s(10)) if radius is None else radius
        lift = max(1, int(round(self.s(1.2))))
        shadow = mix(fill, BG, 0.46)
        self.chamfer(x0, y0 + lift, x1, y1 + lift, radius,
                     fill=shadow, outline="", width=0,
                     tags=("ui", "button-shadow"))
        face = self.chamfer(x0, y0, x1, y1, radius, fill=fill,
                            outline=outline, width=max(1, int(self.dpi)),
                            tags=("ui", "button-face"))
        # Garis atas yang redup memberi batas yang jelas tanpa efek bevel
        # tebal; tidak perlu pada tombol yang sangat pendek.
        if h >= self.s(12):
            inset = min(radius, max(self.s(4), h * 0.32))
            self.c.create_line(x0 + inset, y0 + max(1, lift),
                               x1 - inset, y0 + max(1, lift),
                               fill=mix(fill, FG, 0.13),
                               width=max(1, int(self.dpi)),
                               capstyle="round", tags=("ui", "button-glow"))
        return face

    def box(self, x0, y0, x1, y1, text, fn, fill=None, fg=None, size=10,
            outline=None):
        fill = BTN if fill is None else fill
        fg = FG if fg is None else fg
        outline = LINE if outline is None else outline
        self._button_surface(x0, y0, x1, y1, fill=fill, outline=outline)
        self.tx((x0 + x1) / 2, (y0 + y1) / 2, text, fg, size, True, "center")
        self.hits.append((x0, y0, x1, y1, fn))

    def _cpts(self, x0, y0, x1, y1, r):
        return rpts(x0, y0, x1, y1, r)

    def _round_mask(self, x0, y0, x1, y1, r):
        """Tutup ujung-ujung kotak di luar sudut membulat dengan warna celah
        (transparan di Windows), supaya adegan di header ikut membulat."""
        r = max(1.0, min(float(r), (x1 - x0) / 2.0, (y1 - y0) / 2.0))
        n = 7
        for cx, cy, a0, qx, qy in ((x1 - r, y0 + r, -90, x1 + 1, y0 - 1),
                                   (x1 - r, y1 - r, 0, x1 + 1, y1 + 1),
                                   (x0 + r, y1 - r, 90, x0 - 1, y1 + 1),
                                   (x0 + r, y0 + r, 180, x0 - 1, y0 - 1)):
            pts = [qx, qy]
            for i in range(n + 1):
                a = math.radians(a0 + 90.0 * i / n)
                pts += [cx + (r + 0.6) * math.cos(a), cy + (r + 0.6) * math.sin(a)]
            self.c.create_polygon(*pts, fill=gap_color(),
                                   outline=gap_color(), width=1, tags="ui")

    def card(self, x0, y0, x1, y1, fill=None, outline=None, r=None, bw=None):
        """Kartu dengan sudut terpotong; return id supaya tingginya bisa
        disesuaikan setelah isinya digambar (card_to)."""
        fill = SURFACE if fill is None else fill
        outline = LINE if outline is None else outline
        r = self.s(5) if r is None else r
        return self.c.create_polygon(
            *self._cpts(x0, y0, x1, y1, r), fill=fill, outline=outline,
            width=bw or max(1, int(self.dpi)), tags="ui", joinstyle="round")

    def card_to(self, cid, x0, y0, x1, y1, r=None):
        r = self.s(5) if r is None else r
        self.c.coords(cid, *self._cpts(x0, y0, x1, y1, r))

    def _col(self, left_pct):
        return smooth_color(left_pct, self.warn_mid, self.warn_low) \
            if left_pct is not None else BG_EMPTY

    # ---------- pet ----------
    def _unit(self):
        """Satu satuan pet dalam piksel (pet = 48 x 44 satuan)."""
        return max(3, self.s(3)) / 3.0 * PET_SCALE

    def _look_vec(self):
        """Arah lirikan mata ke kursor (halus, tetapi tak boros redraw)."""
        if not self._eye_ptr:
            return (0.0, 0.0)
        u = self._unit()
        # Titik ini diisi ulang saat pet digambar, sehingga tetap benar untuk
        # pet yang melayang, sedang bob, atau sedang memainkan ekspresi.
        cx, cy = self._pet_eye_center or (
            self.pet_x + 24 * u, self.s(58) - 24 * u)
        dx, dy = self._eye_ptr[0] - cx, self._eye_ptr[1] - cy
        d = math.hypot(dx, dy)
        if d < 1:
            return (0.0, 0.0)
        # Sedikit lebih lebar di sumbu X agar arah terasa jelas, lalu
        # dibulatkan seperempat unit supaya gambar tidak bergetar setiap px.
        amt = min(1.0, d / (54.0 * u))
        return (round(dx / d * amt * 1.25 * 4) / 4.0,
                round(dy / d * amt * 0.9 * 4) / 4.0)

    def _blink_loop(self):
        """Kedip acak: mata menutup sekejap tiap beberapa detik."""
        self._blink_until = time.time() + 0.17
        try:
            self._draw_pet(self._label in ("HOT", "CRITICAL"))
            self.root.after(190, lambda: self._draw_pet(self._label in ("HOT", "CRITICAL")))
        except tk.TclError:
            return
        self._blink_job = self.root.after(random.randint(2400, 5600),
                                          self._blink_loop)

    def _draw_pet(self, hot=False):
        c = self.c
        c.delete("pet")
        pet = PETS[self.pet_i]
        body, deco = pet["build"](self.frame)
        col = pet["colors"]
        u = self._unit()
        emo = self._cur_emo()
        now = time.time()
        if self._reaction and now < self._reaction_until:
            et0 = self._reaction_t0
        elif self._emo:
            et0 = self._emo_t0
        elif self._idle_action and now < self._idle_until:
            et0 = self._idle_t0
        else:
            et0 = self._busy_t0
        et = now - et0 if emo else 0.0
        dx = dy = 0.0
        if emo == "laugh":         # tertawa: loncat-loncat + bergetar
            dy = -abs(math.sin(et * 13)) * 5 * u
            dx = math.sin(et * 34) * 1 * u
        elif emo == "smile":       # senyum: joget mengikuti lagu
            dy = -abs(math.sin(et * 5)) * 1.4 * u
            dx = 0.0
        elif emo == "busy":        # sibuk: getar kecil seperti mengetik
            dy = -1 * u if int(et * 8) % 2 else 0
        elif emo == "angry":       # marah: gemetar
            dx = math.sin(et * 50) * 2 * u
        elif emo == "panic":       # kritis: panik tetapi tetap ringan
            dx = math.sin(et * 38) * 2.6 * u
            dy = -abs(math.sin(et * 9)) * 1.2 * u
        elif emo == "nervous":
            dx = math.sin(et * 19) * 0.9 * u
        elif emo == "bounce":
            dy = -abs(math.sin(et * 8)) * 2.4 * u
        elif emo == "stretch":
            dx = math.sin(et * 3) * .8 * u
        ox = self.pet_x + dx
        base = self.s(58)          # permukaan tanah
        lift = 0.0
        gcol = mix(GROUND, "#000000", 0.38)
        if pet["hover"]:           # melayang + bayangan di tanah
            lift = 6 * u + (2 * u if self.frame else 0)
            sh = (15 - (3 if self.frame else 0)) * u
            c.create_oval(ox + 24 * u - sh, base - 1.6 * u,
                          ox + 24 * u + sh, base + 1.4 * u, fill=gcol,
                          width=0, tags="pet")
        else:                      # bayangan kontak kecil di tanah
            c.create_oval(ox + 24 * u - 15 * u, base - 1.4 * u,
                          ox + 24 * u + 15 * u, base + 1.8 * u, fill=gcol,
                          width=0, tags="pet")
        bob = 0.0 if pet["hover"] else (0.9 * u if self.frame else 0.0)
        oy = base - lift - PET_H * u + bob + dy
        sel = self.acc.get(pet["name"].lower())
        self._ant_hidden = False
        if sel:
            draw_accessories("back", c, ox, oy, u, pet, sel,
                             mix(BG, "#000000", 0.72), now)
            hk = HAT_KEYS.get(pet["name"].lower())
            if hk and sel.get("hat"):          # topi bawaan diganti
                body = [pr for pr in body if pr[-1] not in hk]
                deco = [pr for pr in deco if pr[-1] not in hk]
                self._ant_hidden = True
        if hot:   # garis kecepatan di belakang (kanan)
            for i, ddx in enumerate((6 * u, 20 * u)):
                yy = base - (8 + i * 7) * u
                c.create_line(ox + PET_W * u + ddx, yy,
                              ox + PET_W * u + ddx + 12 * u, yy, fill=MUTED,
                              width=max(2, 2 * u), capstyle="round",
                              tags="pet")
        edge = mix(BG, "#000000", 0.72)       # kontur gelap agar pet menonjol
        ow = max(2, round(2.7 * u))

        def X(v):
            return ox + v * u

        def Y(v):
            return oy + v * u

        def shape(pr, fill, outline, w, join=True):
            k = pr[0]
            if k == "o":
                _, cx, cy, rx, ry = pr[:5]
                return c.create_oval(X(cx - rx), Y(cy - ry), X(cx + rx),
                                     Y(cy + ry), fill=fill, outline=outline,
                                     width=w, tags="pet")
            if k == "r":
                _, x0, y0, x1, y1, rad = pr[:6]
                pts = rpts(X(x0), Y(y0), X(x1), Y(y1), rad * u, 5)
            else:
                pts = [X(v) if i % 2 == 0 else Y(v)
                       for i, v in enumerate(pr[1])]
            return c.create_polygon(*pts, fill=fill, outline=outline, width=w,
                                    joinstyle="round", tags="pet")
        for pr in body:                       # kontur siluet
            shape(pr, edge, edge, ow)
        for pr in body:                       # isi (poligon dibulatkan)
            fc = col[pr[-1]]
            shape(pr, fc, fc if pr[0] == "p" else "",
                  max(2, round(2.0 * u)) if pr[0] == "p" else 0)
        for pr in deco:
            fc = col[pr[-1]]
            shape(pr, fc, fc if pr[0] == "p" else "", 1 if pr[0] == "p" else 0)
        face_emo = {"panic": "worried", "nervous": "worried",
                    "bounce": "smile", "stretch": "smile",
                    "yawn": "wow", "sleep": None, "status": "busy",
                    "look_left": None, "look_right": None, "look_up": None}
        fe = face_emo.get(emo, emo) if emo else \
            ("worried" if self._low else ("wow" if hot else None))
        eyes = pet["face"]["eyes"]
        self._pet_eye_center = (
            ox + sum(p[0] for p in eyes) / float(len(eyes)) * u,
            oy + sum(p[1] for p in eyes) / float(len(eyes)) * u)
        look = self._look_vec()
        if emo == "look_left":
            look = (-1.0, 0.0)
        elif emo == "look_right":
            look = (1.0, 0.0)
        elif emo == "look_up":
            look = (0.0, -0.9)
        self._draw_face(pet, fe, et, ox, oy, u,
                        now < self._blink_until or emo == "sleep", look)
        if sel:
            draw_accessories("front", c, ox, oy, u, pet, sel, edge, now)
        if hot or self._low or emo == "panic":
            c.create_text(ox + PET_W * u + self.s(6), oy + self.s(4), text="!",
                          fill=RED, tags="pet", font=self.ft(12, True))
        if emo == "sleep":
            c.create_text(ox + PET_W * u + self.s(5), oy + self.s(9), text="zZ",
                          fill=MUTED, tags="pet", font=self.ft(10, True))

    def _draw_face(self, pet, emo, et, ox, oy, u, blink, look):
        """Wajah: mata berkedip & melirik, alis, pipi, mulut + efek kecil.
        emo: None | smile | laugh | busy | angry | worried | wow."""
        if pet["face"].get("led"):
            self._draw_led_face(pet, emo, et, ox, oy, u, blink, look)
            return
        f = pet["face"]
        col = pet["colors"]
        c = self.c
        ink = col[f["ink"]]
        glow = f.get("glow", False)

        def X(v):
            return ox + v * u

        def Y(v):
            return oy + v * u

        def oval(cx, cy, rx, ry, fill, out="", w=0):
            c.create_oval(X(cx - rx), Y(cy - ry), X(cx + rx), Y(cy + ry),
                          fill=fill, outline=out, width=w, tags="pet")

        def line(pts, color=ink, w=1.6, smooth=False):
            c.create_line(*[X(v) if i % 2 == 0 else Y(v)
                            for i, v in enumerate(pts)], fill=color,
                          width=max(1, round(w * u)), capstyle="round",
                          joinstyle="round", smooth=smooth, tags="pet")

        def arc(cx, cy, rx, ry, st, ex, style="arc", color=ink, w=1.6,
                fill=""):
            c.create_arc(X(cx - rx), Y(cy - ry), X(cx + rx), Y(cy + ry),
                         start=st, extent=ex, style=style, outline=color,
                         fill=fill, width=max(1, round(w * u)), tags="pet")
        rx, ry = f["er"]
        lx, ly = look[0] * 1.0, look[1] * 0.8
        typing = glow and emo == "busy"        # Nova: ">_" di layar visor
        if typing:
            vx, vy = f["visor"]
            c.create_text(X(vx), Y(vy + 0.4),
                          text=">_" if int(et * 2.4) % 2 else ">",
                          fill=ink, font=(MONO, self.fz(12), "bold"),
                          tags="pet")
        # Senyum saat pet di-hover tetap mempertahankan tatapan ke kursor;
        # hanya tawa penuh yang menutup mata menjadi bentuk ^ ^.
        happy = emo == "laugh"
        for i, (ex, ey) in enumerate(f["eyes"]):
            if typing:
                break
            sg = -1 if i == 0 else 1
            if happy:                          # mata ^ ^
                arc(ex, ey + ry * 0.6, rx * 1.3, ry * 1.0, 25, 130, "arc",
                    ink, 1.9)
                continue
            if blink and emo not in ("angry", "wow"):
                arc(ex, ey - 0.7, rx * 1.15, 1.7, 200, 140, "arc", ink, 1.7)
                continue
            if glow:                           # pendar lembut di visor
                oval(ex + lx, ey + ly, rx * 1.55, ry * 1.4,
                     mix(col["N"], ink, 0.22))
            if emo == "busy":                  # fokus: mata sipit + alis datar
                oval(ex + lx, ey + 0.5, rx * 0.95, ry * 0.5, ink)
                line([ex - rx - 0.3, ey - ry * 0.9 - 0.7,
                      ex + rx + 0.3, ey - ry * 0.9 - 0.7], ink, 1.5)
                continue
            if emo == "angry":                 # alis miring ke tengah
                oval(ex, ey + 0.6, rx * 0.92, ry * 0.7, ink)
                line([ex + sg * (rx + 0.9), ey - ry - 2.0,
                      ex - sg * (rx + 0.5), ey - ry + 0.1], ink, 1.8)
                continue
            k = 1.12 if emo in ("worried", "wow") else 1.0
            oval(ex + lx, ey + ly, rx * k, ry * k, ink)
            hl = mix(ink, "#FFFFFF", 0.78 if not glow else 0.6)
            oval(ex + lx - rx * 0.32 * k, ey + ly - ry * 0.36 * k,
                 rx * 0.42 * k, ry * 0.34 * k, hl)
            if f.get("glint"):
                oval(ex + lx + rx * 0.4, ey + ly + ry * 0.45, rx * 0.26,
                     ry * 0.2, col[f["glint"]])
            if emo == "worried":               # alis sedih
                line([ex + sg * (rx + 0.5), ey - ry - 0.7,
                      ex - sg * (rx + 0.3), ey - ry - 2.6], ink, 1.5)
        if f.get("blush") and emo not in ("angry", "busy", "worried", "wow"):
            amt = 0.9 if happy else 0.42       # pipi merona
            bc = mix(col[f["base"]], f["blush"], amt)
            for i, (ex, ey) in enumerate(f["eyes"]):
                sg = -1 if i == 0 else 1
                oval(ex + sg * rx * 0.95, ey + ry * 1.75 + 0.9,
                     2.7 if happy else 2.3, 1.5 if happy else 1.3, bc)
        mx, my = f["mouth"]
        mw = f["mw"]
        if typing:
            pass
        elif emo == "smile":                   # senyum lebar terbuka
            arc(mx, my - mw * 0.2, mw * 0.5, mw * 0.5, 180, 180, "chord",
                ink, 1, ink)
            oval(mx, my + mw * 0.2, mw * 0.24, mw * 0.12, TONGUE)
        elif emo == "laugh":                   # tertawa: mulut buka-tutup
            op = 0.75 + 0.25 * abs(math.sin(et * 14))
            arc(mx, my - mw * 0.22, mw * 0.62, mw * 0.62 * op, 180, 180,
                "chord", ink, 1, ink)
            oval(mx, my + mw * 0.24 * op, mw * 0.3, mw * 0.14 * op, TONGUE)
        elif emo == "busy":                    # mulut kecil bergerak
            if int(et * 4) % 2:
                oval(mx, my, mw * 0.12, mw * 0.1, ink)
            else:
                line([mx - mw * 0.2, my, mx + mw * 0.2, my], ink, 1.5)
        elif emo == "angry":                   # cemberut
            arc(mx, my + mw * 0.3, mw * 0.4, mw * 0.28, 40, 100, "arc", ink,
                1.7)
        elif emo == "worried":                 # bibir bergelombang
            line([mx - mw * 0.36, my, mx - mw * 0.18, my - 0.9, mx, my,
                  mx + mw * 0.18, my - 0.9, mx + mw * 0.36, my], ink, 1.5,
                 True)
        elif emo == "wow":                     # mulut bulat "o"
            oval(mx, my + 0.3, mw * 0.15, mw * 0.19, ink)
        else:                                  # senyum tipis
            arc(mx, my - mw * 0.2, mw * 0.4, mw * 0.3, 215, 110, "arc", ink,
                1.5)
        # ---- efek di dekat kepala ----
        q = max(1, self.s(2))
        if emo == "angry":                     # urat marah merah
            vx, vy = X(38.5), Y(4.0)
            for a, b, a2, b2 in ((-3, -1, -1, -1), (-3, -1, -3, 1),
                                 (3, -1, 1, -1), (3, -1, 3, 1)):
                c.create_line(vx + a * q, vy + b * q, vx + a2 * q, vy + b2 * q,
                              fill=RED, width=max(2, q), capstyle="round",
                              tags="pet")
        elif emo in ("busy", "worried", "wow"):   # keringat menetes
            ph = (et * 1.4) % 1.0 if emo == "busy" else 0.35
            sx, sy = X(f.get("sweat", 38.0)), Y(7 + ph * 8)
            d = max(1.5, 1.4 * u)
            c.create_polygon(sx, sy - d * 1.7, sx + d, sy + d * 0.3, sx,
                             sy + d * 1.3, sx - d, sy + d * 0.3,
                             smooth=True, fill=mix("#7FD0FF", BG, ph ** 3),
                             width=0, tags="pet")
        elif emo == "smile":                   # efek lagu: 1 nada (ringan)
            ph = (et * 0.6) % 1.0
            c.create_text(ox + 41 * u + math.sin(ph * 6) * 2.5 * u,
                          oy + 12 * u - ph * 18 * u, text="\u266a",
                          fill=mix(MINT, BG, ph ** 2.2),
                          font=self.ft(11, True), tags="pet")
        elif emo == "laugh":                   # "ha ha" naik
            ph = (et * 1.6) % 1.0
            c.create_text(X(PET_W) + self.s(12), oy + self.s(16) - ph * self.s(16),
                          text="ha ha" if int(et * 3.2) % 2 else "haha",
                          fill=mix(FG, BG, ph ** 2), tags="pet",
                          font=self.ft(9, True))

    def _draw_led_face(self, pet, emo, et, ox, oy, u, blink, look):
        """Wajah layar LED Robo: mata, alis, dan mulut digambar sebagai lampu.

        emo: None | smile | laugh | busy | angry | worried | wow
        Warna lampu ikut suasana: cyan biasa, kuning saat sisa menipis,
        merah saat marah. Saat `busy` (model sedang jalan): mata menyipit
        dan memindai kiri-kanan, tiga titik 'memproses' di mulut, garis
        pindai turun di layar, lampu antena & dada berdenyut (lebih cepat
        bila HOT)."""
        f, col, c = pet["face"], pet["colors"], self.c
        sx0, sy0, sx1, sy1 = f["screen"]
        scr = col["K"]
        ink = col[f["ink"]]
        if emo == "angry":
            ink = "#FF5A5A"
        elif emo == "worried" or (emo == "busy" and self._low):
            ink = "#FFC857"
        spd = 1.8 if (emo == "busy" and self._label in ("HOT", "CRITICAL")) else 1.0

        def X(v):
            return ox + v * u

        def Y(v):
            return oy + v * u

        def oval(cx, cy, rx, ry, fill, out="", w=0):
            c.create_oval(X(cx - rx), Y(cy - ry), X(cx + rx), Y(cy + ry),
                          fill=fill, outline=out, width=w, tags="pet")

        def led(cx, cy, rx, ry, fill):             # lampu persegi membulat
            c.create_polygon(*rpts(X(cx - rx), Y(cy - ry), X(cx + rx),
                                   Y(cy + ry), min(rx, ry) * u, 4),
                             fill=fill, width=0, tags="pet")

        def line(pts, color=ink, w=1.5, smooth=False):
            c.create_line(*[X(v) if i % 2 == 0 else Y(v)
                            for i, v in enumerate(pts)], fill=color,
                          width=max(1, round(w * u)), capstyle="round",
                          joinstyle="round", smooth=smooth, tags="pet")

        def arc(cx, cy, rx, ry, st, ex, style="arc", color=ink, w=1.6,
                fill=""):
            c.create_arc(X(cx - rx), Y(cy - ry), X(cx + rx), Y(cy + ry),
                         start=st, extent=ex, style=style, outline=color,
                         fill=fill, width=max(1, round(w * u)), tags="pet")

        rx, ry = f["er"]
        lx, ly = look[0] * 1.1, look[1] * 0.8
        halo1, halo2 = mix(scr, ink, 0.15), mix(scr, ink, 0.32)
        # Senyum saat pet di-hover tetap mempertahankan tatapan ke kursor;
        # hanya tawa penuh yang menutup mata menjadi bentuk ^ ^.
        happy = emo == "laugh"
        blush = f.get("blush")

        if emo == "busy":              # garis pindai turun di layar
            yy = sy0 + 2.4 + ((et * 0.8 * spd) % 1.0) * (sy1 - sy0 - 4.8)
            line([sx0 + 3.6, yy, sx1 - 3.6, yy], mix(scr, ink, 0.22), 0.9)

        for i, (ex, ey) in enumerate(f["eyes"]):
            sg = -1 if i == 0 else 1           # -1 mata kiri, +1 mata kanan
            if happy:                          # mata ^ ^ + pipi merona
                arc(ex, ey + ry * 0.55, rx * 1.15, ry * 0.95, 25, 130,
                    "arc", ink, 2.1)
                if blush:
                    oval(ex + sg * rx * 1.4, ey + ry + 1.9, 2.1, 1.1,
                         mix(scr, blush, 0.85))
                continue
            if emo == "angry":                 # mata miring ke tengah
                pts = [ex + sg * rx, ey - ry - 0.6, ex - sg * rx,
                       ey - ry * 0.15, ex - sg * rx, ey + ry,
                       ex + sg * rx, ey + ry]
                oval(ex, ey + 0.2, rx * 1.6, ry * 1.4, halo1)
                c.create_polygon(*[X(v) if k % 2 == 0 else Y(v)
                                   for k, v in enumerate(pts)], fill=ink,
                                 outline=ink, width=max(1, round(u)),
                                 joinstyle="round", tags="pet")
                continue
            if emo == "wow":                   # mata bulat besar + pupil kecil
                oval(ex, ey, rx * 1.7, ry * 1.5, halo1)
                oval(ex, ey, rx * 1.3, ry * 1.12, mix(ink, "#FFFFFF", 0.4))
                oval(ex + lx * 0.5, ey + ly * 0.5, rx * 0.5, rx * 0.5, scr)
                continue
            if emo == "busy":                  # fokus: mata menyapu kiri-kanan
                scan = math.sin(et * 3.4 * spd) * 1.8
                ecx, ecy, erx, ery = ex + scan, ey + 0.5, rx, ry * 0.78
                brow = ey - ry * 0.78 - 1.1
                line([ex - rx - 0.3, brow, ex + rx + 0.3, brow], ink, 1.4)
            elif emo == "worried":
                ecx, ecy = ex + lx * 0.6, ey + ly * 0.6
                erx, ery = rx * 1.05, ry * 1.12
                line([ex + sg * (rx + 0.5), ey - ry * 1.12 - 0.5,
                      ex - sg * rx, ey - ry * 1.12 - 2.6], ink, 1.5)
            else:                              # biasa: melirik kursor, kedip
                ecx, ecy, erx, ery = ex + lx, ey + ly, rx, ry
                if blink:
                    ery, ecy = 0.55, ecy + ry * 0.12
            if ery > 1.2:                      # pendar lembut di sekitar mata
                oval(ecx, ecy, erx * 1.7, ery * 1.45, halo1)
                oval(ecx, ecy, erx * 1.3, ery * 1.22, halo2)
            led(ecx, ecy, erx, ery, ink)
            if ery > 1.8:                      # kilau kecil di mata
                oval(ecx - erx * 0.38, ecy - ery * 0.42, erx * 0.3,
                     ery * 0.22, mix(ink, "#FFFFFF", 0.82))

        # ---- mulut ----
        mx, my = f["mouth"]
        mw = f["mw"]
        if emo == "smile":                     # senyum lebar terbuka
            arc(mx, my - mw * 0.25, mw * 0.55, mw * 0.52, 180, 180, "chord",
                ink, 1, ink)
            oval(mx, my + mw * 0.2, mw * 0.27, mw * 0.1, mix(scr, ink, 0.4))
        elif emo == "laugh":                   # buka-tutup
            op = 0.75 + 0.25 * abs(math.sin(et * 14))
            arc(mx, my - mw * 0.25, mw * 0.6, mw * 0.55 * op, 180, 180,
                "chord", ink, 1, ink)
        elif emo == "busy":                    # tiga titik "memproses"
            act = int(et * 5 * spd) % 3
            for j in range(3):
                r = 0.95 if j == act else 0.62
                oval(mx + (j - 1) * 2.5, my - (0.5 if j == act else 0.0), r, r,
                     ink if j == act else mix(scr, ink, 0.5))
        elif emo == "angry":                   # cemberut
            arc(mx, my + mw * 0.3, mw * 0.4, mw * 0.28, 40, 100, "arc", ink,
                1.7)
        elif emo == "worried":                 # bibir bergelombang
            line([mx - mw * 0.36, my, mx - mw * 0.18, my - 0.9, mx, my,
                  mx + mw * 0.18, my - 0.9, mx + mw * 0.36, my], ink, 1.5,
                 True)
        elif emo == "wow":                     # mulut bulat "o"
            oval(mx, my + 0.2, mw * 0.17, mw * 0.2, ink)
            oval(mx, my + 0.2, mw * 0.07, mw * 0.09, scr)
        else:                                  # senyum tipis
            arc(mx, my - mw * 0.2, mw * 0.42, mw * 0.3, 215, 110, "arc", ink,
                1.5)

        # ---- lampu antena & dada (ikut suasana / berdenyut saat busy) ----
        pulse = 0.5 + 0.5 * math.sin(et * 9 * spd) if emo == "busy" else 0.0
        if not getattr(self, "_ant_hidden", False) and \
                (emo or self._low or self._label in ("HOT", "CRITICAL")):
            ax, ay = f["antenna"]
            if emo == "busy":
                oval(ax, ay, 3.1 + 1.3 * pulse, 3.1 + 1.3 * pulse, "",
                     mix(ink, "#000000", 0.45 * (1 - pulse)), 1)
            oval(ax, ay, 2.3, 2.3, mix(ink, "#FFFFFF", 0.55 * pulse))
        if emo:
            lx2, ly2 = f["lamp"]
            on = emo != "busy" or int(et * 4 * spd) % 2 == 0
            oval(lx2, ly2, 1.0, 1.0, ink if on else mix(scr, ink, 0.3))

        # ---- efek di dekat kepala ----
        q = max(1, self.s(2))
        if emo == "angry":                     # urat marah merah
            vx, vy = X(38.5), Y(4.0)
            for a, b, a2, b2 in ((-3, -1, -1, -1), (-3, -1, -3, 1),
                                 (3, -1, 1, -1), (3, -1, 3, 1)):
                c.create_line(vx + a * q, vy + b * q, vx + a2 * q, vy + b2 * q,
                              fill=RED, width=max(2, q), capstyle="round",
                              tags="pet")
        elif emo in ("worried", "wow"):        # keringat menetes di samping
            ph = 0.35 if emo == "wow" else (et * 1.2) % 1.0
            sx, sy = X(f.get("sweat", 45.6)), Y(9 + ph * 6)
            d = max(1.5, 1.4 * u)
            c.create_polygon(sx, sy - d * 1.7, sx + d, sy + d * 0.3, sx,
                             sy + d * 1.3, sx - d, sy + d * 0.3,
                             smooth=True, fill="#7FD0FF", width=0,
                             tags="pet")
        elif emo == "smile":                   # efek lagu: 1 nada (ringan)
            ph = (et * 0.6) % 1.0
            c.create_text(ox + 45 * u + math.sin(ph * 6) * 2.5 * u,
                          oy + 12 * u - ph * 18 * u, text="\u266a",
                          fill=mix(MINT, BG, ph ** 2.2),
                          font=self.ft(11, True), tags="pet")
        elif emo == "laugh":                   # "ha ha" naik
            ph = (et * 1.6) % 1.0
            c.create_text(X(PET_W) + self.s(12),
                          oy + self.s(16) - ph * self.s(16),
                          text="ha ha" if int(et * 3.2) % 2 else "haha",
                          fill=mix(FG, BG, ph ** 2), tags="pet",
                          font=self.ft(9, True))

    # ---------- ikon menu pet (raster halus dari bentuk yang sama) ----------
    @staticmethod
    def _in_shape(pr, x, y, e=0.0):
        k = pr[0]
        if k == "o":
            _, cx, cy, rx, ry = pr[:5]
            rx, ry = rx + e, ry + e
            return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0
        if k == "r":
            _, x0, y0, x1, y1, rad = pr[:6]
            x0, y0, x1, y1, rad = x0 - e, y0 - e, x1 + e, y1 + e, rad + e
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                return False
            qx = min(x - (x0 + rad), (x1 - rad) - x)
            qy = min(y - (y0 + rad), (y1 - rad) - y)
            return qx >= 0 or qy >= 0 or qx * qx + qy * qy <= rad * rad
        pts = pr[1]
        n = len(pts) // 2
        inside, near = False, e * e
        for i in range(n):
            ax, ay = pts[2 * i], pts[2 * i + 1]
            bx, by = pts[2 * ((i + 1) % n)], pts[2 * ((i + 1) % n) + 1]
            if (ay > y) != (by > y) and \
                    x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
            if e > 0 and not inside:
                dx2, dy2 = bx - ax, by - ay
                tt = clamp(((x - ax) * dx2 + (y - ay) * dy2) /
                           (dx2 * dx2 + dy2 * dy2 or 1.0), 0.0, 1.0)
                if (x - ax - tt * dx2) ** 2 + (y - ay - tt * dy2) ** 2 <= near:
                    return True
        return inside

    def _pet_icon(self, i):
        pet = PETS[i]
        body, deco = pet["build"](0)
        col, f = pet["colors"], pet["face"]
        eyes = [("o", ex, ey, f["er"][0], f["er"][1], f["ink"])
                for ex, ey in f["eyes"]]
        top = deco + eyes
        S, W_, H_, ss = 0.58, 30, 27, 2
        edge, bgc = mix(BTN, "#000000", 0.62), BTN
        ox_, oy_ = (W_ - PET_W * S) / 2.0, (H_ - PET_H * S) / 2.0
        e = 1.15 / S

        def rgb(h):
            h = h.lstrip("#")
            return [int(h[j:j + 2], 16) for j in (0, 2, 4)]
        rows = []
        for py in range(H_):
            row = []
            for pxl in range(W_):
                acc = [0, 0, 0]
                for sy in range(ss):
                    for sx in range(ss):
                        x = (pxl + (sx + 0.5) / ss - ox_) / S
                        y = (py + (sy + 0.5) / ss - oy_) / S
                        hc = None
                        for pr in reversed(top):
                            if self._in_shape(pr, x, y):
                                hc = col[pr[-1]]
                                break
                        if hc is None:
                            for pr in reversed(body):
                                if self._in_shape(pr, x, y):
                                    hc = col[pr[-1]]
                                    break
                        if hc is None:
                            hc = edge if any(self._in_shape(pr, x, y, e)
                                             for pr in body) else bgc
                        for j, v in enumerate(rgb(hc)):
                            acc[j] += v
                n = ss * ss
                row.append("#%02x%02x%02x" % tuple(int(a / n) for a in acc))
            rows.append("{" + " ".join(row) + "}")
        img = tk.PhotoImage(master=self.root, width=W_, height=H_)
        img.put(" ".join(rows))
        return img

    def _icon(self, kind, x, y, fn):
        c, col, k = self.c, MUTED, self.k * self.dpi

        def p(*v):
            return [x + a * k if i % 2 == 0 else y + a * k
                    for i, a in enumerate(v)]
        if kind == "sun":
            c.create_oval(*p(4, 4, 12, 12), outline=MINT, width=max(1, int(self.dpi)), tags="ui")
            for a in range(0, 360, 45):
                aa = math.radians(a)
                x1 = x + self.s(8) + math.cos(aa) * self.s(7); y1 = y + self.s(8) + math.sin(aa) * self.s(7)
                x2 = x + self.s(8) + math.cos(aa) * self.s(10); y2 = y + self.s(8) + math.sin(aa) * self.s(10)
                c.create_line(x1, y1, x2, y2, fill=MINT, width=max(1, int(self.dpi)), tags="ui")
        elif kind == "gear":            # config: 3 slider (bukan gir lagi)
            for i, yy in enumerate((4, 8, 12)):
                c.create_line(*p(1, yy, 15, yy), fill=col,
                              width=max(1, int(round(1.4 * k))), tags="ui")
                kx = (11, 5, 9)[i]
                c.create_oval(*p(kx - 2, yy - 2, kx + 2, yy + 2), fill=col,
                              width=0, tags="ui")
        elif kind == "bars":
            for i, hh in enumerate((6, 12, 9)):
                c.create_rectangle(*p(i * 5, 15 - hh, i * 5 + 4, 15),
                                   fill=col, width=0, tags="ui")
        elif kind == "spark":
            c.create_polygon(*p(8, 0, 10, 6, 16, 8, 10, 10, 8, 16, 6, 10,
                                0, 8, 6, 6), fill=col, width=0, tags="ui")
        elif kind == "crown":
            c.create_polygon(*p(0, 4, 4, 9, 8, 2, 12, 9, 16, 4, 14, 14,
                                2, 14), fill=col, width=0, tags="ui")
        elif kind == "bulb":           # bohlam lampu hias
            c.create_oval(*p(3, 0, 13, 10), fill=col, width=0, tags="ui")
            c.create_rectangle(*p(6, 10, 10, 13), fill=col, width=0,
                               tags="ui")
            c.create_rectangle(*p(6, 14, 10, 15.5), fill=col, width=0,
                               tags="ui")
        elif kind == "weather":        # awan + tetes hujan
            wc = MINT
            c.create_oval(*p(0, 4, 8, 11), fill=wc, width=0, tags="ui")
            c.create_oval(*p(4, 0, 13, 9), fill=wc, width=0, tags="ui")
            c.create_oval(*p(8, 4, 16, 11), fill=wc, width=0, tags="ui")
            c.create_rectangle(*p(3, 7, 13, 11), fill=wc, width=0, tags="ui")
            for dx in (4, 8, 12):
                c.create_line(*p(dx, 12.5, dx - 1, 15.5), fill=wc,
                              width=max(1, int(k)), capstyle="round",
                              tags="ui")
        elif kind == "hat":            # topi tinggi kecil
            c.create_polygon(*p(4, 1, 12, 1, 12, 10, 4, 10), fill=col,
                             width=0, tags="ui")
            c.create_polygon(*p(0, 13, 1, 10, 15, 10, 16, 13, 14, 15, 2, 15),
                             fill=col, width=0, tags="ui")
            c.create_rectangle(*p(4, 7, 12, 9), fill=SURFACE, width=0,
                               tags="ui")
        elif kind == "settings":        # settings: gir bergerigi + lubang hub
            cx, cy = x + 8 * k, y + 8 * k
            tw = max(2, int(round(2.4 * k)))
            for a in range(0, 360, 45):
                aa = math.radians(a)
                x1 = cx + math.cos(aa) * 5.0 * k
                y1 = cy + math.sin(aa) * 5.0 * k
                x2 = cx + math.cos(aa) * 7.6 * k
                y2 = cy + math.sin(aa) * 7.6 * k
                c.create_line(x1, y1, x2, y2, fill=col, width=tw,
                              capstyle="round", tags="ui")
            c.create_oval(*p(4, 4, 12, 12), outline=col,
                          width=max(2, int(round(2.2 * k))), tags="ui")
            c.create_oval(*p(6.4, 6.4, 9.6, 9.6), outline=col,
                          width=max(1, int(round(1.4 * k))), tags="ui")
        elif kind == "power":
            col2 = GREEN if self.autostart else col
            wd = max(2, 2 * k)
            c.create_arc(*p(1, 2, 15, 16), start=120, extent=300,
                         style="arc", outline=col2, width=wd, tags="ui")
            c.create_line(*p(8, 0, 8, 8), fill=col2, width=wd, tags="ui")
        pad = 3 * k
        self.hits.append((x - pad, y - pad, x + 16 * k + pad,
                          y + 16 * k + pad, fn))

    # ---------- status footer ----------
    def _status(self):
        avail = self._footer_status_avail()
        if time.time() < self.flash_until:
            return self.fit(self.flash_msg, avail, 10), YELLOW_TXT
        if self.fetching:
            return "memuat data 9router...", MINT
        if self.logged_out:
            return "logged out", MUTED
        if self.error:
            txt, col = "ERR: %s" % self.error, RED
        else:
            txt = (fmt_ago(time.time() - self.last_ok) if self.last_ok
                   else "connecting...")
            if self.demo:
                txt = "demo · " + txt
            col = FG
        return self.fit(txt, avail, 10), col

    def _clip_status(self, txt):
        """Potong teks status agar tidak menimpa bar ikon footer di kirinya."""
        avail = self._footer_status_avail()
        return self.fit(txt, avail, 10)

    def _refresh_status(self):
        if self._status_id is None:
            return
        txt, col = self._status()
        try:
            self.c.itemconfigure(self._status_id, text=self._clip_status(txt),
                                 fill=col)
        except tk.TclError:
            pass

    # ---------- gambar utama ----------
    def _bulb(self, bx, by, col, r, tint=None):
        """Satu bohlam gantung: soket, pendar berlapis, kaca bening + kilau."""
        c, s = self.c, self.s
        wire = tint or mix(BG, "#000000", 0.55)
        glows = []
        for k, (gr, on, off) in enumerate(((3.1, .13, .04), (2.0, .26, .08))):
            gid = c.create_oval(bx - r * gr, by + r * .5 - r * gr,
                                bx + r * gr, by + r * .5 + r * gr,
                                fill=mix(BG, col, on), width=0, tags="ui")
            glows.append((gid, on, off))
        c.create_rectangle(bx - r * .5, by - r * 1.5, bx + r * .5, by - r * .3,
                           fill=mix(wire, "#9AA0A6", .45), width=0, tags="ui")
        c.create_line(bx - r * .5, by - r * .9, bx + r * .5, by - r * .9,
                      fill=wire, width=1, tags="ui")
        body = c.create_polygon(
            bx - r * .55, by - r * .3, bx + r * .55, by - r * .3,
            bx + r * .95, by + r * .55, bx + r * .6, by + r * 1.5,
            bx, by + r * 1.95, bx - r * .6, by + r * 1.5,
            bx - r * .95, by + r * .55, fill=col, smooth=True,
            outline=mix(col, "#000000", .35), width=1, tags="ui")
        hl = c.create_oval(bx - r * .55, by + r * .15, bx - r * .2, by + r * .85,
                           fill=mix(col, "#FFFFFF", .7), width=0, tags="ui")
        self._bulbs.append((body, glows, col, len(self._bulbs), hl))

    def _draw_lights(self, W):
        """Dekorasi gantung di tepi atas header."""
        s, c = self.s, self.c
        self._bulbs = []
        kind = self.decor
        if kind == "none":
            return
        x0, x1 = s(12), W - s(12)
        n_seg = max(1, int(round((x1 - x0) / s(110))))
        seg = (x1 - x0) / n_seg

        def sag(t):                       # 0..1 -> lendutan kabel
            return math.sin(t * math.pi) * s(6)

        def swag(xa, y0=3):
            return [v for j in range(13) for v in
                    (xa + j / 12.0 * seg, s(y0) + sag(j / 12.0))]
        for k in range(n_seg):
            xa = x0 + k * seg
            if kind == "lights":          # lampu natal klasik
                wire = mix("#2E6B3A", BG, .2)
                c.create_line(*swag(xa), fill=wire, width=max(1, s(1.2)),
                              smooth=True, tags="ui")
                for j in range(1, 6):
                    t = j / 6.0
                    self._bulb(xa + t * seg, s(3) + sag(t) + s(1),
                               BULB_COLS[(k * 5 + j) % len(BULB_COLS)],
                               s(2.7), wire)
            elif kind == "warm":          # lampu peri kuning hangat
                wire = mix(BG, "#8A6A3A", .45)
                c.create_line(*swag(xa), fill=wire, width=1, smooth=True,
                              tags="ui")
                for j in range(1, 11):
                    t = j / 11.0
                    bx, by = xa + t * seg, s(3) + sag(t) + s(1.5)
                    col = "#FFD27A" if j % 3 else "#FFE9B0"
                    self._bulb(bx, by, col, s(1.7), wire)
            elif kind == "garland":       # untaian cemara + lampu
                pts = swag(xa, 4)
                c.create_line(*pts, fill="#1F5A33", width=max(4, s(6)),
                              smooth=True, capstyle="round", tags="ui")
                c.create_line(*pts, fill="#2F8A4B", width=max(2, s(3.5)),
                              smooth=True, capstyle="round", tags="ui")
                for j in range(1, 8):
                    t = j / 8.0
                    bx, by = xa + t * seg, s(4) + sag(t)
                    if j % 2:
                        self._bulb(bx, by, BULB_COLS[(k * 4 + j) % 5], s(1.9),
                                   "#1F5A33")
                    else:
                        c.create_oval(bx - s(1.6), by - s(1.6), bx + s(1.6),
                                      by + s(1.6), fill="#E5484D", width=0,
                                      tags="ui")
                bx, by = xa, s(4)
                for sg in (-1, 1):        # pita merah di tiap sambungan
                    c.create_polygon(bx, by, bx + sg * s(5), by - s(3),
                                     bx + sg * s(5), by + s(3),
                                     fill="#E5484D", width=0, tags="ui")
                c.create_oval(bx - s(1.6), by - s(1.6), bx + s(1.6),
                              by + s(1.6), fill="#B8333A", width=0, tags="ui")
            elif kind == "neon":
                col = ("#FF4FD8", "#4FE3FF")[k % 2]
                pts = swag(xa)
                g1 = c.create_line(*pts, fill=mix(BG, col, .14),
                                   width=max(6, s(9)), smooth=True,
                                   capstyle="round", tags="ui")
                g2 = c.create_line(*pts, fill=mix(BG, col, .32),
                                   width=max(4, s(5.5)), smooth=True,
                                   capstyle="round", tags="ui")
                ln = c.create_line(*pts, fill=mix(col, "#FFFFFF", .45),
                                   width=max(2, s(2)), smooth=True,
                                   capstyle="round", tags="ui")
                self._bulbs.append((ln, [(g1, .14, .04), (g2, .32, .1)], col,
                                    k, None))
            elif kind == "bunting":
                wire = mix(BG, "#000000", .5)
                c.create_line(*swag(xa), fill=wire, width=max(1, s(1)),
                              smooth=True, tags="ui")
                for j in range(1, 6):
                    t = (j - .5) / 5.0
                    bx, by = xa + t * seg, s(3) + sag(t)
                    col = BULB_COLS[(k * 5 + j) % len(BULB_COLS)]
                    c.create_polygon(bx - s(4.2), by, bx + s(4.2), by, bx,
                                     by + s(9), fill=col,
                                     outline=mix(col, "#000000", .3), width=1,
                                     tags="ui")
            elif kind == "lanterns":
                bx = xa + seg * 0.5
                col = ("#E5484D", "#F7A23C")[k % 2]
                wire = mix(BG, "#000000", .5)
                c.create_line(bx, 1, bx, s(8), fill=wire, width=max(1, s(1)),
                              tags="ui")
                g1 = c.create_oval(bx - s(10), s(3), bx + s(10), s(26),
                                   fill=mix(BG, col, .10), width=0, tags="ui")
                g2 = c.create_oval(bx - s(7), s(6), bx + s(7), s(23),
                                   fill=mix(BG, col, .2), width=0, tags="ui")
                bid = c.create_oval(bx - s(5), s(8), bx + s(5), s(20),
                                    fill=col, outline=mix(col, "#000000", .35),
                                    width=max(1, s(1)), tags="ui")
                for dx in (-2.5, 0, 2.5):
                    c.create_line(bx + s(dx), s(8.5), bx + s(dx), s(19.5),
                                  fill=mix(col, "#000000", .28), width=1,
                                  smooth=True, tags="ui")
                c.create_rectangle(bx - s(2.5), s(7), bx + s(2.5), s(9),
                                   fill="#F7C948", width=0, tags="ui")
                c.create_rectangle(bx - s(2.5), s(19.5), bx + s(2.5), s(21),
                                   fill="#F7C948", width=0, tags="ui")
                for dx in (-1.2, 0, 1.2):
                    c.create_line(bx + s(dx), s(21), bx + s(dx * 1.6), s(26),
                                  fill="#F7C948", width=1, tags="ui")
                self._bulbs.append((bid, [(g1, .10, .03), (g2, .2, .06)], col,
                                    k, None))
            elif kind == "hologram":
                # Garis data tipis yang berdenyut, bukan lampu gantung biasa.
                base_y = s(8 + (k % 2) * 4)
                for j, col in enumerate(("#7DF9FF", "#FF6FD8", "#A78BFA")):
                    bx = xa + (j + 1) * seg / 4.0
                    glow = c.create_oval(bx - s(7), base_y - s(7),
                                          bx + s(7), base_y + s(7),
                                          fill=mix(BG, col, .12), width=0, tags="ui")
                    node = c.create_polygon(bx, base_y - s(3), bx + s(3), base_y,
                                            bx, base_y + s(3), bx - s(3), base_y,
                                            fill=col, width=0, tags="ui")
                    c.create_line(bx, 1, bx, base_y - s(3), fill=mix(BG, col, .55),
                                  width=max(1, s(1)), tags="ui")
                    self._bulbs.append((node, [(glow, .12, .035)], col, k + j, None))
            elif kind == "stars":
                for j, (t, ln) in enumerate(((.3, 5), (.7, 10))):
                    bx = xa + t * seg
                    col = "#FFE27A" if (k + j) % 2 == 0 else "#9BE3FF"
                    c.create_line(bx, 1, bx, s(ln), fill=mix(BG, "#000000", .4),
                                  width=max(1, s(1)), tags="ui")
                    cy, r = s(ln) + s(4.5), s(4.5)
                    gid = c.create_oval(bx - r * 1.7, cy - r * 1.7,
                                        bx + r * 1.7, cy + r * 1.7,
                                        fill=mix(BG, col, .12), width=0,
                                        tags="ui")
                    pts = []
                    for q in range(10):
                        a = -math.pi / 2 + q * math.pi / 5
                        rr = r if q % 2 == 0 else r * .45
                        pts += [bx + rr * math.cos(a), cy + rr * math.sin(a)]
                    bid = c.create_polygon(*pts, fill=col, width=0, tags="ui")
                    self._bulbs.append((bid, [(gid, .12, .03)], col, k + j,
                                        None))
            elif kind == "orbit":
                bx, by = xa + seg * .5, s(10 + (k % 2) * 3)
                col = ("#9BE3FF", "#FF8AD1")[k % 2]
                glow = c.create_oval(bx - s(13), by - s(6), bx + s(13), by + s(6),
                                      outline=mix(BG, col, .22), width=max(2, s(3)),
                                      tags="ui")
                ring = c.create_oval(bx - s(10), by - s(4), bx + s(10), by + s(4),
                                     outline=col, width=max(1, s(1)), tags="ui")
                dot = c.create_oval(bx + s(7), by - s(2), bx + s(10), by + s(1),
                                    fill="#FFE27A", width=0, tags="ui")
                # Titik orbit yang berdenyut; cincin tetap tipis agar tidak
                # berubah menjadi cakram saat animasi dekorasi berjalan.
                self._bulbs.append((dot, [(glow, .22, .05)], "#FFE27A", k,
                                    None))

    def _decor_twinkle(self):
        """Lampu berkedip bergantian (dipanggil dari _tick)."""
        n = self.tick_n // 3
        for bid, glows, col, i, hl in self._bulbs:
            on = (n + i) % 4 != 0
            try:
                self.c.itemconfigure(bid, fill=col if on else
                                     mix(col, BG, 0.65))
                for gid, a_on, a_off in glows:
                    self.c.itemconfigure(gid, fill=mix(BG, col,
                                                       a_on if on else a_off))
                if hl:
                    self.c.itemconfigure(hl, fill=mix(col, "#FFFFFF", .7)
                                         if on else mix(col, BG, .5))
            except tk.TclError:
                return

    def _draw_decor(self, cx, tw, gy):
        """Hiasan latar sesuai tema pet; semua piksel-art dari kotak."""
        c, s = self.c, self.s
        u = max(2, s(2))
        kind = DECOR

        def R(x0, y0, x1, y1, col):
            c.create_rectangle(x0, y0, x1, y1, fill=col, width=0, tags="ui")

        if kind == "cactus":
            R(cx, gy - s(14), cx + u, gy, DECOR_COL)
            R(cx - 2 * u, gy - s(6), cx, gy - s(6) + u, DECOR_COL)
            R(cx - 2 * u, gy - s(10), cx - u, gy - s(6), DECOR_COL)
            R(cx + u, gy - s(4), cx + 3 * u, gy - s(4) + u, DECOR_COL)
            R(cx + 2 * u, gy - s(8), cx + 3 * u, gy - s(4), DECOR_COL)
        elif kind == "pine":
            R(cx - u // 2, gy - u, cx + u, gy, "#6B4E3A")        # batang
            for i, half in enumerate((3, 3, 2, 2, 1, 1)):        # dari bawah
                y1 = gy - u * (i + 1)
                R(cx - half * u, y1 - u, cx + half * u + u // 2, y1,
                  DECOR_COL)
                if i in (1, 3, 5):                               # salju
                    R(cx - (half - 1) * u, y1 - u,
                      cx + (half - 1) * u + u // 2, y1 - u + max(1, u // 2),
                      DECOR_COL2)
        elif kind == "seaweed":
            for off, col, n in ((0, DECOR_COL, 7), (3 * u, DECOR_COL, 5),
                                (-3 * u, DECOR_COL2, 4)):
                for i in range(n):
                    x = cx + off + (u if i % 2 else 0)
                    R(x, gy - u * (i + 1), x + u, gy - u * i, col)
        elif kind == "crystal":
            for off, h in ((0, 6), (-3 * u, 3), (3 * u, 4)):
                for i in range(h):
                    w = min(i + 1, 3, h - i + 1)
                    y = gy - u * (h - i)
                    R(cx + off - w * u // 2, y, cx + off + w * u // 2 + u // 2,
                      y + u, DECOR_COL)
                    R(cx + off - w * u // 2, y, cx + off - w * u // 2 + u // 2,
                      y + u, DECOR_COL2)
        elif kind == "lantern":
            # Lampu teras kecil untuk tema Senja.
            R(cx - u, gy - s(11), cx + 2 * u, gy - s(2), "#553145")
            R(cx - 2 * u, gy - s(10), cx + 3 * u, gy - s(3), DECOR_COL)
            R(cx - u, gy - s(9), cx + 2 * u, gy - s(4), DECOR_COL2)
            R(cx - 2 * u, gy - s(12), cx + 3 * u, gy - s(10), "#3A2338")
            R(cx - u, gy - s(15), cx + 2 * u, gy - s(12), "#3A2338")
        elif kind == "holo":
            # Pilar hologram dan partikel energi untuk Gravitasi Nol.
            for off, h, col in ((0, 10, DECOR_COL2), (-4 * u, 6, DECOR_COL),
                                (4 * u, 7, DECOR_COL)):
                for i in range(h):
                    x = cx + off + (u if i % 2 else 0)
                    R(x, gy - u * (i + 1), x + u, gy - u * i, col)
            R(cx - s(11), gy - s(1), cx + s(11), gy + u, DECOR_COL2)
        elif kind == "asteroid":
            # Batu-batu bulan rendah agar tema luar angkasa terasa tandus.
            for off, h in ((-5 * u, 2), (-2 * u, 4), (2 * u, 3), (5 * u, 2)):
                for i in range(h):
                    w = min(i + 1, h - i + 1)
                    R(cx + off - w * u // 2, gy - u * (i + 1),
                      cx + off + w * u // 2 + u, gy - u * i, DECOR_COL)
                    if i == h - 1:
                        R(cx + off, gy - u * (i + 1), cx + off + u,
                          gy - u * i, DECOR_COL2)
        elif kind == "city":
            # Pilar equalizer: melompat naik lalu MENABRAK sisi bawah bar
            # status (kilatan + percikan), jatuh lagi, terus bergantian.
            # Posisinya dihitung tiap frame di _sc_update (jenis "eq").
            bar_bot = s(HDR_BAR_Y0 + HDR_BAR_H)
            room = max(s(4), gy - bar_bot - 1)      # tinggi maks sebelum nabrak
            heights = (7, 12, 9, 16, 11, 19, 8, 14, 22, 10, 17)
            pw, pitch = max(s(3), s(4)), s(5)
            capw = max(1, s(1.5))
            for i, h in enumerate(heights):
                bx = cx + (i - len(heights) // 2) * pitch
                col = DECOR_COL if i % 3 == 0 else mix(DECOR_COL, BG, .35)
                h0 = room * (0.2 + 0.35 * h / 22.0)
                apex = room * (1.3 if i % 4 != 2 else 0.8) - h0
                body = c.create_rectangle(bx, gy - h0, bx + pw, gy, fill=col,
                                          width=0, tags="ui")
                cap = c.create_rectangle(bx, gy - h0, bx + pw, gy - h0 + capw,
                                         fill=mix(col, "#FFFFFF", .55),
                                         width=0, tags="ui")
                glow = c.create_rectangle(bx - u, bar_bot, bx + pw + u,
                                          bar_bot + max(1, s(2)),
                                          fill="#FFFFFF", width=0, tags="ui",
                                          state="hidden")
                sp = [c.create_rectangle(0, 0, 1, 1, fill=SPARK, width=0,
                                         tags="ui", state="hidden")
                      for _ in range(2)]
                self._sc.append({"k": "eq", "body": body, "cap": cap,
                                 "glow": glow, "sp": sp, "x": bx, "w": pw,
                                 "gy": gy, "room": room, "h0": h0,
                                 "apex": max(1.0, apex), "capw": capw,
                                 "per": 1.5 + 0.17 * (i % 5), "ph": i * 0.37,
                                 "bar": bar_bot, "col": col, "u": u,
                                 "imp": None})
            R(cx - s(31), gy - s(1), cx + s(31), gy + u, DECOR_COL2)
        elif kind == "stars":
            for fx, fy, col in ((0.00, 12, DECOR_COL), (0.30, 7, DECOR_COL2),
                                (0.55, 13, DECOR_COL), (0.80, 6, DECOR_COL2)):
                x, y = cx + int(tw * fx), gy - s(fy)
                R(x, y - u, x + u, y + 2 * u, col)               # plus
                R(x - u, y, x + 2 * u, y + u, col)

    # ---------- adegan latar header (per tema) + animasinya ----------
    def _ridge(self, base, amp, col, seed, step=6, f1=0.021, f2=0.057):
        """Siluet gunung/bukit bertangga ala piksel."""
        s, W = self.s, self.W
        q, stp = 1, max(2, s(min(step, 2)))
        unit = max(1.0, self.k * self.dpi)
        pts, x = [2, base], 2
        while x < W - 2:
            xu = x / unit
            h = (math.sin(xu * f1 + seed) * 0.5 +
                 math.sin(xu * f2 + seed * 2.3) * 0.3 + 0.8) / 1.6
            y = base - int(amp * h / q) * q
            x2 = min(x + stp, W - 2)
            pts += [x, y, x2, y]
            x = x2
        pts += [W - 2, base]
        self.c.create_polygon(*pts, fill=col, width=0, tags=("ui", "scene"))

    def _day_phase(self):
        """Fase waktu lokal untuk SEMUA tema: malam -> pagi -> siang -> senja -> malam."""
        lt = time.localtime()
        hour = lt.tm_hour + lt.tm_min / 60.0
        if 5.0 <= hour < 10.0:
            return "morning"
        if 10.0 <= hour < 16.0:
            return "day"
        if 16.0 <= hour < 19.0:
            return "sunset"
        return "night"

    def _phase_sky(self, top, bot, phase):
        """Toning lembut agar semua tema ikut siklus waktu tanpa kehilangan identitas tema."""
        if phase == "morning":
            return mix(top, "#D98E73", 0.16), mix(bot, "#FFE0B2", 0.20)
        if phase == "day":
            return mix(top, "#62B6D9", 0.14), mix(bot, "#EAF8FF", 0.14)
        if phase == "sunset":
            return mix(top, "#C95F5F", 0.26), mix(bot, "#F2A15E", 0.25)
        return mix(top, "#020611", 0.34), mix(bot, "#091326", 0.34)

    def _draw_scene(self, gy, tx0, tw, tint=0.0):
        c, s, W, sc = self.c, self.s, self.W, SCENE
        self._sc = []
        if not sc:
            return
        T = ("ui", "scene")
        top, bot = sc["sky"]
        phase = self._day_phase()
        top, bot = self._phase_sky(top, bot, phase)
        top = mix(top, ALERT_BG, tint)
        bot = mix(bot, ALERT_BG, tint)
        nb = 10
        for i in range(nb):
            ya = 1 + (gy - 1) * i / float(nb)
            yb = 1 + (gy - 1) * (i + 1) / float(nb)
            c.create_rectangle(2, ya, W - 2, yb + 1,
                               fill=mix(top, bot, i / float(nb - 1)),
                               width=0, tags=T)
        mid = mix(top, bot, 0.5)
        kind, u = sc["kind"], max(2, s(2))
        rng = random.Random(11)
        now = time.time()

        def sky_at(y):
            return mix(top, bot, clamp((y - 1) / float(max(1, gy - 1)), 0, 1))

        def stars(n, ymax, col):
            for _ in range(n):
                x = 4 + rng.random() * (W - 8)
                y = 2 + rng.random() * ymax
                i = c.create_rectangle(x, y, x + max(1, s(1.5)),
                                       y + max(1, s(1.5)), fill=col,
                                       width=0, tags=T)
                self._sc.append({"k": "twinkle", "id": i,
                                 "ph": rng.random() * 6.28,
                                 "sp": 2.0 + rng.random() * 3.0,
                                 "bg": sky_at(y), "col": col})

        if kind == "snownight":
            if phase == "night":
                stars(22, gy * 0.6, "#DDE3FF")
                mx, my, r = W - s(118), s(15), s(7)
                c.create_oval(mx-r, my-r, mx+r, my+r, fill=sc["moon"], width=0, tags=T)
                c.create_oval(mx-r+s(4), my-r-s(2), mx+r+s(4), my+r-s(2), fill=sky_at(my), width=0, tags=T)
            else:
                sx = W * (0.22 if phase == "morning" else 0.72)
                sy = s(14 if phase != "sunset" else 18)
                rr = s(6 if phase != "sunset" else 8)
                c.create_oval(sx-rr, sy-rr, sx+rr, sy+rr, fill="#FFF0B0", width=0, tags=T)
            self._ridge(gy, s(24), sc["far"], 1.3)
            self._ridge(gy, s(12), sc["near"], 4.1)
        elif kind == "sunset":
            if phase == "night":
                mx, my, rr = W * 0.72, s(15), s(7)
                c.create_oval(mx-rr, my-rr, mx+rr, my+rr, fill="#FFF1C7", width=0, tags=T)
                c.create_oval(mx-rr+s(4), my-rr-s(2), mx+rr+s(4), my+rr-s(2), fill=sky_at(my), width=0, tags=T)
                stars(12, gy * 0.48, "#FFE8A3")
            else:
                cx, cy = int(W * (0.22 if phase == "morning" else 0.71)), gy - s(23 if phase != "sunset" else 21)
                ids = []
                for r, col in zip((s(25), s(19), s(13), s(7)), sc["rings"]):
                    ids.append(c.create_oval(cx-r, cy-r, cx+r, cy+r, fill=col, width=0, tags=T))
                self._sc.append({"k": "sun", "ids": ids, "cols": sc["rings"]})
            self._ridge(gy, s(15), sc["far"], 2.2, f1=0.014)
            self._ridge(gy, s(8), sc["near"], 5.7)
            if phase in ("morning", "day", "sunset"):
                self._sc.append({"k": "bird", "x": W * 0.45, "y": s(11),
                                 "id": c.create_line(0, 0, 0, 0, fill="#3A1D12",
                                                     width=max(2, s(2)), tags=T)})
        elif kind == "twilight":
            # Senja sengaja bukan gurun: teras kota, lampu hangat, dan bulan
            # tipis memberi siluet yang jelas berbeda dari bukit pasir.
            if phase == "night":
                stars(18, gy * .48, "#FFE2B1")
                mx, my, rr = W * .72, s(14), s(7)
                c.create_oval(mx - rr, my - rr, mx + rr, my + rr,
                              fill=sc["moon"], width=0, tags=T)
                c.create_oval(mx - rr + s(3), my - rr - s(2), mx + rr + s(3),
                              my + rr - s(2), fill=sky_at(my), width=0, tags=T)
            else:
                sx = W * (.22 if phase == "morning" else .73)
                sy, rr = s(16 if phase != "sunset" else 20), s(7)
                c.create_oval(sx - rr, sy - rr, sx + rr, sy + rr,
                              fill="#FFD58A", width=0, tags=T)
            # Lapisan gedung rendah dan pagar rooftop.
            for j, (fx, hh, ww) in enumerate(((.04, 15, 38), (.21, 23, 55),
                                               (.53, 17, 44), (.78, 28, 62))):
                x0, y0 = W * fx, gy - s(hh)
                c.create_rectangle(x0, y0, min(W - 2, x0 + s(ww)), gy,
                                   fill=sc["far"], width=0, tags=T)
                if j in (1, 3):
                    for wx in range(int(x0 + s(6)), int(min(W - 2, x0 + s(ww - 4))),
                                    max(s(10), 8)):
                        c.create_rectangle(wx, y0 + s(7), wx + max(1, s(2)),
                                           y0 + s(10), fill=sc["lamp"], width=0,
                                           tags=T)
            c.create_rectangle(2, gy - s(5), W - 2, gy + s(2), fill=sc["near"],
                               width=0, tags=T)
            for lx in (W * .16, W * .84):
                c.create_line(lx, gy - s(22), lx, gy - s(5), fill="#392540",
                              width=max(1, s(2)), tags=T)
                c.create_oval(lx - s(3), gy - s(24), lx + s(3), gy - s(18),
                              fill=sc["lamp"], width=0, tags=T)
        elif kind == "antigravity":
            # Dunia anti-gravitasi: lantai kisi holografik dan pulau-pulau
            # melayang. Tidak ada planet/bulan agar tak mirip tema angkasa.
            stars(14, gy * .44, "#D8CEFF")
            horizon = gy - s(8)
            for yy in range(int(horizon), gy + s(2), max(2, s(4))):
                t = (yy - horizon) / float(max(1, gy - horizon))
                c.create_line(2, yy, W - 2, yy, fill=mix(sc["near"], sc["grid"],
                                                           .18 + .38 * t),
                              width=max(1, int(self.dpi)), tags=T)
            for xx in range(-W // 2, W * 2, max(8, s(22))):
                c.create_line(W * .5, horizon, xx, gy + s(2),
                              fill=mix(sc["near"], sc["grid"], .35),
                              width=max(1, int(self.dpi)), tags=T)
            for j, (fx, fy, ww) in enumerate(((.15, 23, 24), (.48, 14, 33),
                                               (.79, 29, 20))):
                tag = "island%d" % j
                x0, y0, iw = W * fx, gy - s(fy), s(ww)
                c.create_oval(x0 - iw * .15, y0 - s(3), x0 + iw * 1.15,
                              y0 + s(5), fill=sc["island"], width=0, tags=T + (tag,))
                c.create_polygon(x0, y0 + s(2), x0 + iw, y0 + s(2),
                                 x0 + iw * .72, y0 + s(9), x0 + iw * .24,
                                 y0 + s(9), fill=mix(sc["island"], "#000000", .32),
                                 width=0, tags=T + (tag,))
                c.create_oval(x0 + iw * .42 - s(3), y0 - s(7),
                              x0 + iw * .42 + s(3), y0 - s(1), fill=sc["orb"],
                              width=0, tags=T + (tag,))
                self._sc.append({"k": "bob", "tag": tag, "off": 0.0,
                                 "amp": s(1.2 + j * .4)})
        elif kind == "ocean":
            for j in range(3):
                xa = W * (0.12 + 0.34 * j)
                wd, sl = s(46), s(30)
                tag = "ray%d" % j
                c.create_polygon(xa, 1, xa + wd, 1, xa + wd - sl, gy,
                                 xa - sl, gy,
                                 fill=mix(mid, sc["ray"], 0.15), width=0,
                                 tags=T + (tag,))
                self._sc.append({"k": "sway", "tag": tag, "off": 0.0,
                                 "ph": j * 2.1, "amp": s(9)})
            self._ridge(gy, s(16), sc["far"], 3.4, f1=0.017)
            self._ridge(gy, s(8), sc["near"], 0.6)
            for j, (col, fy, spd) in enumerate((("#FF8FB8", 34, 0.9),
                                                ("#8FE8FF", 20, 0.6))):
                fx0 = W * (0.30 + 0.4 * j)
                tag = "fish%d" % j
                tg = T + (tag,)
                y0 = s(fy)
                c.create_rectangle(fx0, y0, fx0 + 4 * u, y0 + 2 * u, fill=col,
                                   width=0, tags=tg)
                c.create_rectangle(fx0 - u, y0 - u // 2, fx0, y0 + 2 * u + u // 2,
                                   fill=col, width=0, tags=tg)
                c.create_rectangle(fx0 + 3 * u, y0 + u // 2, fx0 + 3 * u + u // 2,
                                   y0 + u, fill="#14224A", width=0, tags=tg)
                self._sc.append({"k": "drift", "tag": tag, "x": fx0,
                                 "vx": spd, "m": 30})
        elif kind == "storm":
            self._ridge(gy, s(20), sc["far"], 1.1, f2=0.09)
            self._ridge(gy, s(10), sc["near"], 3.3, f2=0.08)
            cl = []
            for j, (cxx, cyy, wd) in enumerate(((0.12, 8, 50), (0.52, 14, 60),
                                                (0.86, 5, 44))):
                tag = "cl%d" % j
                tg = T + (tag,)
                x0, y0, w0 = W * cxx, s(cyy), s(wd)
                cl.append(c.create_rectangle(x0, y0 + s(6), x0 + w0, y0 + s(14),
                                             fill=sc["cloud"], width=0,
                                             tags=tg))
                cl.append(c.create_rectangle(x0 + s(8), y0, x0 + w0 * 0.55,
                                             y0 + s(8), fill=sc["cloud"],
                                             width=0, tags=tg))
                cl.append(c.create_rectangle(x0 + w0 * 0.5, y0 + s(3),
                                             x0 + w0 * 0.85, y0 + s(9),
                                             fill=sc["cloud"], width=0,
                                             tags=tg))
                self._sc.append({"k": "drift", "tag": tag, "x": x0,
                                 "vx": 0.25 + 0.12 * j, "m": s(60)})
            self._sc.append({"k": "flash", "ids": cl, "col": sc["cloud"],
                             "next": now + 4 + random.random() * 6,
                             "until": 0.0})
        elif kind == "city":
            lt=time.localtime(); hour=lt.tm_hour+lt.tm_min/60.0
            if 5.0<=hour<10.0: phase="morning"; ptop,pbot="#5B9BC4","#A8DDF2"; skyline="#27445A"; light="#7DD3FC"
            elif 10.0<=hour<16.0: phase="day"; ptop,pbot="#3B82B6","#A5DFF5"; skyline="#31566C"; light="#67E8F9"
            elif 16.0<=hour<19.0: phase="sunset"; ptop,pbot="#334B72","#526A96"; skyline="#252F4A"; light="#38BDF8"
            else: phase="night"; ptop,pbot="#07111F","#203957"; skyline="#0D1A2A"; light="#8BE7FF"
            for i in range(nb):
                ya=1+(gy-1)*i/float(nb); yb=1+(gy-1)*(i+1)/float(nb)
                c.create_rectangle(2,ya,W-2,yb+1,fill=mix(ptop,pbot,i/float(nb-1)),width=0,tags=T)
            rng_city=random.Random(27); x=2
            while x<W-2:
                bw=s(10+rng_city.randint(0,7)); bh=s(8+rng_city.randint(0,22)); y0=gy-bh
                c.create_rectangle(x,y0,min(W-2,x+bw),gy,fill=skyline,width=0,tags=T)
                for wy in range(int(y0+s(3)),int(gy-s(2)),max(s(5),5)):
                    for wx in range(int(x+s(2)),int(min(W-2,x+bw-s(2))),max(s(5),5)):
                        if rng_city.random()>(0.35 if phase=="night" else 0.72): c.create_rectangle(wx,wy,wx+max(1,s(1.5)),wy+max(1,s(1.5)),fill=light,width=0,tags=T)
                x+=bw+max(s(2),3)
            if phase in ("morning","day","sunset"):
                sx=W*(0.72 if phase!="morning" else 0.22); sy=s(15 if phase!="sunset" else 19); rr=s(6 if phase!="sunset" else 8)
                sid=c.create_oval(sx-rr,sy-rr,sx+rr,sy+rr,fill="#38BDF8",width=0,tags=T); self._sc.append({"k":"city_sun","id":sid,"base":"#38BDF8"})
            else:
                mx,my,rr=W-s(70),s(14),s(7); c.create_oval(mx-rr,my-rr,mx+rr,my+rr,fill=sc.get("moon","#E8F2FF"),width=0,tags=T)
                c.create_oval(mx-rr+s(4),my-rr-s(2),mx+rr+s(4),my+rr-s(2),fill=sky_at(my),width=0,tags=T); stars(14,gy*.45,"#D9F4FF")
            c.create_rectangle(2,gy-s(4),W-2,gy+s(2),fill="#101820",width=0,tags=T)
            for lx in range(s(8),W-s(8),s(18)): c.create_rectangle(lx,gy-s(1),lx+s(7),gy,fill="#6B7B88",width=0,tags=T)
        elif kind == "space":
            c.create_oval(tx0 + tw * 0.62 - s(46), s(14) - s(11),
                          tx0 + tw * 0.62 + s(46), s(14) + s(11),
                          fill=mix(mid, sc["neb"], 0.30), width=0, tags=T)
            c.create_oval(tx0 + tw * 0.10 - s(40), s(36) - s(9),
                          tx0 + tw * 0.10 + s(40), s(36) + s(9),
                          fill=mix(mid, sc["neb"], 0.16), width=0, tags=T)
            self._ridge(gy, s(8), sc["far"], 2.0, f1=0.03)
            self._ridge(gy, s(4), sc["near"], 6.1)
            px_, py_, r = tx0 + tw * 0.80, s(13), s(6)
            tg = T + ("planet",)
            c.create_oval(px_ - r, py_ - r, px_ + r, py_ + r,
                          fill=sc["planet"], width=0, tags=tg)
            c.create_oval(px_ - r + s(2), py_ - r + s(1), px_ - r + s(5),
                          py_ - r + s(4), fill=shade(sc["planet"], 0.45),
                          width=0, tags=tg)
            c.create_oval(px_ - s(12), py_ - s(3), px_ + s(12), py_ + s(3),
                          outline=sc["ring"], width=max(1, s(1.5)), tags=tg)
            self._sc.append({"k": "bob", "tag": "planet", "off": 0.0,
                             "amp": s(1.6)})

    def _sc_update(self):
        c, W = self.c, self.W
        sc_ = self.k * self.dpi
        t = time.time()
        for it in self._sc:
            k = it["k"]
            if k == "twinkle":
                ph = (math.sin(t * it["sp"] + it["ph"]) + 1.0) / 2.0
                c.itemconfigure(it["id"],
                                fill=mix(it["bg"], it["col"], 0.2 + 0.8 * ph))
            elif k == "sun":
                ph = (math.sin(t * 2.4) + 1.0) / 2.0
                for i, (iid, col) in enumerate(zip(it["ids"], it["cols"])):
                    c.itemconfigure(iid, fill=shade(col, 0.16 * ph * (i + 1) / 4))
            elif k == "bird":
                it["x"] += 34.0 * sc_ * self._sc_dt
                if it["x"] > W + 20:
                    it["x"] = -20.0
                x, y, u = it["x"], it["y"], max(2, int(2 * sc_))
                up = int(t * 7) % 2
                c.coords(it["id"], x - 3 * u, y + (0 if up else u), x, y + u,
                         x + 3 * u, y + (0 if up else u))
            elif k == "sway":
                off = math.sin(t * 0.9 + it["ph"]) * it["amp"]
                c.move(it["tag"], off - it["off"], 0)
                it["off"] = off
            elif k == "bob":
                off = math.sin(t * 2.0) * it["amp"]
                c.move(it["tag"], 0, off - it["off"])
                it["off"] = off
            elif k == "drift":
                dx = it["vx"] * sc_ * self._sc_dt * 22.0
                c.move(it["tag"], dx, 0)
                it["x"] += dx
                if it["x"] > W + it["m"]:
                    c.move(it["tag"], -(W + 2 * it["m"]), 0)
                    it["x"] -= W + 2 * it["m"]
            elif k == "flash":
                if t >= it["next"]:
                    it["until"], it["next"] = t + 0.22, t + 6 + random.random() * 9
                col = mix(it["col"], "#FFFFFF", 0.22) if t < it["until"] \
                    else it["col"]
                for iid in it["ids"]:
                    c.itemconfigure(iid, fill=col)
            elif k == "sym":                  # simbol melayang naik + memudar
                ph = (t % 2.0) / 2.0
                c.coords(it["id"], it["x"] + math.sin(ph * 6.28) * it["sw"] * 2,
                         it["y"] - it["rise"] * ph)
                c.itemconfigure(it["id"], fill=mix(it["bg"], MUTED,
                                                   math.sin(ph * 3.1416)))
            elif k == "eq":                   # pilar menabrak bar status
                u_ = ((t + it["ph"]) / it["per"]) % 1.0
                raw = it["h0"] + it["apex"] * 4.0 * u_ * (1.0 - u_)
                h = min(it["room"], raw)
                top = it["gy"] - h
                x, w = it["x"], it["w"]
                c.coords(it["body"], x, top, x + w, it["gy"])
                c.coords(it["cap"], x, top, x + w, top + it["capw"])
                imp = False
                if raw >= it["room"]:         # menempel di bar: ada benturan
                    r = (it["room"] - it["h0"]) / it["apex"]
                    u_hit = (1.0 - math.sqrt(max(0.0, 1.0 - r))) / 2.0
                    imp = 0.0 <= u_ - u_hit < 0.12
                if imp != it["imp"]:
                    it["imp"] = imp
                    st = "normal" if imp else "hidden"
                    c.itemconfigure(it["glow"], state=st)
                    for sid in it["sp"]:
                        c.itemconfigure(sid, state=st)
                    c.itemconfigure(it["cap"], fill="#FFFFFF" if imp else
                                    mix(it["col"], "#FFFFFF", .55))
                if imp:                       # percikan terlempar ke samping
                    q = max(1, it["u"] // 2 + 1)
                    sx = (u_ - (1.0 - math.sqrt(max(0.0, 1.0 - (it["room"] - it["h0"]) / it["apex"]))) / 2.0) / 0.12
                    for sid, sg in zip(it["sp"], (-1, 1)):
                        px = x + w / 2.0 + sg * (w / 2.0 + q * (1 + 2.5 * sx))
                        py = it["bar"] + q * (1 + 1.5 * sx)
                        c.coords(sid, px, py, px + q, py + q)
            elif k == "gem":                  # berlian di pojok berkilau
                ph = (math.sin(t * 3.0) + 1.0) / 2.0
                c.itemconfigure(it["id"], fill=mix(it["bg"], SPARK,
                                                   0.4 + 0.6 * ph))

    def _sc_step(self):
        now = time.time()
        self._sc_dt = clamp(now - self._sc_t, 0.005, 0.2)
        self._sc_t = now
        try:
            if self._sc:
                self._sc_update()
        except Exception:                     # animasi tak boleh merusak widget
            log_exc("scene")
            self._sc = []
        self._sc_job = self.root.after(33, self._sc_step)
        # Refresh scene periodically so morning/day/sunset/night changes automatically.
        if not getattr(self, "_phase_refresh_armed", False):
            self._phase_refresh_armed = True
            self.root.after(30000, self._phase_refresh)

    def _phase_refresh(self):
        self._phase_refresh_armed = False
        try:
            self.draw_all()
        finally:
            self._phase_refresh_armed = True
            self.root.after(30000, self._phase_refresh)

    def draw_all(self):
        self._drawing = True
        try:
            self._draw_all_impl()
            self._hov_sync()
        finally:
            self._drawing = False

    def _draw_all_impl(self):
        c = self.c
        self._hov_item = None
        c.delete("ui")
        self.hits = []
        self._rst_items = []
        self._status_id = None
        W = self.W
        self.k = clamp(W / self.base_w, 0.75, 1.9)
        s = self.s
        S = self._state()
        Q = self._quota_view()            # pet ChatGPT -> tampilkan kuota akun
        if Q:
            S = dict(S)
            S.update(left_pct=Q["left_pct"], label=Q["label"], low=Q["low"],
                     txt=Q["txt"])
        S["raw_label"] = S["label"]
        S["label"] = self._update_mood(S)
        self._label, self._low = S["label"], bool(S["low"] or
                                                    S["label"] == "CRITICAL")
        hot = S["label"] in ("HOT", "CRITICAL")
        Hc = s(68)
        lp0 = S["left_pct"]
        sev = 0.0                 # 0 = aman .. 1 = kritis (warna ikut berubah)
        if lp0 is not None and self.warn_low > 0:
            lim = self.warn_low * 1.6
            sev = clamp((lim - lp0) / lim, 0.0, 1.0)
        blinking = bool(S["low"] and self.blink_on)
        bg = ALERT_BG if blinking else mix(BG, ALERT_BG, 0.45 * sev)
        edge = BORDER if lp0 is None else mix(
            BORDER, self._col(lp0), 0.22 + 0.6 * sev)
        bw2 = max(1, int(self.dpi))                 # border tipis header/panel
        c.create_polygon(*self._cpts(1, 1, W - 1, Hc - 1, s(15)), fill=bg,
                         outline=edge, width=bw2, tags=("ui", "bgrect"),
                         joinstyle="round")
        # --- header: pet di kiri, label periode, bar bersegmen, persen, ^ ---
        pct_right = W - s(50)
        sel_tok, sel_mode = None, None
        if self.selected and not Q:
            u = dict(self._per).get(self.selected,
                                    {"tokens": 0.0, "requests": 0})
            pct, mode = self._model_pct(self.selected, u["tokens"],
                                        S["tot_t"])
            fill_frac = min(100.0, pct) / 100.0
            col = GREEN if mode == "share" else self._col(100 - pct)
            ptxt = fmt_pct(pct)
            sub = short_model(self.selected, 200)
            sel_tok, sel_mode = u["tokens"], mode
        elif S["left_pct"] is not None:
            fill_frac = S["left_pct"] / 100.0      # bar = sisa, seperti "65% left"
            col = self._col(S["left_pct"])
            ptxt = fmt_left(S["left_pct"])
            sub = ""
        else:
            fill_frac, col, ptxt, sub = 0.0, BG_EMPTY, "--%", ""
        alerting = (not Q) and time.time() < self.alert_until
        self._alert_shown = alerting
        stale = Q["stale"] if Q else self.is_stale()
        self._stale_drawn = stale
        if stale:
            col = shade(col, -0.55)
            sub = "data lama - 9router tak terjangkau" if self.error \
                else "data lama"
        if alerting:
            sub = self.alert_msg

        # --- geometri responsif: semua posisi diturunkan dari ukuran nyata ---
        gy = s(58)
        px = max(2, s(3))
        self.pet_x = max(s(7), int(W * 0.035))
        lab = Q["tab"] if Q else self.tabs[self.tab_i][0]
        lab_w = self.measure(lab, 11, True)
        badge_w = lab_w + s(20)
        pet_u = self._unit()
        pet_reserved = PET_W * pet_u + s(8)
        lab_x = self.pet_x + pet_reserved
        pct_w = max(self.measure(ptxt, 15, True), self.measure("sisa", 8))
        tx0 = lab_x + badge_w + s(8)
        tx1 = pct_right - pct_w - s(14)
        tw = max(s(20), tx1 - tx0)
        dark = DARK                           # isi lencana / tombol / bar kosong
        acc = col                             # aksen header ikut status

        # teks pemakaian: "48.9M / 100.0M"
        if alerting:
            used = self.alert_msg
        elif stale:
            used = "data lama - 9router tak terjangkau" if self.error \
                else "data lama"
        elif self.selected:
            used = "%s  %s" % (fmt_tokens(sel_tok), sub)
        elif S["budget"] > 0:
            used = "%s / %s" % (fmt_tokens(S["tot_t"]) if self._have else "--",
                                fmt_tokens(S["budget"]))
        else:
            used = fmt_tokens(S["tot_t"])
        under = "lama" if stale else (
            "sisa" if not self.selected else
            ("share" if sel_mode == "share" else "terpakai"))
        hdr_err = bool(Q["err"]) if Q else bool(self.error)
        if Q:                              # header = kuota ChatGPT
            used = Q["used_txt"]
            under = ("lama" if stale else "sisa") \
                if Q["left_pct"] is not None else ""

        # adegan latar (langit, gunung, matahari/bulan/planet, dst.)
        self._draw_scene(gy, tx0, tw, 0.55 if blinking else 0.3 * sev)
        if self._fx or self._shoot:           # efek cuaca di atas adegan,
            c.tag_raise("fx", "scene")        # tetap di belakang tanah/bar/teks

        self._draw_lights(W)

        # tanah: strip bergaris + bintik/rumput + bayangan
        c.create_rectangle(s(5), gy, W - s(5), gy + s(8), fill=GROUND, width=0,
                           tags="ui")
        c.create_rectangle(s(5), gy, W - s(5), gy + max(1, s(1)), fill=GROUND_HI,
                           width=0, tags="ui")
        c.create_rectangle(s(5), gy + s(6), W - s(5), gy + s(8), fill=GROUND_LO,
                           width=0, tags="ui")
        for gx in range(s(8), W - s(10), s(15)):
            c.create_rectangle(gx, gy + s(3), gx + s(4), gy + s(5),
                               fill=GROUND_DOT, width=0, tags="ui")
        for gx in range(s(30), W - s(10), s(46)):
            c.create_rectangle(gx, gy - max(1, s(1)), gx + s(7), gy + s(2),
                               fill=GROUND_TUFT, width=0, tags="ui")

        # hiasan tema (kaktus/cemara/rumput laut/kristal/bintang)
        if tw >= s(110):
            self._draw_decor(int(tx0 + tw * 0.13), tw, gy)
        # border header digambar ulang di atas adegan supaya selalu rapi
        self._round_mask(1, 1, W - 1, Hc - 1, s(15))
        c.create_polygon(*self._cpts(1, 1, W - 1, Hc - 1, s(15)), fill="",
                         outline=edge, width=bw2, tags="ui",
                         joinstyle="round")
        # border ikut menetes 0.5px ke luar sudut -> tutup lagi supaya
        # sudut bawah jendela tidak menyisakan bracket lancip.
        self._round_mask(1, 1, W - 1, Hc - 1, s(15))

        # bar bersegmen bulat (segmen kosong gelap)
        # Bar status ditempatkan tepat di bawah badge periode (TODAY/24H/7D/ALL).
        # Ujung kanan tetap sama seperti sebelumnya; hanya titik awal diperlebar
        # ke kiri agar bar membentang dari bawah badge TODAY sampai kanan.
        hdr_bar_x = lab_x
        hdr_bar_w = max(s(20), pct_right - pct_w - s(14) - hdr_bar_x)
        self._hdr_n = max(6, int(hdr_bar_w / (10.5 * self.k * self.dpi)))
        self._hdr_x, self._hdr_w = hdr_bar_x, hdr_bar_w
        self.seg(hdr_bar_x, s(HDR_BAR_Y0), hdr_bar_w, s(HDR_BAR_H), fill_frac, col,
                 self._hdr_n, rounded=True, empty=dark, key="header")

        # Pet click opens a compact HUD; changing pet remains available from
        # Quick Actions and the context menu.
        self.hits.append((self.pet_x - s(4), gy - PET_H * pet_u - s(4),
                          self.pet_x + PET_W * pet_u + s(4), gy + s(2),
                          self.toggle_pet_hud))

        # lencana periode (klik = ganti periode)
        self._button_surface(lab_x, s(8), lab_x + badge_w, s(25), fill=dark,
                             outline=mix(BG, acc, 0.6))
        self.tx(lab_x + badge_w / 2.0, s(17), lab, acc, 11, True, "center")
        self.hits.append((lab_x, s(6), lab_x + badge_w, s(28),
                          self._q_cycle if Q else
                          (lambda: self.set_tab(
                              (self.tab_i + 1) % len(self.tabs)))))

        # "48.9M / 100.0M"
        ux = lab_x + badge_w + s(10)
        hid = self.tx(ux, s(17), self.fit(used, max(0, tx1 + s(6) - ux), 10),
                      RED if (alerting or (stale and hdr_err)) else
                      (MUTED if stale else FG), 10, alerting)
        if Q and Q["wins"]:
            def _hdr_txt(ux=ux, lim=max(0, tx1 + s(6) - ux)):
                V = self._quota_view()
                return self.fit(V["used_txt"], lim, 10) if V else ""
            self._rst_items.append((hid, _hdr_txt))

        # persen besar + keterangan kecil di bawahnya
        px = pct_right
        under_t = under
        uw = self.measure(under_t, 8, False)
        if uw > px - s(10):
            under_t = self.fit(under_t, max(s(40), px - s(10)), 8)
        self.tx(pct_right, s(27), ptxt,
                MUTED if stale else (col if S["low"] else BRIGHT), 15,
                True, "e")
        self.tx(pct_right, s(44), under_t, MUTED, 8, False, "e")

        # tombol buka/tutup: kontrol kecil dengan elevasi yang konsisten
        bx0, by0, bx1, by1 = W - s(42), s(17), W - s(14), s(42)
        self._button_surface(bx0, by0, bx1, by1, fill=dark,
                             outline=mix(BG, MUTED, 0.35))
        mx, my, a2 = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0, s(5)
        d = -a2 if self.expanded else a2
        c.create_line(mx - a2, my - d / 2.0, mx, my + d / 2.0, mx + a2,
                      my - d / 2.0, fill=FG, width=max(2, s(2)),
                      capstyle="round", joinstyle="round", tags="ui")
        self.hits.append((bx0, by0, bx1, by1, self.toggle))

        # simbol melayang di dekat pet (nada / ~ / z), hilang saat HOT / rendah
        if not (hot or S["low"]):
            sid = c.create_text(0, 0, text=SYM, fill=BG, tags="ui",
                                font=self.ft(11, True))
            self._sc.append({"k": "sym", "id": sid, "bg": mix(BG, "#000000", 0.2),
                             "x": self.pet_x + PET_W * pet_u + s(5), "y": s(30),
                             "rise": s(14), "sw": s(2)})

        # pegangan resize di tepi kanan
        for i in range(3):
            c.create_oval(W - s(5), Hc // 2 - s(7) + i * s(6), W - s(2.5),
                          Hc // 2 - s(4.5) + i * s(6), fill=BORDER,
                          width=0, tags="ui")
        self._sc_update()
        self._draw_pet(hot)
        self._draw_speech_bubble(lab_x, W - s(50))
        if not (self.expanded or self._anim):
            self._fit_window(Hc)
            return

        if getattr(self, "view", "main") == "settings":
            self._draw_settings_panel(Hc, edge, bw2)
            return

        # --- panel: kartu terpisah di bawah header (ada celah + border) ---
        top = Hc + s(12)
        pnl = self.card(1, top, W - 1, top + s(60), fill=BG, outline=edge,
                        r=s(15), bw=bw2)
        if Q:                     # pet ChatGPT: kuota akun, bukan model 9router
            self._draw_quota_panel(Q, top, pnl, edge, bw2)
            return
        pad = s(14)               # jarak kartu dari tepi
        ix = s(26)                # jarak isi dari tepi (di dalam kartu)
        y = top + s(26)
        # titik koneksi + judul
        link = RED if self.error else (MUTED if (stale or not self._have)
                                       else GREEN)
        c.create_oval(s(18), y - s(4), s(26), y + s(4), fill=link, width=0,
                      tags="ui")
        tid = self.tx(s(34), y, "9ROUTER", ORANGE, 15, True)
        nm = self.combo_name if isinstance(self.combo_name, str) else "combos"
        name_x = c.bbox(tid)[2] + s(10)
        # Empat periode menjadi satu segmented control horizontal: lebih
        # cepat dipindai daripada dua baris tombol kecil dan memberi ruang
        # napas yang rapi pada header panel.
        tab_gap, tab_w = s(4), s(50)
        tabs_w = tab_w * len(self.tabs) + tab_gap * (len(self.tabs) - 1)
        tabs_x = W - s(18) - tabs_w
        self.tx(name_x, y,
                self.fit("· " + ("semua combo" if nm == "*" else nm),
                         max(s(48), tabs_x - name_x - s(8)), 10), MUTED, 10)
        for i, (lab, _p) in enumerate(self.tabs):
            x0 = tabs_x + i * (tab_w + tab_gap)
            yc = y
            on = i == self.tab_i
            self.box(x0, yc - s(11), x0 + tab_w, yc + s(11), lab,
                     (lambda i=i: self.set_tab(i)),
                     fill=MINT if on else SURFACE,
                     fg=ON_ACCENT if on else MUTED,
                     outline=MINT if on else LINE, size=9)

        # pace + ucapan si pet
        y += s(36)
        badge = S["label"] if S["label"] in MoodController.ORDER else "STABLE"
        bcol = self._mood_color(badge)
        bw = self.measure(badge, 10, True) + s(16)
        self.chamfer(s(18), y - s(10), s(18) + bw, y + s(10), s(10),
                     fill=bcol, width=0)
        self.tx(s(18) + bw / 2.0, y, badge, self._mood_foreground(badge),
                10, True, "center")
        mood = "hampir habis, pelan-pelan ya!" if S["low"] else \
            MOOD.get(S["label"], MOOD["STABLE"])
        if self._running > 0 and time.time() < self._busy_until:
            mood = "model lagi jalan - %d request aktif" % self._running
        mx = s(18) + bw + s(12)
        self.tx(mx, y, self.fit('"%s"' % mood, W - mx - s(18), 10), FG, 10)
        y += s(20)
        self.tx(s(18), y, S["txt"], MUTED, 9)

        # --- kartu ringkasan: total + bar sisa + keterangan batas ---
        ct = y + s(14)
        cid = self.card(pad, ct, W - pad, ct + s(100), r=s(12),
                        outline=mix(LINE, self._col(S["left_pct"]), 0.35)
                        if S["left_pct"] is not None else LINE)
        y = ct + s(28)
        tid = self.tx(ix, y, fmt_tokens(S["tot_t"]), BRIGHT, 20, True)
        lt = "sisa " + fmt_left(S["left_pct"]) \
            if S["left_pct"] is not None else ""
        if lt:
            self.tx(W - ix, y - s(1), lt, self._col(S["left_pct"]), 13,
                    True, "e")
        # keterangan di bawah angka besar (dipotong bila sempit)
        y += s(20)
        self.tx(ix, y, self.fit("token  ·  %d req  ·  %s"
                                % (S["tot_r"], self.tabs[self.tab_i][0]),
                                W - 2 * ix, 9), MUTED, 9)
        y += s(12)
        bw_all = W - 2 * ix
        # kotak berdiri seperti header: ukuran per kotak sama dgn header
        self._card_n = max(10, int(bw_all / (8.0 * self.k * self.dpi)))
        if S["left_pct"] is not None:
            sfrac, scol = S["left_pct"] / 100.0, self._col(S["left_pct"])   # = sisa, sama dgn header
        else:
            sfrac, scol = 0.0, BG_EMPTY
        self.seg(ix, y + s(2), bw_all, s(10), sfrac, scol,
                 self._card_n, rounded=True, empty=DARK, key="summary")
        y += s(32)
        # Batas otomatis ikut sendiri mengikuti pemakaian, jadi tak ada
        # angka yang bisa diklik user -> captionnya bukan target klik.
        if S["bsrc"] == "auto":
            capt = ("batas %s (otomatis)" % fmt_tokens(S["budget"])
                    if S["budget"] > 0 else "batas otomatis")
            self.tx(ix, y, capt, MUTED, 8)
            cw = self.measure(capt, 8)
        else:
            hint = " · klik utk ubah" if self._have else ""
            capt = ("batas %s (%s)%s"
                    % (fmt_tokens(S["budget"]), S["bsrc"], hint)
                    if S["budget"] > 0 else "batas belum diatur" + hint)
            cw = self.measure(capt, 8)
            self.tx(ix, y, capt, MUTED, 8)
            if self._have:             # saat loading belum bisa diubah
                self.hits.append((ix - s(4), y - s(8), ix + cw + s(6),
                                  y + s(8), self.edit_budget))
        o, parts = self._other, []
        if o["tokens"] > 0:
            parts.append("di luar combo: %s" % fmt_tokens(o["tokens"]))
        if o.get("maybe", 0) > 0:
            parts.append("tak pasti: %s" % fmt_tokens(o["maybe"]))
        if parts:
            self.tx(W - ix, y, self.fit(" · ".join(parts),
                                        W - 2 * ix - cw - s(10), 8),
                    MUTED, 8, False, "e")
        self.card_to(cid, pad, ct, W - pad, y + s(14), r=s(12))
        y += s(14)

        # --- daftar model ---
        per = S["per"]
        n = len(per)
        has_b = any(any(k in self.budgets for k in model_keys(e))
                    for e in self.models)
        y += s(24)
        c.create_polygon(*rpts(s(18), y - s(7), s(21.5), y + s(7), s(1.7), 3),
                         fill=MINT, width=0, tags="ui")
        self.tx(s(28), y, "MODELS (%d)" % n, FG, 10, True)
        self.tx(W - s(18), y, "terpakai/budget" if has_b else
                "porsi dari combo", MUTED, 9, False, "e")
        y -= s(18)

        collapsed = self._collapsible() and not self.show_all
        if collapsed:
            rows, cap = per[:self.collapsed_rows], self.collapsed_rows
        else:
            cap = self._rows_cap()
            self.list_off = clamp(self.list_off, 0, max(0, n - cap))
            rows = per[self.list_off:self.list_off + cap]
        for entry, u in rows:
            y += s(56)
            pct, mode = self._model_pct(entry, u["tokens"], S["tot_t"])
            has = u["tokens"] > 0 or u["requests"] > 0
            sel = entry == self.selected
            dot = self.model_color(entry)
            self.card(pad, y - s(14), W - pad, y + s(34),
                      fill=mix(SURFACE, MINT, 0.14) if sel else SURFACE,
                      outline=MINT if sel else LINE, r=s(10))
            c.create_oval(s(26), y - s(5), s(34), y + s(3),
                          fill=dot if has else DARK, width=0, tags="ui")
            right = "%s · %s" % (fmt_tokens(u["tokens"]), fmt_pct(pct))
            self.tx(W - ix, y - s(1), right, FG if has else MUTED, 10,
                    False, "e")
            rw = self.measure(right, 10)
            name = self.fit(short_model(entry, 200),
                            W - ix - rw - s(42) - s(10), 10, sel)
            self.tx(s(42), y - s(1), name,
                    MINT if sel else (FG if has else MUTED), 10, sel)
            if mode == "budget":
                frac = min(100.0, pct) / 100.0
                bcol2 = self._col(100 - pct) if has else dot
            else:
                frac, bcol2 = pct / 100.0, dot
            self.bar(ix, y + s(10), W - 2 * ix, s(8), frac, bcol2,
                     self._card_n, key="model:" + entry)  # sama dgn ringkasan
            rst_w = W - 2 * ix
            rst_txt = self._model_reset_label()
            brk = "in %s · cache %s · out %s · %s req" % (
                fmt_tokens(u["prompt"]), fmt_tokens(u["cached"]),
                fmt_tokens(u["completion"]), fmt_count(u["requests"]))
            brk_w = rst_w - self.measure(rst_txt, 8) - s(10)
            self.tx(ix, y + s(26), self.fit(brk, max(s(40), brk_w), 8),
                    MUTED, 8)
            rid = self.tx(W - ix, y + s(26),
                          self.fit(rst_txt, rst_w, 8),
                          MUTED, 8, False, "e")
            self._rst_items.append(
                (rid, lambda cw=rst_w: self.fit(self._model_reset_label(),
                                                cw, 8)))
            self.hits.append((pad, y - s(14), W - pad, y + s(34),
                              (lambda e=entry: self.select_model(e))))

        # tombol sembunyi/tampilkan model + info gulir
        has_toggle = self._collapsible() or n > cap
        if has_toggle:
            y += s(56)
            if self._collapsible():
                lab = ("- sembunyikan %d model" % (n - self.collapsed_rows)
                       if self.show_all else
                       "+ tampilkan %d model lain" % (n - self.collapsed_rows))
                bwid = self.measure(lab, 9, True) + s(20)
                self.box(s(18), y - s(11), s(18) + bwid, y + s(11), lab,
                         self.toggle_models, fill=SURFACE, outline=LINE,
                         size=9)
                lx = s(18) + bwid + s(10)
            else:
                lx = s(18)
            if collapsed:
                hid = per[self.collapsed_rows:]
                ht = sum(u["tokens"] for _e, u in hid)
                info = "lainnya: %s · %s" % (
                    fmt_tokens(ht),
                    fmt_pct(ht / S["tot_t"] * 100.0 if S["tot_t"] > 0
                            else 0.0))
                self.tx(W - s(18), y, self.fit(info, W - s(18) - lx, 9),
                        MUTED, 9, False, "e")
            elif n > cap:
                self.tx(W - s(18), y, "%d-%d / %d · scroll" % (
                    self.list_off + 1, self.list_off + len(rows), n),
                    MUTED, 9, False, "e")

        # footer: garis pemisah + tombol ikon dalam chip
        y += s(40) if has_toggle else s(52)
        self._draw_footer(y, pnl, top, pad)

    def _draw_history(self, y_top):
        """Kartu grafik batang aktivitas token (terekam widget).
        Return y bawah kartu."""
        s, c, W = self.s, self.c, self.W
        pad, ix = s(14), s(26)
        vals, step = self.hist.series(self.period)
        peak = max(vals)
        per_txt = "jam" if step == 3600 else "6 jam"
        lab = "aktivitas %s" % ("24 jam" if step == 3600 else "7 hari terakhir")
        if peak > 0:
            lab += " · puncak %s/%s" % (fmt_tokens(peak), per_txt)
        else:
            lab += " · belum ada riwayat (terekam saat widget menyala)"
        h = s(30)
        bottom = y_top + s(20) + h + s(14)
        self.card(pad, y_top, W - pad, bottom, r=s(12))
        self.tx(ix, y_top + s(13), self.fit(lab, W - 2 * ix, 8), MUTED, 8)
        top = y_top + s(24)
        n, x0, w = len(vals), ix, W - 2 * ix
        gap = max(1, s(2))
        bw = (w - gap * (n - 1)) / float(n)
        base = mix(GREEN, SURFACE, 0.55)       # batang rendah: redup
        for i, v in enumerate(vals):
            x = x0 + i * (bw + gap)
            if v > 0:
                bh = max(s(2), h * v / peak)
                col = ORANGE if i == n - 1 else mix(base, GREEN, v / peak)
                if bh > s(4) and bw > s(3):
                    self.chamfer(x, top + h - bh, x + bw, top + h,
                                 min(s(3), bw / 2.0), fill=col, width=0)
                    continue
            else:
                bh, col = max(1, s(1)), LINE
            c.create_rectangle(x, top + h - bh, x + bw, top + h, fill=col,
                               width=0, tags="ui")
        return bottom

    _redraw = draw_all

    def _tick(self):
        step = {"HOT": 1, "WARM": 2}.get(self._label, 3)
        self.tick_n += 1
        if self.tick_n % 10 == 0:
            self._quota_kick()
        if self.tick_n % step == 0:
            self.frame ^= 1
            self._draw_pet(self._label in ("HOT", "CRITICAL"))
        if self.tick_n % 300 == 0:
            self.hist.save()
        self._intel_tick()
        if self.tick_n % 25 == 0:
            self._enforce_topmost()  # Windows kadang melepas topmost
        if self._bulbs and self.tick_n % 3 == 0:
            self._decor_twinkle()
        if self._alert_shown and time.time() >= self.alert_until:
            self.draw_all()               # banner peringatan habis waktu
        if self.tick_n % 5 == 0 and self.is_stale() != self._stale_drawn:
            self.draw_all()
        if self.tick_n % 5 == 0:
            self._rst_update()            # hitung mundur reset tiap detik
            if self._low:                 # kedip hanya saat sisa rendah
                self.blink_on = not self.blink_on
                self.draw_all()
            else:
                if self.blink_on:
                    self.blink_on = False
                    self.draw_all()
                self._refresh_status()    # cukup ubah teks, tanpa gambar ulang
        self._tick_job = self.root.after(200, self._tick)


# =====================================================================
# Selftest
# =====================================================================
def _selftest_intel():
    """Cek logika Local Intelligence (murni lokal, tanpa GUI)."""
    if LocalIntelligenceEngine is None:
        print("intelligence: DILEWATI (%s)" % INTEL_ERR)
        return
    import tempfile
    from local_assistant import LocalAssistant
    from local_intel import INSUFFICIENT, UNSUPPORTED
    e = LocalIntelligenceEngine(os.path.join(tempfile.mkdtemp(), "i.json"))
    t = 1_800_000_000.0
    e.observe({"m": (1e6, 1e5, 10)}, "24h", {}, now=t)          # baseline saja
    assert e.analyze(t + 1, force=True)["today"]["tokens"] == 0, "dedup gagal"
    e.observe({"m": (1e6 + 900, 1e5 + 100, 11)}, "24h", {}, now=t + 5)
    assert e.analyze(t + 6, force=True)["week"]["tokens"] == 1000
    bot = LocalAssistant(e)
    assert bot.ask("resep nasi goreng")[1] == UNSUPPORTED
    assert bot.ask("Kapan quota diperkirakan mencapai batas?")[0] == \
        "quota_prediction"
    assert e.analyze(t + 6)["prediction"]["budget"] is None
    e2 = LocalIntelligenceEngine(os.path.join(tempfile.mkdtemp(), "j.json"))
    assert bot.__class__(e2).ask("Berapa total token saya?")[1] == INSUFFICIENT
    print("intelligence OK (dedup, sesi, asisten, data kurang)")


def selftest():
    print("== selftest ==")
    _selftest_intel()
    p = PaceTracker(window=600)
    now = time.time()
    p.first, p.last, p.events = now - 60, 6000.0, [(now - 30, 6000.0)]
    assert p.decide(1000, 3600)[0] == "HOT"
    assert p.decide(300000, 3600)[0] == "WARM"
    assert p.decide(500000, 3600)[0] == "CHILL"
    assert PaceTracker().decide(100, 100)[0] == "STABLE"
    q = PaceTracker(window=600)
    q.add(1000)
    q.first -= 100
    q.add(1000 + 6000)       # naik 6000
    q.add(3000)              # jendela bergulir (turun) -> diabaikan
    assert abs(sum(e[1] for e in q.events) - 6000) < 1e-6
    print("pace OK")

    assert bar_color(80) == GREEN and bar_color(30) == YELLOW
    assert bar_color(10) == RED
    assert fmt_countdown(16620) == "4h 37m"
    assert fmt_countdown(430800) == "4d 23h"
    assert fmt_tokens(999) == "999" and fmt_tokens(1500) == "1.5K"
    assert fmt_tokens(999960) == "1.0M" and fmt_tokens(999.97e6) == "1.00B"
    assert fmt_tokens(48677686) == "48.7M" and fmt_tokens(2e9) == "2.00B"
    assert fmt_pct(0.0002) == "<0.1%" and fmt_pct(0) == "0.0%"
    assert fmt_pct(99.24) == "99.2%"
    assert fmt_left(46.3) == "46%" and fmt_left(0.4) == "0.4%"
    print("format OK")

    for pt in PETS:
        fc = pt["face"]
        for k in (pt["face"]["ink"], pt["face"].get("base", pt["face"]["ink"])):
            assert k in pt["colors"], (pt["name"], k)
        assert len(fc["eyes"]) == 2 and len(fc["er"]) == 2, pt["name"]
        for fr in (0, 1):
            body, deco = pt["build"](fr)
            assert body, pt["name"]
            for pr in body + deco:
                assert pr[0] in ("o", "r", "p") and pr[-1] in pt["colors"], \
                    (pt["name"], pr)
                if pr[0] != "p":
                    assert all(isinstance(v, (int, float)) for v in pr[1:-1]), \
                        (pt["name"], pr)
                else:
                    assert len(pr[1]) % 2 == 0 and len(pr[1]) >= 6, pt["name"]
    print("pets OK (%d)" % len(PETS))
    for pt in PETS:
        th = THEMES.get(pt["name"].lower())
        assert th, "tema hilang: " + pt["name"]
        assert all(k in th for k in THEME_KEYS), "kunci tema kurang: " + pt["name"]
    for k, th in THEMES.items():
        fx = th.get("FX")
        assert all(x in th for x in ("WARN", "BAD", "BRIGHT", "SPARK",
                                     "OTHER", "MODELS")), "palet: " + k
        assert len(th["MODELS"]) >= 8, k
        assert fx and fx["kind"] in ("sand", "snow", "rain", "bubble",
                                     "stars", "petal", "firefly", "meteor") \
            and fx["cols"], "fx: " + k
    assert THEMES["claude"]["SCENE"]["kind"] == "twilight"
    assert THEMES["obi"]["SCENE"]["kind"] == "sunset"
    assert THEMES["antigravity"]["SCENE"]["kind"] == "antigravity"
    assert THEMES["zuzu"]["SCENE"]["kind"] == "space"
    assert "meteor" in dict(WEATHER_MENU) and "hologram" in dict(DECOR_MENU)
    assert mix("#000000", "#FFFFFF", 0.5) == "#808080"
    apply_theme("obi")
    print("themes OK (%d)" % len(THEMES))

    # combo bersarang + totals resmi
    combos = [{"name": "A", "models": ["oc/x", "B", "A"]},
              {"name": "B", "models": ["ag/y", "oc/x", "C"]},
              {"name": "C", "models": ["gh/z"]}]
    ms, fnd = expand_combos(combos, ["A"])
    assert fnd and ms == ["oc/x", "ag/y", "gh/z"], ms
    assert expand_combos(combos, ["tidak-ada"])[1] is False
    assert parse_stats_totals({"totalPromptTokens": 10,
                               "totalCompletionTokens": 5,
                               "totalRequests": 2}) == {"tokens": 15.0,
                                                        "requests": 2}
    assert parse_stats_totals({}) is None

    # metrik: kartu dashboard hanya menampilkan 3 angka terpisah
    v = {"prompt": 1000.0, "cached": 400.0, "completion": 60.0}
    assert metric_value(v, "io") == 1060.0
    assert metric_value(v, "input") == 1000.0
    assert metric_value(v, "output") == 60.0
    assert metric_value(v, "input_noncached") == 600.0
    st_c = {"totalPromptTokens": 10, "totalCompletionTokens": 5,
            "totalCachedTokens": 4, "totalRequests": 2}
    assert parse_stats_components(st_c) == {"prompt": 10.0, "cached": 4.0,
                                            "completion": 5.0}
    assert parse_stats_components({}) is None
    assert parse_stats_totals(st_c, "input")["tokens"] == 10.0
    assert parse_stats_totals(st_c, "input_noncached")["tokens"] == 6.0
    ents_m = parse_model_stats(
        {"byModel": {"a (p)": {"promptTokens": 100, "cachedTokens": 40,
                               "completionTokens": 6, "requests": 1,
                               "rawModel": "a"}}}, "input_noncached")
    assert ents_m[0]["tokens"] == 60.0 and ents_m[0]["prompt"] == 100.0
    assert set(METRICS) == set(METRIC_LABEL)
    # Regresi: tiap kartu dashboard harus baca field-nya sendiri. Kalau
    # key-nya ikut dikasih ke metric_value, semua baris jadi input+output.
    assert [card_value(v, k) for _n, k in DASH_CARDS] == [1000.0, 400.0, 60.0]
    assert [n for n, _k in DASH_CARDS] == ["input", "cached", "output"]
    print("combo bersarang + totals OK")

    # Regresi budget: batas WAJIB > terpakai, dan tidak boleh ikut berubah
    # sendiri saat pemakaian naik. Versi lama memakai total terpakai sbg
    # "budget otomatis" -> sisa ~0% dan alarm berbunyi terus.
    def _bs(period, manual=None):
        return (manual or {}).get(period, 0.0) or DEFAULT_BUDGET.get(period, 0.0)

    for _per in ("24h", "7d", "today", "all"):
        b1, b2 = _bs(_per), _bs(_per)
        assert b1 == b2, _per
        assert b1 > 0, _per
    assert _bs("24h") == 100e6 and _bs("all") == 1e9
    # sisa benar: terpakai 89M dari batas 100M -> sisa 11%
    assert abs(max(0.0, 100.0 - 89.0 / 100.0 * 100.0) - 11.0) < 0.001
    # batas lebih besar dari terpakai -> tak mungkin 0% saat baru mulai
    assert max(0.0, 100.0 - 0.0 / 100e6 * 100.0) == 100.0
    print("budget = batas (bukan terpakai) OK")

    # Regresi batas otomatis: batas ikut mengikuti pemakaian dan SELALU
    # lebih besar dari terpakai. Dulu batas = total terpakai -> sisa ~0%.
    assert "24h" in AUTO_WINDOWED and "7d" not in AUTO_WINDOWED \
        and "all" not in AUTO_WINDOWED, AUTO_WINDOWED

    class _Auto(PetMonitor):
        """PetMonitor tanpa Tk, cuma logika batas."""

        def __init__(self):
            self.auto_budget = True
            self.auto_headroom, self.auto_floor = 25.0, 1e6
            self._have = True
            self.combo_budget = dict(DEFAULT_BUDGET)
            self.manual_budget = {}
            self._auto_peak = {}
            self._auto_cap_seen = {}
            self._auto_seen = {}
            self.tab_i = 0
            self.tabs = [("24H", "24h"), ("7D", "7d"), ("TODAY", "today"),
                         ("ALL", "all")]
            self.period = "24h"
            self._save_pos = lambda *a, **k: None
            self._prune_auto_saved = True

        def _prune_auto(self):
            pass                        # jangan buang data di tengah test

    a = _Auto()
    for used in (89.0e6, 95.0e6, 150.0e6, 400.0e6, 1e9, 89.0e6):
        a._tot_t = used
        a._track_auto(used)
        cap, src = a.budget_source()
        assert cap > used, (cap, used)  # batas WAJIB > terpakai
        assert src == "auto", src
        assert abs((cap - used) / cap * 100.0 - 20.0) < 0.5, (cap, used)
    # 24h = window geser -> batas ikut turun lagi, tak dikunci di puncak
    assert a._auto_cap() < 1.25e9, a._auto_cap()
    # 7d = kumulatif -> batas hanya naik, tak pernah turun
    b = _Auto()
    b.period = "7d"
    for used in (400e6, 693e6, 1.2e9):
        b._tot_t = used
        b._track_auto(used)
        assert b.budget_source()[0] > used
    high = b.budget_source()[0]
    b._tot_t = 1e6
    b._track_auto(1e6)
    assert b.budget_source()[0] >= high, "kumulatif tak boleh turun"
    # prioritas sumber: manual > auto > config
    b.manual_budget["7d"] = 5e9
    assert b.budget_source()[1] == "manual"
    b.manual_budget.clear()
    assert b.budget_source()[1] == "auto"
    b.auto_budget = False
    assert b.budget_source()[1] == "config"
    print("batas otomatis (ikut pemakaian) OK")
    a._period_anchor = {"24h": time.time()}
    assert 0.0 < a._period_reset_secs() <= 86400.0
    assert a._period_reset_secs("all") is None
    assert 0.0 <= a._period_reset_secs("today") <= 86400.0
    assert a._model_reset_label() == "jendela 24 jam terakhir"
    a.period = "today"
    assert a._model_reset_label().startswith("reset ")
    a.period = "7d"
    assert a._model_reset_label() == "jendela 7 hari terakhir"
    a.period = "all"
    assert a._model_reset_label() == "kumulatif - tanpa reset"
    a.period = "24h"
    print("reset per-model OK")

    assert extract_auth_cookie(
        ["auth_token=abc123; Path=/; HttpOnly"]) == "abc123"
    assert AuthSession({"auth": {"password_env": "TP_NONE_X"}},
                       3).enabled() is False
    os.environ["TP_ENV_X"] = "rahasia"
    a = AuthSession({"auth": {"password_env": "TP_ENV_X",
                              "password": "lama"}}, 3)
    assert a.password == "rahasia"            # env menang atas config
    del os.environ["TP_ENV_X"]
    print("auth OK")

    st = {"byModel": {
        "muse-spark-1.3-contributor-free (opencode)": {
            "promptTokens": 100, "completionTokens": 50, "requests": 3,
            "rawModel": "muse-spark-1.3-contributor-free"},
        "deepseek/deepseek-v4-pro-0813 (openrouter)": {
            "promptTokens": 100, "completionTokens": 24, "requests": 1,
            "rawModel": "deepseek/deepseek-v4-pro-0813"},
        "nvidia/nemotron-3-ultra-550b-a55b (nvidia)": {
            "promptTokens": 100, "completionTokens": 0, "requests": 2,
            "rawModel": "nvidia/nemotron-3-ultra-550b-a55b"},
        "qwen3.8-flash:free (tokenharbor)": {
            "promptTokens": 62, "completionTokens": 55, "requests": 1,
            "rawModel": "qwen3.8-flash:free"},
        "unrelated (x)": {"promptTokens": 7, "completionTokens": 0,
                          "requests": 1, "rawModel": "unrelated"},
    }}
    ents = parse_model_stats(st)
    assert len(ents) == 5
    models = ["oc/muse-spark-1.3-contributor-free",
              "openrouter/deepseek/deepseek-v4-pro-0813",
              "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
              "tokenharbor/qwen3.8-flash:free",
              "ag/claude-opus-4-6-thinking"]
    per, other = assign_usage(models, ents, DEFAULT_ALIASES)
    assert per[models[0]]["tokens"] == 150.0
    assert per[models[1]]["requests"] == 1
    assert per[models[2]]["tokens"] == 100.0
    assert per[models[3]]["tokens"] == 117.0
    assert per[models[4]]["tokens"] == 0.0
    assert other["tokens"] == 7.0               # di luar combo
    # total tidak dobel: jumlah combo + luar = jumlah semua stats
    assert sum(u["tokens"] for u in per.values()) + other["tokens"] == \
        sum(e["tokens"] for e in ents)
    # nama sama di 2 provider -> tiap baris stats ke provider yang benar
    ents2 = parse_model_stats({"byModel": {
        "big-pickle (opencode)": {"promptTokens": 10, "requests": 1,
                                  "rawModel": "big-pickle"},
        "big-pickle (other)": {"promptTokens": 5, "requests": 1,
                               "rawModel": "big-pickle"}}})
    per2, _o = assign_usage(["oc/big-pickle", "other/big-pickle"], ents2,
                            DEFAULT_ALIASES)
    assert per2["oc/big-pickle"]["tokens"] == 10.0
    assert per2["other/big-pickle"]["tokens"] == 5.0
    # varian dgn/tanpa tag :free tidak tertukar
    ents3 = parse_model_stats({"byModel": {
        "m:free (p)": {"promptTokens": 3, "requests": 1, "rawModel": "m:free"},
        "m (p)": {"promptTokens": 9, "requests": 1, "rawModel": "m"}}})
    per3, _o = assign_usage(["p/m:free", "p/m"], ents3)
    assert per3["p/m:free"]["tokens"] == 3.0 and per3["p/m"]["tokens"] == 9.0
    assert short_model("oc/big-pickle") == "big-pickle"
    # provider beda utk prefix yang dikenal -> di luar combo (strict)
    perS, otS = assign_usage(["oc/big-pickle"], ents2, DEFAULT_ALIASES)
    assert perS["oc/big-pickle"]["tokens"] == 10.0 and otS["tokens"] == 5.0
    perN, otN = assign_usage(["oc/big-pickle"], ents2, DEFAULT_ALIASES,
                             strict=False)
    assert perN["oc/big-pickle"]["tokens"] == 15.0 and otN["maybe"] == 5.0
    # prefix tak dikenal (tak bisa dipetakan) -> tetap dihitung per nama
    perU, otU = assign_usage(["zz/big-pickle"], ents2, DEFAULT_ALIASES)
    assert perU["zz/big-pickle"]["tokens"] == 15.0 and otU["tokens"] == 0.0
    print("model-match OK")

    assert parse_amount("100M") == 100e6 and parse_amount("2,5b") == 2.5e9
    assert parse_amount("750k") == 750e3 and parse_amount("1500000") == 1.5e6
    assert parse_amount("abc") is None and parse_amount("") is None
    lv = [20, 10, 5]
    assert next_alert_level(15, lv, None) == (1, True)
    assert next_alert_level(15, lv, 1) == (1, False)
    assert next_alert_level(8, lv, 1) == (2, True)
    assert next_alert_level(21, lv, 1) == (1, False)    # histeresis
    assert next_alert_level(23, lv, 1) == (0, False)    # pulih
    assert next_alert_level(4, lv, 0) == (3, True)
    assert next_alert_level(60, lv, None) == (0, False)
    h = History(os.path.join(BASE_DIR, "_selftest_hist.json"))
    h.b = {}
    t0 = 1_700_000_000.0
    assert h.feed("24h", 1000, t0) == 0
    assert h.feed("24h", 1600, t0 + 10) == 600
    assert h.feed("24h", 1500, t0 + 20) == 0          # turun diabaikan
    h.reset()
    assert h.feed("24h", 9000, t0 + 30) == 0          # tak dobel setelah reset
    vals, step = h.series("24h", t0 + 60)
    assert len(vals) == 24 and step == 3600 and sum(vals) == 600
    assert len(h.series("7d", t0 + 60)[0]) == 28
    print("alert/history/parse OK")

    # --- data nyata 9router 2026-10-04: field + provider + name ---
    real = {"byModel": {
        "muse-spark-1.3-contributor-free (opencode)": {
            "requests": 714, "promptTokens": 53581161,
            "completionTokens": 731870, "cachedTokens": 47634919, "cost": 0,
            "rawModel": "muse-spark-1.3-contributor-free",
            "provider": "opencode", "lastUsed": "2026-10-04T06:26:27.833Z"},
        "deepseek/deepseek-v4-pro-0813 (openrouter)": {
            "requests": 1, "promptTokens": 84, "completionTokens": 40,
            "rawModel": "deepseek/deepseek-v4-pro-0813",
            "provider": "openrouter"},
        "qwen3.8-flash:free (tokenharbor)": {
            "requests": 1, "promptTokens": 62, "completionTokens": 55,
            "rawModel": "qwen3.8-flash:free", "provider": "tokenharbor"},
        "claude-opus-4-6-thinking (antigravity)": {
            "requests": 7, "promptTokens": 306282, "completionTokens": 4872,
            "rawModel": "claude-opus-4-6-thinking",
            "provider": "antigravity"},
        "muse (openai-compatible-chat-9039484f-e6d2-45d3-be70-af3a87a9943c)": {
            "requests": 1, "promptTokens": 1, "completionTokens": 6,
            "rawModel": "muse", "provider": "Muse AI"},
    }}
    rent = parse_model_stats(real)
    assert len(rent) == 5
    by = {e["name"]: e for e in rent}
    assert by["muse-spark-1.3-contributor-free"]["provider"] == "opencode"
    assert by["muse-spark-1.3-contributor-free"]["tokens"] == \
        53581161 + 731870
    assert by["deepseek/deepseek-v4-pro-0813"]["provider"] == "openrouter"
    assert by["claude-opus-4-6-thinking"]["provider"] == "antigravity"
    assert by["muse"]["provider"] == "muse ai"   # provider case direndahkan
    rmodels = ["oc/muse-spark-1.3-contributor-free",
               "openrouter/deepseek/deepseek-v4-pro-0813",
               "tokenharbor/qwen3.8-flash:free",
               "ag/claude-opus-4-6-thinking"]
    rper, roth = assign_usage(rmodels, rent, DEFAULT_ALIASES)
    assert rper["oc/muse-spark-1.3-contributor-free"]["tokens"] == \
        53581161 + 731870
    assert rper["ag/claude-opus-4-6-thinking"]["tokens"] == 306282 + 4872
    assert rper["tokenharbor/qwen3.8-flash:free"]["requests"] == 1
    # 'muse (Muse AI)' bukan bagian combo -> di luar combo
    assert roth["tokens"] == 7.0
    assert sum(u["tokens"] for u in rper.values()) + roth["tokens"] == \
        sum(e["tokens"] for e in rent)
    print("real-data OK")

    # --- util baru Tahap 3 ---
    assert mask_secret("") == "****" and mask_secret("ab") == "****"
    assert mask_secret("abcdef") == "ab****ef"
    assert mask_secret("auth_token=xyz123") == "au****23"
    try:
        raise RuntimeError("uji-log")
    except RuntimeError:
        log_exc("selftest")
    assert os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 0
    si_a, si_b = SingleInstance("TokenPetSelftestX"), \
        SingleInstance("TokenPetSelftestX")
    assert si_a.acquire() is True
    if os.name == "nt":
        assert si_b.acquire() is False      # mutex kedua ditolak
    si_a.release()
    si_b.release()
    r = visible_rect()
    assert r is None or (len(r) == 4 and r[2] > 0 and r[3] > 0)
    vx, vy, vw, vh = r if r else (0, 0, 1536, 864)
    nx, ny = clamp_to_visible(vx + vw + 5000, vy + vh + 5000)
    assert vx <= nx <= vx + vw and vy <= ny <= vy + vh
    print("util (log/mask/single/visible) OK")

    cfg = load_config()
    demo_cfg = dict(cfg)
    demo_cfg["demo"] = True
    sim = DemoSim()
    r = sim.poll()
    assert len(r["models"]) > 0 and r["usage"]
    print("demo OK")

    # --- request aktif 9router (pet sibuk saat model jalan) ---
    assert parse_stats_running({}) is None
    assert parse_stats_running({"pending": {"byModel": {}}}) == 0
    assert parse_stats_running({"pending": {"byModel": {"a (b)": 2, "c (d)": 1}}}) == 3
    assert parse_stats_running({"activeRequests": [{"count": 2}]}) == 2
    print("request aktif (pending/activeRequests) OK")

    # --- aksesoris: setiap pet harus punya anchor ---
    for pt in PETS:
        assert pt["name"].lower() in ACC_ANCHOR, "anchor aksesoris hilang: " + pt["name"]
    print("anchor aksesoris OK")

    # --- penyedia AI: tiap layanan punya pet sendiri, tanpa Copilot ---
    keys = [k for k, _l, _d in AI_PROVIDERS]
    assert "copilot" not in keys, "Copilot harus sudah dihapus"
    for k, _l, dp in AI_PROVIDERS:
        assert PETS[dp]["name"].lower() == k, "pet layanan salah: " + k
    assert len({pt["name"] for pt in PETS}) == len(PETS)
    print("penyedia AI (pet per layanan, tanpa Copilot) OK")

    # --- kuota ChatGPT: parser + kredensial (tanpa jaringan) ---
    _team = {"rate_limit": {"limit_reached": False,
             "primary_window": {"used_percent": 74, "limit_window_seconds": 18000,
                                "reset_after_seconds": 6198, "reset_at": 1789801452},
             "secondary_window": {"used_percent": 27, "limit_window_seconds": 604800,
                                  "reset_after_seconds": 11991, "reset_at": 1789807245}},
             "plan_type": "team", "credits": {"balance": "18.79"}}
    _r = parse_chatgpt_usage(json.dumps(_team), now=1789795254)
    assert [w["tab"] for w in _r["windows"]] == ["5J", "MGG"] and _r["credits"] == 18.79
    _one = {"rate_limit": {"primary_window": {"used_percent": 42,
            "limit_window_seconds": 604800, "reset_after_seconds": 5},
            "secondary_window": None}}
    assert len(parse_chatgpt_usage(_one)["windows"]) == 1
    for _bad in ("bukan json", {}, {"rate_limit": {}}):
        try:
            parse_chatgpt_usage(_bad)
            raise AssertionError("respons rusak harus ditolak")
        except QuotaError:
            pass
    try:
        chatgpt_credentials({"use_codex_auth": False})
        raise AssertionError("tanpa token harus QuotaError")
    except QuotaError as _e:
        assert _e.kind == "nocred"
    assert chatgpt_credentials({"access_token": "T", "account_id": "A"}) == ("T", "A", "config")
    assert fmt_reset_hms(6198) == "1j 43m 18d" and fmt_reset_hms(45) == "45d"
    assert fmt_reset_hms(339877) == "3 hari 22j 24m 37d"
    assert fmt_reset_in(6198) == "1j 43m" and fmt_reset_in(339877) == "3 hari 22j"
    print("kuota ChatGPT (parser, kredensial) OK")

    # --- login Google: OAuth + PKCE lokal (server Google palsu) ---
    import threading as _th
    _st = {}

    class _Mock(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            f = urllib.parse.parse_qs(self.rfile.read(
                int(self.headers.get("Content-Length", 0))).decode())
            v = f["code_verifier"][0]
            ok = _b64url(hashlib.sha256(v.encode()).digest()) == _st["ch"] \
                and f["code"][0] == "kode"
            tok = {"id_token": "x.%s.y" % _b64url(json.dumps(
                {"email": "tes@gmail.com", "name": "Tes"}).encode())}
            self.send_response(200 if ok else 400)
            self.end_headers()
            self.wfile.write(json.dumps(tok if ok else {}).encode())

        def log_message(self, *a):
            pass
    _srv = http.server.HTTPServer(("127.0.0.1", 0), _Mock)
    _th.Thread(target=_srv.serve_forever, daemon=True).start()
    _g = {"client_id": "cid", "auth_url": "http://x/auth",
          "token_url": "http://127.0.0.1:%d/t" % _srv.server_address[1]}

    def _browser(bad_state=False):
        def op(url):
            q = {k: v[0] for k, v in urllib.parse.parse_qs(
                urllib.parse.urlparse(url).query).items()}
            assert q["code_challenge_method"] == "S256"
            _st["ch"] = q["code_challenge"]
            cb = q["redirect_uri"] + "/?" + urllib.parse.urlencode(
                {"code": "kode", "state": "palsu" if bad_state else q["state"]})
            _th.Thread(target=lambda: urllib.request.urlopen(
                cb, timeout=5).read(), daemon=True).start()
        return op
    assert google_oauth_login(_g, _browser(), 10)["email"] == "tes@gmail.com"
    try:
        google_oauth_login(_g, _browser(True), 10)
        raise AssertionError("state palsu harus ditolak")
    except GoogleLoginError:
        pass
    _srv.shutdown()
    print("login Google (PKCE + state) OK")

    import tempfile as _tf
    _td = _tf.mkdtemp()                    # jangan menimpa posisi/akun asli
    globals()["POS_PATH"] = os.path.join(_td, "pos.json")
    globals()["AI_PATH"] = os.path.join(_td, "ai.json")
    root = tk.Tk()
    app = PetMonitor(root, demo_cfg)
    # Regresi save otomatis: tema/cuaca/dekor/aksesori WAJIB pulih restart.
    # Bug lama: scene_theme nyangkut di dalam "budgets" -> load tak baca.
    app.scene_theme, app.theme_follow = "chatgpt", False
    app.weather, app.decor = "rain", "lights"
    app.acc = {"robo": {"hat": "crown", "eyes": "sun"}}
    app._save_pos()
    _saved = json.load(open(globals()["POS_PATH"], encoding="utf-8"))
    assert _saved.get("scene_theme") == "chatgpt", _saved.get("scene_theme")
    assert _saved.get("theme_follow") is False
    assert _saved.get("weather") == "rain" and _saved.get("decor") == "lights"
    assert _saved.get("acc") == {"robo": {"hat": "crown", "eyes": "sun"}}
    assert "scene_theme" not in (_saved.get("budgets") or {}), "tema nyangkut di budgets"
    # simulasi restart: nilai diubah lalu dimuat ulang dari file
    app.scene_theme, app.theme_follow = "robo", True
    app.weather, app.decor, app.acc = "auto", "none", {}
    app._load_pos()
    assert app.scene_theme == "chatgpt" and app.theme_follow is False
    assert app.weather == "rain" and app.decor == "lights"
    assert app.acc == {"robo": {"hat": "crown", "eyes": "sun"}}, app.acc
    # migrasi file lama: tema di dalam budgets tetap terbaca
    _legacy = dict(_saved)
    _legacy.pop("scene_theme", None)
    _legacy["budgets"] = dict(_legacy.get("budgets") or {})
    _legacy["budgets"]["scene_theme"] = "chatgpt"
    json.dump(_legacy, open(globals()["POS_PATH"], "w", encoding="utf-8"))
    app.scene_theme = "robo"
    app._load_pos()
    assert app.scene_theme == "chatgpt", app.scene_theme
    print("save otomatis tema/cuaca/dekor/aksesori OK")
    # Regresi: caption batas otomatis harus TIDAK punya target klik, dan
    # teks "klik utk ubah" harus hilang. Mode manual/config tetap bisa klik.
    # PENTING: error di callback TkAfter tidak naik ke mainloop (Tk diam-diam
    # lewat), jadi hasilnya direkam dulu lalu diperiksa setelah mainloop.
    def _hits_to(fn):
        return len([h for h in app.hits
                    if getattr(h[4], "__func__", None) is fn])

    def _caption():
        return next((app.c.itemcget(t, "text") for t in app.c.find_all()
                     if app.c.type(t) == "text"
                     and app.c.itemcget(t, "text").startswith("batas")), "")

    def _check_bounds():
        try:
            # demo belum punya data -> paksa mode auto supaya yang diuji
            # benar-benar cabang auto, bukan fallback config
            app._have = True
            app._tot_t = 60e6
            app._track_auto(60e6)
            app.draw_all()
            fn = PetMonitor.edit_budget
            assert app.budget_source()[1] == "auto", app.budget_source()
            capt = _caption()
            assert capt and "klik" not in capt, capt
            assert _hits_to(fn) == 0, "batas auto tak boleh punya target klik"
            # config tetap bisa diklik (fallback waktu data belum ada)
            app.auto_budget = False
            app.draw_all()
            assert app.budget_source()[1] == "config", app.budget_source()
            capt = _caption()
            assert _hits_to(fn) == 1 and "klik utk ubah" in capt, capt
            app.auto_budget = True
            app.draw_all()
        except AssertionError as e:
            bounds_err.append(str(e))
    bounds_err = []

    def _check_faces():
        """Semua ekspresi wajah & semua aksesoris harus tergambar tanpa error."""
        try:
            for emo in (None, "smile", "laugh", "busy", "angry", "worried", "wow"):
                for low, lab in ((False, "STABLE"), (True, "HOT")):
                    app._low, app._label = low, lab
                    app._emo = emo
                    app._emo_t0 = time.time()
                    app._draw_pet(lab == "HOT")
            app._emo, app._low, app._label = None, False, "STABLE"
            for _i, _pt in enumerate(PETS):        # semua pet x semua aksesoris
                app.set_pet(_i)
                for _slot, _t, lst in ACC_SLOTS:
                    for aid, _lab in lst:
                        app.acc = {_pt["name"].lower(): {_slot: aid}}
                        app._draw_pet(False)
                app.acc = {}
                app._draw_pet(False)
            # pet ChatGPT: panel = kuota akun, bukan daftar model 9router
            app.set_pet([pt["name"] for pt in PETS].index("ChatGPT"))
            app._apply_quota(DemoQuota().get(), None)
            txt = [app.c.itemcget(t, "text") for t in app.c.find_all()
                   if app.c.type(t) == "text"]
            assert any("CHATGPT" in t for t in txt), "judul kuota hilang"
            assert not any(t.startswith("MODELS") for t in txt), \
                "daftar model 9router masih tampil di pet ChatGPT"
            assert any("Mingguan" in t for t in txt), "kartu kuota mingguan hilang"
            app.set_pet(0)                         # pet lain: model 9router (Robo)
            txt = [app.c.itemcget(t, "text") for t in app.c.find_all()
                   if app.c.type(t) == "text"]
            assert any(t.startswith("MODELS") for t in txt), "daftar model hilang"
            app.set_pet(0)
        except Exception as e:
            bounds_err.append("wajah/aksesoris/kuota: %r" % (e,))
    root.after(1000, _check_bounds)
    root.after(500, app.toggle)
    root.after(1500, app.toggle_models)
    root.after(2500, lambda: root.geometry("720x%d" % root.winfo_height()))
    root.after(3500, lambda: root.geometry("380x%d" % root.winfo_height()))
    root.after(3900, _check_faces)
    root.after(4800, root.destroy)
    try:
        root.mainloop()
    except Exception as e:
        print("GUI FAIL:", e)
        sys.exit(1)
    assert not bounds_err, "batas otomatis: " + "; ".join(bounds_err)
    print("GUI demo OK (expand, hide/show model, resize lebar)")
    print("== SELFTEST LULUS ==")


def debug_stats():
    """Login, ambil /api/combos + /api/usage/stats, cetak ringkasan.

    Password dan cookie WAJIB disamarkan (mask_secret).
    """
    cfg = load_config()
    timeout = max(1, int(cfg.get("request_timeout_seconds", 10)))
    auth = AuthSession(cfg, timeout)
    print("== debug-stats ==")
    print("demo:", bool(cfg.get("demo")))
    print("combos_url:", cfg.get("combos_url"))
    print("stats_url:", cfg.get("stats_url"))
    a = cfg.get("auth", {}) or {}
    print("login_url:", a.get("login_url"))
    pw_src = "env(%s)" % a.get("password_env", "TOKENPET_PASSWORD") \
        if os.environ.get(a.get("password_env", "TOKENPET_PASSWORD")) \
        else "config"
    print("password: %s (sumber: %s)" % (mask_secret(auth.password), pw_src))
    if not auth.enabled():
        print("password kosong; isi auth.password / env dulu.")
        return
    auth.login()
    print("login: OK, cookie: %s" % mask_secret(auth.cookie))
    data = auth.get(cfg["combos_url"], cfg.get("combos_headers", {}),
                    timeout)
    items = data.get("combos", data) if isinstance(data, dict) else data
    names = cfg.get("combo_name", "*")
    names = [names] if isinstance(names, str) else list(names)
    models = []
    for c in items if isinstance(items, list) else []:
        if not isinstance(c, dict):
            continue
        if "*" in names or c.get("name") in names:
            for m in c.get("models", []):
                m = str(m).strip()
                if m and m not in models:
                    models.append(m)
    print("combo %s: %d model" % (names, len(models)))
    for m in models:
        print("  combo:", m)
    aliases = {**DEFAULT_ALIASES,
               **{str(k).lower(): str(v).lower()
                  for k, v in (cfg.get("provider_aliases") or {}).items()}}
    strict = bool(cfg.get("strict_provider", True))
    for period in ("24h", "7d"):
        u = cfg.get("stats_url", "")
        url = re.sub(r"period=[^&]*", "period=" + period, u) \
            if "period=" in u else \
            u + ("&" if "?" in u else "?") + "period=" + period
        try:
            st = auth.get(url, cfg.get("stats_headers"), timeout)
        except Exception as e:
            print("[%s] gagal: %s" % (period, str(e)[:80]))
            log_exc("debug-stats " + period)
            continue
        entries = parse_model_stats(st)
        fields = set()
        for v in ((st or {}).get("byModel") or {}).values():
            if isinstance(v, dict):
                fields.update(v.keys())
        print("[%s] byModel: %d baris, field: %s"
              % (period, len(entries), sorted(fields)))
        per, other = assign_usage(models, entries, aliases, strict)
        tot_c = sum(x["tokens"] for x in per.values())
        tot_s = sum(e["tokens"] for e in entries)
        print("  total combo %.0f + luar %.0f = stats %.0f (cocok: %s)"
              % (tot_c, other["tokens"], tot_s,
                 abs(tot_c + other["tokens"] - tot_s) < 1e-3))
        known = {e["provider"] for e in entries if e["provider"]}
        for m in models:
            u2 = per.get(m, {"tokens": 0.0, "requests": 0})
            print("    %-50s tok=%-10.0f req=%d"
                  % (m[:50], u2["tokens"], u2["requests"]))
        for s in entries:
            best, bsc = None, 0
            for m in models:
                sc = match_score(m, s, aliases, known, strict)
                if abs(sc) > abs(bsc):
                    best, bsc = m, sc
            if best is None:
                print("    LUAR: %-45s tok=%.0f prov=%s"
                      % (s["name"][:45], s["tokens"], s["provider"]))
    print("== debug-stats SELESAI (rahasia disamarkan) ==")


def verify_stats():
    """Bandingkan angka widget dengan total resmi 9router (24h & 7d)."""
    cfg = load_config()
    timeout = max(1, int(cfg.get("request_timeout_seconds", 10)))
    auth = AuthSession(cfg, timeout)
    print("== verify ==")
    if not auth.enabled():
        print("password kosong; isi auth.password / env dulu.")
        return
    auth.login()
    data = auth.get(cfg["combos_url"], cfg.get("combos_headers", {}), timeout)
    items = data.get("combos", data) if isinstance(data, dict) else data
    names = cfg.get("combo_name", "*")
    names = [names] if isinstance(names, str) else list(names)
    models, found = expand_combos(items if isinstance(items, list) else [],
                                  names)
    if not found:
        print("combo %s tak ketemu" % names)
        return
    aliases = {**DEFAULT_ALIASES,
               **{str(k).lower(): str(v).lower()
                  for k, v in (cfg.get("provider_aliases") or {}).items()}}
    strict = bool(cfg.get("strict_provider", True))
    budgets = {**DEFAULT_BUDGET, **{str(k): float(v) for k, v in
                                    (cfg.get("combo_budget") or {}).items()}}
    for period in ("24h", "7d"):
        u = cfg.get("stats_url", "")
        url = re.sub(r"period=[^&]*", "period=" + period, u) \
            if "period=" in u else \
            u + ("&" if "?" in u else "?") + "period=" + period
        st = auth.get(url, cfg.get("stats_headers"), timeout)
        entries = parse_model_stats(st)
        per, other = assign_usage(models, entries, aliases, strict)
        raw = parse_stats_components(st)
        combo_parts = {"prompt": sum(x["prompt"] for x in per.values()),
                       "cached": sum(x["cached"] for x in per.values()),
                       "completion": sum(x["completion"] for x in per.values())}
        rep = parse_stats_totals(st)
        print("[%s]" % period)
        if raw:
            print("  kartu dashboard 9router:")
            print("    Total Input Tokens : %s" % "{:,}".format(int(raw["prompt"])))
            print("    Cached Tokens      : %s" % "{:,}".format(int(raw["cached"])))
            print("    Output Tokens      : %s" % "{:,}".format(int(raw["completion"])))
            print("  cocok kolom per kolom (combo + luar vs kartu):")
            for name, key in DASH_CARDS:
                cb, ou = card_value(combo_parts, key), card_value(other, key)
                print("    %-7s %13.0f + %9.0f = %13.0f | %13.0f | selisih %.0f"
                      % (name, cb, ou, cb + ou, raw[key],
                         abs(cb + ou - raw[key])))
        else:
            print("  total resmi: tidak ada di respons 9router")
        print("  masuk combo '%s': %s" % (",".join(names),
                                          fmt_tokens(metric_value(combo_parts))))
        print("  di luar combo  : %s" % fmt_tokens(other["tokens"]))
        if rep:
            gap = abs(rep["tokens"] - sum(e["tokens"] for e in entries))
            print("  jumlah baris byModel == total resmi: %s (selisih %.0f)"
                  % ("YA" if gap <= max(1000.0, 0.01 * rep["tokens"]) else "TIDAK",
                     gap))
        b = budgets.get(period, 0.0)
        if b > 0:
            print("  sisa budget per metrik:")
            for m in METRICS:
                print("    %-14s widget %-8s / %-8s = sisa %.1f%%"
                      % (m, fmt_tokens(metric_value(combo_parts, m)),
                         fmt_tokens(b),
                         max(0.0, 100.0 - metric_value(combo_parts, m)
                             / b * 100.0)))
    print("'kartu dashboard' = angka yang tampil di dashboard 9router.")
    print("combo + luar harus sama persis dng kartu itu -> berarti akurat.")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    if "--debug-stats" in sys.argv:
        debug_stats()
        return
    if "--verify" in sys.argv:
        verify_stats()
        return
    if "--autostart" in sys.argv:
        i = sys.argv.index("--autostart")
        val = sys.argv[i + 1].lower() if i + 1 < len(sys.argv) else ""
        if val not in ("on", "off"):
            print("pakai: python pet_monitor.py --autostart on|off")
            return
        set_autostart(val == "on")
        print("autostart", val.upper())
        return
    cfg = load_config()
    if cfg.get("dpi_aware", True):
        enable_dpi_awareness()
    _single = SingleInstance()
    if not _single.acquire():
        print("TokenPet sudah berjalan (satu instance saja).")
        return
    root = tk.Tk()
    root.report_callback_exception = \
        lambda exc, val, tb: log_exc("tk-callback")
    app = PetMonitor(root, cfg)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.quit()
    except Exception:
        log_exc("mainloop")


if __name__ == "__main__":
    main()
