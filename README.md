# TokenPet — widget desktop pemantau token 9Router + pet vektor

Widget kecil tanpa border, selalu di atas, untuk Windows 10/11.
Python + Tkinter saja (standard library, tanpa dependensi tambahan).

## File

| File | Guna |
|---|---|
| `pet_monitor.py` | Program utama (widget, polling, kuota layanan, mood) |
| `pet_monitor.pyw` | Launcher tanpa konsol (klik-ganda langsung jalan) |
| `local_intel.py` | Mesin Local Intelligence: sesi, prediksi, anomali, health, gamifikasi (100% lokal, stdlib saja) |
| `local_assistant.py` | Asisten lokal rule-based, 12 intent → template deterministik (BUKAN LLM) |
| `intel_panels.py` | Jendela panel intelligence (7 tab) |
| `test_intel.py` | 115 cek mesin intel + asisten (`python test_intel.py` → `OK 115 checks`) |
| `secure_store.py` | Kredensial terenkripsi DPAPI per-user Windows (blob base64, bukan plaintext) |
| `config.json` | Config aktif (**jangan push** — bisa berisi password) |
| `config.example.json` | Contoh config tanpa rahasia |
| `window_pos.json` | Posisi, lebar, pet, tab, panel, budget, cuaca/dekor/aksesori, always-on-top |
| `history.json` | Bucket token per 5 menit yang terekam widget (otomatis, retensi 35 hari) |
| `intel_state.json` | State intelligence: bucket 5 mnt (35 hari), sesi, anomali, XP/level, notifikasi, settings |
| `intel_state_demo.json` | State intel saat mode `"demo": true` |
| `ai_accounts.json` | Status akun AI per layanan (tanpa token mentah) |
| `tokenpet_credentials.dat` | Blob DPAPI terenkripsi (bukan plaintext) |
| `tokenpet.log` / `tokenpet.lock` | Log error (rotasi ~200 KB) / lock fallback single-instance |

> `config.json` bisa berisi password dashboard 9Router — jangan commit/push
> ke GitHub (sudah ditutup `.gitignore`). **Lebih aman:** kosongkan
> `auth.password` dan set `TOKENPET_PASSWORD`
> (nama variabel bisa diganti lewat `auth.password_env`). Env menang atas
> config.
>
> ```bat
> setx TOKENPET_PASSWORD "passwordmu"
> ```
> (buka terminal baru setelahnya).
>
> `insight_state.json`, `intel_data.json`, `intel_profile.json` yang mungkin
> ada di folder adalah **file sisa lama — tidak dibaca kode mana pun**.

## Pet, ekspresi, dan bentuk

- **Font** proporsional yang lebih ringan dan tidak kaku: otomatis memakai
  Segoe UI (Windows) / Inter / Noto Sans / DejaVu Sans bila ada, dengan
  varian *semibold* untuk judul. Ukuran huruf diperkecil lewat
  `"font_scale"` (default `0.86`; naikkan bila terasa kekecilan).
  Mau font sendiri? Isi `"font": "Nama Font"` di `config.json`.
- **Bentuk** semuanya membulat: header, kartu, tombol, lencana, dan bar
  berujung bulat dengan segmen tipis (bukan balok besar). Sudut header ikut
  membulat sampai ke tepi jendela (celah memakai warna transparan Windows).
  `"bar_style": "solid"` = bar polos tanpa garis segmen.
- **Pet**: 6 pet vektor halus + kontur gelap (Robo, Claude, ChatGPT,
  Antigravity, Cursor, Codex — tiap layanan punya pet sendiri, Copilot
  dihapus). Setiap pet punya wajah sendiri: mata berkedip acak, melirik ke
  arah kursor, pipi merona, dan ekspresi:

| Keadaan | Ekspresi |
|---|---|
| Biasa | senyum tipis, kedip, melirik kursor |
| Hover pet | mata ^ ^, senyum lebar + lidah, pipi merah, nada & kilau |
| Token naik (sibuk) | mata fokus + alis datar, keringat; Antigravity/Codex menampilkan `>_` |
| Sisa menipis | alis sedih, mulut bergelombang, keringat, tanda `!` |
| HOT (ngebut) | mata membelalak, mulut `o`, garis kecepatan, tanda `!` |
| Marah / tertawa | alis miring + urat / mata ^ ^ + mulut buka-tutup + "ha ha" |

