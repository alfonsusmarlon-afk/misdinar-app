from flask import Flask, render_template, request, session, redirect, url_for, send_file
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
import sqlite3
import os
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'your-secret-key-misdinar-2024'

# Konfigurasi Database dan Folder Upload File
DB_NAME = 'misdinar.db'
UPLOAD_DOKUMEN = 'static/uploads/dokumen'
UPLOAD_GALERI = 'static/uploads/galeri'

os.makedirs(UPLOAD_DOKUMEN, exist_ok=True)
os.makedirs(UPLOAD_GALERI, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    conn.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT NOT NULL, nama TEXT NOT NULL, role TEXT NOT NULL)''')
    
    db_columns = [col[1] for col in conn.execute('PRAGMA table_info(users)').fetchall()]
    if 'no_hp' not in db_columns:
        conn.execute('ALTER TABLE users ADD COLUMN no_hp TEXT')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS pengumuman (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, waktu_pelaksanaan TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS jadwal (id INTEGER PRIMARY KEY AUTOINCREMENT, jadwal_datetime TIMESTAMP NOT NULL, tanggal TEXT NOT NULL, bulan TEXT NOT NULL, hari TEXT NOT NULL, waktu TEXT NOT NULL, acara TEXT NOT NULL, status TEXT NOT NULL, pengguna TEXT NOT NULL, nama_pengguna TEXT NOT NULL, FOREIGN KEY(pengguna) REFERENCES users(username))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS dokumen (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, file_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS galeri (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, foto_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    
    users = [
        ('superadmin', 'super123', 'Super Admin', 'super admin', '081234567890'),
        ('abi', 'abi123', 'Abi', 'bph', '081111111111'),
        ('florensia', 'flor123', 'Florensia', 'bph', '082222222222'),
        ('angela_d', 'angela123', 'Angela D', 'bph', '083333333333'),
        ('rena', 'rena123', 'Rena', 'pelatihan', '084444444444'),
        ('gabriel', 'gabriel123', 'Gabriel', 'pelatihan', '085555555555'),
        ('dicky', 'dicky123', 'Dicky', 'pelatihan', '086666666666'),
        ('marlon@gmail.com', 'marlon123', 'Marlon', 'penjadwalan', '087777777777'),
        ('lydia', 'lydia123', 'Lydia', 'penjadwalan', '088888888888'),
        ('emily', 'emily123', 'Emily', 'penjadwalan', '089999999999'),
        ('galant', 'galant123', 'Galant', 'user', '081010101010'),
        ('dyota', 'dyota123', 'Dyota', 'user', '081212121212'),
        ('anton', '123456', 'Anton Wijaya', 'user', '081313131313'),
        ('budi', 'password', 'Budi Santoso', 'user', '081414141414'),
        ('citra', 'citra123', 'Citra Dewi', 'user', '081515151515')
    ]
    conn.executemany('INSERT OR REPLACE INTO users (username, password, nama, role, no_hp) VALUES (?, ?, ?, ?, ?)', users)
    
    pengumuman_count = conn.execute('SELECT COUNT(*) FROM pengumuman').fetchone()[0]
    if pengumuman_count == 0:
        pengumumans = [
            ('Latihan Paduan Suara Misdinar', '2024-05-25T16:00', '24 Mei 2024', 'semua', 'superadmin'),
            ('Perubahan Jadwal Misa Sabtu', '2024-05-22T18:00', '21 Mei 2024', 'semua', 'superadmin'),
            ('Rapat Evaluasi Penjadwalan', '2024-05-19T19:00', '19 Mei 2024', 'marlon@gmail.com,lydia,emily', 'superadmin')
        ]
        conn.executemany('INSERT INTO pengumuman (judul, waktu_pelaksanaan, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?)', pengumumans)
    
    # Jadwal seeder dihapus agar testing jadwal murni dari upload Excel. (Tabel aman jika kosong)
    conn.commit()
    conn.close()

init_db()

def get_filtered_items(table_name, user_id=None):
    conn = get_db_connection()
    rows = conn.execute(f'SELECT * FROM {table_name} ORDER BY id DESC').fetchall()
    conn.close()
    
    filtered = []
    for r in rows:
        p = dict(r)
        target_list = p.get('target', 'semua').split(',')
        pembuat = p.get('pembuat', '')
        
        if 'semua' in target_list:
            filtered.append(p)
        elif user_id and (user_id in target_list or user_id == pembuat):
            filtered.append(p)
    return filtered

def get_jadwal_from_db():
    conn = get_db_connection()
    # Menampilkan semua jadwal dari sekarang ke masa depan
    threshold_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    rows = conn.execute('SELECT * FROM jadwal WHERE jadwal_datetime >= ? ORDER BY jadwal_datetime ASC', (threshold_time,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

liturgi_data = {'minggu': 'Minggu Biasa VII', 'tahun': 'Tahun B', 'tanggal': '26 Mei 2024'}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['username']
            session['nama_user'] = user['nama']
            session['role'] = user['role']
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Username atau password salah')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/')
def index():
    user_id = session.get('user_id')
    filtered_pengumuman = get_filtered_items('pengumuman', user_id)
    valid_jadwal = get_jadwal_from_db()
    
    if user_id:
        user_jadwal = [j for j in valid_jadwal if j['pengguna'] == user_id and j['status'] == 'Bertugas']
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=user_jadwal[:4], liturgi=liturgi_data, user_id=user_id, is_logged_in=True)
    else:
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=valid_jadwal[:8], liturgi=liturgi_data, is_logged_in=False)

@app.route('/jadwal')
def jadwal():
    valid_jadwal = get_jadwal_from_db()
    if 'user_id' in session:
        user_jadwal = [j for j in valid_jadwal if j['pengguna'] == session['user_id']]
        return render_template('jadwal.html', jadwal=user_jadwal, user_id=session['user_id'], is_logged_in=True, view_mode='private')
    else:
        return render_template('jadwal.html', jadwal=valid_jadwal, is_logged_in=False, view_mode='public')

@app.route('/anggota')
@login_required
def anggota():
    if session.get('role') not in ['super admin', 'bph', 'penjadwalan', 'pelatihan']: return redirect(url_for('index'))
    conn = get_db_connection()
    all_users = conn.execute("SELECT username, nama, role FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall()
    conn.close()
    return render_template('anggota.html', users=all_users, current_role=session.get('role'))

@app.route('/ubah-role', methods=['POST'])
@login_required
def ubah_role():
    current_role = session.get('role')
    if current_role not in ['super admin', 'bph']: 
        return redirect(url_for('index'))
        
    username = request.form.get('username')
    new_role = request.form.get('role')
    
    valid_roles = ['user', 'bph', 'penjadwalan', 'pelatihan']
    if current_role == 'super admin':
        valid_roles.append('super admin')
        
    if username and new_role in valid_roles:
        conn = get_db_connection()
        target_user = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
        if target_user and target_user['role'] == 'super admin' and current_role != 'super admin':
            conn.close()
            return redirect(url_for('anggota'))
            
        conn.execute('UPDATE users SET role = ? WHERE username = ?', (new_role, username))
        conn.commit()
        conn.close()
        
    return redirect(url_for('anggota'))

@app.route('/bph')
@login_required
def bph():
    if session.get('role') not in ['super admin', 'bph']: return redirect(url_for('index'))
    return render_template('bph.html')

# ================= FITUR PENJADWALAN OTOMATIS EXCEL =================
@app.route('/penjadwalan', methods=['GET', 'POST'])
@login_required
def penjadwalan():
    if session.get('role') not in ['super admin', 'penjadwalan']: return redirect(url_for('index'))
    
    # Ambil list username dan nama anggota untuk panduan
    conn = get_db_connection()
    users_db = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall()
    conn.close()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # PROSES 1: GENERATE TEMPLATE EXCEL
        if action == 'generate':
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            
            # Jika rentang tidak valid
            if not start_date_str or not end_date_str:
                return redirect(url_for('penjadwalan'))
                
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            
            data = []
            days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
            
            current_date = start_date
            while current_date <= end_date:
                hari_idx = current_date.weekday()
                hari = days_id[hari_idx]
                tgl_str = current_date.strftime('%Y-%m-%d')
                
                # Aturan standard Misa yang bisa diedit di Excel nanti
                if hari_idx == 5: # Sabtu
                    data.append({'Tanggal': tgl_str, 'Hari': hari, 'Waktu': '17.00', 'Acara': 'Misa Vigili', 'Username Petugas': ''})
                elif hari_idx == 6: # Minggu
                    data.append({'Tanggal': tgl_str, 'Hari': hari, 'Waktu': '06.00', 'Acara': 'Misa Pagi', 'Username Petugas': ''})
                    data.append({'Tanggal': tgl_str, 'Hari': hari, 'Waktu': '08.00', 'Acara': 'Misa Pagi II', 'Username Petugas': ''})
                    data.append({'Tanggal': tgl_str, 'Hari': hari, 'Waktu': '17.00', 'Acara': 'Misa Sore', 'Username Petugas': ''})
                else: # Misa Harian
                    data.append({'Tanggal': tgl_str, 'Hari': hari, 'Waktu': '05.30', 'Acara': 'Misa Pagi', 'Username Petugas': ''})
                    data.append({'Tanggal': tgl_str, 'Hari': hari, 'Waktu': '18.00', 'Acara': 'Misa Sore', 'Username Petugas': ''})
                
                current_date += timedelta(days=1)
                
            df = pd.DataFrame(data)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Template_Jadwal')
            output.seek(0)
            
            return send_file(output, download_name=f'Template_Jadwal_{start_date_str}_to_{end_date_str}.xlsx', as_attachment=True)
            
        # PROSES 2: UPLOAD & INSERT EXCEL KE DATABASE
        elif action == 'upload':
            file = request.files.get('file_excel')
            if file and file.filename.endswith('.xlsx'):
                try:
                    df = pd.read_excel(file)
                    conn = get_db_connection()
                    months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
                    
                    for index, row in df.iterrows():
                        petugas_raw = str(row.get('Username Petugas', ''))
                        
                        # Abaikan jika sel kosong (nan)
                        if pd.isna(row.get('Username Petugas')) or petugas_raw.strip() == '' or petugas_raw.lower() == 'nan':
                            continue
                            
                        # Standarisasi data per baris
                        tgl_raw = str(row['Tanggal']).split(' ')[0] 
                        waktu = str(row['Waktu']).replace(':', '.') 
                        acara = str(row['Acara'])
                        hari = str(row['Hari'])
                        
                        dt = datetime.strptime(tgl_raw, '%Y-%m-%d')
                        jadwal_dt = datetime.strptime(f"{tgl_raw} {waktu.replace('.', ':')}:00", '%Y-%m-%d %H:%M:%S')
                        tanggal_num = dt.strftime('%d')
                        bulan_str = months_id[dt.month]
                        
                        # Memecah jika ada multi-petugas (Misal diisi: anton, dyota)
                        list_petugas = [p.strip() for p in petugas_raw.split(',')]
                        for p in list_petugas:
                            if not p: continue
                            
                            user_db = conn.execute("SELECT nama FROM users WHERE username=?", (p,)).fetchone()
                            nama_pengguna = user_db['nama'] if user_db else p
                            
                            conn.execute('''
                                INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (jadwal_dt.strftime('%Y-%m-%d %H:%M:%S'), tanggal_num, bulan_str, hari, waktu, acara, 'Bertugas', p, nama_pengguna))
                            
                    conn.commit()
                    conn.close()
                    # Arahkan ke halaman utama jadwal untuk melihat hasilnya
                    return redirect(url_for('jadwal'))
                except Exception as e:
                    print("Error parsing Excel:", e)
                    return redirect(url_for('penjadwalan'))
                    
    return render_template('penjadwalan.html', users=users_db)

