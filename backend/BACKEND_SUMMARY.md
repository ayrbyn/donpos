# DonPOS Backend - Ringkasan Lengkap

Terakhir diperbarui: 31 Oktober 2026
Status: Isolasi data multi-tenant, multi-outlet, onboarding owner, pembayaran tunai, impor produk massal, laporan CSV, diskon/pajak, nomor invoice per tenant/outlet, perlindungan SKU/barcode Excel, dan kolom BIGINT untuk stok serta nilai transaksi tersedia. Terapkan seluruh migrasi sebelum API digunakan. Billing, verifikasi email, MFA, dan kontrol operasi platform belum tersedia.

Dokumen ini adalah acuan utama backend: stack, struktur, desain database dan relasi, logika tiap modul, daftar endpoint, aturan bisnis, keamanan, hasil pengujian, kekurangan yang diketahui, dan panduan integrasi untuk aplikasi mobile.

---

## Daftar isi

1. Gambaran umum
2. Stack
3. Struktur folder
4. Konfigurasi dan cara menjalankan
5. Arsitektur dan alur request
6. Desain database
7. Role dan hak akses
8. Logika per modul
9. Daftar endpoint lengkap
10. Aturan bisnis dan invarian data
11. Konkurensi dan integritas data
12. Keamanan
13. Kode status dan format error
14. Panduan integrasi mobile
15. Hasil pengujian
16. Kekurangan yang diketahui
17. Rencana berikutnya
18. Perintah yang sering dipakai

---

## 1. Gambaran umum

Backend DonPOS adalah REST API untuk aplikasi kasir (POS) mobile. Fitur yang sudah selesai:

- Login dengan token JWT, password di-hash dengan Argon2.
- Tiga role: owner, admin, cashier, dengan pembatasan akses per endpoint.
- Manajemen kategori dan produk, pencarian, dan pencarian lewat barcode.
- Impor produk massal dari file CSV atau XLSX, dengan pratinjau dan semua-atau-tidak-sama-sekali.
- Transaksi tunai dengan pengurangan stok otomatis dan pencegahan transaksi ganda.
- Pembatalan transaksi (void) yang mengembalikan stok.
- Penyesuaian stok manual dengan riwayat lengkap (stock ledger).

Belum ada: pembayaran QRIS atau e-wallet, refresh token, dan sinkronisasi offline.

## 2. Stack

| Bagian | Teknologi |
|---|---|
| Bahasa | Python 3.11 |
| Framework | FastAPI |
| Server | Uvicorn |
| Database | PostgreSQL 18 (lokal, dikelola lewat pgAdmin) |
| ORM | SQLAlchemy 2.0 async, driver asyncpg |
| Migrasi | Alembic (template async) |
| Validasi dan konfigurasi | Pydantic v2, pydantic-settings |
| Hash password | pwdlib (Argon2) |
| Token | PyJWT, algoritma HS256 |
| Impor file | openpyxl (XLSX), xlrd (XLS), modul csv bawaan Python, python-multipart (upload) |

## 3. Struktur folder

```
donpos/
  backend/
    alembic/                    konfigurasi dan file migrasi
    alembic.ini
    requirements.txt
    .env                        rahasia dan konfigurasi (tidak masuk git)
    app/
      main.py                   aplikasi FastAPI dan pendaftaran router
      api/
        deps.py                 get_current_user dan require_roles
        auth.py                 tenant signup, register, login, me
        tenants.py              profil tenant aktif
        outlets.py              daftar dan pengelolaan outlet
        categories.py           CRUD kategori
        users.py                daftar, ubah, aktifkan/nonaktifkan, dan reset password pengguna
        products.py             CRUD produk, barcode, penyesuaian stok, riwayat stok
        product_import.py       impor produk dari CSV atau XLSX
        transactions.py         buat, daftar, detail, dan void transaksi
        reports.py              laporan penjualan JSON dan ekspor CSV
      core/
        config.py               pembacaan .env (Settings)
        security.py             hash password dan JWT
      db/
        base.py                 Base dan BaseModel (UUID, timestamp, soft delete)
        session.py              engine, session, dependency get_db
      models/
        user.py
        tenant.py               organisasi tenant
        outlet.py               Outlet dan relasi penugasan pengguna
        category.py
        product.py
        stock_movement.py
        transaction.py          Transaction, TransactionItem, dan InvoiceCounter
      schemas/
        user.py
        category.py
        product.py              termasuk StockAdjust dan StockMovementOut
        product_import.py       ImportResult dan RowMessage
        transaction.py          termasuk skema pajak dan diskon
```

## 4. Konfigurasi dan cara menjalankan

### File .env

| Variabel | Fungsi |
|---|---|
| DATABASE_URL | `postgresql+asyncpg://pos_user:PASSWORD@localhost:5432/pos_db` |
| SECRET_KEY | Kunci penanda token JWT, acak dan panjang |
| ACCESS_TOKEN_EXPIRE_MINUTES | Masa berlaku token dalam menit (bawaan 60) |
| TAX_RATE_PERCENT | Tarif pajak persen (bawaan 0; maksimal 100 dengan dua desimal) |

Membuat SECRET_KEY:

```
python -c "import secrets; print(secrets.token_hex(32))"
```

### Menjalankan

```
cd D:\dzakky\project\donpos\backend
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0
```

- Dokumentasi interaktif: `http://127.0.0.1:8000/docs`
- Cek kesehatan: `http://127.0.0.1:8000/health`
- Opsi `--host 0.0.0.0` membuat backend bisa diakses HP lewat jaringan WiFi yang sama.

### Riwayat migrasi Alembic