Ikon di menu pilih pet juga dirender halus dari bentuk yang sama.

| Pet | Layanan | Ciri |
|---|---|---|
| Robo | 9Router (utama) | robot berlapis, visor LED biru, inti dada bercahaya; wajah = lampu (kedip, lirik kursor, semua ekspresi) |
| Claude | Claude | gumpalan terakota, pelat wajah krem |
| ChatGPT | ChatGPT | gelembung ucapan hijau-toska + titik ketik |
| Antigravity | Antigravity | roh kubah ungu melayang, cincin orbit; tampilkan `>_` saat jalan |
| Cursor | Cursor | kotak grafit, pelat wajah terang, panah kursor |
| Codex | Codex | awan lavender, layar terminal, prompt `>_` |

- **Sibuk = request sedang jalan**: terdeteksi dari `pending.byModel` /
  `activeRequests` 9Router ("N request aktif"); bila 9Router lama tak
  mengirimnya, dipakai cara lama (token naik, `busy_seconds`).
- `ai_accounts.json` lama otomatis dimigrasi: akun Copilot dibuang, pet tiap
  layanan direset ke pet barunya (status login tetap dipertahankan).

## Tema otomatis per pet

Ganti pet (klik pet di header, atau tombol `p`) → warna widget, tanah, dan
hiasan ikut berganti sesuai warna pet (`theme_follows_pet`, default true).
Kunci tema diambil dari nama pet huruf kecil; tanpa entri dipakai Gurun.
Menu matahari (`THEME_MENU`, 10 entri) = pilih manual (mematikan ikut-pet).

| Pet | Tema | Adegan | Efek |
|---|---|---|---|
| Robo | Perkotaan | kota + pilar equalizer yang menabrak bar status | bintang |
| Claude | Senja | langit senja + lampion | kelopak |
| ChatGPT | Laguna | laut + berkas cahaya | gelembung |
| Antigravity | Gravitasi Nol | kisi holografik + pulau melayang | kunang-kunang |
| Cursor | Editor | hujan + pilar kota | hujan |
| Codex | Awan Kode | malam salju + bulan | salju |
| (manual) | Gurun / Salju / Batu / Luar Angkasa | bukit pasir / salju / badai / planet bercincin | pasir / salju / hujan / meteor |

- **Animasi cuaca di header** (di belakang bar/teks, tidak mengganggu).
  Saat status **HOT**, efeknya ikut kencang.
  Matikan efek saja: `"weather_effects": false` di `config.json`.
- Tema ikut tersimpan lewat pilihan pet di `window_pos.json`.
- Matikan: set `"theme_follows_pet": false` (selalu gurun).
- **Yang ikut tema:** latar, border, semua tombol, badge status, bar &
  persen, grafik aktivitas, titik warna tiap model, menu pilih pet, dan
  dialog budget. Warna teks di atas tombol/badge dipilih otomatis agar
  tetap terbaca.
- **Pilar menabrak bar** (tema Perkotaan dan Editor): pilar equalizer
  melompat bergantian dan menabrak sisi bawah bar status (kilatan putih +
  percikan), lalu jatuh lagi.

## Cara menjalankan

```bat
cd C:\Website\TokenPet
python pet_monitor.py
```

Tanpa konsol: klik-ganda `pet_monitor.pyw`, atau `start pet_monitor.pyw`.
Tutup: `^` → `QUIT`. Darurat: `taskkill /F /IM pythonw.exe`.

```bat
python pet_monitor.py --selftest      :: uji otomatis (wajib lulus sebelum push)
python test_intel.py                 :: 115 cek intel + asisten
python pet_monitor.py --debug-stats  :: diagnostik data asli (secret disamarkan)
python pet_monitor.py --verify       :: cek akurasi vs angka resmi 9Router
python pet_monitor.py --autostart on|off
```

`--debug-stats` mencetak: daftar model combo, field tiap baris `byModel`
(`promptTokens`, `completionTokens`, `requests`, `rawModel`, `provider`,
...), hasil pencocokan tiap model combo → baris stats, dan yang masuk
"di luar combo" (24h dan 7d). `--verify` mencetak total resmi 9Router vs
jumlah baris `byModel` vs bagian combo/luar-combo.

