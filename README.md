# TokenPet — widget desktop pemantau token 9router + pet vektor yang halus

Widget kecil tanpa border, selalu di atas, untuk Windows 10/11.
Python + Tkinter saja (tanpa library tambahan).

## File

| File | Guna |
|---|---|
| `pet_monitor.py` | Program utama |
| `pet_monitor.pyw` | Launcher tanpa konsol (klik-ganda langsung jalan) |
| `config.json` | Combo, URL, jalur field, budget model, **password dashboard** |
| `config.example.json` | Contoh config tanpa password (aman dibagikan) |
| `window_pos.json` | Posisi, lebar, pet, tab, panel terbuka, batas token |
| `history.json` | Riwayat token yang terekam widget (otomatis, 8 hari) |
| `tokenpet.log` | Log error tak tertangani + rotasi sederhana (otomatis) |

> `config.json` bisa berisi password dashboard 9router — jangan commit/push
> ke GitHub (sudah ditutup `.gitignore`). **Lebih aman:** kosongkan
> `auth.password` dan set environment variable `TOKENPET_PASSWORD`
> (nama variabel bisa diganti lewat `auth.password_env`). Env menang atas
> config.
>
> ```bat
> setx TOKENPET_PASSWORD "passwordmu"
> ```
> (buka terminal baru setelahnya).

## Gaya tampilan: font, bentuk, pet

- **Font** proporsional yang lebih ringan dan tidak kaku: otomatis memakai
  Segoe UI (Windows) / Inter / Noto Sans / DejaVu Sans bila ada, dengan
  varian *semibold* untuk judul. Ukuran huruf diperkecil lewat
  `"font_scale"` (default `0.86`; naikkan bila terasa kekecilan).
  Mau font sendiri? Isi `"font": "Nama Font"` di `config.json`.
- **Bentuk** semuanya membulat: header, kartu, tombol, lencana, dan bar
  berujung bulat dengan segmen tipis (bukan balok besar). Sudut header ikut
  membulat sampai ke tepi jendela (celah memakai warna transparan Windows).
  `"bar_style": "solid"` = bar polos tanpa garis segmen.
- **Pet** digambar vektor halus + kontur gelap, bukan blok piksel. Setiap pet
  punya wajah sendiri: mata berkedip acak, melirik ke arah kursor, pipi
  merona, dan ekspresi lebih lengkap:

| Keadaan | Ekspresi |
|---|---|
| Biasa | senyum tipis, kedip, melirik kursor |
| Hover pet | mata ^ ^, senyum lebar + lidah, pipi merah, nada & kilau |
| Token naik (sibuk) | mata fokus + alis datar, keringat; Nova menampilkan `>_` |
| Sisa menipis | alis sedih, mulut bergelombang, keringat, tanda `!` |
| HOT (ngebut) | mata membelalak, mulut `o`, garis kecepatan, tanda `!` |
| Marah / tertawa | alis miring + urat / mata ^ ^ + mulut buka-tutup + "ha ha" |

Ikon di menu pilih pet juga dirender halus dari bentuk yang sama.

## Tampilan header (adegan per pet)

Header kini berupa adegan pixel-art penuh yang ikut berganti per pet:

| Pet | Adegan | Animasi |
|---|---|---|
| Nova (astronot) | Malam salju + aurora + bulan sabit + pegunungan | aurora bergelombang, bintang berkedip, salju turun, nada ♪ melayang |
| Obi (gurita topi) | Gurun senja + matahari berlapis + bukit pasir | matahari berdenyut, burung terbang, debu tertiup, `~` melayang |
| Piko (robot helm) | Laut dalam + berkas cahaya diagonal + bukit karang | cahaya bergoyang, ikan berenang, gelembung naik |
| Kubo (kubus) | Malam berawan + pegunungan batu + kristal | awan bergeser, kilat sesekali, hujan + percikan |
| Zuzu (UFO) | Ruang hampa gelap + planet bercincin + asteroid | planet melayang naik-turun, hujan meteor, `z` melayang |

Tata letak: lencana periode (`24H`) + teks `terpakai / budget` di baris atas,
bar segmen bulat di bawahnya, persen besar + keterangan `sisa` di kanan,
tombol `^`, dan berlian kecil berkilau di pojok. Pet diberi kontur gelap
otomatis. Semua animasi mati bersama `"weather_effects": false` hanya untuk
partikel cuaca; adegan tetap tampil.

