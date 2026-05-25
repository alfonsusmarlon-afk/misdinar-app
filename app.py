from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-misdinar-2024'

# Data dummy untuk pengguna beserta role masing-masing
users_data = {
    'anton': {'password': '123456', 'nama': 'Anton Wijaya', 'role': 'user'},
    'budi': {'password': 'password', 'nama': 'Budi Santoso', 'role': 'user'},
    'citra': {'password': 'citra123', 'nama': 'Citra Dewi', 'role': 'user'},
    'admin': {'password': 'admin123', 'nama': 'Admin Misdinar', 'role': 'admin'},
    'pengurus': {'password': 'pengurus123', 'nama': 'Pengurus Misdinar', 'role': 'pengurus'}
}

# Data dummy untuk pengumuman dengan penambahan 'target'
pengumuman_data = [
    {
        'judul': 'Latihan Paduan Suara Misdinar',
        'tanggal': '25 Mei 2024',
        'target': 'all'
    },
    {
        'judul': 'Perubahan Jadwal Misa Sabtu',
        'tanggal': '22 Mei 2024',
        'target': 'all'
    },
    {
        'judul': 'Retret Misdinar 2024',
        'tanggal': '20 Mei 2024',
        'target': 'all'
    },
    {
        'judul': 'Rapat Pengurus Khusus (Internal)',
        'tanggal': '19 Mei 2024',
        'target': ['admin', 'pengurus']
    }
]

# Fungsi pembantu untuk membuat jadwal dinamis hari ini dan besok secara real-time
def get_dynamic_jadwal():
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    day3 = now + timedelta(days=2)
    
    months_id = {
        1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI',
        7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'
    }
    
    days_id = {
        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
    }
    
    return [
        {
            'tanggal': now.strftime('%d'),
            'bulan': months_id[now.month],
            'hari': days_id[now.strftime('%A')],
            'waktu': '06.00',
            'acara': 'Misa Pagi',
            'status': 'Bertugas',
            'pengguna': 'budi',
            'nama_pengguna': 'Budi Santoso'
        },
        {
            'tanggal': now.strftime('%d'),
            'bulan': months_id[now.month],
            'hari': days_id[now.strftime('%A')],
            'waktu': '18.00',
            'acara': 'Misa Sore',
            'status': 'Bertugas',
            'pengguna': 'citra',
            'nama_pengguna': 'Citra Dewi'
        },
        {
            'tanggal': tomorrow.strftime('%d'),
            'bulan': months_id[tomorrow.month],
            'hari': days_id[tomorrow.strftime('%A')],
            'waktu': '06.00',
            'acara': 'Misa Pagi',
            'status': 'Bertugas',
            'pengguna': 'anton',
            'nama_pengguna': 'Anton Wijaya'
        },
        {
            'tanggal': tomorrow.strftime('%d'),
            'bulan': months_id[tomorrow.month],
            'hari': days_id[tomorrow.strftime('%A')],
            'waktu': '18.00',
            'acara': 'Misa Sore',
            'status': 'Bertugas',
            'pengguna': 'budi',
            'nama_pengguna': 'Budi Santoso'
        },
        {
            'tanggal': day3.strftime('%d'),
            'bulan': months_id[day3.month],
            'hari': days_id[day3.strftime('%A')],
            'waktu': '08.00',
            'acara': 'Misa Minggu',
            'status': 'Bertugas',
            'pengguna': 'anton',
            'nama_pengguna': 'Anton Wijaya'
        }
    ]

# Fungsi pembantu untuk memfilter pengumuman
def get_filtered_pengumuman(user_id=None):
    filtered = []
    user_role = session.get('role') if user_id else None
    for p in pengumuman_data:
        target = p.get('target', 'all')
        if target == 'all':
            filtered.append(p)
        elif user_role and isinstance(target, list) and user_role in target:
            filtered.append(p)
    return filtered

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
            session['role'] = users_data[username]['role']
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
    user_id = session.get('user_id')
    filtered_pengumuman = get_filtered_pengumuman(user_id)
    
    all_jadwal = get_dynamic_jadwal()
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    
    today_date = now.strftime('%d')
    tomorrow_date = tomorrow.strftime('%d')
    
    # Poin 1: Menampilkan maksimal 4 jadwal dari hari ini dan besoknya
    jadwal_terdekat = [item for item in all_jadwal if item['tanggal'] in [today_date, tomorrow_date]]
    jadwal_terdekat = jadwal_terdekat[:4]
    
    if user_id:
        return render_template('index.html', 
                             pengumuman=filtered_pengumuman,
                             jadwal=jadwal_terdekat,
                             liturgi=liturgi_data,
                             user_id=user_id,
                             is_logged_in=True)
    else:
        return render_template('index.html', 
                             pengumuman=filtered_pengumuman,
                             jadwal=jadwal_terdekat,
                             liturgi=liturgi_data,
                             is_logged_in=False)

@app.route('/jadwal')
def jadwal():
    all_jadwal = get_dynamic_jadwal()
    if 'user_id' in session:
        user_jadwal = [item for item in all_jadwal if item['pengguna'] == session['user_id']]
        return render_template('jadwal.html', 
                             jadwal=user_jadwal, 
                             user_id=session['user_id'],
                             is_logged_in=True,
                             view_mode='private')
    else:
        return render_template('jadwal.html', 
                             jadwal=all_jadwal, 
                             is_logged_in=False,
                             view_mode='public')

@app.route('/anggota')
@login_required
def anggota():
    # Proteksi tambahan agar user biasa tidak bisa menembak URL langsung
    if session.get('role') not in ['admin', 'pengurus']:
        return redirect(url_for('index'))
    return render_template('anggota.html')

@app.route('/pengaturan')
@login_required
def pengaturan():
    return render_template('pengaturan.html')

@app.route('/pendaftaran')
def pendaftaran():
    return render_template('pendaftaran.html')

@app.route('/pengumuman')
def pengumuman():
    user_id = session.get('user_id')
    filtered_pengumuman = get_filtered_pengumuman(user_id)
    return render_template('pengumuman.html', pengumuman=filtered_pengumuman)

@app.route('/galeri')
def galeri():
    return render_template('galeri.html')

@app.route('/dokumen')
def dokumen():
    return render_template('dokumen.html')

@app.route('/kontak')
def kontak():
    return render_template('kontak.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)