## Cara kerja data (live, bukan dummy)

1. **Daftar model otomatis dari combo** — tiap `poll_interval_seconds`
   (default 5 dtk) widget baca `combos_url` (`/api/combos`) dan ambil
   `models` milik `combo_name`. Tambah/hapus model di dashboard → langsung
   tampil tanpa edit config. Combo berisi combo lain diurai rekursif.
2. **Token per-model dari stats asli** — `stats_url`
   (`/api/usage/stats?period=24h`): `byModel` = prompt + completion +
   request per model.
3. **Login otomatis** — blok `auth` (`login_url` + `password`), cookie
   `auth_token` hanya di memori, refresh sendiri bila 401.

### Akurasi

- Tiap baris stats dicocokkan ke **satu** model combo saja (skor: path
  persis > nama + tag `:free` > nama tanpa tag; provider jadi penentu bila
  nama sama). Tidak ada lagi token yang terhitung dobel.
- Stats yang tidak cocok ke model combo mana pun tampil terpisah sebagai
  `di luar combo: ...` di bawah bar total — jadi total combo murni milik combo.
- **Provider ikut dicek** bila prefix combo (`oc/`, `ag/`, ...) bisa dipetakan
  ke provider di stats (`provider_aliases` + awalan nama). Nama model sama
  tapi provider beda = dipakai di luar combo, tidak dihitung ke combo.
  Prefix yang tak bisa dipetakan tetap dicocokkan lewat nama. Atur
  `"strict_provider": false` bila ingin tetap menghitungnya (ditandai
  `tak pasti: ...`).
- Persen sangat kecil tampil `<0.1%` (bukan `0.0%` palsu); sisa < 10%
  tampil 1 desimal.
- **Pace** dihitung dari *penambahan* token yang teramati (penurunan akibat
  jendela 24h/7d bergulir diabaikan) dan baru dipercaya setelah ±30 detik
  pengamatan ("mengukur pace..." sebelum itu).
- Hasil polling periode lama (mis. baru ganti 24H→7D) dibuang, tidak
  menimpa tampilan.

## Arti % di tiap baris model

9Router **tidak memberi limit per-model**, jadi widget memakai dua mode:

- **Default: `% = share of combo`** — pangsa token model dari total token
  combo. Panjang bar = persen yang tertulis.
- **Budget: `% = used/budget`** — isi `model_budgets` di config, mis.
  `"model_budgets": {"muse-spark-1.3-contributor-free": 100000000}`;
  bar jadi bar sisa kuota (hijau→kuning→merah). Kunci fleksibel: cukup
  segmen akhir nama (`"nemotron-3-ultra-550b-a55b": 5000000`).

## Cek akurasi vs 9Router

```bat
python pet_monitor.py --verify
```

Mencetak, untuk 24h dan 7d: total resmi 9Router (prompt+completion), jumlah
semua baris `byModel`, bagian yang masuk combo, bagian di luar combo, dan
apakah semuanya cocok. Bandingkan baris *total resmi* dengan dashboard
9Router.

Yang dijaga widget:

- Sebelum data pertama masuk (atau setelah ganti tab 24H/7D) bar menampilkan
  `--%`, bukan `100%` palsu.
- Combo yang berisi combo lain diurai rekursif, jadi token model aslinya ikut.
- Panel menampilkan `total 9Router` dan `selisih rincian` bila total resmi
  berbeda dari jumlah baris `byModel`.
- Bila 9Router tak terjangkau / data tak diperbarui, bar header meredup dan
  bertuliskan `data lama`.
- Persen sisa = 100% - terpakai / **budget di config** (9Router tidak punya
  limit per combo). Total yang dihitung hanya model di combo; token di luar
  combo ditampilkan terpisah.
- Bila header menampilkan `%` satu model (bukan sisa combo), itu karena model
  tersebut sedang dipilih: klik barisnya lagi di panel untuk melepas.

## Bar utama + budget + notifikasi + riwayat

- Bar ringkas = **total token semua model di combo** vs `combo_budget`
  (`24h` 100M / `7d` 500M / `today` 100M / `all` 1B default). Hijau sisa >
  50%, kuning 20–50%, merah < 20%. `"bar_style": "solid"` = bar polos.
