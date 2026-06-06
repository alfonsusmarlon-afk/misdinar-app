import os
import json
import random
import string
import sqlite3
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Flask, render_template, request, session, redirect, url_for, send_file, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ==========================================
# 1. KONFIGURASI APLIKASI & FOLDER SERVER
# ==========================================
app = Flask(__name__)
app.secret_key = 'misdinar-secure-key-2026-production' 
app.permanent_session_lifetime = timedelta(days=7) 

DB_NAME = 'misdinar.db'
UPLOAD_DOKUMEN = 'static/uploads/dokumen'
UPLOAD_GALERI = 'static/uploads/galeri'
UPLOAD_PROFIL = 'static/uploads/profil'

for folder in [UPLOAD_DOKUMEN, UPLOAD_GALERI, UPLOAD_PROFIL]:
    os.makedirs(folder, exist_ok=True)

# ==========================================
# 2. SISTEM DATABASE & AUTO-MIGRATION
# ==========================================
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT NOT NULL, nama TEXT NOT NULL, role TEXT NOT NULL)''')
    
    new_user_columns = {
        'no_hp': 'TEXT', 'nama_panggilan': 'TEXT', 'email': 'TEXT',
        'tanggal_lahir': 'TEXT', 'no_hp_ortu': 'TEXT', 'nama_ortu': 'TEXT',
        'alamat': 'TEXT', 'foto_profil': 'TEXT'
    }
    existing_columns = [col[1] for col in conn.execute('PRAGMA table_info(users)').fetchall()]
    for col_name, col_type in new_user_columns.items():
        if col_name not in existing_columns:
            conn.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')

    conn.execute('''CREATE TABLE IF NOT EXISTS pengumuman (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, deskripsi TEXT DEFAULT "", waktu_pelaksanaan TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS jadwal (id INTEGER PRIMARY KEY AUTOINCREMENT, jadwal_datetime TIMESTAMP NOT NULL, tanggal TEXT NOT NULL, bulan TEXT NOT NULL, hari TEXT NOT NULL, waktu TEXT NOT NULL, acara TEXT NOT NULL, status TEXT NOT NULL, pengguna TEXT NOT NULL, nama_pengguna TEXT NOT NULL, FOREIGN KEY(pengguna) REFERENCES users(username))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS dokumen (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, file_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS galeri (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, foto_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS kehadiran (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, kegiatan TEXT NOT NULL, status TEXT NOT NULL, keterangan TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS hukuman (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, pelanggaran TEXT NOT NULL, tindakan TEXT NOT NULL, status TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS form_fields (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, tipe TEXT NOT NULL, wajib INTEGER DEFAULT 1)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS pendaftaran (id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, data_respon TEXT NOT NULL, status TEXT DEFAULT 'Menunggu')''')
    
    if conn.execute('SELECT COUNT(*) FROM form_fields').fetchone()[0] == 0:
        conn.executemany('INSERT INTO form_fields (label, tipe, wajib) VALUES (?, ?, ?)', [
            ('Nama Lengkap', 'text', 1), ('Nomor WhatsApp', 'number', 1), ('Alasan Bergabung', 'textarea', 1)
        ])

    if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        hashed_pw = generate_password_hash('super123')
        conn.execute('INSERT INTO users (username, password, nama, role, no_hp, nama_panggilan) VALUES (?, ?, ?, ?, ?, ?)', 
                     ('superadmin', hashed_pw, 'Super Admin', 'super admin', '081234567890', 'Admin'))
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 3. HELPER & MIDDLEWARE
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_filtered_items(table_name, user_id=None):
    conn = get_db_connection()
    rows = conn.execute(f'SELECT * FROM {table_name} ORDER BY id DESC').fetchall()
    conn.close()
    filtered = []
    for r in rows:
        p = dict(r)
        target_list = p.get('target', 'semua').split(',')
        pembuat = p.get('pembuat', '')
        if 'semua' in target_list or (user_id and (user_id in target_list or user_id == pembuat)): 
            filtered.append(p)
    return filtered

def get_jadwal_from_db():
    conn = get_db_connection()
    threshold_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND nama_pengguna != '' ORDER BY jadwal_datetime ASC", (threshold_time,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

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

# ==========================================
# 4. ROUTING UTAMA (AUTENTIKASI & BERANDA)
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user:
            is_valid = False
            if check_password_hash(user['password'], password): is_valid = True
            elif user['password'] == password: 
                is_valid = True
                conn.execute('UPDATE users SET password = ? WHERE username = ?', (generate_password_hash(password), username))
                conn.commit()
                
            if is_valid:
                session.permanent = True
                session['user_id'] = user['username']
                session['nama_user'] = user['nama']
                session['role'] = user['role']
                session['foto_profil'] = user['foto_profil']
                conn.close()
                return redirect(url_for('index'))
                
        conn.close()
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
    quotes = ["Melayani dengan hati, bukan karena ingin dipuji.", "Kasih itu sabar; kasih itu murah hati.", "Lakukan segala pekerjaanmu dalam kasih."]
    quote = quotes[datetime.now().timetuple().tm_yday % len(quotes)]
    
    if user_id:
        user_jadwal = [j for j in valid_jadwal if j['pengguna'] == user_id and j['status'] == 'Bertugas']
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=user_jadwal[:4], quote=quote, user_id=user_id, is_logged_in=True)
    return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=valid_jadwal[:8], quote=quote, is_logged_in=False)

@app.route('/jadwal')
def jadwal():
    valid_jadwal = get_jadwal_from_db()
    if 'user_id' in session:
        user_jadwal = [j for j in valid_jadwal if j['pengguna'] == session['user_id']]
        return render_template('jadwal.html', jadwal=user_jadwal, user_id=session['user_id'], is_logged_in=True, view_mode='private')
    return render_template('jadwal.html', jadwal=valid_jadwal, is_logged_in=False, view_mode='public')

# ==========================================
# 5. MANAJEMEN AKUN & PROFIL 
# ==========================================
@app.route('/pengaturan', methods=['GET', 'POST'])
@login_required
def pengaturan():
    user_id = session.get('user_id')
    conn = get_db_connection()
    
    if request.method == 'POST':
        nama_lengkap, nama_panggilan, email, tanggal_lahir = request.form.get('nama_lengkap'), request.form.get('nama_panggilan'), request.form.get('email'), request.form.get('tanggal_lahir')
        no_hp, nama_ortu, no_hp_ortu, alamat = request.form.get('no_hp'), request.form.get('nama_ortu'), request.form.get('no_hp_ortu'), request.form.get('alamat')
        password_baru = request.form.get('password_baru')
        
        foto_profil_path = None
        foto_file = request.files.get('foto_profil')
        if foto_file and foto_file.filename != '':
            old_data = conn.execute('SELECT foto_profil FROM users WHERE username=?', (user_id,)).fetchone()
            if old_data and old_data['foto_profil']:
                old_path = os.path.join('static', old_data['foto_profil'])
                if os.path.exists(old_path): os.remove(old_path)
            
            filename = secure_filename(f"{user_id}_{int(datetime.now().timestamp())}_{foto_file.filename}")
            foto_file.save(os.path.join(UPLOAD_PROFIL, filename))
            foto_profil_path = f"uploads/profil/{filename}"
            session['foto_profil'] = foto_profil_path

        query = 'UPDATE users SET nama=?, nama_panggilan=?, email=?, tanggal_lahir=?, no_hp=?, nama_ortu=?, no_hp_ortu=?, alamat=?'
        params = [nama_lengkap, nama_panggilan, email, tanggal_lahir, no_hp, nama_ortu, no_hp_ortu, alamat]
        if foto_profil_path: query += ', foto_profil=?'; params.append(foto_profil_path)
        if password_baru and password_baru.strip() != '': query += ', password=?'; params.append(generate_password_hash(password_baru))
        query += ' WHERE username=?'
        params.append(user_id)
        
        conn.execute(query, params)
        conn.commit()
        session['nama_user'] = nama_lengkap
        
    user_data = conn.execute('SELECT * FROM users WHERE username = ?', (user_id,)).fetchone()
    conn.close()
    return render_template('pengaturan.html', user=user_data)

@app.route('/anggota')
@login_required
def anggota():
    if session.get('role') not in ['super admin', 'bph', 'penjadwalan', 'pelatihan']: return redirect(url_for('index'))
    conn = get_db_connection()
    all_users = conn.execute("SELECT * FROM users WHERE role != 'super admin' ORDER BY role ASC, nama ASC").fetchall()
    conn.close()
    return render_template('anggota.html', users=all_users, current_role=session.get('role'))

@app.route('/ubah-role', methods=['POST'])
@login_required
def ubah_role():
    if session.get('role') not in ['super admin', 'bph']: return redirect(url_for('index'))
    conn = get_db_connection()
    username, new_role, new_password = request.form.get('username'), request.form.get('role'), request.form.get('password')
    if username and new_role:
        if session.get('role') == 'super admin' and new_password: conn.execute('UPDATE users SET role = ?, password = ? WHERE username = ?', (new_role, generate_password_hash(new_password), username))
        else: conn.execute('UPDATE users SET role = ? WHERE username = ?', (new_role, username))
        conn.commit()
    conn.close()
    return redirect(url_for('anggota'))

@app.route('/hapus-anggota', methods=['POST'])
@login_required
def hapus_anggota():
    if session.get('role') not in ['super admin', 'bph']: return redirect(url_for('index'))
    username = request.form.get('username')
    if username:
        conn = get_db_connection()
        target_user = conn.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
        if target_user and target_user['role'] != 'super admin':
            conn.execute('DELETE FROM users WHERE username = ?', (username,))
            conn.execute('DELETE FROM kehadiran WHERE username = ?', (username,))
            conn.execute('DELETE FROM hukuman WHERE username = ?', (username,))
            conn.commit()
        conn.close()
    return redirect(url_for('anggota'))

# ==========================================
# 6. PENDAFTARAN & KELOLA PENDAFTARAN
# ==========================================
@app.route('/pendaftaran', methods=['GET', 'POST'])
def pendaftaran():
    conn = get_db_connection()
    if request.method == 'POST':
        fields = conn.execute('SELECT * FROM form_fields ORDER BY id ASC').fetchall()
        respon_data, nama_pendaftar, no_hp_pendaftar = {}, "User Baru", ""
        
        for f in fields:
            input_val = request.form.get(f'field_{f["id"]}', '')
            respon_data[f['label']] = input_val
            lbl_lower = f['label'].lower()
            if 'nama' in lbl_lower and nama_pendaftar == "User Baru": nama_pendaftar = input_val
            elif ('nomor' in lbl_lower or 'hp' in lbl_lower or 'wa' in lbl_lower) and no_hp_pendaftar == "": no_hp_pendaftar = input_val
                
        base_username = "".join(e for e in nama_pendaftar.split()[0].lower() if e.isalnum())
        if not base_username: base_username = "user"
        username, counter = base_username, 1
        while conn.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            username = f"{base_username}{counter}"; counter += 1
            
        random_password = ''.join(random.choices("abcdefghjkmnpqrstuvwxyz23456789", k=6))
        conn.execute('INSERT INTO users (username, password, nama, role, no_hp, nama_panggilan) VALUES (?, ?, ?, ?, ?, ?)', 
                     (username, generate_password_hash(random_password), nama_pendaftar, 'user', no_hp_pendaftar, nama_pendaftar.split()[0] if nama_pendaftar != "User Baru" else "User"))
                     
        respon_data['[Sistem] Username Dibuat'] = username
        conn.execute('INSERT INTO pendaftaran (tanggal, data_respon, status) VALUES (?, ?, ?)', (datetime.now().strftime('%Y-%m-%d %H:%M'), json.dumps(respon_data), 'Menunggu'))
        conn.commit(); conn.close()
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
        if action == 'tambah_field': conn.execute('INSERT INTO form_fields (label, tipe, wajib) VALUES (?, ?, ?)', (request.form.get('label'), request.form.get('tipe'), int(request.form.get('wajib', 1))))
        elif action == 'hapus_field': conn.execute('DELETE FROM form_fields WHERE id=?', (request.form.get('id'),))
        elif action == 'update_status': conn.execute('UPDATE pendaftaran SET status=? WHERE id=?', (request.form.get('status'), request.form.get('id')))
        elif action == 'hapus_pendaftar': conn.execute('DELETE FROM pendaftaran WHERE id=?', (request.form.get('id'),))
        conn.commit()
        return redirect(url_for('kelola_pendaftaran'))

    fields = conn.execute('SELECT * FROM form_fields ORDER BY id ASC').fetchall()
    pendaftar_list = []
    for p in conn.execute('SELECT * FROM pendaftaran ORDER BY id DESC').fetchall():
        p_dict = dict(p)
        try: p_dict['data_parsed'] = json.loads(p['data_respon'])
        except: p_dict['data_parsed'] = {}
        pendaftar_list.append(p_dict)
    conn.close()
    return render_template('kelola_pendaftaran.html', fields=fields, pendaftar=pendaftar_list)

# ==========================================
# 7. FITUR OPERASIONAL (ADMINISTRASI)
# ==========================================
@app.route('/kehadiran', methods=['GET', 'POST'])
@login_required
def kehadiran():
    user_id, user_role = session.get('user_id'), session.get('role')
    conn = get_db_connection()
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            target = conn.execute("SELECT nama FROM users WHERE username=?", (request.form.get('username'),)).fetchone()
            nama = target['nama'] if target else request.form.get('username')
            if action == 'tambah': conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan) VALUES (?, ?, ?, ?, ?, ?)', (request.form.get('username'), nama, request.form.get('tanggal'), request.form.get('kegiatan'), request.form.get('status'), request.form.get('keterangan', '')))
            else: conn.execute('UPDATE kehadiran SET username=?, nama=?, tanggal=?, kegiatan=?, status=?, keterangan=? WHERE id=?', (request.form.get('username'), nama, request.form.get('tanggal'), request.form.get('kegiatan'), request.form.get('status'), request.form.get('keterangan', ''), request.form.get('id')))
        elif action == 'hapus': conn.execute('DELETE FROM kehadiran WHERE id=?', (request.form.get('id'),))
        conn.commit(); return redirect(url_for('kehadiran'))

    users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else []
    data_kehadiran = conn.execute('SELECT * FROM kehadiran ORDER BY id DESC').fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else conn.execute('SELECT * FROM kehadiran WHERE username=? ORDER BY id DESC', (user_id,)).fetchall()
    conn.close()
    return render_template('kehadiran.html', kehadiran=data_kehadiran, users=users_list, role=user_role)

@app.route('/hukuman', methods=['GET', 'POST'])
@login_required
def hukuman():
    user_id, user_role = session.get('user_id'), session.get('role')
    conn = get_db_connection()
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            target = conn.execute("SELECT nama FROM users WHERE username=?", (request.form.get('username'),)).fetchone()
            nama = target['nama'] if target else request.form.get('username')
            if action == 'tambah': conn.execute('INSERT INTO hukuman (username, nama, tanggal, pelanggaran, tindakan, status) VALUES (?, ?, ?, ?, ?, ?)', (request.form.get('username'), nama, request.form.get('tanggal'), request.form.get('pelanggaran'), request.form.get('tindakan'), request.form.get('status')))
            else: conn.execute('UPDATE hukuman SET username=?, nama=?, tanggal=?, pelanggaran=?, tindakan=?, status=? WHERE id=?', (request.form.get('username'), nama, request.form.get('tanggal'), request.form.get('pelanggaran'), request.form.get('tindakan'), request.form.get('status'), request.form.get('id')))
        elif action == 'hapus': conn.execute('DELETE FROM hukuman WHERE id=?', (request.form.get('id'),))
        conn.commit(); return redirect(url_for('hukuman'))

    users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else []
    data_hukuman = conn.execute('SELECT * FROM hukuman ORDER BY id DESC').fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else conn.execute('SELECT * FROM hukuman WHERE username=? ORDER BY id DESC', (user_id,)).fetchall()
    conn.close()
    return render_template('hukuman.html', hukuman=data_hukuman, users=users_list, role=user_role)

@app.route('/pengumuman', methods=['GET', 'POST'])
def pengumuman():
    user_id, user_role = session.get('user_id'), session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        conn = get_db_connection()
        if action in ['tambah', 'edit']:
            target_str = 'semua' if 'semua' in request.form.getlist('target') else ','.join(request.form.getlist('target'))
            if action == 'tambah': conn.execute('INSERT INTO pengumuman (judul, deskripsi, waktu_pelaksanaan, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?, ?)', (request.form.get('judul'), request.form.get('deskripsi', ''), request.form.get('waktu_pelaksanaan'), datetime.now().strftime("%d %b %Y"), target_str, user_id))
            else: conn.execute('UPDATE pengumuman SET judul=?, deskripsi=?, waktu_pelaksanaan=?, target=? WHERE id=?', (request.form.get('judul'), request.form.get('deskripsi', ''), request.form.get('waktu_pelaksanaan'), target_str, request.form.get('id')))
        elif action == 'hapus': conn.execute('DELETE FROM pengumuman WHERE id=?', (request.form.get('id'),))
        conn.commit(); conn.close()
        return redirect(url_for('pengumuman'))
    return render_template('pengumuman.html', pengumuman=get_filtered_items('pengumuman', user_id), role=user_role, users_by_role=get_grouped_users())

@app.route('/dokumen', methods=['GET', 'POST'])
def dokumen():
    user_id, user_role = session.get('user_id'), session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        conn = get_db_connection()
        if action in ['tambah', 'edit']:
            target_str = 'semua' if 'semua' in request.form.getlist('target') else ','.join(request.form.getlist('target'))
            file_paths = []
            for idx, file in enumerate(request.files.getlist('file')):
                if file and file.filename != '':
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{idx}_{file.filename}")
                    file.save(os.path.join(UPLOAD_DOKUMEN, filename))
                    file_paths.append(f"uploads/dokumen/{filename}")
            if action == 'tambah': conn.execute('INSERT INTO dokumen (judul, file_path, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?)', (request.form.get('judul'), ','.join(file_paths), datetime.now().strftime("%d %b %Y"), target_str, user_id))
            else:
                p_id = request.form.get('id')
                if file_paths:
                    old_doc = conn.execute('SELECT file_path FROM dokumen WHERE id=?', (p_id,)).fetchone()
                    if old_doc and old_doc['file_path']:
                        for p in old_doc['file_path'].split(','):
                            if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
                    conn.execute('UPDATE dokumen SET judul=?, file_path=?, target=? WHERE id=?', (request.form.get('judul'), ','.join(file_paths), target_str, p_id))
                else: conn.execute('UPDATE dokumen SET judul=?, target=? WHERE id=?', (request.form.get('judul'), target_str, p_id))
        elif action == 'hapus':
            p_id = request.form.get('id')
            old_doc = conn.execute('SELECT file_path FROM dokumen WHERE id=?', (p_id,)).fetchone()
            if old_doc and old_doc['file_path']:
                for p in old_doc['file_path'].split(','):
                    if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
            conn.execute('DELETE FROM dokumen WHERE id=?', (p_id,))
        conn.commit(); conn.close()
        return redirect(url_for('dokumen'))
    return render_template('dokumen.html', dokumen=get_filtered_items('dokumen', user_id), role=user_role, users_by_role=get_grouped_users())

@app.route('/galeri', methods=['GET', 'POST'])
def galeri():
    user_id, user_role = session.get('user_id'), session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        conn = get_db_connection()
        if action in ['tambah', 'edit']:
            target_str = 'semua' if 'semua' in request.form.getlist('target') else ','.join(request.form.getlist('target'))
            foto_paths = []
            for idx, foto in enumerate(request.files.getlist('foto')):
                if foto and foto.filename != '':
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{idx}_{foto.filename}")
                    foto.save(os.path.join(UPLOAD_GALERI, filename))
                    foto_paths.append(f"uploads/galeri/{filename}")
            if action == 'tambah': conn.execute('INSERT INTO galeri (judul, foto_path, tanggal_dibuat, target, pembuat) VALUES (?, ?, ?, ?, ?)', (request.form.get('judul'), ','.join(foto_paths), datetime.now().strftime("%d %b %Y"), target_str, user_id))
            else:
                p_id = request.form.get('id')
                if foto_paths:
                    old_gal = conn.execute('SELECT foto_path FROM galeri WHERE id=?', (p_id,)).fetchone()
                    if old_gal and old_gal['foto_path']:
                        for p in old_gal['foto_path'].split(','):
                            if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
                    conn.execute('UPDATE galeri SET judul=?, foto_path=?, target=? WHERE id=?', (request.form.get('judul'), ','.join(foto_paths), target_str, p_id))
                else: conn.execute('UPDATE galeri SET judul=?, target=? WHERE id=?', (request.form.get('judul'), target_str, p_id))
        elif action == 'hapus':
            p_id = request.form.get('id')
            old_gal = conn.execute('SELECT foto_path FROM galeri WHERE id=?', (p_id,)).fetchone()
            if old_gal and old_gal['foto_path']:
                for p in old_gal['foto_path'].split(','):
                    if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
            conn.execute('DELETE FROM galeri WHERE id=?', (p_id,))
        conn.commit(); conn.close()
        return redirect(url_for('galeri'))
    return render_template('galeri.html', galeri=get_filtered_items('galeri', user_id), role=user_role, users_by_role=get_grouped_users())

@app.route('/kontak')
def kontak():
    conn = get_db_connection()
    pengurus_db = conn.execute("SELECT nama, role, no_hp FROM users WHERE role IN ('bph', 'penjadwalan', 'pelatihan') ORDER BY role ASC, nama ASC").fetchall()
    conn.close()
    pengurus_by_role = {}
    for p in pengurus_db: pengurus_by_role.setdefault(p['role'], []).append(dict(p))
    return render_template('kontak.html', pengurus_by_role=pengurus_by_role)


# ==========================================
# 8. SISTEM PENJADWALAN (MATRIKS SPREADSHEET WEB)
# ==========================================
@app.route('/penjadwalan', methods=['GET', 'POST'])
@login_required
def penjadwalan():
    if session.get('role') not in ['super admin', 'penjadwalan']: return redirect(url_for('index'))
    
    conn = get_db_connection()
    users_db = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        # FITUR 1: MEMBUAT KANVAS SPREADSHEET DI WEB
        if action == 'buat_matriks':
            start_str = request.form.get('start_date')
            end_str = request.form.get('end_date')
            
            if not start_str or not end_str: return redirect(url_for('penjadwalan'))
            
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d')
            days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
            
            matrix_data = []
            curr = start_dt
            
            while curr <= end_dt:
                hari_idx = curr.weekday()
                if hari_idx == 5: masses = [('05.30', 'Misa Pagi'), ('17.00', 'Misa Vigili')]
                elif hari_idx == 6: masses = [('06.00', 'Misa Pagi'), ('08.00', 'Misa Pagi II'), ('10.00', 'Misa Siang'), ('17.00', 'Misa Sore')]
                else: masses = [('05.30', 'Misa Pagi'), ('18.00', 'Misa Sore')]
                
                matrix_data.append({
                    'date_str': curr.strftime('%Y-%m-%d'),
                    'hari': days_id[hari_idx],
                    'tanggal_format': f"{days_id[hari_idx]}, {curr.day} {curr.strftime('%b')}",
                    'masses': masses
                })
                curr += timedelta(days=1)
                
            conn.close()
            return render_template('penjadwalan.html', matrix=matrix_data, users=users_db, start=start_str, end=end_str)

        # FITUR 2: MENYIMPAN HASIL KETIKAN DARI MATRIKS WEB KE DB
        elif action == 'simpan_matriks':
            months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
            parsed_data = []
            
            rendered_dates_raw = request.form.get('rendered_dates')
            if rendered_dates_raw:
                s_str, e_str = rendered_dates_raw.split('|')
                s_dt = datetime.strptime(s_str, '%Y-%m-%d')
                e_dt = datetime.strptime(e_str, '%Y-%m-%d')
                all_dates = []
                c = s_dt
                while c <= e_dt:
                    all_dates.append(c.strftime('%Y-%m-%d'))
                    c += timedelta(days=1)
                
                placeholders = ','.join('?' for _ in all_dates)
                conn.execute(f"DELETE FROM jadwal WHERE date(jadwal_datetime) IN ({placeholders})", all_dates)
            
            for key in request.form.keys():
                if key.startswith('ptgs|'):
                    parts = key.split('|')
                    tgl_str = parts[1]
                    wkt = parts[2]
                    
                    # Dinamis mengambil Nama Acara (Keterangan) yang diedit
                    acara = request.form.get(f"acr|{tgl_str}|{wkt}", 'Misa')
                    hari = request.form.get(f"hri|{tgl_str}|{wkt}", '')
                    
                    dt = datetime.strptime(tgl_str, '%Y-%m-%d')
                    try: jadwal_dt = datetime.strptime(f"{tgl_str} {wkt.replace('.', ':')}:00", '%Y-%m-%d %H:%M:%S')
                    except: jadwal_dt = dt
                    
                    values = request.form.getlist(key)
                    for val in values:
                        if val and val.strip():
                            names = [n.strip() for n in val.split(',') if n.strip()]
                            for n in names:
                                parsed_data.append({
                                    'jadwal_dt': jadwal_dt, 'dt': dt, 'hari': hari,
                                    'wkt': wkt, 'acara': acara, 'nama': n
                                })
            
            for p in parsed_data:
                user_db = conn.execute("SELECT username, nama FROM users WHERE nama LIKE ? OR nama_panggilan LIKE ? OR username = ?", (f"%{p['nama']}%", f"%{p['nama']}%", p['nama'])).fetchone()
                username = user_db['username'] if user_db else p['nama']
                nama_pengguna = user_db['nama'] if user_db else p['nama']
                
                conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                             (p['jadwal_dt'].strftime('%Y-%m-%d %H:%M:%S'), p['dt'].strftime('%d'), months_id[p['dt'].month], p['hari'], p['wkt'], p['acara'], 'Bertugas', username, nama_pengguna))
            
            conn.commit()
            conn.close()
            return redirect(url_for('cetak_jadwal', target_start=s_str, target_end=e_str))

    conn.close()
    return render_template('penjadwalan.html', users=users_db)

# ==========================================
# 9. CETAK JADWAL
# ==========================================
@app.route('/cetak-jadwal')
@login_required
def cetak_jadwal():
    if session.get('role') not in ['super admin', 'penjadwalan', 'bph']: return redirect(url_for('index'))
    
    target_start = request.args.get('target_start')
    target_end = request.args.get('target_end')
    
    conn = get_db_connection()
    if target_start and target_end:
        start_time = f"{target_start} 00:00:00"
        end_time = f"{target_end} 23:59:59"
        rows = conn.execute('SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC', (start_time, end_time)).fetchall()
    else:
        threshold_time = datetime.now().strftime('%Y-%m-%d 00:00:00')
        end_limit = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d 23:59:59')
        rows = conn.execute('SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC', (threshold_time, end_limit)).fetchall()
    conn.close()

    if not rows:
        return render_template('cetak_jadwal.html', weeks=[], periode="-")

    min_date = min([datetime.strptime(r['jadwal_datetime'], '%Y-%m-%d %H:%M:%S') for r in rows])
    max_date = max([datetime.strptime(r['jadwal_datetime'], '%Y-%m-%d %H:%M:%S') for r in rows])
    
    if target_start and target_end:
        min_date = datetime.strptime(target_start, '%Y-%m-%d')
        max_date = datetime.strptime(target_end, '%Y-%m-%d')

    months_id = {1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}
    days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
    
    # PERMINTAAN 1: BIKIN STRING PERIODE
    periode_str = f"{min_date.day} {months_id[min_date.month]} {min_date.year} - {max_date.day} {months_id[max_date.month]} {max_date.year}"

    jadwal_dict = {}
    
    # Prefill struktur tabel supaya rentang hari lengkap
    curr = min_date
    while curr <= max_date:
        date_key = curr.strftime('%Y-%m-%d')
        hari_idx = curr.weekday()
        if hari_idx == 5: masses = [('05.30', 'Misa Pagi'), ('17.00', 'Misa Vigili')]
        elif hari_idx == 6: masses = [('06.00', 'Misa Pagi'), ('08.00', 'Misa Pagi II'), ('10.00', 'Misa Siang'), ('17.00', 'Misa Sore')]
        else: masses = [('05.30', 'Misa Pagi'), ('18.00', 'Misa Sore')]
        
        jadwal_dict[date_key] = {
            'hari': days_id[hari_idx],
            'tanggal_teks': f"{days_id[hari_idx]}, {curr.day} {months_id[curr.month]} {curr.year}",
            'misa': {w: {'acara': a, 'petugas': []} for w, a in masses}
        }
        curr += timedelta(days=1)

    for r in rows:
        dt = datetime.strptime(r['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
        date_key = dt.strftime('%Y-%m-%d')
        if date_key in jadwal_dict:
            wkt = r['waktu']
            if wkt not in jadwal_dict[date_key]['misa']:
                jadwal_dict[date_key]['misa'][wkt] = {'acara': r['acara'], 'petugas': []}
            
            jadwal_dict[date_key]['misa'][wkt]['acara'] = r['acara']
            if r['nama_pengguna'] != '':
                jadwal_dict[date_key]['misa'][wkt]['petugas'].append(r['nama_pengguna'])

    weeks = []
    current_week = {'senin_kamis': [], 'jumat_minggu': []}
    
    sorted_dates = sorted(jadwal_dict.keys())
    for d in sorted_dates:
        dt = datetime.strptime(d, '%Y-%m-%d')
        day_idx = dt.weekday()
        day_obj = {'tanggal_teks': jadwal_dict[d]['tanggal_teks'], 'misa': jadwal_dict[d]['misa']}
        
        if day_idx == 0 and (len(current_week['senin_kamis']) > 0 or len(current_week['jumat_minggu']) > 0):
            weeks.append(current_week)
            current_week = {'senin_kamis': [], 'jumat_minggu': []}
            
        if day_idx <= 3: current_week['senin_kamis'].append(day_obj)
        else: current_week['jumat_minggu'].append(day_obj)
            
    if current_week['senin_kamis'] or current_week['jumat_minggu']: weeks.append(current_week)
        
    final_weeks = []
    for w in weeks:
        # PERMINTAAN 3: HITUNG SLOTS OTOMATIS (Mencegah tabel kosong diprint)
        max_sk = 0
        for day in w['senin_kamis']:
            for wkt, m_data in day['misa'].items():
                if len(m_data['petugas']) > max_sk: max_sk = len(m_data['petugas'])
        w['max_slots_sk'] = max_sk
        
        max_jm = 0
        for day in w['jumat_minggu']:
            for wkt, m_data in day['misa'].items():
                if len(m_data['petugas']) > max_jm: max_jm = len(m_data['petugas'])
        w['max_slots_jm'] = max_jm
        
        for day in w['senin_kamis']:
            for wkt, m_data in day['misa'].items():
                while len(m_data['petugas']) < max_sk: m_data['petugas'].append("")
                    
        for day in w['jumat_minggu']:
            for wkt, m_data in day['misa'].items():
                while len(m_data['petugas']) < max_jm: m_data['petugas'].append("")
        
        final_weeks.append(w)
        
    return render_template('cetak_jadwal.html', weeks=final_weeks, periode=periode_str)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)