@app.route('/pelatihan')
@login_required
def pelatihan():
    if session.get('role') not in ['super admin', 'pelatihan']: return redirect(url_for('index'))
    return render_template('pelatihan.html')

@app.route('/pengaturan')
@login_required
def pengaturan(): return render_template('pengaturan.html')

@app.route('/pendaftaran')
def pendaftaran(): return render_template('pendaftaran.html')

def get_grouped_users():
    conn = get_db_connection()
    all_users = conn.execute("SELECT username, nama, role FROM users WHERE role != 'super admin'").fetchall()
    conn.close()
    users_by_role = {}
    for u in all_users:
        r = u['role']
        if r not in users_by_role: users_by_role[r] = []
        users_by_role[r].append(dict(u))
    return users_by_role

@app.route('/pengumuman', methods=['GET', 'POST'])
def pengumuman():
    user_id = session.get('user_id')
    user_role = session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            judul = request.form.get('judul')
            waktu_pelaksanaan = request.form.get('waktu_pelaksanaan')
            target_list = request.form.getlist('target')
            target_str = 'semua' if 'semua' in target_list else ','.join(target_list)
            
            months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            now = datetime.now()
            tanggal_dibuat = f"{now.day} {months[now.month - 1]} {now.year}"
            
            conn = get_db_connection()
            if action == 'tambah':
                conn.execute('INSERT INTO pengumuman (judul, waktu_pelaksanaan, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?)', (judul, waktu_pelaksanaan, tanggal_dibuat, target_str, user_id))
            else:
                p_id = request.form.get('id')
                conn.execute('UPDATE pengumuman SET judul=?, waktu_pelaksanaan=?, target=? WHERE id=?', (judul, waktu_pelaksanaan, target_str, p_id))
            conn.commit()
            conn.close()
        elif action == 'hapus':
            p_id = request.form.get('id')
            conn = get_db_connection()
            conn.execute('DELETE FROM pengumuman WHERE id=?', (p_id,))
            conn.commit()
            conn.close()
        return redirect(url_for('pengumuman'))
    return render_template('pengumuman.html', pengumuman=get_filtered_items('pengumuman', user_id), role=user_role, users_by_role=get_grouped_users())

