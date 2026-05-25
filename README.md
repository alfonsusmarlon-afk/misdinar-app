# MISDINAR - Sistem Informasi Pelayanan Misdinar

Web aplikasi untuk mengelola informasi dan jadwal pelayanan misdinar di gereja.

## Fitur

- **Dashboard/Beranda**: Tampilan ringkasan jadwal, pengumuman, dan kalender liturgi
- **Jadwal**: Melihat dan mengelola jadwal pelayanan
- **Anggota**: Direktori anggota misdinar
- **Pendaftaran**: Mendaftar untuk kegiatan dan pelayanan
- **Pengumuman**: Informasi terbaru dari tim
- **Galeri**: Foto-foto kegiatan
- **Dokumen**: Repositori dokumen penting
- **Kontak**: Informasi kontak
- **Pengaturan**: Konfigurasi akun

## Instalasi

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Jalankan aplikasi:
```bash
python app.py
```

3. Buka browser dan akses:
```
http://localhost:5000
```

## Struktur Folder

```
misdinar_app/
├── app.py                  # File utama aplikasi Flask
├── requirements.txt        # Dependencies Python
├── static/
│   ├── css/
│   │   └── style.css      # Styling utama
│   ├── js/
│   │   └── script.js      # JavaScript untuk interaktivitas
│   └── images/            # Folder untuk gambar
└── templates/
    ├── base.html          # Template dasar
    ├── index.html         # Halaman beranda
    ├── jadwal.html        # Halaman jadwal
    └── ...                # Template lainnya
```

## Customisasi

### Mengubah Warna
Edit variabel CSS di `static/css/style.css`:
```css
:root {
    --primary-green: #2d5f3f;
    --light-green: #d4e5dc;
    --accent-green: #3d7f5a;
}
```

### Menambah Data
Edit data dummy di `app.py`:
- `pengumuman_data`: Daftar pengumuman
- `jadwal_data`: Daftar jadwal
- `liturgi_data`: Informasi liturgi

### Menambah Halaman Baru
1. Buat route baru di `app.py`
2. Buat template HTML di folder `templates/`
3. Tambahkan link di sidebar di `base.html`

## Technology Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, JavaScript
- **Icons**: Font Awesome 6
- **Design**: Responsive, Mobile-friendly

## Pengembangan Selanjutnya

Fitur yang bisa ditambahkan:
- [ ] Autentikasi & Login
- [ ] Database integration (SQLite/PostgreSQL)
- [ ] CRUD untuk jadwal dan anggota
- [ ] Upload foto untuk galeri
- [ ] Notifikasi real-time
- [ ] Export jadwal ke PDF/iCal
- [ ] API untuk mobile app
- [ ] Multi-gereja support

## Lisensi

Open source - bebas digunakan dan dimodifikasi sesuai kebutuhan.
