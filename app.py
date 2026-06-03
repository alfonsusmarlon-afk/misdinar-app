from flask import Flask, render_template, request, session, redirect, url_for, send_file
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
import sqlite3
import os
import json 
import random
import string

app = Flask(__name__)
app.secret_key = 'your-secret-key-misdinar-2024'

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
    if 'no_hp' not in db_columns: conn.execute('ALTER TABLE users ADD COLUMN no_hp TEXT')
    if 'nama_panggilan' not in db_columns: conn.execute('ALTER TABLE users ADD COLUMN nama_panggilan TEXT')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS pengumuman (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, waktu_pelaksanaan TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    
    db_columns_peng = [col[1] for col in conn.execute('PRAGMA table_info(pengumuman)').fetchall()]
    if 'deskripsi' not in db_columns_peng: conn.execute('ALTER TABLE pengumuman ADD COLUMN deskripsi TEXT DEFAULT ""')

    conn.execute('''CREATE TABLE IF NOT EXISTS jadwal (id INTEGER PRIMARY KEY AUTOINCREMENT, jadwal_datetime TIMESTAMP NOT NULL, tanggal TEXT NOT NULL, bulan TEXT NOT NULL, hari TEXT NOT NULL, waktu TEXT NOT NULL, acara TEXT NOT NULL, status TEXT NOT NULL, pengguna TEXT NOT NULL, nama_pengguna TEXT NOT NULL, FOREIGN KEY(pengguna) REFERENCES users(username))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS dokumen (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, file_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS galeri (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, foto_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS kehadiran (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, kegiatan TEXT NOT NULL, status TEXT NOT NULL, keterangan TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS hukuman (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, pelanggaran TEXT NOT NULL, tindakan TEXT NOT NULL, status TEXT NOT NULL)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS form_fields (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, tipe TEXT NOT NULL, wajib INTEGER DEFAULT 1)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS pendaftaran (id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, data_respon TEXT NOT NULL, status TEXT DEFAULT 'Menunggu')''')
    
    if conn.execute('SELECT COUNT(*) FROM form_fields').fetchone()[0] == 0:
        conn.executemany('INSERT INTO form_fields (label, tipe, wajib) VALUES (?, ?, ?)', [
            ('Nama Lengkap', 'text', 1),
            ('Nomor WhatsApp', 'number', 1),
            ('Alasan Ingin Bergabung', 'textarea', 1)
        ])

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
    if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        for u in users:
            conn.execute('INSERT INTO users (username, password, nama, role, no_hp, nama_panggilan) VALUES (?, ?, ?, ?, ?, ?)', (u[0], u[1], u[2], u[3], u[4], u[2].split()[0]))
    
    conn.commit()
    conn.close()

init_db()

def get_quote_hari_ini():
    quotes = [
        "Melayani dengan hati, bukan karena ingin dipuji.",
        "Kasih itu sabar; kasih itu murah hati.",
        "Lakukan segala pekerjaanmu dalam kasih.",
        "Iman tanpa perbuatan adalah mati.",
        "Janganlah hendaknya kamu kuatir tentang apapun juga.",
        "Segala perkara dapat kutanggung di dalam Dia.",
        "Bersukacitalah senantiasa, tetaplah berdoa.",
        "Jadilah terang di tempat yang gelap."
    ]
    day_of_year = datetime.now().timetuple().tm_yday
    return quotes[day_of_year % len(quotes)]

def get_filtered_items(table_name, user_id=None):
    conn = get_db_connection()
    rows = conn.execute(f'SELECT * FROM {table_name} ORDER BY id DESC').fetchall()
    conn.close()
    filtered = []
    for r in rows:
        p = dict(r)
        target_list = p.get('target', 'semua').split(',')
        pembuat = p.get('pembuat', '')
        if 'semua' in target_list: filtered.append(p)
        elif user_id and (user_id in target_list or user_id == pembuat): filtered.append(p)
    return filtered

def get_jadwal_from_db():
    conn = get_db_connection()
    threshold_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    rows = conn.execute('SELECT * FROM jadwal WHERE jadwal_datetime >= ? ORDER BY jadwal_datetime ASC', (threshold_time,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

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
    quote_hari_ini = get_quote_hari_ini()
    
    if user_id:
        user_jadwal = [j for j in valid_jadwal if j['pengguna'] == user_id and j['status'] == 'Bertugas']
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=user_jadwal[:4], 
                               quote=quote_hari_ini, user_id=user_id, is_logged_in=True)
    else:
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=valid_jadwal[:8], 
                               quote=quote_hari_ini, is_logged_in=False)

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
    all_users = conn.execute("SELECT * FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall()
    conn.close()
    return render_template('anggota.html', users=all_users, current_role=session.get('role'))

@app.route('/ubah-role', methods=['POST'])
@login_required
def ubah_role():
    current_role = session.get('role')
    if current_role not in ['super admin', 'bph']: return redirect(url_for('index'))
    username = request.form.get('username')
    new_role = request.form.get('role')
    new_password = request.form.get('password') 
    valid_roles = ['user', 'bph', 'penjadwalan', 'pelatihan']
    if current_role == 'super admin': valid_roles.append('super admin')
    if username and new_role in valid_roles:
        conn = get_db_connection()
        target_user = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
        if target_user and target_user['role'] == 'super admin' and current_role != 'super admin':
            conn.close()
            return redirect(url_for('anggota'))
        if current_role == 'super admin' and new_password:
            conn.execute('UPDATE users SET role = ?, password = ? WHERE username = ?', (new_role, new_password, username))
        else:
            conn.execute('UPDATE users SET role = ? WHERE username = ?', (new_role, username))
        conn.commit()
        conn.close()
    return redirect(url_for('anggota'))

# FITUR BARU: HAPUS ANGGOTA PERMANEN
@app.route('/hapus-anggota', methods=['POST'])
@login_required
def hapus_anggota():
    current_role = session.get('role')
    if current_role not in ['super admin', 'bph']: return redirect(url_for('index'))
    
    username = request.form.get('username')
    if username:
        conn = get_db_connection()
        target_user = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
        
        # Super admin tidak boleh dihapus oleh siapapun
        if target_user and target_user['role'] != 'super admin':
            # Hapus akun dari tabel users
            conn.execute('DELETE FROM users WHERE username = ?', (username,))
            # Hapus rekam jejak pribadi (opsional namun baik untuk kebersihan database)
            conn.execute('DELETE FROM kehadiran WHERE username = ?', (username,))
            conn.execute('DELETE FROM hukuman WHERE username = ?', (username,))
            conn.commit()
        conn.close()
        
    return redirect(url_for('anggota'))

@app.route('/kehadiran', methods=['GET', 'POST'])
@login_required
def kehadiran():
    user_id = session.get('user_id')
    user_role = session.get('role')
    conn = get_db_connection()
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            username_target = request.form.get('username')
            tanggal = request.form.get('tanggal')
            kegiatan = request.form.get('kegiatan')
            status = request.form.get('status')
            keterangan = request.form.get('keterangan', '')
            target_user = conn.execute("SELECT nama FROM users WHERE username=?", (username_target,)).fetchone()
            nama_target = target_user['nama'] if target_user else username_target
            if action == 'tambah': conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan) VALUES (?, ?, ?, ?, ?, ?)', (username_target, nama_target, tanggal, kegiatan, status, keterangan))
            else: conn.execute('UPDATE kehadiran SET username=?, nama=?, tanggal=?, kegiatan=?, status=?, keterangan=? WHERE id=?', (username_target, nama_target, tanggal, kegiatan, status, keterangan, request.form.get('id')))
        elif action == 'hapus':
            conn.execute('DELETE FROM kehadiran WHERE id=?', (request.form.get('id'),))
        conn.commit()
        conn.close()
        return redirect(url_for('kehadiran'))
    if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        data_kehadiran = conn.execute('SELECT * FROM kehadiran ORDER BY id DESC').fetchall()
        users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall()
    else:
        data_kehadiran = conn.execute('SELECT * FROM kehadiran WHERE username=? ORDER BY id DESC', (user_id,)).fetchall()
        users_list = []
    conn.close()
    return render_template('kehadiran.html', kehadiran=data_kehadiran, users=users_list, role=user_role)

@app.route('/hukuman', methods=['GET', 'POST'])
@login_required
def hukuman():
    user_id = session.get('user_id')
    user_role = session.get('role')
    conn = get_db_connection()
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            username_target = request.form.get('username')
            tanggal = request.form.get('tanggal')
            pelanggaran = request.form.get('pelanggaran')
            tindakan = request.form.get('tindakan')
            status = request.form.get('status')
            target_user = conn.execute("SELECT nama FROM users WHERE username=?", (username_target,)).fetchone()
            nama_target = target_user['nama'] if target_user else username_target
            if action == 'tambah': conn.execute('INSERT INTO hukuman (username, nama, tanggal, pelanggaran, tindakan, status) VALUES (?, ?, ?, ?, ?, ?)', (username_target, nama_target, tanggal, pelanggaran, tindakan, status))
            else: conn.execute('UPDATE hukuman SET username=?, nama=?, tanggal=?, pelanggaran=?, tindakan=?, status=? WHERE id=?', (username_target, nama_target, tanggal, pelanggaran, tindakan, status, request.form.get('id')))
        elif action == 'hapus':
            conn.execute('DELETE FROM hukuman WHERE id=?', (request.form.get('id'),))
        conn.commit()
        conn.close()
        return redirect(url_for('hukuman'))
    if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        data_hukuman = conn.execute('SELECT * FROM hukuman ORDER BY id DESC').fetchall()
        users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall()
    else:
        data_hukuman = conn.execute('SELECT * FROM hukuman WHERE username=? ORDER BY id DESC', (user_id,)).fetchall()
        users_list = []
    conn.close()
    return render_template('hukuman.html', hukuman=data_hukuman, users=users_list, role=user_role)

@app.route('/penjadwalan', methods=['GET'])
@login_required
def penjadwalan():
    if session.get('role') not in ['super admin', 'penjadwalan']: return redirect(url_for('index'))
    return render_template('penjadwalan.html')

@app.route('/cetak-jadwal')
@login_required
def cetak_jadwal():
    if session.get('role') not in ['super admin', 'penjadwalan', 'bph']: return redirect(url_for('index'))
    return render_template('cetak_jadwal.html', weeks=[])

@app.route('/pengaturan', methods=['GET', 'POST'])
@login_required
def pengaturan():
    user_id = session.get('user_id')
    conn = get_db_connection()
    if request.method == 'POST':
        nama_lengkap = request.form.get('nama_lengkap')
        nama_panggilan = request.form.get('nama_panggilan')
        no_hp = request.form.get('no_hp')
        password_baru = request.form.get('password_baru')
        if password_baru and password_baru.strip() != '': conn.execute('UPDATE users SET nama=?, nama_panggilan=?, no_hp=?, password=? WHERE username=?', (nama_lengkap, nama_panggilan, no_hp, password_baru, user_id))
        else: conn.execute('UPDATE users SET nama=?, nama_panggilan=?, no_hp=? WHERE username=?', (nama_lengkap, nama_panggilan, no_hp, user_id))
        conn.commit()
        session['nama_user'] = nama_lengkap
        user_data = conn.execute('SELECT * FROM users WHERE username = ?', (user_id,)).fetchone()
        conn.close()
        return render_template('pengaturan.html', user=user_data, success="Profil berhasil diperbarui!")
    user_data = conn.execute('SELECT * FROM users WHERE username = ?', (user_id,)).fetchone()
    conn.close()
    return render_template('pengaturan.html', user=user_data)

@app.route('/pendaftaran', methods=['GET', 'POST'])
def pendaftaran():
    conn = get_db_connection()
    
    if request.method == 'POST':
        fields = conn.execute('SELECT * FROM form_fields ORDER BY id ASC').fetchall()
        respon_data = {}
        nama_pendaftar = "User Baru"
        no_hp_pendaftar = ""
        
        for f in fields:
            input_val = request.form.get(f'field_{f["id"]}', '')
            respon_data[f['label']] = input_val
            lbl_lower = f['label'].lower()
            if 'nama' in lbl_lower and nama_pendaftar == "User Baru":
                nama_pendaftar = input_val
            elif ('nomor' in lbl_lower or 'hp' in lbl_lower or 'wa' in lbl_lower) and no_hp_pendaftar == "":
                no_hp_pendaftar = input_val
                
        base_username = "".join(e for e in nama_pendaftar.split()[0].lower() if e.isalnum())
        if not base_username: base_username = "user"
        username = base_username
        counter = 1
        while conn.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            username = f"{base_username}{counter}"
            counter += 1
            
        chars = "abcdefghjkmnpqrstuvwxyz23456789"
        random_password = ''.join(random.choices(chars, k=6))
        nama_panggilan = nama_pendaftar.split()[0] if nama_pendaftar != "User Baru" else "User"
        
        conn.execute('INSERT INTO users (username, password, nama, role, no_hp, nama_panggilan) VALUES (?, ?, ?, ?, ?, ?)', 
                     (username, random_password, nama_pendaftar, 'user', no_hp_pendaftar, nama_panggilan))
                     
        respon_data['[Sistem] Username Dibuat'] = username
        json_string = json.dumps(respon_data)
        tanggal_sekarang = datetime.now().strftime('%Y-%m-%d %H:%M')
        conn.execute('INSERT INTO pendaftaran (tanggal, data_respon, status) VALUES (?, ?, ?)', (tanggal_sekarang, json_string, 'Menunggu'))
        
        conn.commit()
        conn.close()
        return render_template('pendaftaran.html', success=True, new_username=username, new_password=random_password)

    fields = conn.execute('SELECT * FROM form_fields ORDER BY id ASC').fetchall()
    conn.close()
    return render_template('pendaftaran.html', fields=fields)

@app.route('/kelola-pendaftaran', methods=['GET', 'POST'])
@login_required
def kelola_pendaftaran():
    if session.get('role') not in ['super admin', 'bph']: return redirect(url_for('index'))
    conn = get_db_connection()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'tambah_field':
            conn.execute('INSERT INTO form_fields (label, tipe, wajib) VALUES (?, ?, ?)', (request.form.get('label'), request.form.get('tipe'), int(request.form.get('wajib', 1))))
        elif action == 'hapus_field':
            conn.execute('DELETE FROM form_fields WHERE id=?', (request.form.get('id'),))
        elif action == 'update_status':
            conn.execute('UPDATE pendaftaran SET status=? WHERE id=?', (request.form.get('status'), request.form.get('id')))
        elif action == 'hapus_pendaftar':
            conn.execute('DELETE FROM pendaftaran WHERE id=?', (request.form.get('id'),))
        conn.commit()
        return redirect(url_for('kelola_pendaftaran'))

    fields = conn.execute('SELECT * FROM form_fields ORDER BY id ASC').fetchall()
    pendaftar_raw = conn.execute('SELECT * FROM pendaftaran ORDER BY id DESC').fetchall()
    pendaftar_list = []
    for p in pendaftar_raw:
        p_dict = dict(p)
        try: p_dict['data_parsed'] = json.loads(p['data_respon'])
        except: p_dict['data_parsed'] = {}
        pendaftar_list.append(p_dict)
    conn.close()
    return render_template('kelola_pendaftaran.html', fields=fields, pendaftar=pendaftar_list)

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
            deskripsi = request.form.get('deskripsi', '')
            waktu_pelaksanaan = request.form.get('waktu_pelaksanaan')
            target_list = request.form.getlist('target')
            target_str = 'semua' if 'semua' in target_list else ','.join(target_list)
            months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            now = datetime.now()
            tanggal_dibuat = f"{now.day} {months[now.month - 1]} {now.year}"
            conn = get_db_connection()
            if action == 'tambah': conn.execute('INSERT INTO pengumuman (judul, deskripsi, waktu_pelaksanaan, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?, ?)', (judul, deskripsi, waktu_pelaksanaan, tanggal_dibuat, target_str, user_id))
            else: conn.execute('UPDATE pengumuman SET judul=?, deskripsi=?, waktu_pelaksanaan=?, target=? WHERE id=?', (judul, deskripsi, waktu_pelaksanaan, target_str, request.form.get('id')))
            conn.commit()
            conn.close()
        elif action == 'hapus':
            conn = get_db_connection()
            conn.execute('DELETE FROM pengumuman WHERE id=?', (request.form.get('id'),))
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
                    old_doc = conn.execute('SELECT file_path FROM dokumen WHERE id=?', (p_id,)).fetchone()
                    if old_doc and old_doc['file_path']:
                        for p in old_doc['file_path'].split(','):
                            old_file_loc = os.path.join('static', p)
                            if os.path.exists(old_file_loc): os.remove(old_file_loc)
                    file_paths_str = ','.join(file_paths)
                    conn.execute('UPDATE dokumen SET judul=?, file_path=?, target=? WHERE id=?', (judul, file_paths_str, target_str, p_id))
                else:
                    conn.execute('UPDATE dokumen SET judul=?, target=? WHERE id=?', (judul, target_str, p_id))
            conn.commit()
            conn.close()
        elif action == 'hapus':
            p_id = request.form.get('id')
            conn = get_db_connection()
            old_doc = conn.execute('SELECT file_path FROM dokumen WHERE id=?', (p_id,)).fetchone()
            if old_doc and old_doc['file_path']:
                for p in old_doc['file_path'].split(','):
                    old_file_loc = os.path.join('static', p)
                    if os.path.exists(old_file_loc): os.remove(old_file_loc)
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
                    old_gal = conn.execute('SELECT foto_path FROM galeri WHERE id=?', (p_id,)).fetchone()
                    if old_gal and old_gal['foto_path']:
                        for p in old_gal['foto_path'].split(','):
                            old_file_loc = os.path.join('static', p)
                            if os.path.exists(old_file_loc): os.remove(old_file_loc)
                    foto_paths_str = ','.join(foto_paths)
                    conn.execute('UPDATE galeri SET judul=?, foto_path=?, target=? WHERE id=?', (judul, foto_paths_str, target_str, p_id))
                else:
                    conn.execute('UPDATE galeri SET judul=?, target=? WHERE id=?', (judul, target_str, p_id))
            conn.commit()
            conn.close()
        elif action == 'hapus':
            p_id = request.form.get('id')
            conn = get_db_connection()
            old_gal = conn.execute('SELECT foto_path FROM galeri WHERE id=?', (p_id,)).fetchone()
            if old_gal and old_gal['foto_path']:
                for p in old_gal['foto_path'].split(','):
                    old_file_loc = os.path.join('static', p)
                    if os.path.exists(old_file_loc): os.remove(old_file_loc)
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
        if r not in pengurus_by_role: pengurus_by_role[r] = []
        pengurus_by_role[r].append(dict(p))
    return render_template('kontak.html', pengurus_by_role=pengurus_by_role)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)