@app.route('/dokumen', methods=['GET', 'POST'])
def dokumen():
    user_id = session.get('user_id')
    user_role = session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            judul = request.form.get('judul')
            target_list = request.form.getlist('target')
            target_str = 'semua' if 'semua' in target_list else ','.join(target_list)
            
            months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            now = datetime.now()
            tanggal_dibuat = f"{now.day} {months[now.month - 1]} {now.year}"
            
            files = request.files.getlist('file')
            file_paths = []
            for idx, file in enumerate(files):
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    filename = f"{int(now.timestamp())}_{idx}_{filename}"
                    file.save(os.path.join(UPLOAD_DOKUMEN, filename))
                    file_paths.append(f"uploads/dokumen/{filename}")
            
            conn = get_db_connection()
            if action == 'tambah':
                file_paths_str = ','.join(file_paths)
                conn.execute('INSERT INTO dokumen (judul, file_path, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?)', (judul, file_paths_str, tanggal_dibuat, target_str, user_id))
            else:
                p_id = request.form.get('id')
                if file_paths:
                    file_paths_str = ','.join(file_paths)
                    conn.execute('UPDATE dokumen SET judul=?, file_path=?, target=? WHERE id=?', (judul, file_paths_str, target_str, p_id))
                else:
                    conn.execute('UPDATE dokumen SET judul=?, target=? WHERE id=?', (judul, target_str, p_id))
            conn.commit()
            conn.close()
        elif action == 'hapus':
            p_id = request.form.get('id')
            conn = get_db_connection()
            conn.execute('DELETE FROM dokumen WHERE id=?', (p_id,))
            conn.commit()
            conn.close()
        return redirect(url_for('dokumen'))
    return render_template('dokumen.html', dokumen=get_filtered_items('dokumen', user_id), role=user_role, users_by_role=get_grouped_users())

