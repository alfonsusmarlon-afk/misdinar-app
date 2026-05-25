from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-misdinar-2024'

# Data dummy untuk pengguna
users_data = {
    'anton': {'password': '123456', 'nama': 'Anton Wijaya', 'role': 'user'},
    'budi': {'password': 'password', 'nama': 'Budi Santoso', 'role': 'user'},
    'citra': {'password': 'citra123', 'nama': 'Citra Dewi', 'role': 'user'},
    'admin': {'password': 'admin123', 'nama': 'Admin Misdinar', 'role': 'admin'}
}

# Data dummy untuk pengumuman
pengumuman_data = [
    {
        'judul': 'Latihan Paduan Suara Misdinar',
        'tanggal': '25 Mei 2024'
    },
    {
        'judul': 'Perubahan Jadwal Misa Sabtu',
        'tanggal': '22 Mei 2024'
    },
    {
        'judul': 'Retret Misdinar 2024',
        'tanggal': '20 Mei 2024'
    }
]

# Data jadwal dengan informasi pengguna
jadwal_semua_data = [
    {
        'tanggal': '24',
        'bulan': 'MEI',
        'hari': 'Jumat',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '24',
        'bulan': 'MEI',
        'hari': 'Jumat',
        'waktu': '18.00',
        'acara': 'Misa Sore',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    },
    {
        'tanggal': '25',
        'bulan': 'MEI',
        'hari': 'Sabtu',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'anton',
        'nama_pengguna': 'Anton Wijaya'
    },
    {
        'tanggal': '25',
        'bulan': 'MEI',
        'hari': 'Sabtu',
        'waktu': '18.00',
        'acara': 'Misa Vigili',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '26',
        'bulan': 'MEI',
        'hari': 'Minggu',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    },
    {
        'tanggal': '26',
        'bulan': 'MEI',
        'hari': 'Minggu',
        'waktu': '08.00',
        'acara': 'Misa Minggu',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'anton',
        'nama_pengguna': 'Anton Wijaya'
    },
    {
        'tanggal': '26',
        'bulan': 'MEI',
        'hari': 'Minggu',
        'waktu': '10.00',
        'acara': 'Misa Minggu II',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '26',
        'bulan': 'MEI',
        'hari': 'Minggu',
        'waktu': '18.00',
        'acara': 'Misa Sore',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'anton',
        'nama_pengguna': 'Anton Wijaya'
    },
    {
        'tanggal': '27',
        'bulan': 'MEI',
        'hari': 'Senin',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    },
    {
        'tanggal': '27',
        'bulan': 'MEI',
        'hari': 'Senin',
        'waktu': '18.00',
        'acara': 'Misa Sore',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '28',
        'bulan': 'MEI',
        'hari': 'Selasa',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'anton',
        'nama_pengguna': 'Anton Wijaya'
    },
    {
        'tanggal': '28',
        'bulan': 'MEI',
        'hari': 'Selasa',
        'waktu': '18.00',
        'acara': 'Misa Sore',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    },
    {
        'tanggal': '29',
        'bulan': 'MEI',
        'hari': 'Rabu',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '29',
        'bulan': 'MEI',
        'hari': 'Rabu',
        'waktu': '18.00',
        'acara': 'Misa Harian',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'anton',
        'nama_pengguna': 'Anton Wijaya'
    },
    {
        'tanggal': '30',
        'bulan': 'MEI',
        'hari': 'Kamis',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    },
    {
        'tanggal': '30',
        'bulan': 'MEI',
        'hari': 'Kamis',
        'waktu': '18.00',
        'acara': 'Misa Sore',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '31',
        'bulan': 'MEI',
        'hari': 'Jumat',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'anton',
        'nama_pengguna': 'Anton Wijaya'
    },
    {
        'tanggal': '31',
        'bulan': 'MEI',
        'hari': 'Jumat',
        'waktu': '18.00',
        'acara': 'Misa Sore',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    },
    {
        'tanggal': '01',
        'bulan': 'JUNI',
        'hari': 'Sabtu',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '01',
        'bulan': 'JUNI',
        'hari': 'Sabtu',
        'waktu': '18.00',
        'acara': 'Misa Vigili',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    },
    {
        'tanggal': '02',
        'bulan': 'JUNI',
        'hari': 'Minggu',
        'waktu': '06.00',
        'acara': 'Misa Pagi',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'anton',
        'nama_pengguna': 'Anton Wijaya'
    },
    {
        'tanggal': '02',
        'bulan': 'JUNI',
        'hari': 'Minggu',
        'waktu': '08.00',
        'acara': 'Misa Minggu',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'budi',
        'nama_pengguna': 'Budi Santoso'
    },
    {
        'tanggal': '02',
        'bulan': 'JUNI',
        'hari': 'Minggu',
        'waktu': '18.00',
        'acara': 'Misa Sore',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas',
        'pengguna': 'citra',
        'nama_pengguna': 'Citra Dewi'
    }
]