| Urutan | Isi |
|---|---|
| 1 | Tabel users dan products |
| 2 | Tabel categories dan kolom products.category_id |
| 3 | Tabel transactions, transaction_items, stock_movements |
| 4 | Kolom note dan user_id di stock_movements |
| 5 | Pajak dan diskon transaksi serta counter invoice harian |
| 6 | Multi-outlet, pemisahan katalog/stok, keanggotaan user, dan counter per outlet |
| 7 | Tenant, isolasi akun/outlet, onboarding tenant, dan versi sesi token |

Tabel `invoice_counters` memakai gabungan tanggal WIB dan outlet sebagai primary key. Migrasi multi-outlet memindahkan data lama ke outlet bawaan `MAIN`; migrasi tenant memindahkan semua data lama ke tenant `DONPOS01`. Nomor invoice baru menyertakan kode tenant dan outlet. Setiap model baru harus didaftarkan di `app/models/__init__.py` agar terdeteksi Alembic.

## 5. Arsitektur dan alur request

Alur umum sebuah request:

```
Client -> Router (app/api/*.py)
       -> Dependency: get_db (membuka session)
       -> Dependency: get_current_user / require_roles (membaca token, cek user di database)
       -> Validasi body dengan skema Pydantic (app/schemas)
       -> Logika bisnis di fungsi endpoint
       -> SQLAlchemy async -> PostgreSQL
       -> Response dibentuk dari response_model
```

Prinsip yang dipakai:

- Satu session database per request. Perubahan baru tersimpan saat `commit()` dipanggil. Kalau terjadi error (misalnya `HTTPException`) sebelum commit, session ditutup tanpa menyimpan apa pun, sehingga tidak ada data setengah tersimpan.
- Hak akses dicek lewat dependency, bukan di dalam logika endpoint.
- Role dan tenant yang dipakai untuk otorisasi diambil dari database pada setiap request. Klaim tenant dan versi sesi token harus cocok dengan database; perubahan password, status, role, atau penugasan outlet dapat membatalkan sesi.
- Endpoint bisnis membutuhkan header `X-Outlet-ID`. Owner dapat memilih outlet mana pun; admin/kasir hanya boleh memilih outlet yang ditugaskan kepadanya.
- Tenant ditentukan dari akun yang sudah terautentikasi. API tidak menerima `tenant_id` dari klien sebagai dasar otorisasi. Semua outlet harus berada dalam tenant akun; assignment pengguna-outlet ditegakkan lagi dengan foreign key gabungan.
- `POST /auth/signup` dibatasi maksimum lima permintaan per alamat IP per jam dengan counter PostgreSQL lintas worker; IP disimpan sebagai HMAC, bukan plaintext.
- Router impor produk didaftarkan sebelum router produk agar `/products/import` tidak tertangkap oleh `/products/{product_id}`. Di router produk, `/products/barcode/{barcode}` juga ditulis sebelum `/products/{product_id}`.

## 6. Desain database

### 6.1 Konvensi semua tabel

Tabel bisnis mewarisi `BaseModel` dengan kolom berikut. Pengecualian `invoice_counters` hanya memiliki tanggal invoice, outlet, dan counter untuk mendukung urutan atomik harian per outlet.

| Kolom | Tipe | Keterangan |
|---|---|---|
| id | UUID | Primary key, dibuat dengan uuid4 (tidak bergantung urutan, aman untuk data dari perangkat offline) |
| created_at | timestamptz | Otomatis saat dibuat (server default now) |
| updated_at | timestamptz | Otomatis saat dibuat dan diubah |
| deleted_at | timestamptz, boleh kosong | Penanda soft delete |

Konvensi lain:

- Uang disimpan sebagai integer rupiah, tanpa desimal. Tidak ada float.
- Waktu disimpan dengan zona waktu (UTC). Nomor invoice memakai tanggal WIB.
- Penghapusan memakai soft delete (`deleted_at` diisi), agar data historis tetap utuh.

### 6.2 Diagram relasi

```
tenants    1 ----- * users, outlets
outlets    1 ----- * categories, products, transactions, stock_movements
users      * ----- * outlets               user_outlets (owner memiliki akses global di tenant-nya)
categories 1 ----- * products             products.category_id -> categories.id (boleh kosong)
users      1 ----- * transactions          transactions.cashier_id -> users.id
transactions 1 --- * transaction_items     transaction_items.transaction_id -> transactions.id
products   1 ----- * transaction_items     transaction_items.product_id -> products.id
products   1 ----- * stock_movements       stock_movements.product_id -> products.id
users      1 ----- * stock_movements       stock_movements.user_id -> users.id (boleh kosong)
transactions 1 --- * stock_movements       hubungan logis lewat reference_id (tanpa foreign key)
```

`stock_movements.reference_id` sengaja tanpa foreign key karena dipakai untuk berbagai jenis referensi (saat ini ID transaksi untuk alasan sale dan void).

### 6.3 Tabel users

| Kolom | Tipe | Aturan |
|---|---|---|
| username | varchar(50) | Unik, index, disimpan huruf kecil |
| full_name | varchar(100) | Wajib |
| password_hash | varchar(255) | Hash Argon2 |
| role | varchar(20) | owner, admin, atau cashier. Bawaan cashier |
| is_active | boolean | Bawaan true |

Pengguna non-owner dapat ditugaskan ke beberapa outlet melalui `user_outlets`; owner memiliki akses global dan tidak memerlukan baris penugasan.

Setiap pengguna dimiliki tepat oleh satu tenant (`users.tenant_id`). Username tetap unik global untuk login yang tidak ambigu. JWT menyimpan tenant ID dan `token_version`; API membandingkan keduanya terhadap data terbaru setiap request.

### 6.3a Tabel tenants, outlets, dan user_outlets