- **Budget otomatis**: batas ikut naik mengikuti pemakaian + cadangan
  (`auto_headroom` 25%, `auto_floor` 1M). `auto_budget: false` = batas
  tetap. 24H/TODAY ikut turun saat jendela bergeser; 7D/ALL kumulatif.
  Klik teks `budget ...` di panel untuk ubah budget periode aktif
  (`100M`, `2.5B`, `750k`); tersimpan di `window_pos.json`.
- **Notifikasi**: sisa melewati 20%/10%/5% (atau pace HOT) → nada sistem +
  banner merah ±12 dtk, hanya saat kondisi *memburuk* (histeresis +
  cooldown). Blok `alerts`: `enabled`, `sound`, `levels`, `hot`,
  `cooldown_seconds`, `banner_seconds`.
- **Riwayat**: grafik batang dari penambahan yang **terekam widget selama
  menyala** (kosong saat widget mati). Bucket 5 menit, retensi 35 hari,
  di `history.json`.

## Local Intelligence (tanpa API key, tanpa kirim data keluar)

`local_intel.py` + `local_assistant.py` + `intel_panels.py`: **100% lokal,
stdlib saja, nol network call, nol LLM**. Analisis memakai statistik
sederhana atas data yang SUDAH dibaca TokenPet. Setiap hasil dibedakan:
`FACT` (teramati), `ESTIMATE` (perkiraan), `RECOMMENDATION` (saran info,
tak mengubah apa pun otomatis). Data kurang → `INSUFFICIENT`, bukan
karangan. Bila modul hilang/rusak, widget tetap jalan tanpa fitur ini.

Buka: klik kanan → **Local Intelligence** (7 submenu), **Statistics** /
tombol `h` (→ tab Smart Insights), atau tombol `i` (→ Assistant).
Nonaktifkan total: `"intelligence": {"enabled": false}` di `config.json`.

7 tab (`open_intel(tab)`, refresh 5 dtk):

- **Assistant** (`assistant`): 9 saran + kolom chat. `LocalAssistant.ask()`:
  12 intent (model terpakai, total token/request, rata-rata, sesi, tren,
  status & prediksi kuota, anomali, efisiensi, provider, bantuan) →
  template deterministik dari `engine.analyze()`. Di luar itu `UNSUPPORTED`.
- **Insights** (`insights`): ringkasan hari/24 jam/minggu + tren + prediksi
  kuota (regresi linear + sampel jendela resmi; label ESTIMATE) +
  rekomendasi model paling efisien (info saja).
- **Anomali** (`anomaly`): lonjakan token/request vs baseline (z-score/MAD
  per jam + ambang global; sensitivitas low/medium/high) + alasan angka.
  Bisa ditandai "bukan anomali".
- **Sesi** (`session`): sesi berjalan + terakhir (durasi, token, request,
  rata-rata/request) + tombol reset (hanya catatan sesi).
- **Progres** (`progress`): 4 misi harian @20 XP (buka app, tinjau
  peringatan, selesaikan sesi, cek pemakaian) + 6 pencapaian @50 XP (hari
  pertama, streak 3/7 hari, 5 tinjauan, semua misi, level 5). Level butuh
  100 + 40×(level−1) XP. **XP hanya dari memantau, bukan dari memakai
  token lebih banyak.** Hadiah level = penanda aksesori (lv 2 topi, 3
  kacamata, 4 dasi, 5 lencana, 7 mahkota, 10 jubah); aksesori lama tetap
  bebas dipakai.
- **Provider** (`health`): ONLINE/OFFLINE/AUTH ERROR/QUOTA LIMIT/UNKNOWN
  dari hasil polling yang SUDAH ada (tanpa request tambahan). 3 gagal
  beruntun baru OFFLINE. Latensi rata-rata ikut tampil.
- **Pengaturan** (`settings`): enable prediksi/anomali/gamifikasi,
  sensitivitas, idle sesi (1–120 menit, default 10), notifikasi per 7
  kategori (`quota_warning`, `quota_prediction`, `anomaly`,
  `provider_connection`, `session_summary`, `smart_recommendation`,
  `achievement`). Tersimpan di `intel_state.json`.