## Warna responsif & panel kartu

- Warna status bergradasi halus hijau -> kuning -> merah mengikuti sisa token
  (bukan 3 loncatan), dipakai bersama oleh bar header, bar ringkasan, persen,
  lencana periode, dan tepi header.
- Saat sisa menipis, latar & tepi header ikut memerah pelan-pelan sebelum
  mode kedip menyala.
- Palet turunan otomatis per tema: `SURFACE` (kartu), `DARK` (track bar),
  `LINE` (garis tipis), jadi semua tema tetap serasi tanpa edit satu per satu.
- Panel dibuat berkartu: ringkasan, grafik aktivitas, dan tiap baris model
  (model terpilih disorot). Tab, tombol, dan bar memakai sudut membulat
  yang sama dengan header.

## Periode: 24H, 7D, TODAY, ALL

Di panel, tombol periode tersusun 2 baris: **24H · 7D** di atas, **TODAY · ALL**
di bawahnya. Klik lencana periode di header untuk berganti berurutan.
Tiap periode punya batas sendiri. Batas ikut sendiri mengikuti pemakaian,
jadi captionnya tidak bisa diklik (lihat [Batas otomatis](#batas-otomatis)).
Pace TODAY dihitung terhadap sisa waktu sampai tengah malam. Bila 9router
memakai nama periode lain, petakan lewat `"period_api"` di `config.json`, mis.
`"period_api": {"today": "24h"}`.

**Batas = batas token yang boleh dipakai, bukan jumlah yang sudah terpakai.**
Sisa = batas − terpakai, jadi angka batas harus lebih besar dari pemakaian.

### Batas otomatis

Batas **ikut sendiri** mengikuti pemakaian — begitu pemakaian tembus batas
lama, batas ikut naik, jadi widget tidak pernah merah karena batasnya basi.
Cadangan selalu dijamin di atas pemakaian, jadi sisanya tidak pernah 0%.

- **24H / TODAY** — angka 9router sudah berupa *jendela geser*, jadi batas
  ikut turun lagi saat jendela bergeser.
- **7D / ALL** — angkanya kumulatif, jadi batas ikut naik dan tidak pernah turun.

Angka batas = pemakaian + cadangan, dan catatan batasnya disimpan di
`window_pos.json`, jadi restart tidak mengembalikan batas ke nilai lama.

| Setelan config | Guna |
|---|---|
| `auto_budget` | `false` = batas tetap dari `combo_budget` (tanpa ikut naik) |
| `auto_headroom` | Cadangan dalam persen di atas pemakaian (default 25) |
| `auto_floor` | Cadangan minimum token (default 1M) |

Batas otomatis ikut sendiri, jadi captionnya **tidak bisa diklik** — tidak
ada yang perlu diubah karena batasnya memang bergerak sendiri. Kalau mau
batas tetap, isi `manual_budgets` di `window_pos.json` atau setel
`"auto_budget": false` di `config.json`.

9router **tidak punya** field limit/quota — `/api/usage/stats` hanya mengirim
`total*Token`, `by*`, dan `last10Minutes`, dan tidak ada endpoint limit.
Jadi angka batas **tidak pernah dikarang dari API**: batas otomatis dihitung
dari pemakaian nyata yang benar-benar dilaporkan, bukan dari tebakan.

## Tema otomatis per pet

Ganti pet (klik pet di header) → warna widget, tanah, dan hiasan
ikut berganti sesuai warna pet:

| Pet | Tema | Hiasan |
|---|---|---|
| Obi (default) | Gurun: coklat gelap + pasir | kaktus |
| Nova | Salju: indigo malam + salju putih | cemara bersalju |
| Piko | Samudra: biru laut | rumput laut |
| Kubo | Batu: abu-biru slate | kristal |
| Zuzu | Luar angkasa: ungu malam | bintang |

- **Animasi cuaca di header** (di belakang bar/teks, tidak mengganggu):

  | Tema | Efek |
  |---|---|
  | Gurun | debu & pasir tertiup angin (embusan bergelombang) |
  | Salju | salju turun melayang |
  | Samudra | gelembung naik |
  | Batu | hujan + percikan di tanah |
  | Luar angkasa | bintang berkedip + bintang jatuh sesekali |

  Saat status **HOT**, efeknya ikut kencang (angin/hujan/salju lebih cepat).
  Matikan efek saja: `"weather_effects": false` di `config.json`.
- Tema ikut tersimpan lewat pilihan pet di `window_pos.json`.
- Matikan: set `"theme_follows_pet": false` di `config.json` (selalu gurun).
- Tambah pet baru: tambahkan entri di `THEMES` (`pet_monitor.py`) dengan
  nama pet huruf kecil (salin salah satu tema yang ada sebagai contoh); tanpa entri, dipakai tema gurun.
- **Yang ikut tema:** latar, border, semua tombol (periode aktif, QUIT,
  chevron, sembunyikan model), badge CHILL/WARM/HOT, bar & persen, grafik
  aktivitas, titik warna tiap model, menu pilih pet, dan dialog budget.
  Warna "aman / hati-hati / bahaya" tetap dibedakan, tetapi nuansanya
  disesuaikan tema (aman = warna aksen tema, hati-hati = kuning/amber,
  bahaya = merah). Warna teks di atas tombol/badge dipilih otomatis agar
  tetap terbaca.

## Cara menjalankan

```bat
cd C:\Website\TokenPet
python pet_monitor.py
```

Tanpa jendela konsol (mode widget murni): klik-ganda `pet_monitor.pyw`,
atau dari terminal:

```bat
start pet_monitor.pyw
```

Cara menutup: klik `^` untuk buka panel → klik `QUIT`.
Darurat (tanpa GUI): `taskkill /F /IM pythonw.exe`.

Uji otomatis (data simulasi + GUI demo terbuka 5 detik):

```bat
python pet_monitor.py --selftest
```

Diagnostik data asli (tanpa widget, password/cookie disamarkan):

```bat
python pet_monitor.py --debug-stats
```

Mencetak: daftar model combo, field tiap baris `byModel`
(`promptTokens`, `completionTokens`, `requests`, `rawModel`,
`provider`, ...), hasil pencocokan tiap model combo → baris stats,
dan daftar yang masuk "di luar combo" untuk periode 24h dan 7d.

## Cara kerja data (live, bukan dummy)

1. **Daftar model otomatis dari combo** — tiap polling (5 detik) widget
   baca `combos_url` (`/api/combos`) dan ambil `models` milik
   `combo_name`. Tambah/hapus model di dashboard 9router →
   langsung tampil di GUI tanpa edit config.
2. **Token per-model dari stats asli** — `/api/usage/stats?period=24h`
   (`byModel`: prompt + completion + request per model).
3. **Login otomatis** — blok `auth` (`login_url` + `password`),
   cookie `auth_token` hanya di memori, refresh sendiri bila 401.

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

9router **tidak memberi limit per-model**, jadi widget memakai dua mode:

- **Default: `% = share of combo`** — pangsa token model dari total token
  combo. Panjang bar = persen yang tertulis.
- **Budget: `% = used/budget`** — isi `model_budgets` di config, mis.
  `"model_budgets": {"muse-spark-1.3-contributor-free": 100000000}`;
  bar jadi bar sisa kuota (hijau→kuning→merah). Kunci fleksibel: cukup
  segmen akhir nama (`"nemotron-3-ultra-550b-a55b": 5000000`).

## Cek akurasi vs 9router

```bat
python pet_monitor.py --verify
```

Mencetak, untuk 24h dan 7d: total resmi 9router (prompt+completion), jumlah
semua baris `byModel`, bagian yang masuk combo, bagian di luar combo, dan
apakah semuanya cocok. Bandingkan baris *total resmi* dengan dashboard
9router.

Yang dijaga widget:

- Sebelum data pertama masuk (atau setelah ganti tab 24H/7D) bar menampilkan
  `--%`, bukan `100%` palsu.
- Combo yang berisi combo lain diurai rekursif, jadi token model aslinya ikut.
- Panel menampilkan `total 9router` dan `selisih rincian` bila total resmi
  berbeda dari jumlah baris `byModel`.
- Bila 9router tak terjangkau / data tak diperbarui, bar header meredup dan
  bertuliskan `data lama`.
- Persen sisa = 100% - terpakai / **budget di config** (9router tidak punya
  limit per combo). Total yang dihitung hanya model di combo; token di luar
  combo ditampilkan terpisah.
- Bila header menampilkan `%` satu model (bukan sisa combo), itu karena model
  tersebut sedang dipilih: klik barisnya lagi di panel untuk melepas.

## Bar utama + pace

Bar ringkas = **total token semua model di combo** vs `combo_budget`
(`"24h"` / `"7d"` / `"today"` / `"all"`). Gaya bar bersegmen (hijau sisa > 50%, kuning 20–50%,
merah < 20%) dipakai di bar atas, bar total panel, dan bar tiap model.
Ingin bar polos? Set `"bar_style": "solid"`.

## Budget (bukan limit provider)

"sisa budget 46%" = 100% − terpakai / **budget yang Anda tentukan**; 9router
tidak memberi limit asli per model. Klik teks `budget ... · klik utk ubah`
di panel untuk mengganti budget periode aktif (`100M`, `2.5B`, `750k`);
tersimpan di `window_pos.json` (tidak menulis ulang `config.json`).

## Notifikasi

Saat sisa budget melewati 20% / 10% / 5% (atau pace jadi HOT) widget
membunyikan nada sistem dan menampilkan banner merah di bar atas selama
12 detik. Bunyi hanya saat kondisi *memburuk* (ada histeresis, tidak
berulang saat angka naik-turun). Atur di blok `alerts` pada config
(`enabled`, `sound`, `levels`, `hot`, `cooldown_seconds`, `banner_seconds`).

## Riwayat

Grafik batang di panel (per jam untuk 24H, per 6 jam untuk 7D) dibuat dari
penambahan token yang **terekam widget selama menyala** — jadi kosong
untuk waktu saat widget mati. Disimpan di `history.json`.

## Insight lokal (tanpa API key, tanpa kirim data keluar)

Ikon **grafik** di footer (atau tekan `h`) membuka panel **INSIGHT** —
analisis dari `history.json` di mesin ini, bukan fitur dashboard 9router:

- **Sesi**: durasi, token, request sesi terakhir + jumlah sesi hari ini
  (tombol `RESET SESI` hanya menghapus catatan sesi, bukan riwayat token).
- **Prediksi**: estimasi kapan pemakaian mencapai batas — selalu dilabeli
  estimasi lokal TokenPet, bukan kuota resmi 9router. Muncul hanya bila
  data cukup (min 6 bucket); kalau kurang, panel bilang "belum", bukan menebak.
- **Anomali**: penanda lonjakan token/request vs rata-rata sebelumnya
  (alasan angka disertakan; bukan tuduhan penyebab).
- **Saran hemat**: urutan rata-rata token/request terkecil — info saja,
  tak menilai mutu jawaban dan tak mengganti model aktif.
- **Tanya pet**: 4 tombol cepat (hemat, sesi, prediksi, batas) + `TANYA...`
  untuk menulis sendiri. Dijawab dari angka lokal; pertanyaan di luar itu
  dijawab jujur "belum paham".
- **Progres pet**: misi harian + XP + level (maks 40). XP hanya dari
  memantau aplikasi (buka widget, cek insight, sesi berturut) — **bukan**
  dari memakai token lebih banyak. Hadiah level memakai aksesori yang
  sudah ada dan tak pernah menimpa pilihanmu sendiri.
- **Kesehatan provider**: status koneksi yang sudah dipakai TokenPet
  (9router + akun AI yang login). Satu request gagal ≠ provider down.

Pengaturan di `config.json`:

- `insight`: `enabled` (master), `predict`, `anomaly`, `sessions`,
  `missions`, `anomaly_sensitivity` (2.5), `session_idle_seconds` (600),
  `min_buckets` (6), `maintenance_days` (30). Dua saklar utama juga ada
  di Settings: "Insight (sesi+prediksi)" dan "Misi & progres pet".
- `alert_notify`: kategori notifikasi pintar — `predict`, `anomaly`,
  `session` (default mati), `provider`, `mission` — masing-masing dengan
  cooldown sendiri, terpisah dari alert sisa token lama.
- Pet ikut bereaksi: gelisah saat anomali, tertawa saat naik level.

## Autostart Windows

Atur lewat perintah:
`python pet_monitor.py --autostart on` / `off`. Memakai registry
`HKCU\...\Run` (tanpa admin), menjalankan `pet_monitor.pyw`.

## Satu instance + log error

- Widget hanya berjalan **satu instance**: instance kedua langsung keluar
  dengan pesan `TokenPet sudah berjalan` (named mutex Windows,
  fallback file lock di OS lain).
- Error tak tertangani (termasuk dari thread polling dan callback Tk)
  ditulis ke **`tokenpet.log`** di folder program dengan rotasi sederhana
  (maks ~200 KB, lama jadi `tokenpet.log.1`). Penting karena `.pyw`
  tidak punya konsol. Keduanya (`tokenpet.log`, `tokenpet.lock`)
  sudah di `.gitignore`.

## Layar 125% / 150%

Widget memakai DPI-aware sehingga tajam, dan seluruh ukuran mengikuti
skala layar. Bila ada masalah, set `"dpi_aware": false`.

## Daftar model banyak: sembunyi dulu

Bila model di combo > `collapsed_rows` (default 4), panel hanya
menampilkan 5 teratas (urut token). Klik **`+ tampilkan N model lain`**
untuk membuka semua; di sebelahnya ada ringkasan `lainnya: <token> · <%>`.
Saat terbuka dan melebihi `max_model_rows` (atau tinggi layar), daftar bisa
digulir dengan **scroll mouse**. Klik **`- sembunyikan`** untuk menutup lagi.

## Responsif

- **Header responsif**: posisi pet, label, bar, dan persen dihitung dari
  ukuran teks nyata; seluruh tampilan (termasuk panel) membesar/mengecil
  proporsional dari 360 sampai 900 px, dan digambar ulang langsung saat
  tepi kanan ditarik. Kaktus ada di belakang bar (disembunyikan bila sempit).
- **Ubah lebar**: seret **tepi kanan** widget (kursor berubah jadi panah
  ↔). Lebar 360–900 px; seluruh tata letak, font, jumlah segmen bar, dan
  pemotongan nama model menyesuaikan lebar. Lebar tersimpan di
  `window_pos.json`.
- Tinggi mengikuti isi dan otomatis bergeser naik bila panel akan keluar
  layar. Posisi tersimpan juga dijaga agar selalu terlihat (virtual
  screen Windows, aman untuk multi-monitor yang berubah).
- Tidak lagi menggambar ulang tiap detik: hanya saat data berubah,
  diklik, atau di-resize (teks "just now" diperbarui saja).
- Kursor jadi tangan di atas tombol/baris yang bisa diklik.

## Jika widget menampilkan ERR

| Pesan | Arti |
|---|---|
| `ERR: login gagal (password salah?)` | Password di `auth.password` salah |
| `ERR: HTTP Error 401 ...` | Cookie ditolak & login ulang gagal — cek 9router jalan di `:20128` |
| `ERR: <urlopen error ...>` | 9router mati / port berubah |
| `ERR: combo '...' tak ketemu` | `combo_name` salah ketik — cek nama di dashboard |

## Pakai

- Seret dari area mana saja (kecuali tombol) untuk pindah.
- Pengaturan tampilan (panel terbuka, daftar model, model terpilih, urutan,
  tab 24H/7D, pet, lebar) diingat saat dibuka lagi.
- `^` / `v`: buka/tutup panel detail. `QUIT`: keluar (posisi tersimpan).
- **Klik baris model = pilih**: bar ringkas ikut tampilkan `%` model itu
  + nama pendeknya; klik lagi untuk lepas. Model terpilih ditandai `>`.
- Bar kuota hijau sisa > 50%, kuning 20–50%, merah < 20%.
- Klik **pet di header** = dropdown pilih pet:
  Nova (astronot), Obi (gurita topi), Piko (robot helm),
  Kubo (kubus 3D), Zuzu (UFO melayang). Pilihan tersimpan di
  `window_pos.json`.
- Widget berkedip + tanda `!` muncul saat HOT atau sisa < 20%.
- Demo (`"demo": true`): data simulasi untuk coba tampilan tanpa 9router.

## Aksesoris pet & logout

- Tombol paling kanan di barisan ikon footer membuka **dropdown aksesoris**:
  Topi (17), Kacamata (9), Wajah (8), Leher (6), Punggung (4), Lainnya (5),
  plus *Acak* dan *Lepas semua*. Tambahan modern mencakup topi cyber, visor
  AR, jetpack mini, dan lencana AI. Bisa dikombinasi
  dan disimpan per pet di `window_pos.json` (`acc`).
- Efek lagu saat hover pet diringankan: 1 nada, tanpa kilau, joget kecil,
  animasi ~11 fps.
- Tombol **LOGOUT** di sebelah teks status ("just now"): menghapus cookie,
  memberi tahu server (`auth.logout_url`, default `/api/auth/logout`) dan
  menghentikan polling. Berubah jadi **LOGIN** untuk menyambung lagi.

## Cuaca, dekorasi, QUIT/LOGOUT

- Footer: **bohlam** = dekorasi latar (lampu hias berkedip, lampion, bendera
  segitiga, bintang gantung, hologram data, atau orbit kosmik); **awan** =
  ganti cuaca (otomatis ikut tema,
  pasir, salju, hujan, gelembung, bintang, kelopak sakura, daun gugur,
  kunang-kunang, hujan meteor, atau tanpa cuaca). Pengaturan yang sama kini
  juga terlihat di Settings, bersama tombol **ATUR** aksesori.
  Pilihan tersimpan di `window_pos.json`.
- QUIT sekarang di sebelah teks status ("just now"); LOGOUT/LOGIN pindah ke
  posisi QUIT yang lama. Tombol bintang (refresh) dihapus; data tetap
  diperbarui otomatis, dan LOGIN memaksa ambil data baru.

## Update: pet per layanan, kuota ChatGPT, pilar menabrak

**Enam pet, tiap layanan punya pet sendiri** (Copilot dihapus):

| Pet | Layanan | Ciri |
|---|---|---|
| Robo | 9router (utama) | robot futuristis berlapis, visor LED biru, inti dada bercahaya |
| Claude | Claude | gumpalan terakota, pelat wajah krem, kilau 4 titik |
| ChatGPT | ChatGPT | gelembung ucapan hijau-toska + titik ketik |
| Antigravity | Antigravity | roh kubah ungu melayang, cincin orbit, api kecil |
| Cursor | Cursor | kotak grafit, pelat wajah terang, panah kursor |
| Codex | Codex | awan lavender, layar terminal, prompt `>_` |

- Semua pet punya ekspresi lengkap (kedip, senyum, tertawa, sibuk, cemas,
  kaget, marah) dan anchor aksesoris sendiri (49 aksesori dicek per pet).
  Pet Antigravity & Codex menampilkan `>_` saat model sedang jalan.
- **Tema ikut pet** (Settings > "Tema ikut pet" ON): tiap pet punya adegan
  dan warna sendiri. Senja berupa rooftop hangat, Gurun tetap bukit pasir;
  Gravitasi Nol berupa kisi holografik dan pulau melayang, sedangkan Luar
  Angkasa berupa ruang hampa gelap dengan asteroid dan meteor.
  Memilih tema dari ikon matahari = manual, mematikan "ikut pet". Pilihan
  ini sekarang tersimpan di `window_pos.json`.
- `ai_accounts.json` lama otomatis dimigrasi: akun Copilot dibuang, pet tiap
  layanan direset ke pet barunya (status login tetap dipertahankan).

**Kuota ChatGPT** (saat pet ChatGPT tampil, mis. akun ChatGPT diaktifkan di
Settings, panel dan header menampilkan kuota akun, bukan model 9router):

- Header: jendela terpilih (`5J` / `MGG`), persen terpakai, hitung mundur
  reset, dan bar sisa. Ketuk lencana untuk ganti jendela.
- Panel: kartu **5 jam** dan **Mingguan** (sisa %, terpakai %, waktu reset
  dan jam reset), kredit tersisa bila ada, tombol `↻` untuk segarkan.
  Pet ikut bereaksi (cemas saat sisa menipis, sibuk saat pemakaian naik).
- Sumber data: `GET https://chatgpt.com/backend-api/wham/usage`, endpoint
  internal yang juga dipakai Codex CLI. **Tidak terdokumentasi resmi** dan
  bisa berubah; bila gagal, widget menampilkan pesan, bukan crash. Paket
  yang hanya punya batas mingguan hanya menampilkan satu kartu.
- Token (urutan): `chatgpt_quota.access_token` di `config.json` >
  env `TOKENPET_CHATGPT_TOKEN` > file Codex CLI `~/.codex/auth.json` (atau
  `$CODEX_HOME`; cukup `codex login` sekali). File itu hanya **dibaca**:
  widget tidak menulis atau me-refresh token. Token hanya dikirim ke
  `https://` kuota di atas, tidak masuk log/file. Matikan pembacaan file
  Codex dengan `"use_codex_auth": false`. Jika token kedaluwarsa, jalankan
  `codex` sekali lalu ketuk `↻`.
- Opsi di `config.json` > `chatgpt_quota`: `poll_seconds` (min 20, bawaan
  60), `use_codex_auth`, `access_token`, `account_id`, `auth_file`.
- Catatan: login Google di Settings hanya penanda lokal; kuota diambil dari
  token Codex/ChatGPT di atas, bukan dari login Google itu.

**Pilar di belakang bar header** (tema Perkotaan dan Editor) kini melompat
bergantian dan **menabrak** sisi bawah bar status: pilar berhenti di bar,
kilatan putih + percikan, lalu jatuh lagi.

## Update: robot berekspresi, cuaca kembali, login Google

- **Wajah Robo (layar LED)**: mata, alis, dan mulut digambar sebagai lampu
  (bukan glyph statis), jadi bisa kedip, melirik kursor, dan berganti
  ekspresi: biasa, senyum (hover), tertawa, **sibuk**, cemas (lampu kuning
  saat sisa menipis), kaget (HOT), marah. Warna lampu antena ikut suasana.
- **Ekspresi sibuk = model sedang jalan**: mata menyapu kiri-kanan, tiga
  titik "memproses" di mulut, garis pindai di layar, lampu antena berdenyut
  (lebih cepat bila HOT; kuning bila sisa menipis). Dideteksi dari
  `pending.byModel` / `activeRequests` di `/api/usage/stats` 9router (request
  yang *sedang* berjalan). Panel menulis "model lagi jalan - N request
  aktif". Jika 9router lama tidak mengirim info itu, widget memakai cara
  lama (total token naik, `busy_seconds`).
- **Aksesoris kembali muncul** untuk Robo (anchor `robo` sebelumnya hilang).
  Antena disembunyikan saat memakai topi. Semua 45 aksesoris sudah dicek.
- **Bar status header** lebih tebal (11 -> 16 satuan).
- **Cuaca kembali**: ikon **awan** di footer (di antara matahari dan
  bohlam) membuka menu cuaca; ada juga baris "Cuaca header" di Settings.
  (Matahari tetap = tema, bohlam = dekorasi.)
- **Login Google untuk Claude & ChatGPT** (Settings > Akun AI, ketuk OFF):
  - Tanpa setup: browser dibuka ke halaman login layanan (claude.ai /
    chatgpt.com) tempat tombol *Continue with Google* berada; setelah
    selesai, konfirmasi di widget (email boleh diisi).
  - Dengan `google_oauth.client_id` di `config.json` (OAuth client tipe
    *Desktop app* dari Google Cloud Console; `client_secret` bila diminta):
    widget menjalankan OAuth + PKCE di `127.0.0.1`, memverifikasi email
    Google Anda, lalu membuka halaman login layanan. Tidak ada token Google
    yang disimpan; hanya email dan penanda `via: Google` di
    `ai_accounts.json`.
  - Catatan: login ke ChatGPT/Claude tetap terjadi di browser; widget tidak
    membaca sesi/cookie mereka, jadi status "tersambung" bersifat lokal
    (menandai akun & pet), bukan token API.

## Update: deteksi manual, hanya 9router yang aktif

- **Tidak ada lagi yang tersambung sendiri.** Saat widget dibuka, hanya pet
  9router (Robo) yang tampil. Akun Claude / ChatGPT / Codex yang dulu
  tersambung otomatis direset ke OFF.
- Akun baru aktif setelah **Anda** mengetuknya: `OFF` (Claude) atau `DETEKSI`
  (ChatGPT / Codex) untuk mendeteksi login CLI, lalu `ON` untuk memakainya.
  Pet layanan baru muncul di menu setelah akunnya terdeteksi.
- Tidak ada pemindaian berkala di latar belakang lagi.

## Update: ChatGPT + Codex disatukan, tombol DETEKSI

- **ChatGPT dan Codex kini satu akun** di Settings > Akun AI
  (`ChatGPT + Codex`). Pet ChatGPT dan pet Codex sama-sama muncul setelah
  akun ini login dan sama-sama menampilkan kuota akun yang dipilih. Dua tombol
  eksplisit, **CHATGPT** dan **CODEX**, memilih pet yang sesuai lalu membuka
  portal resminya dengan akun yang sama.
- Tombol **DETEKSI** di baris itu mencari semua akun ChatGPT/Codex yang
  sedang login. Satu akun: langsung dipakai. Dua akun atau lebih: muncul menu
  pilih (`●` = yang sedang dipakai). Pilihan disimpan; kuota langsung diganti
  ke akun terpilih. Baris akun menampilkan `(N akun)` bila ada lebih dari satu.
- Yang dipindai: `$CODEX_HOME`, `~/.codex`, setiap folder `~/.codex*/`, serta
  `chatgpt_quota.auth_file` / `auth_files` (daftar) di `config.json`.
- **Akun kedua** (mis. akun kerja) - login ke folder terpisah, sekali saja:

  ```bat
  set CODEX_HOME=%USERPROFILE%\.codex-kerja
  codex login
  ```

  Folder `~/.codex-kerja` otomatis ikut terdeteksi.
- Catatan: widget **tidak membaca sesi/cookie browser**. "Akun yang sedang
  login" berarti akun yang login lewat Codex CLI (file `auth.json`); login
  chatgpt.com di browser tidak terlihat oleh widget.

## Update: login otomatis (tanpa browser) + kuota Claude

- **Claude, ChatGPT, dan Codex terdeteksi otomatis** dari token login CLI
  masing-masing; tidak ada lagi jendela browser / konfirmasi manual:

  | Layanan | File token yang dibaca | Cara login |
  |---|---|---|
  | Claude | `~/.claude/.credentials.json` (`$CLAUDE_CONFIG_DIR`) | jalankan `claude`, login sekali |
  | ChatGPT / Codex | `~/.codex/auth.json` (`$CODEX_HOME`, `~/.codex*/`) | `codex login` sekali |

  Deteksi hanya berjalan saat Anda mengetuk `OFF` / `DETEKSI` (lihat update
  "deteksi manual"), tanpa browser. File token hanya
  **dibaca**; tidak ditulis, tidak di-refresh, dan **tidak disalin** ke
  `ai_accounts.json` (hanya email + paket).
- **Kuota tiap layanan dari tokennya sendiri, bukan 9router.** Pet Claude
  menampilkan kuota akun Claude (5 jam / mingguan / Opus / Sonnet bila ada),
  pet ChatGPT dan Codex menampilkan kuota akun OpenAI. Pet 9router tetap
  menampilkan token 9router.
- Sumber Claude: `GET https://api.anthropic.com/api/oauth/usage` (header
  `anthropic-beta: oauth-2025-04-20`), endpoint internal yang dipakai Claude
  Code. **Tidak terdokumentasi resmi** dan bisa berubah; bila gagal widget
  menampilkan pesan, bukan crash. Token kedaluwarsa: jalankan `claude`
  sekali, lalu ketuk `↻`. Opsi di `config.json` > `claude_quota`:
  `url`, `auth_file`.
- Cursor dan Antigravity belum punya deteksi otomatis (tetap login manual).

## Update: dekorasi saja

- (Riwayat; tombol cuaca sudah kembali, lihat update di atas.) Tombol **bohlam** di footer kini hanya untuk dekorasi
  latar: lampu natal warna-warni, lampu kuning hangat, lampu neon, lampion,
  bendera segitiga, bintang gantung. Tombol LOGOUT dihapus; QUIT tetap di
  sebelah teks status.

## Update: lampu, tema salju, daftar model

- Dekorasi lampu digambar ulang: bohlam gantung dengan soket, pendar
  berlapis, dan kilau kaca; ada lampu natal, lampu peri hangat, untaian
  cemara + lampu, neon, lampion, bendera, bintang gantung.
- Tema Salju: warna peringatan bar kini biru es (bukan kuning/oranye).
- Daftar model di panel awalnya hanya 4; klik "+ tampilkan N model lain".