Tenant adalah batas kepemilikan usaha. Setiap user dimiliki tepat oleh satu tenant; owner memiliki akses global hanya di tenant-nya. Tenant dibuat melalui `POST /auth/signup` bersama owner dan outlet pertama secara atomik. Tenant ditentukan dari akun terautentikasi, bukan dari header atau parameter yang dikirim klien.

Setiap outlet memiliki nama, kode unik 2–8 karakter alfanumerik, dan status aktif. Produk, kategori, transaksi, pergerakan stok, dan counter invoice terikat pada satu outlet. Katalog serta stok antar outlet sepenuhnya terpisah.

### 6.4 Tabel categories

| Kolom | Tipe | Aturan |
|---|---|---|
| outlet_id | UUID | Foreign key ke outlets, index |
| name | varchar(100) | Unik dalam outlet |

Saat kategori dihapus, namanya diubah menjadi `nama__dihapus__id` supaya nama aslinya bisa dipakai lagi.

### 6.5 Tabel products

| Kolom | Tipe | Aturan |
|---|---|---|
| name | varchar(150) | Wajib, index |
| outlet_id | UUID | Foreign key ke outlets, index |
| sku | varchar(50) | Unik dalam outlet, boleh kosong |
| barcode | varchar(50) | Unik dalam outlet, boleh kosong |
| price | bigint | Rupiah, minimal 0, maksimal 9.223.372.036.854.775.807 |
| stock | bigint | Bawaan 0, tidak boleh negatif (dijaga di logika), maksimal 9.223.372.036.854.775.807 |
| is_active | boolean | Bawaan true |
| category_id | UUID | Foreign key ke categories, boleh kosong, index |

Saat produk dihapus, `sku` dan `barcode` dikosongkan supaya bisa dipakai produk baru.

### 6.6 Tabel stock_movements (buku besar stok)

| Kolom | Tipe | Keterangan |
|---|---|---|
| product_id | UUID | Foreign key ke products, index |
| outlet_id | UUID | Foreign key ke outlets, index |
| change | bigint | Positif menambah, negatif mengurangi |
| stock_after | bigint | Stok setelah perubahan ini |
| reason | varchar(30) | Lihat tabel alasan di bawah |
| note | varchar(255) | Catatan bebas, boleh kosong |
| reference_id | UUID | ID transaksi untuk sale dan void, boleh kosong, index |
| user_id | UUID | Foreign key ke users, siapa yang mengubah, boleh kosong |

Nilai `reason`:

| Reason | Asal | Pencatat (user_id) |
|---|---|---|
| initial | Produk dibuat dengan stok awal, atau produk baru dari impor file | Diisi |
| sale | Transaksi penjualan | Kasir yang membuat transaksi |
| void | Pembatalan transaksi | Owner atau admin yang membatalkan |
| restock | Penyesuaian manual | Diisi |
| correction | Penyesuaian manual | Diisi |
| damaged | Penyesuaian manual | Diisi |
| return | Penyesuaian manual | Diisi |

Stok produk selalu bisa ditelusuri: jumlah semua `change` per produk harus sama dengan `products.stock`.

### 6.7 Tabel transactions

| Kolom | Tipe | Aturan |
|---|---|---|
| invoice_number | varchar(50) | Unik global. Format `INV-{KODE_TENANT}-{KODE_OUTLET}-YYYYMMDD-NNNNNN`, counter terpisah per outlet dan reset setiap hari WIB |
| outlet_id | UUID | Foreign key ke outlets, index |
| cashier_id | UUID | Foreign key ke users, index |
| subtotal | bigint | Jumlah semua subtotal item |
| discount | bigint | Total diskon rupiah (item dan transaksi) |
| discount_percent | numeric(5,2) | Persentase diskon tingkat transaksi jika dipakai |
| tax_percent | numeric(5,2) | Tarif pajak server saat transaksi dibuat |
| tax_amount | bigint | Pajak rupiah setelah diskon |
| total | bigint | subtotal dikurangi diskon lalu ditambah pajak |
| payment_method | varchar(20) | Saat ini hanya cash |
| paid_amount | bigint | Uang yang diterima |
| change_amount | bigint | Kembalian |
| status | varchar(20) | completed atau voided |
| note | varchar(255) | Boleh kosong |

### 6.8 Tabel transaction_items

| Kolom | Tipe | Keterangan |
|---|---|---|
| transaction_id | UUID | Foreign key ke transactions, index |
| product_id | UUID | Foreign key ke products, index |
| product_name | varchar(150) | Salinan nama saat transaksi |
| price | bigint | Salinan harga saat transaksi |
| quantity | bigint | Jumlah |
| subtotal | bigint | price dikali quantity |
| discount | bigint | Diskon rupiah pada baris item |
| discount_percent | numeric(5,2) | Persentase diskon item jika dipakai |

Nama dan harga disalin agar laporan lama tidak berubah ketika produk diedit atau dihapus.

### 6.9 Tabel alembic_version

Dikelola Alembic, menyimpan versi migrasi yang sedang diterapkan.

### 6.10 Batasan angka

Nilai harga, stok, kuantitas, dan nominal transaksi memakai `BIGINT` PostgreSQL bertanda, dengan batas maksimum 9.223.372.036.854.775.807. API memvalidasi batas tersebut dan menolak subtotal/total atau stok yang akan melampauinya. Counter invoice dan nilai teknis kecil tetap memakai integer biasa.

## 7. Role dan hak akses