# Data dummy untuk jadwal default (untuk kompatibilitas)
jadwal_data = [
    {
        'tanggal': '25',
        'bulan': 'MEI',
        'hari': 'Sabtu',
        'waktu': '18.00',
        'acara': 'Misa Vigili',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas'
    },
    {
        'tanggal': '26',
        'bulan': 'MEI',
        'hari': 'Minggu',
        'waktu': '08.00',
        'acara': 'Misa Minggu',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Bertugas'
    },
    {
        'tanggal': '29',
        'bulan': 'MEI',
        'hari': 'Rabu',
        'waktu': '18.00',
        'acara': 'Misa Harian',
        'lokasi': 'Gereja St. Yosef',
        'status': 'Tidak Bertugas'
    }
]

# Decorator untuk check login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Data liturgi
liturgi_data = {
    'minggu': 'Minggu Biasa VII',
    'tahun': 'Tahun B',
    'tanggal': '26 Mei 2024'
}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in users_data and users_data[username]['password'] == password:
            session['user_id'] = username
            session['nama_user'] = users_data[username]['nama']
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Username atau password salah')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' in session:
        # User sudah login
        return render_template('index.html', 
                             pengumuman=pengumuman_data,
                             jadwal=jadwal_data,
                             liturgi=liturgi_data,
                             user_id=session['user_id'],
                             is_logged_in=True)
    else:
        # Tampilan publik
        return render_template('index.html', 
                             pengumuman=pengumuman_data,
                             jadwal=jadwal_data,
                             liturgi=liturgi_data,
                             is_logged_in=False)

@app.route('/jadwal')
def jadwal():
    if 'user_id' in session:
        # User sudah login - tampilkan hanya jadwal user tersebut
        user_jadwal = [item for item in jadwal_semua_data if item['pengguna'] == session['user_id']]
        return render_template('jadwal.html', 
                             jadwal=user_jadwal, 
                             user_id=session['user_id'],
                             is_logged_in=True,
                             view_mode='private')
    else:
        # Tampilan publik - tampilkan semua jadwal semua orang
        return render_template('jadwal.html', 
                             jadwal=jadwal_semua_data, 
                             is_logged_in=False,
                             view_mode='public')

# Data liturgi
liturgi_data = {
    'minggu': 'Minggu Biasa VII',
    'tahun': 'Tahun B',
    'tanggal': '26 Mei 2024'
}

@app.route('/anggota')
@login_required
def anggota():
    return render_template('anggota.html')

@app.route('/pendaftaran')
@login_required
def pendaftaran():
    return render_template('pendaftaran.html')

@app.route('/pengumuman')
@login_required
def pengumuman():
    return render_template('pengumuman.html', pengumuman=pengumuman_data)

@app.route('/galeri')
@login_required
def galeri():
    return render_template('galeri.html')

@app.route('/dokumen')
@login_required
def dokumen():
    return render_template('dokumen.html')

@app.route('/kontak')
@login_required
def kontak():
    return render_template('kontak.html')

@app.route('/pengaturan')
@login_required
def pengaturan():
    return render_template('pengaturan.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