Mood: `MoodController` (`STABLE`→`CHILL`→`WARM`→`HOT`→`CRITICAL`, settle
±8 dtk, recover ±20 dtk) untuk bar/pet; `MOODS` engine (ERROR >
DISCONNECTED > CRITICAL > WORRIED > SURPRISED > THINKING > EFFICIENT >
HAPPY > IDLE > SLEEPING).

> Catatan jujur: kunci `insight` dan `alert_notify` di
> `config.example.json` adalah **sisa rancangan lama dan tidak dibaca
> kode**. Yang berlaku: `"intelligence": {"enabled": ...}` + tab
> Pengaturan panel.

## Pakai

- Seret area mana saja (kecuali tombol) untuk pindah. `^`/`v`: buka/tutup
  panel. Shortcut: `r` refresh, `s` settings, `h` statistics, `p` pet
  berikut, `i` assistant, `Esc` kembali/tutup.
- **Klik baris model = pilih** (bar ikut `%` model itu + nama pendek;
  klik lagi melepas; terpilih ditandai `>`). Klik lencana periode =
  ganti 24H→7D→TODAY→ALL (tersimpan `stats_period`).
- Klik **pet di header** (atau `p`) = dropdown 6 pet. Pilihan tersimpan.
- Klik kanan: Refresh, Statistics, Local Intelligence (7 submenu),
  Settings, Change Pet, Lock Position, Always on Top, Exit.
- Footer 7 ikon: settings (gir), sort (bars), tema (matahari), cuaca
  (awan), dekorasi (bohlam), aksesori (topi), config (slider).
- Daftar > `collapsed_rows` (4): hanya 5 teratas + `+ tampilkan N model
  lain` + ringkasan `lainnya:`; scroll mouse bila panjang; `- sembunyikan`.
- **Aksesori** (ikon topi, per pet di `window_pos.json`): Topi 17,
  Kacamata 9, Wajah 8, Leher 6, Punggung 4, Lainnya 5 = **49**, plus
  *Acak* dan *Lepas semua*.
- **LOGOUT** di sebelah status: hapus cookie + panggil `logout_url` +
  hentikan polling → jadi **LOGIN**. Demo (`"demo": true`): data simulasi
  (state intel terpisah).

## Cuaca & dekorasi

- Menu **awan** (11 pilihan: otomatis ikut tema, pasir, salju, hujan,
  gelembung, bintang, kelopak sakura, daun gugur, kunang-kunang, hujan
  meteor, tanpa cuaca). Menu **bohlam** (10: lampu natal, hangat, cemara,
  neon, lampion, bendera, bintang gantung, hologram, orbit, tanpa
  dekorasi). Tersimpan di `window_pos.json`; juga ada di Settings +
  tombol **ATUR** aksesori.

## Akun AI + kuota tiap layanan

Hanya 9Router yang aktif awal. Akun baru aktif setelah **Anda**
mengetuknya: `OFF` (Claude) atau `DETEKSI` (ChatGPT/Codex), lalu `ON`.
Tanpa pemindaian latar. `ai_accounts.json` lama otomatis dimigrasi
(Copilot dibuang, pet direset, status login dipertahankan).

| Layanan | File token (hanya dibaca) | Login |
|---|---|---|
| Claude | `~/.claude/.credentials.json` (`$CLAUDE_CONFIG_DIR`) | jalankan `claude` sekali |
| ChatGPT / Codex | `~/.codex/auth.json` (`$CODEX_HOME`, `~/.codex*/`) | `codex login` sekali |