| Aksi | cashier | admin | owner |
|---|---|---|---|
| Login, lihat profil sendiri | ya | ya | ya |
| Lihat kategori dan produk | ya | ya | ya |
| Buat transaksi | ya | ya | ya |
| Lihat daftar dan detail transaksi | milik sendiri | semua | semua |
| Tambah, ubah, hapus kategori | tidak | ya | ya |
| Tambah, ubah, hapus produk | tidak | ya | ya |
| Impor produk dari file dan unduh template | tidak | ya | ya |
| Penyesuaian stok dan lihat riwayat stok | tidak | ya | ya |
| Void transaksi | tidak | ya | ya |
| Lihat dan ekspor laporan penjualan | tidak | ya | ya |
| Buat akun pengguna baru | tidak | tidak | ya |
| Lihat dan kelola akun pengguna | tidak | ya | ya |
| Mengubah password sendiri | ya | ya | ya |

## 8. Logika per modul

### 8.1 Autentikasi (app/api/auth.py, app/core/security.py, app/api/deps.py)

**Hash dan token**
- Password di-hash dengan Argon2 (`PasswordHash.recommended()` dari pwdlib).
- Token JWT berisi `sub` (ID user), `role`, dan `exp` (kedaluwarsa). Ditandatangani HS256 dengan SECRET_KEY.
- `decode_access_token` mengembalikan kosong jika token rusak atau kedaluwarsa.

**Pendaftaran tenant (`POST /auth/signup`)**
- Membuat tenant, owner, dan outlet pertama sebagai satu unit atomik.
- Dibatasi lima permintaan per IP per jam; endpoint bootstrap tanpa autentikasi sudah dihapus.

**Register (`POST /auth/register`)**
- Hanya owner. Role harus owner, admin, atau cashier.
- Username dijadikan huruf kecil dan dicek belum dipakai.

### 8.2 Manajemen pengguna (app/api/users.py)

- Owner dan admin dapat melihat daftar pengguna dengan paginasi; akun soft-deleted tidak ditampilkan dan akun nonaktif dapat disaring.
- Owner dan admin dapat mengubah username, nama lengkap, dan role. Admin tidak dapat mengubah akun owner atau memberi role owner.
- Owner dan admin dapat mengaktifkan atau menonaktifkan akun. Pengguna tidak dapat menonaktifkan dirinya sendiri; owner aktif terakhir tidak dapat dinonaktifkan atau diturunkan role-nya.
- Owner dan admin dapat menetapkan password baru pengguna lain; admin tidak dapat mereset password owner. Setiap pengguna dapat mengganti passwordnya sendiri setelah memverifikasi password saat ini.
- Password baru mengikuti batas 8–72 karakter dan selalu disimpan sebagai hash Argon2.

**Login (`POST /auth/login`)**
- Menerima form (`username` dan `password`), format standar OAuth2 password agar tombol Authorize di /docs berfungsi.
- Pesan error sama untuk user tidak ada dan password salah ("Username atau password salah").
- Akun nonaktif ditolak 403.

**get_current_user**
- Membaca token dari header `Authorization: Bearer ...`, lalu memverifikasi user, tenant, dan versi token terhadap database.
- Ditolak 401 jika token tidak valid, user tidak ada, sudah dihapus, atau tidak aktif.

**require_roles(*roles)**
- Memakai get_current_user, lalu membandingkan role di database dengan daftar yang diizinkan. Gagal berarti 403.

### 8.2 Kategori (app/api/categories.py)

- List: semua kategori yang belum dihapus, urut nama.
- Create dan update: nama di-strip, dicek belum dipakai (kecuali oleh kategori itu sendiri saat update).
- Delete: menolak dengan 400 jika masih ada produk (termasuk produk terhapus) yang menunjuk kategori tersebut. Kategori dikunci saat pemeriksaan; jika tidak dipakai, soft delete dan nama diubah menjadi `nama__dihapus__id`.

### 8.3 Produk (app/api/products.py)

**List (`GET /products`)**
- Filter: `q` (cari nama, SKU, atau barcode secara case-insensitive), `category_id`, `only_active` (bawaan true).
- Urut nama. Paginasi `limit` (bawaan 50, maksimal 200) dan `offset`.

**Barcode (`GET /products/barcode/{barcode}`)**
- Mengembalikan produk aktif dengan barcode tersebut. 404 jika tidak ada.

**Create**
- Nama, SKU, dan barcode di-strip. SKU dan barcode dicek unik. Kategori dicek ada.
- Jika stok awal lebih dari nol, dicatat satu baris stock_movements dengan reason `initial`.

**Update (`PUT /products/{id}`)**
- Hanya mengubah field yang dikirim. Field yang bisa diubah: name, sku, barcode, price, is_active, category_id.
- Stok tidak bisa diubah di sini (field stock diabaikan). Perubahan stok hanya lewat transaksi, void, impor produk baru, atau penyesuaian stok.

**Delete**
- Soft delete. SKU dan barcode dikosongkan.

**Penyesuaian stok (`POST /products/{id}/stock-adjustments`)**
- Body: `change` (positif atau negatif, tidak boleh nol), `reason` (restock, correction, damaged, return), `note`.
- Baris produk dikunci (FOR UPDATE). Stok baru tidak boleh negatif.
- Mencatat stock_movements dengan user_id pengubah.

**Riwayat stok (`GET /products/{id}/stock-movements`)**
- Urut terbaru. Paginasi limit dan offset. Khusus owner dan admin.

### 8.4 Transaksi (app/api/transactions.py)

**Pembuatan transaksi (`POST /transactions`), urutan langkah**