@app.route('/galeri', methods=['GET', 'POST'])
def galeri():
    user_id = session.get('user_id')
    user_role = session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            judul = request.form.get('judul')
            target_list = request.form.getlist('target')
            target_str = 'semua' if 'semua' in target_list else ','.join(target_list)
            
            months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            now = datetime.now()
            tanggal_dibuat = f"{now.day} {months[now.month - 1]} {now.year}"
            
            fotos = request.files.getlist('foto')
            foto_paths = []
            for idx, foto in enumerate(fotos):
                if foto and foto.filename != '':
                    filename = secure_filename(foto.filename)
                    filename = f"{int(now.timestamp())}_{idx}_{filename}"
                    foto.save(os.path.join(UPLOAD_GALERI, filename))
                    foto_paths.append(f"uploads/galeri/{filename}")
                    
            conn = get_db_connection()
            if action == 'tambah':
                foto_paths_str = ','.join(foto_paths)
                conn.execute('INSERT INTO galeri (judul, foto_path, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?)', (judul, foto_paths_str, tanggal_dibuat, target_str, user_id))
            else:
                p_id = request.form.get('id')
                if foto_paths:
                    foto_paths_str = ','.join(foto_paths)
                    conn.execute('UPDATE galeri SET judul=?, foto_path=?, target=? WHERE id=?', (judul, foto_paths_str, target_str, p_id))
                else:
                    conn.execute('UPDATE galeri SET judul=?, target=? WHERE id=?', (judul, target_str, p_id))
            conn.commit()
            conn.close()
        elif action == 'hapus':
            p_id = request.form.get('id')
            conn = get_db_connection()
            conn.execute('DELETE FROM galeri WHERE id=?', (p_id,))
            conn.commit()
            conn.close()
        return redirect(url_for('galeri'))
    return render_template('galeri.html', galeri=get_filtered_items('galeri', user_id), role=user_role, users_by_role=get_grouped_users())

@app.route('/kontak')
def kontak():
    conn = get_db_connection()
    pengurus_db = conn.execute("SELECT nama, role, no_hp FROM users WHERE role IN ('bph', 'penjadwalan', 'pelatihan') ORDER BY role ASC, nama ASC").fetchall()
    conn.close()
    
    pengurus_by_role = {}
    for p in pengurus_db:
        r = p['role']
        if r not in pengurus_by_role:
            pengurus_by_role[r] = []
        pengurus_by_role[r].append(dict(p))
        
    return render_template('kontak.html', pengurus_by_role=pengurus_by_role)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)