Satu akun `ChatGPT + Codex`: tombol **CHATGPT**/**CODEX** (pilih pet + buka
portal), **DETEKSI** (pindai `$CODEX_HOME`, `~/.codex`, `~/.codex*/`,
`chatgpt_quota.auth_file`/`auth_files`; >1 akun → menu pilih, `●` =
terpakai). Akun kedua: `set CODEX_HOME=%USERPROFILE%\.codex-kerja` lalu
`codex login`. Kuota dari endpoint internal CLI resmi masing-masing
(**tak terdokumentasi, bisa berubah**; gagal = pesan, bukan crash).
Opsi: `chatgpt_quota` (`poll_seconds` min 20, `use_codex_auth`,
`access_token`, `account_id`, `auth_file`) dan `claude_quota` (`url`,
`auth_file`). Token kedaluwarsa: jalankan CLI-nya sekali, ketuk `↻`.
Cursor dan Antigravity: login manual. Login Google di Settings hanya
penanda lokal.

**Kuota ChatGPT** (saat pet ChatGPT tampil, panel dan header menampilkan
kuota akun, bukan model 9Router):

- Header: jendela terpilih (`5J` / `MGG`), persen terpakai, hitung mundur
  reset, dan bar sisa. Ketuk lencana untuk ganti jendela.
- Panel: kartu **5 jam** dan **Mingguan** (sisa %, terpakai %, waktu reset
  dan jam reset), kredit tersisa bila ada, tombol `↻` untuk segarkan.
  Pet ikut bereaksi (cemas saat sisa menipis, sibuk saat pemakaian naik).
- Sumber data: `GET https://chatgpt.com/backend-api/wham/usage`, endpoint
  internal yang juga dipakai Codex CLI. **Tidak terdokumentasi resmi** dan
  bisa berubah; bila gagal, widget menampilkan pesan, bukan crash. Paket
  yang hanya punya batas mingguan hanya menampilkan satu kartu.
- Token (urutan): secure store (DPAPI) > `chatgpt_quota.access_token` di
  `config.json` > env `TOKENPET_CHATGPT_TOKEN` (+`TOKENPET_CHATGPT_ACCOUNT`)
  > file Codex CLI `~/.codex/auth.json` (atau `$CODEX_HOME`; cukup
  `codex login` sekali). File itu hanya **dibaca**: widget tidak menulis
  atau me-refresh token. Token hanya dikirim ke `https://` kuota di atas,
  tidak masuk log/file. Matikan pembacaan file Codex dengan
  `"use_codex_auth": false`. Jika token kedaluwarsa, jalankan `codex`
  sekali lalu ketuk `↻`.
- Opsi di `config.json` > `chatgpt_quota`: `poll_seconds` (min 20, bawaan
  60), `use_codex_auth`, `access_token`, `account_id`, `auth_file` /
  `auth_files`.
- Kuota Claude: jendela 5 jam (`5J`) / mingguan (`MGG`), plus Opus (`OPUS`)
  / Sonnet (`SON`) bila ada di respons; hanya maks 3 jendela pertama yang
  dipakai.

## Selalu di depan, satu instance, autostart

- **Always-on-top**: `-topmost` + ditegakkan kembali saat `FocusOut` dan
  cek berkala (tanpa `lift`/`focus_force`, tidak curi fokus). Dialog login
  mematikan sementara lalu mengembalikan. Toggle permanen di klik kanan
  (tersimpan di `window_pos.json`, default true).
- **Satu instance**: instance kedua keluar (`TokenPet sudah berjalan`) —
  named mutex Windows, fallback file lock.
- **Autostart**: `--autostart on/off` → registry `HKCU\...\Run`
  (tanpa admin), menjalankan `.pyw`.
- Error tak tertangani (termasuk thread polling & callback Tk) →
  `tokenpet.log` (rotasi ~200 KB). Penting karena `.pyw` tanpa konsol.

## Responsif & layar HiDPI

- Header responsif: posisi pet, label, bar, persen dari ukuran teks nyata;
  360–900 px proporsional, redraw langsung saat tepi kanan ditarik
  (kursor ↔). Tinggi ikut isi, digeser naik bila panel keluar layar;
  posisi dijaga terlihat (multi-monitor aman).
- Hanya redraw saat data berubah / diklik / resize. Kursor tangan di
  atas yang bisa diklik. DPI-aware (set `"dpi_aware": false` bila
  bermasalah).

## Jika widget menampilkan ERR

| Pesan | Arti |
|---|---|
| `ERR: login gagal (password salah?)` | Password di `auth.password` salah |
| `ERR: HTTP Error 401 ...` | Cookie ditolak & login ulang gagal — cek 9Router di `:20128` |
| `ERR: <urlopen error ...>` | 9Router mati / port berubah |
| `ERR: combo '...' tak ketemu` | `combo_name` salah ketik — cek dashboard |