1. `tx_id` diambil dari body (`id`) atau dibuat server.
2. Cek idempotensi: jika transaksi dengan ID itu sudah ada dan milik kasir yang sama, kembalikan transaksi lama tanpa memproses ulang. Jika milik kasir lain, tolak 409.
3. Daftar ID produk unik diurutkan untuk penguncian stok yang konsisten. Setiap baris request tetap disimpan sebagai item transaksi agar diskon per baris terjaga.
4. Baris produk dikunci dengan `SELECT ... FOR UPDATE`. Hanya produk aktif dan belum dihapus. Jika ada yang tidak ditemukan, tolak 400.
5. Cek stok menurut kuantitas gabungan tiap produk, lalu siapkan item beserta diskon nominal atau persentasenya.
6. Terapkan diskon item, lalu diskon transaksi pada sisa subtotal. Nominal diskon dan persentase saling eksklusif di setiap tingkat; persentase dibulatkan ke rupiah terdekat (half up).
7. Terapkan `TAX_RATE_PERCENT` dari konfigurasi server pada subtotal setelah diskon. Simpan tarif dan nilai pajak pada transaksi.
8. Cek pembayaran mencukupi total setelah pajak dan hitung kembalian.
9. Buat nomor invoice berurutan untuk tanggal WIB dan simpan transaksi, item, counter invoice, serta pergerakan stok dalam satu commit.
10. Jika terjadi IntegrityError (dua request dengan ID sama bersamaan), rollback lalu kembalikan transaksi yang sudah ada jika milik kasir yang sama.

Tidak ada commit sebelum semua validasi lolos, sehingga pengurangan stok di langkah 5 tidak pernah tersimpan jika langkah 6 atau 7 gagal.

**Validasi masukan (skema)**
- `items` minimal satu. `quantity` 1 sampai 10.000. Diskon nominal minimal 0; persentase 0 sampai 100 dengan maksimal dua desimal. Nominal dan persen tidak boleh dikirim bersamaan untuk item atau transaksi. `paid_amount` minimal 0.
- `payment_method` saat ini hanya `cash`. `note` maksimal 255 karakter.
- `TAX_RATE_PERCENT` adalah konfigurasi server, bawaan 0, maksimum 100 dengan dua desimal. Perubahan tarif hanya berlaku pada transaksi baru.

**Nomor invoice**
- Format `INV-{KODE_TENANT}-{KODE_OUTLET}-YYYYMMDD-NNNNNN`: counter WIB per outlet dinaikkan atomik dan ikut commit/rollback bersama transaksi; maksimum 999.999 transaksi per outlet per hari.

**Daftar dan detail**
- Cashier hanya melihat transaksi miliknya. Owner dan admin melihat semua.
- Cashier yang membuka transaksi kasir lain mendapat 404 (bukan 403) agar keberadaannya tidak bocor.
- Daftar bisa difilter `status`, urut terbaru, dengan limit dan offset.

**Void (`POST /transactions/{id}/void`)**
- Hanya owner dan admin. Baris transaksi dikunci. Jika sudah voided, tolak 400.
- Baris produk terkait dikunci, stok dikembalikan sesuai jumlah item, dan dicatat stock_movements (reason void, reference_id sama dengan ID transaksi, user_id owner/admin pemanggil).
- Status transaksi menjadi `voided`. Data transaksi tidak dihapus.

### 8.5 Impor produk (app/api/product_import.py)

**Endpoint**
- `GET /products/import/template`: mengunduh `template_produk.csv`.
- `POST /products/import?dry_run=true|false`: mengunggah file. Bawaan `dry_run=true` (hanya pratinjau).

**Batas dan format**
- Format `.csv` (pemisah koma atau titik koma), `.xlsx`, dan `.xls`. Semua sheet Excel yang berisi data diproses; maksimal 20 sheet, 2.000 baris gabungan, dan 5 MB.
- Encoding CSV UTF-8 (dengan atau tanpa BOM), cadangan cp1252.
- Maksimal 5 MB dan 2.000 baris data.
- Pembacaan file berjalan di threadpool agar server tidak tersendat.

**Kolom**

| Kolom | Wajib | Nama alternatif yang dikenali |
|---|---|---|
| name | ya | nama, nama produk |
| price | ya | harga, harga jual |
| sku | tidak | - |
| barcode | tidak | - |
| stock | tidak | stok |
| category | tidak | kategori |

Nama kolom tidak peka huruf besar-kecil. Kolom lain di file diabaikan. Baris kosong dilewati. Nomor baris di laporan mengikuti nomor baris di file (baris 2 adalah data pertama).

**Validasi per baris**
- Nama wajib, maksimal 150 karakter. SKU dan barcode maksimal 50 karakter. Kategori maksimal 100 karakter.
- Harga dan stok harus angka bulat tanpa titik, koma, atau huruf (awalan `Rp` pada harga diperbolehkan) dan tidak melebihi batas BIGINT.
- Untuk Excel, SKU/barcode yang berupa angka hanya diterima bila format angka berupa nol berulang (misalnya `0000000000000`) sehingga padding dapat dipulihkan. Simpan SKU/barcode sebagai Text untuk mencegah kehilangan nol atau presisi; angka numerik tanpa format aman ditandai error per baris.
- SKU atau barcode yang dobel di dalam file ditolak. Baris tanpa SKU dan barcode yang namanya dobel di dalam file juga ditolak.

**Pencocokan dengan produk yang sudah ada**
1. Dicocokkan lewat SKU, lalu barcode.
2. Jika baris tidak punya SKU maupun barcode, dicocokkan lewat nama (tidak peka huruf besar-kecil). Jika ada lebih dari satu produk dengan nama itu, baris ditolak dan diminta menambah SKU atau barcode.
3. Jika SKU dan barcode di baris menunjuk dua produk berbeda, baris ditolak.
4. Jika dua baris menunjuk produk yang sama, baris kedua ditolak.

**Perilaku**
- Produk baru: dibuat dengan stok dari file. Jika stok lebih dari nol, dicatat stock_movements reason `initial` dengan catatan "Impor file" dan user pengimpor.
- Produk lama (upsert): nama, harga, dan kategori diperbarui. SKU atau barcode diisi jika ada di file. Stok diabaikan dan dilaporkan sebagai peringatan (stok hanya boleh berubah lewat penyesuaian stok).
- Kategori yang belum ada dibuat otomatis.
- Semua atau tidak sama sekali: jika ada satu saja error, tidak ada data yang tersimpan (`saved` tetap false). Penyimpanan dilakukan dalam satu commit. Jika terjadi bentrok data saat commit, rollback dan respons 409.
- Respons memuat: `dry_run`, `saved`, `total_rows`, `to_create`, `to_update`, `categories_to_create`, `error_count`, `errors` (maksimal 200), dan `warnings` (maksimal 200).

### 8.6 Laporan penjualan (app/api/reports.py)

- `GET /reports/sales?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`: laporan JSON rentang tanggal inklusif WIB; khusus owner dan admin.
- `GET /reports/sales/export.csv` memakai parameter yang sama dan mengunduh CSV UTF-8 dengan BOM, berisi bagian summary, daily, product, dan cashier.
- Transaksi completed dihitung dalam subtotal, diskon, pajak, total penjualan, kuantitas produk, dan jumlah transaksi selesai. Void dikecualikan dari metrik penjualan, dengan jumlah void terpisah. Nilai produk adalah subtotal item dikurangi diskon langsung item; diskon transaksi dan pajak tidak dialokasikan ke produk.
- Tanggal memakai `transactions.created_at` dalam zona `Asia/Jakarta`. Produk dikelompokkan dari nama snapshot item; nama kasir berasal dari data user saat ini.
- Rentang terbalik ditolak dengan 400. Agregasi dilakukan di SQL dan tidak memerlukan perubahan skema.

## 9. Daftar endpoint lengkap

### Umum

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | / | publik | Pesan bahwa API berjalan |
| GET | /health | publik | Cek koneksi ke database |

### Autentikasi

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| POST | /auth/signup | publik, maksimal 5 kali/IP/jam | Membuat tenant, owner, dan outlet pertama secara atomik; password minimal 12 karakter |
| POST | /auth/register | owner | Membuat akun. Body: username, full_name, password, role, outlet_ids (untuk non-owner) |
| POST | /auth/login | publik | Form username dan password. Mengembalikan access_token |
| GET | /auth/me | user login | Data user yang sedang login |

### Tenant

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | /tenants/me | user login | Profil tenant akun aktif |
| PATCH | /tenants/me | owner | Mengubah nama usaha |

### Outlet

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | /outlets | user login | Outlet aktif yang dapat dipilih pengguna |
| POST | /outlets | owner | Membuat outlet dengan nama dan kode unik |
| PATCH | /outlets/{id} | owner | Mengubah nama/kode; kode terkunci setelah outlet memiliki transaksi |

### Pengguna

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | /users | owner, admin | Daftar; parameter `limit`, `offset`, `include_inactive` |
| PATCH | /users/{id} | owner, admin | Ubah username, full_name, role, atau outlet_ids |
| PATCH | /users/{id}/status | owner, admin | Aktifkan/nonaktifkan; body `is_active` |
| PUT | /users/{id}/password | owner, admin | Set password baru pengguna lain; admin tidak dapat mengubah password owner |
| PUT | /users/me/password | user login | Ganti password sendiri; body `current_password`, `new_password` |
| GET | /users/{id}/outlets | owner, admin | Lihat outlet penugasan pengguna |
| PUT | /users/{id}/outlets | owner, admin | Ganti penugasan; body `outlet_ids` |

### Kategori

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | /categories | user login | Daftar kategori |
| POST | /categories | owner, admin | Body: name. 201 |
| PUT | /categories/{id} | owner, admin | Body: name |
| DELETE | /categories/{id} | owner, admin | Soft delete. 204 |

### Produk

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | /products | user login | Parameter: q, category_id, only_active, limit, offset |
| GET | /products/barcode/{barcode} | user login | Produk aktif berdasarkan barcode |
| GET | /products/{id} | user login | Detail produk |
| POST | /products | owner, admin | Body: name, sku, barcode, price, stock, category_id. 201 |
| PUT | /products/{id} | owner, admin | Body (semua opsional): name, sku, barcode, price, is_active, category_id |
| DELETE | /products/{id} | owner, admin | Soft delete. 204 |

### Stok

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| POST | /products/{id}/stock-adjustments | owner, admin | Body: change, reason, note |
| GET | /products/{id}/stock-movements | owner, admin | Riwayat stok. Parameter: limit, offset |

### Impor produk

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | /products/import/template | owner, admin | Unduh template CSV |
| POST | /products/import | owner, admin | Multipart `file`. Parameter: dry_run (bawaan true) |

### Transaksi

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| POST | /transactions | user login | Buat transaksi tunai. Diskon amount atau percent pada item dan/atau transaksi. Pajak dari `TAX_RATE_PERCENT`. 201 |
| GET | /transactions | user login | Parameter: status, limit, offset. Cashier hanya miliknya |
| GET | /transactions/{id} | user login | Detail transaksi |
| POST | /transactions/{id}/void | owner, admin | Batalkan dan kembalikan stok |

### Laporan

| Method | Path | Akses | Keterangan |
|---|---|---|---|
| GET | /reports/sales | owner, admin | Parameter wajib `date_from`, `date_to` (YYYY-MM-DD); ringkasan harian, produk, dan kasir |
| GET | /reports/sales/export.csv | owner, admin | Parameter wajib sama; unduh laporan CSV |

### Contoh request dan respons

Login (form-urlencoded):

```
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=kasir1&password=kasir12345
```

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

Membuat transaksi:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "items": [
    {
      "product_id": "2b9c7c32-6b58-440d-846b-30dc528690eb",
      "quantity": 3,
      "discount_percent": 10
    }
  ],
  "discount_percent": 0,
  "payment_method": "cash",
  "paid_amount": 20000,
  "note": null
}
```

Respons (201):

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "invoice_number": "INV-DONPOS01-MAIN-20261028-000001",
  "cashier_id": "72c577cf-5aff-4379-8b43-0081d9aab743",
  "subtotal": 15000,
  "discount": 1500,
  "discount_percent": 0,
  "tax_percent": 0,
  "tax_amount": 0,
  "total": 13500,
  "payment_method": "cash",
  "paid_amount": 20000,
  "change_amount": 6500,
  "status": "completed",
  "note": null,
  "created_at": "2026-10-28T06:31:38.793023Z",
  "items": [
    {
      "product_id": "2b9c7c32-6b58-440d-846b-30dc528690eb",
      "product_name": "Teh Botol",
      "price": 5000,
      "quantity": 3,
      "subtotal": 15000,
      "discount": 1500,
      "discount_percent": 10
    }
  ]
}
```

Penyesuaian stok:

```json
{
  "change": 20,
  "reason": "restock",
  "note": "Barang datang dari supplier"
}
```

## 10. Aturan bisnis dan invarian data

- Harga, stok, kuantitas, dan uang selalu integer BIGINT. Rupiah tanpa desimal; batas maksimum 9.223.372.036.854.775.807.
- Stok tidak pernah negatif, baik oleh penjualan maupun penyesuaian manual.
- Stok hanya berubah lewat: transaksi (sale), void, produk baru dengan stok awal (create atau impor), dan penyesuaian stok. Semuanya tercatat di stock_movements.
- Harga dan nama pada item transaksi adalah salinan, tidak ikut berubah saat produk diedit.
- Diskon nominal atau persentase dapat dipakai per item atau per transaksi; nominal dan persen di level yang sama saling eksklusif. Diskon item dihitung lebih dahulu, diskon transaksi atas sisa subtotal, lalu pajak server dihitung setelah seluruh diskon.
- Tarif dan nilai pajak yang dipakai disimpan pada transaksi agar riwayat tidak berubah saat konfigurasi pajak diganti.
- Uang dibayar tidak boleh kurang dari total. Kembalian dihitung server.
- Transaksi bersifat idempotent berdasarkan ID transaksi dari klien.
- Transaksi yang sudah voided tidak bisa di-void lagi dan tidak bisa dihapus.
- Username unik dan disimpan huruf kecil. Password 8 sampai 72 karakter.
- SKU dan barcode unik (boleh kosong). Nama kategori unik.
- Penghapusan selalu soft delete.
- Kasir hanya melihat transaksinya sendiri.

## 11. Konkurensi dan integritas data

- **Penguncian baris:** pembuatan transaksi, void, dan penyesuaian stok memakai `SELECT ... FOR UPDATE` pada produk (dan transaksi saat void). Dua kasir yang menjual produk yang sama bersamaan akan diproses bergantian, jadi stok tidak bisa terpotong dua kali dari angka yang sama.
- **Urutan penguncian:** ID produk selalu diurutkan sebelum dikunci untuk mencegah deadlock.
- **Idempotensi:** ID transaksi dibuat klien. Kirim ulang karena sinyal putus tidak menggandakan transaksi maupun memotong stok dua kali. Dua request ber-ID sama yang bersamaan ditangani lewat penanganan IntegrityError.
- **Nomor invoice:** counter per outlet/tanggal WIB dinaikkan atomik dengan upsert PostgreSQL. Counter berada dalam transaksi database yang sama sehingga kegagalan transaksi tidak menghabiskan nomor.
- **Atomik:** transaksi, item, dan pergerakan stok disimpan dalam satu commit. Impor produk juga satu commit.
- **Auditabilitas:** stock_movements menyimpan perubahan dan stok sesudahnya sehingga selisih stok bisa dilacak.

## 12. Keamanan

- Password disimpan sebagai hash Argon2, tidak pernah polos.
- Token JWT berlaku 60 menit (atur lewat .env).
- Role dicek dari database pada setiap request, jadi penonaktifan akun berlaku langsung walau token belum kedaluwarsa.
- `/auth/bootstrap` sudah dihapus. Pendaftaran tenant baru memakai `/auth/signup` dan dibatasi lima permintaan per IP per jam.
- File `.env` masuk `.gitignore`. SECRET_KEY dan isi `.env` tidak boleh dibagikan.
- Screenshot dari halaman /docs memuat token login di bagian Curl. Jangan dibagikan.
- Akun uji (`owner`, `kasir1`) dan password contoh harus dihapus atau diganti sebelum dipakai untuk data sungguhan.
- Gunakan HTTPS di produksi.
- Validasi masukan dilakukan dua lapis: skema Pydantic (tipe, panjang, rentang) dan pemeriksaan bisnis di endpoint.
- Query memakai SQLAlchemy dengan parameter, jadi aman dari SQL injection.

## 13. Kode status dan format error

| Kode | Arti dalam API ini |
|---|---|
| 200, 201, 204 | Berhasil (204 untuk hapus) |
| 400 | Aturan bisnis dilanggar (stok kurang, uang kurang, SKU dobel, transaksi sudah dibatalkan, dan sebagainya) |
| 401 | Token tidak ada, tidak valid, atau kedaluwarsa. Atau username atau password salah saat login |
| 403 | Role tidak punya izin atau akun/tenant nonaktif |
| 429 | Batas pendaftaran tenant per alamat IP terlampaui |
| 404 | Data tidak ditemukan (juga dipakai untuk transaksi milik kasir lain) |
| 409 | Konflik, misalnya ID transaksi sudah dipakai kasir lain, bentrok saat impor, atau nomor invoice harian habis |
| 413 | File impor melebihi 5 MB |
| 422 | Format body tidak sesuai skema (otomatis dari FastAPI) |

Format error aplikasi:

```json
{ "detail": "Stok Teh Botol tidak cukup (sisa 47)" }
```

Error 422 dari FastAPI berbentuk daftar (`detail` berisi array berisi `loc`, `msg`, `type`).

## 14. Panduan integrasi mobile

- **Base URL:** pakai alamat IP komputer di jaringan WiFi, bukan localhost (contoh `http://192.168.1.10:8000`). Simpan di `EXPO_PUBLIC_API_URL`. Jika HP tidak bisa terhubung, cek Windows Firewall untuk port 8000 dan pastikan HP satu jaringan WiFi.
- **Login:** kirim `application/x-www-form-urlencoded`, bukan JSON. Simpan `access_token` di `expo-secure-store`.
- **Header:** semua endpoint terlindungi memakai `Authorization: Bearer <token>`. Endpoint bisnis terkait outlet juga memerlukan `X-Outlet-ID: <uuid>`; ambil daftar outlet yang tersedia melalui `GET /outlets` setelah login.
- **Token kedaluwarsa:** respons 401 berarti perlu login ulang (refresh token belum ada).
- **ID transaksi:** buat UUID di HP saat kasir menekan Bayar, simpan bersama transaksi, dan pakai ID yang sama untuk setiap percobaan kirim ulang.
- **Uang:** semua angka integer rupiah. Format tampilan (pemisah ribuan) dilakukan di sisi mobile.
- **Pencarian cepat:** `GET /products?q=...` untuk pencarian teks, `GET /products/barcode/{barcode}` untuk hasil scan.
- **Paginasi:** gunakan `limit` dan `offset`. Batas maksimal 200 per permintaan.
- **Tampilan berdasarkan role:** panggil `GET /auth/me` setelah login untuk mengetahui role dan menyembunyikan menu yang tidak boleh dipakai (server tetap menolak dengan 403).
- **Pesan error:** tampilkan isi `detail` ke pengguna untuk error 400, karena sudah berbahasa Indonesia.

## 15. Hasil pengujian

Skenario pada tabel berikut merupakan pengujian manual MVP awal lewat /docs. Fitur pajak/diskon dan counter invoice berurutan belum diuji ulang.

| Area | Skenario | Hasil |
|---|---|---|
| Dasar | /health | status ok, database terhubung |
| Auth | Bootstrap owner | 201, role owner |
| Auth | Bootstrap kedua kali | 403 |
| Auth | Endpoint terlindungi tanpa token | 401 |
| Auth | Register kasir oleh owner | 201 |
| Katalog | Buat kategori dan produk | 201 |
| Katalog | Cari lewat q dan barcode | 200 |
| Katalog | Kasir membuat produk | 403 |
| Transaksi | Transaksi normal | 201, total dan kembalian benar, stok turun |
| Transaksi | ID transaksi dikirim ulang | Transaksi lama dikembalikan, stok tetap |
| Transaksi | Quantity melebihi stok | 400 |
| Transaksi | Uang kurang | 400 |
| Void | Kasir void | 403 |
| Void | Owner void | 200, status voided, stok kembali |
| Void | Void kedua kali | 400 |
| Stok | Restock +20 | 200, stok bertambah |
| Stok | Perubahan -9999 | 400, tidak boleh negatif |
| Stok | Perubahan 0 | 400 |
| Stok | Kasir menyesuaikan stok | 403 |
| Stok | Riwayat stok | restock, sale, dan void tercatat |
| Impor | Pratinjau file valid | saved false, jumlah create dan update benar, peringatan stok |
| Impor | Simpan file valid | saved true, produk dan kategori baru muncul, stok awal tercatat |
| Impor | File dengan 4 baris error | saved false, tidak ada data masuk |
| Impor | Impor ulang file yang sama | to_create 0, to_update sesuai, tidak ada produk ganda |
| Impor | Kasir mengimpor | 403 |

Belum diuji ulang secara eksplisit: `PUT /products` dengan field `stock` (seharusnya diabaikan). Belum ada pengujian otomatis.

## 16. Kekurangan yang diketahui

| No | Kekurangan | Dampak |
|---|---|---|
| 4 | Belum ada refresh token | Pengguna login ulang tiap 60 menit |
| 6 | Belum ada rate limit login | Rentan ditebak berulang |
| 8 | Pembayaran baru tunai | QRIS dan e-wallet belum ada |
| 11 | Belum ada pengujian otomatis (pytest) | Perubahan kode berisiko regresi |
| 17 | Belum ada verifikasi email, MFA, billing, atau konsol operator platform | Isolasi data tenant tersedia, tetapi onboarding dan operasi SaaS komersial belum lengkap |

## 17. Rencana berikutnya

1. Setup aplikasi mobile: Expo, NativeWind, koneksi ke backend, layar login, daftar produk, keranjang, dan pembayaran tunai.
2. Cetak struk bluetooth dan scan barcode.
3. Pembayaran QRIS dan e-wallet lewat Midtrans (sandbox dulu, butuh alamat publik HTTPS untuk webhook).
4. Refresh token.
5. Mode offline di mobile dengan sinkronisasi (memanfaatkan ID transaksi dari klien).
6. Pengujian otomatis, backup database terjadwal, dan deployment.

## 18. Perintah yang sering dipakai

```
cd D:\dzakky\project\donpos\backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0
alembic revision --autogenerate -m "deskripsi perubahan"
alembic upgrade head
pip freeze > requirements.txt
git add .
git commit -m "pesan commit"
```
