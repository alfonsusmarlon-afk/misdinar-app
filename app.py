import os
import json
import random
import string
import sqlite3
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Flask, render_template, request, session, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'misdinar-secure-key-2026-production' 
app.permanent_session_lifetime = timedelta(days=7) 

DB_NAME = 'misdinar.db'
UPLOAD_DOKUMEN = 'static/uploads/dokumen'
UPLOAD_GALERI = 'static/uploads/galeri'
UPLOAD_PROFIL = 'static/uploads/profil'

for folder in [UPLOAD_DOKUMEN, UPLOAD_GALERI, UPLOAD_PROFIL]:
    os.makedirs(folder, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
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

    conn.execute('''CREATE TABLE IF NOT EXISTS pengumuman (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, deskripsi TEXT DEFAULT "", tanggal_pelaksanaan TEXT DEFAULT "-", waktu_pelaksanaan TEXT NOT NULL, tempat TEXT DEFAULT "-", tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL, editor_terakhir TEXT, waktu_edit TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS dokumen (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, file_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL, editor_terakhir TEXT, waktu_edit TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS galeri (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, foto_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL, editor_terakhir TEXT, waktu_edit TEXT)''')
    
    for table in ['pengumuman', 'dokumen', 'galeri']:
        cols = [col[1] for col in conn.execute(f'PRAGMA table_info({table})').fetchall()]
        if 'editor_terakhir' not in cols: conn.execute(f'ALTER TABLE {table} ADD COLUMN editor_terakhir TEXT')
        if 'waktu_edit' not in cols: conn.execute(f'ALTER TABLE {table} ADD COLUMN waktu_edit TEXT')

    pengumuman_cols = [col[1] for col in conn.execute('PRAGMA table_info(pengumuman)').fetchall()]
    if 'tempat' not in pengumuman_cols: conn.execute('ALTER TABLE pengumuman ADD COLUMN tempat TEXT DEFAULT "-"')
    if 'tanggal_pelaksanaan' not in pengumuman_cols: conn.execute('ALTER TABLE pengumuman ADD COLUMN tanggal_pelaksanaan TEXT DEFAULT "-"')

    conn.execute('''CREATE TABLE IF NOT EXISTS jadwal (id INTEGER PRIMARY KEY AUTOINCREMENT, jadwal_datetime TIMESTAMP NOT NULL, tanggal TEXT NOT NULL, bulan TEXT NOT NULL, hari TEXT NOT NULL, waktu TEXT NOT NULL, acara TEXT NOT NULL, status TEXT NOT NULL, pengguna TEXT NOT NULL, nama_pengguna TEXT NOT NULL, jenis TEXT DEFAULT "Matriks", FOREIGN KEY(pengguna) REFERENCES users(username))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS kehadiran (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, kegiatan TEXT NOT NULL, status TEXT NOT NULL, keterangan TEXT, waktu_scan TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS hukuman (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, pelanggaran TEXT NOT NULL, tindakan TEXT NOT NULL, status TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS form_fields (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL, tipe TEXT NOT NULL, wajib INTEGER DEFAULT 1)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS pendaftaran (id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, data_respon TEXT NOT NULL, status TEXT DEFAULT 'Menunggu')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS notifikasi (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, pesan TEXT NOT NULL, waktu TEXT NOT NULL, status_baca INTEGER DEFAULT 0, link TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS izin_jadwal (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, jadwal_id INTEGER NOT NULL, tanggal_misa TEXT NOT NULL, acara TEXT NOT NULL, alasan TEXT NOT NULL, pengganti TEXT DEFAULT "-", status TEXT DEFAULT "Menunggu", waktu_pengajuan TEXT NOT NULL, tanggapan_admin TEXT DEFAULT "-", jenis_izin TEXT DEFAULT "Jadwal")''')
    conn.execute('''CREATE TABLE IF NOT EXISTS buka_titip (id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, waktu TEXT NOT NULL, acara TEXT NOT NULL, kuota INTEGER DEFAULT 1, pembuat TEXT NOT NULL, waktu_dibuat TEXT NOT NULL)''')

    izin_cols = [col[1] for col in conn.execute('PRAGMA table_info(izin_jadwal)').fetchall()]
    if izin_cols and 'jenis_izin' not in izin_cols:
        try: conn.execute('ALTER TABLE izin_jadwal ADD COLUMN jenis_izin TEXT DEFAULT "Jadwal"')
        except: pass

    conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
    
    # DITAMBAHKAN FITUR ON/OFF
    default_settings = {
        'scan_window_before': '60',
        'scan_window_after': '180',
        'sanksi_alpa_harian': '10',
        'sanksi_izin_harian': '0',
        'sanksi_alpa_mingguan': '15',
        'sanksi_izin_mingguan': '5',
        'sanksi_alpa_besar': '30',
        'sanksi_izin_besar': '10',
        'fitur_scan_window': 'on',
        'fitur_sanksi': 'on'
    }
    for k, v in default_settings.items():
        if conn.execute('SELECT COUNT(*) FROM settings WHERE key=?', (k,)).fetchone()[0] == 0:
            conn.execute('INSERT INTO settings (key, value) VALUES (?, ?)', (k, v))
        
    jadwal_columns = [col[1] for col in conn.execute('PRAGMA table_info(jadwal)').fetchall()]
    try:
        if 'scan_before' not in jadwal_columns: conn.execute('ALTER TABLE jadwal ADD COLUMN scan_before INTEGER')
        if 'scan_after' not in jadwal_columns: conn.execute('ALTER TABLE jadwal ADD COLUMN scan_after INTEGER')
        if 'kategori_misa' not in jadwal_columns: conn.execute('ALTER TABLE jadwal ADD COLUMN kategori_misa TEXT DEFAULT "Harian"')
    except sqlite3.OperationalError:
        pass

    kehadiran_columns = [col[1] for col in conn.execute('PRAGMA table_info(kehadiran)').fetchall()]
    try:
        if 'waktu_scan' not in kehadiran_columns: conn.execute('ALTER TABLE kehadiran ADD COLUMN waktu_scan TEXT')
    except sqlite3.OperationalError:
        pass

    if conn.execute('SELECT COUNT(*) FROM form_fields').fetchone()[0] == 0:
        conn.executemany('INSERT INTO form_fields (label, tipe, wajib) VALUES (?, ?, ?)', [('Nama Lengkap', 'text', 1), ('Nomor WhatsApp', 'number', 1), ('Alasan Bergabung', 'textarea', 1)])

    if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        hashed_pw = generate_password_hash('super123')
        conn.execute('INSERT INTO users (username, password, nama, role, no_hp, nama_panggilan) VALUES (?, ?, ?, ?, ?, ?)', ('superadmin', hashed_pw, 'Super Admin', 'super admin', '081234567890', 'Admin'))
    
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_filtered_items(table_name, user_id=None, user_role=None):
    conn = get_db_connection()
    rows = conn.execute(f'SELECT * FROM {table_name} ORDER BY id DESC').fetchall()
    conn.close()
    filtered = []
    for r in rows:
        p = dict(r)
        target_list = [t.strip() for t in p.get('target', 'semua').split(',')]
        pembuat = p.get('pembuat', '')
        if 'semua' in target_list or (user_id and pembuat == user_id): filtered.append(p)
        elif user_id and user_id in target_list: filtered.append(p)
        elif user_role and user_role in target_list: filtered.append(p)
    return filtered

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

def process_auto_absent(conn):
    settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    global_after = int(settings.get('scan_window_after', 180))
    fitur_sanksi = settings.get('fitur_sanksi', 'on')
    now = datetime.now()
    past_jadwals = conn.execute("SELECT * FROM jadwal WHERE status='Bertugas' AND nama_pengguna != '' AND jadwal_datetime <= ?", (now.strftime('%Y-%m-%d %H:%M:%S'),)).fetchall()
    
    for j in past_jadwals:
        j_dict = dict(j) 
        dt_obj = datetime.strptime(j_dict['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
        sa = j_dict['scan_after'] if j_dict.get('scan_after') is not None else global_after
        waktu_tutup = dt_obj + timedelta(minutes=sa)
        
        if now > waktu_tutup:
            username = j_dict['pengguna']
            nama = j_dict['nama_pengguna']
            tanggal = dt_obj.strftime('%Y-%m-%d')
            kegiatan = f"{j_dict['acara']} Pkl {j_dict['waktu']}"
            kategori = j_dict.get('kategori_misa') or 'Harian'
            
            exist = conn.execute("SELECT 1 FROM kehadiran WHERE username=? AND tanggal=? AND kegiatan=?", (username, tanggal, kegiatan)).fetchone()
            
            if not exist:
                conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan, waktu_scan) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                             (username, nama, tanggal, kegiatan, 'Tidak Hadir', 'Otomatis oleh Sistem (Melewati Batas Waktu)', 'Sistem (Auto)'))
                
                if fitur_sanksi == 'on':
                    key_sanksi = f"sanksi_alpa_{kategori.lower()}"
                    weight = int(settings.get(key_sanksi, 0))
                    if weight > 0:
                        pelanggaran = f"Alpa - {kategori}"
                        exist_hk = conn.execute("SELECT * FROM hukuman WHERE username=? AND status='Belum Selesai' ORDER BY id DESC LIMIT 1", (username,)).fetchone()
                        if exist_hk:
                            try: current_weight = int(exist_hk['tindakan'].split()[0])
                            except: current_weight = 0
                            new_weight = current_weight + weight
                            new_pelanggaran = exist_hk['pelanggaran'] + f" + {pelanggaran}"
                            conn.execute("UPDATE hukuman SET pelanggaran=?, tindakan=? WHERE id=?", 
                                         (new_pelanggaran, f"{new_weight} Kali Berlutut", exist_hk['id']))
                        else:
                            conn.execute('INSERT INTO hukuman (username, nama, tanggal, pelanggaran, tindakan, status) VALUES (?, ?, ?, ?, ?, ?)',
                                         (username, nama, tanggal, pelanggaran, f"{weight} Kali Berlutut", 'Belum Selesai'))
    conn.commit()

def create_notification(conn, target_str, pesan, link_url):
    waktu_sekarang = datetime.now().strftime('%d %b %Y, %H:%M')
    target_list = [t.strip() for t in target_str.split(',')]
    if 'semua' in target_list:
        users = conn.execute("SELECT username FROM users").fetchall()
        for u in users: conn.execute('INSERT INTO notifikasi (username, pesan, waktu, link) VALUES (?, ?, ?, ?)', (u['username'], pesan, waktu_sekarang, link_url))
    else:
        users = conn.execute("SELECT username, role FROM users").fetchall()
        for u in users:
            if u['username'] in target_list or u['role'] in target_list:
                conn.execute('INSERT INTO notifikasi (username, pesan, waktu, link) VALUES (?, ?, ?, ?)', (u['username'], pesan, waktu_sekarang, link_url))

@app.context_processor
def inject_notifications():
    if 'user_id' in session:
        conn = get_db_connection()
        notifs = conn.execute("SELECT * FROM notifikasi WHERE username=? ORDER BY id DESC LIMIT 15", (session['user_id'],)).fetchall()
        unread_count = conn.execute("SELECT COUNT(*) FROM notifikasi WHERE username=? AND status_baca=0", (session['user_id'],)).fetchone()[0]
        conn.close()
        return dict(notifs=notifs, unread_count=unread_count)
    return dict(notifs=[], unread_count=0)

@app.route('/baca-notif', methods=['POST'])
@login_required
def baca_notif():
    conn = get_db_connection()
    conn.execute("UPDATE notifikasi SET status_baca=1 WHERE username=?", (session['user_id'],))
    conn.commit()
    conn.close()
    return json.dumps({'success': True})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
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
def logout(): session.clear(); return redirect(url_for('index'))

@app.route('/')
def index():
    user_id = session.get('user_id')
    user_role = session.get('role')
    filtered_pengumuman = get_filtered_items('pengumuman', user_id, user_role)
    conn = get_db_connection()
    threshold_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    quotes = ["Melayani dengan hati, bukan karena ingin dipuji.", "Kasih itu sabar; kasih itu murah hati.", "Lakukan segala pekerjaanmu dalam kasih."]
    quote = quotes[datetime.now().timetuple().tm_yday % len(quotes)]
    
    if user_id:
        rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND status = 'Bertugas' AND pengguna = ? ORDER BY jadwal_datetime ASC LIMIT 4", (threshold_time, user_id)).fetchall()
        user_jadwal = [dict(r) for r in rows]
        conn.close()
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=user_jadwal, quote=quote, user_id=user_id, is_logged_in=True)
    else:
        rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND status = 'Bertugas' AND nama_pengguna != '' ORDER BY jadwal_datetime ASC LIMIT 8", (threshold_time,)).fetchall()
        valid_jadwal = [dict(r) for r in rows]
        conn.close()
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=valid_jadwal, quote=quote, is_logged_in=False)

@app.route('/jadwal', methods=['GET', 'POST'])
def jadwal():
    conn = get_db_connection()
    process_auto_absent(conn)
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')
    user_role = session.get('role', '')
    now_time = datetime.now()
    
    if request.method == 'POST' and is_logged_in:
        action = request.form.get('action')
        
        if action == 'ajukan_izin':
            jadwal_id = request.form.get('jadwal_id')
            alasan = request.form.get('alasan')
            pengganti = request.form.get('pengganti', '-')
            
            jadwal_target = conn.execute("SELECT * FROM jadwal WHERE id=?", (jadwal_id,)).fetchone()
            if jadwal_target and dict(jadwal_target)['pengguna'] == user_id:
                waktu_pengajuan = datetime.now().strftime('%d %b %Y, %H:%M')
                dt_obj = datetime.strptime(dict(jadwal_target)['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
                tgl_misa = dt_obj.strftime('%d %b %Y')
                acara = f"{dict(jadwal_target)['acara']} Pkl {dict(jadwal_target)['waktu']}"
                
                exist_izin = conn.execute("SELECT 1 FROM izin_jadwal WHERE jadwal_id=? AND username=?", (jadwal_id, user_id)).fetchone()
                if not exist_izin:
                    conn.execute('INSERT INTO izin_jadwal (username, nama, jadwal_id, tanggal_misa, acara, alasan, pengganti, status, waktu_pengajuan, jenis_izin) VALUES (?, ?, ?, ?, ?, ?, ?, "Menunggu", ?, "Jadwal")',
                                 (user_id, session.get('nama_user'), jadwal_id, tgl_misa, acara, alasan, pengganti, waktu_pengajuan))
                    create_notification(conn, 'penjadwalan,super admin,bph', f"{session.get('nama_user')} mengajukan izin untuk {acara}.", url_for('kehadiran'))
                    conn.commit()
                    flash("Pengajuan izin berhasil dikirim ke pengurus.", "success")
                else:
                    flash("Anda sudah mengajukan izin untuk jadwal ini.", "error")
                    
        return redirect(url_for('jadwal'))

    view_req = request.args.get('view', '')
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')
    
    if is_logged_in:
        if user_role == 'user' or view_req == 'private':
            user_shifts = conn.execute("SELECT DISTINCT jadwal_datetime, acara FROM jadwal WHERE jadwal_datetime >= ? AND status = 'Bertugas' AND pengguna = ? ORDER BY jadwal_datetime ASC", (thirty_days_ago, user_id)).fetchall()
            jadwal_data = []
            
            kehadirans = conn.execute("SELECT * FROM kehadiran WHERE username=?", (user_id,)).fetchall()
            keh_dict = {(k['tanggal'], k['kegiatan']): k['status'] for k in kehadirans}
            
            for shift in user_shifts:
                shift_rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND status = 'Bertugas' AND nama_pengguna != '' ORDER BY id ASC", (dict(shift)['jadwal_datetime'], dict(shift)['acara'])).fetchall()
                for r in shift_rows:
                    j = dict(r)
                    dt_obj = datetime.strptime(j['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
                    tgl = dt_obj.strftime('%Y-%m-%d')
                    keg = f"{j['acara']} Pkl {j['waktu']}"
                    
                    j['is_past'] = dt_obj < now_time
                    if j['pengguna'] == user_id:
                        if (tgl, keg) in keh_dict: j['status_kehadiran'] = keh_dict[(tgl, keg)]
                        elif j['is_past']: j['status_kehadiran'] = 'Tidak Hadir'
                        else: j['status_kehadiran'] = 'Belum Absen'
                    
                    jadwal_data.append(j)
                    
            jadwal_data = sorted(jadwal_data, key=lambda k: k['jadwal_datetime'])
            view_mode = 'private'
        else:
            rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND status = 'Bertugas' AND nama_pengguna != '' ORDER BY jadwal_datetime ASC", (thirty_days_ago,)).fetchall()
            kehadirans = conn.execute("SELECT * FROM kehadiran").fetchall()
            keh_dict = {(k['username'], k['tanggal'], k['kegiatan']): k['status'] for k in kehadirans}
            jadwal_data = []
            for r in rows:
                j = dict(r)
                dt_obj = datetime.strptime(j['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
                tgl = dt_obj.strftime('%Y-%m-%d')
                keg = f"{j['acara']} Pkl {j['waktu']}"
                usr = j['pengguna']
                key = (usr, tgl, keg)
                
                j['is_past'] = dt_obj < now_time
                if key in keh_dict: j['status_kehadiran'] = keh_dict[key]
                elif j['is_past']: j['status_kehadiran'] = 'Tidak Hadir'
                else: j['status_kehadiran'] = 'Belum Absen'
                jadwal_data.append(j)
            view_mode = 'admin_all'
            
        user_izin = conn.execute("SELECT jadwal_id, status FROM izin_jadwal WHERE username=? AND jenis_izin='Jadwal'", (user_id,)).fetchall()
        izin_dict = {i['jadwal_id']: i['status'] for i in user_izin}
        
        conn.close()
        return render_template('jadwal.html', jadwal=jadwal_data, user_id=user_id, is_logged_in=True, view_mode=view_mode, user_role=user_role, izin_dict=izin_dict)
    else:
        rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND status = 'Bertugas' AND nama_pengguna != '' ORDER BY jadwal_datetime ASC", (thirty_days_ago,)).fetchall()
        jadwal_data = []
        for r in rows:
            j = dict(r)
            j['is_past'] = datetime.strptime(j['jadwal_datetime'], '%Y-%m-%d %H:%M:%S') < now_time
            jadwal_data.append(j)
        conn.close()
        return render_template('jadwal.html', jadwal=jadwal_data, user_id=None, is_logged_in=False, view_mode='public', user_role=None, izin_dict={})

@app.route('/titip', methods=['GET', 'POST'])
@login_required
def titip():
    user_id, user_role = session.get('user_id'), session.get('role')
    conn = get_db_connection()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'buka_slot' and user_role in ['super admin', 'penjadwalan', 'bph']:
            tgl = request.form.get('tanggal')
            wkt = request.form.get('waktu')
            acara = request.form.get('acara')
            kuota = int(request.form.get('kuota', 1))
            conn.execute("INSERT INTO buka_titip (tanggal, waktu, acara, kuota, pembuat, waktu_dibuat) VALUES (?, ?, ?, ?, ?, ?)",
                         (tgl, wkt, acara, kuota, user_id, now_str))
            create_notification(conn, 'semua', f"Slot Titip Absen baru dibuka untuk {acara} tgl {tgl}! Cepat ambil sebelum penuh.", url_for('titip'))
            conn.commit()
            flash("Slot titip absen berhasil dibuka dan diumumkan!", "success")
            
        elif action == 'hapus_slot' and user_role in ['super admin', 'penjadwalan', 'bph']:
            conn.execute("DELETE FROM buka_titip WHERE id=?", (request.form.get('id'),))
            conn.commit()
            flash("Slot titip absen telah ditutup/dihapus.", "success")
            
        elif action == 'ambil_slot':
            slot_id = request.form.get('slot_id')
            slot = conn.execute("SELECT * FROM buka_titip WHERE id=?", (slot_id,)).fetchone()
            if slot:
                dt_str = f"{slot['tanggal']} {slot['waktu']}:00"
                
                terisi = conn.execute("SELECT COUNT(*) FROM jadwal WHERE jadwal_datetime=? AND acara=? AND jenis='Titip'", (dt_str, slot['acara'])).fetchone()[0]
                if terisi < slot['kuota']:
                    sudah = conn.execute("SELECT 1 FROM jadwal WHERE jadwal_datetime=? AND acara=? AND pengguna=?", (dt_str, slot['acara'], user_id)).fetchone()
                    if not sudah:
                        dt = datetime.strptime(slot['tanggal'], '%Y-%m-%d')
                        months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
                        days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
                        
                        waktu_dot = slot['waktu'].replace(':', '.')
                        conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna, jenis, kategori_misa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "Titip", "Harian")', 
                                     (dt_str, dt.strftime('%d'), months_id[dt.month], days_id[dt.weekday()], waktu_dot, slot['acara'], 'Bertugas', user_id, session.get('nama_user')))
                        conn.commit()
                        flash("Selamat! Anda berhasil mengamankan slot titip absen. Cek menu Jadwal Anda.", "success")
                    else:
                        flash("Anda sudah terdaftar di jadwal Misa tersebut.", "error")
                else:
                    flash("Maaf, slot sudah penuh! Anda kalah cepat.", "error")
        return redirect(url_for('titip'))
        
    slots = conn.execute("SELECT * FROM buka_titip ORDER BY tanggal DESC, waktu DESC LIMIT 50").fetchall()
    slot_data = []
    for s in slots:
        d = dict(s)
        dt_str = f"{d['tanggal']} {d['waktu']}:00"
        terisi = conn.execute("SELECT pengguna, nama_pengguna FROM jadwal WHERE jadwal_datetime=? AND acara=? AND jenis='Titip'", (dt_str, d['acara'])).fetchall()
        d['terisi'] = len(terisi)
        d['sisa'] = d['kuota'] - len(terisi)
        d['peserta'] = [p['nama_pengguna'] for p in terisi]
        d['sudah_join'] = user_id in [p['pengguna'] for p in terisi]
        d['is_past'] = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S') < datetime.now()
        slot_data.append(d)
        
    conn.close()
    return render_template('titip.html', slots=slot_data, role=user_role)

@app.route('/scan-absen')
@login_required
def scan_absen():
    return render_template('scan_absen.html')

@app.route('/api/absen', methods=['POST'])
@login_required
def api_absen():
    current_user = session.get('user_id')
    try:
        data = request.json
        if not data: return json.dumps({'success': False, 'message': 'Format QR Code tidak valid.'})
        conn = get_db_connection()
        now = datetime.now()
        settings_dict = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        fitur_scan = settings_dict.get('fitur_scan_window', 'on')
        
        if data.get('type') == 'event':
            dt_val, ac_val = data.get('dt'), data.get('ac')
            if not dt_val or not ac_val: return json.dumps({'success': False, 'message': 'Data QR Acara tidak lengkap.'})
            user = conn.execute("SELECT nama FROM users WHERE username=?", (current_user,)).fetchone()
            
            assigned = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND pengguna = ?", (dt_val, ac_val, current_user)).fetchone()
            if not assigned:
                conn.close()
                return json.dumps({'success': False, 'message': 'Akses Ditolak: Anda TIDAK ditugaskan pada jadwal Misa ini!'})
            
            assigned_dict = dict(assigned)
            dt_obj = datetime.strptime(dt_val, '%Y-%m-%d %H:%M:%S')
            kegiatan = f"{ac_val} Pkl {dt_obj.strftime('%H.%M')}"
            scan_before, scan_after = assigned_dict.get('scan_before'), assigned_dict.get('scan_after')
            nama_user = user['nama']
            
        else:
            if 'j' not in data: return json.dumps({'success': False, 'message': 'Format QR Code Kertas tidak valid.'})
            jadwal_id = data['j']
            
            jadwal = conn.execute("SELECT * FROM jadwal WHERE id=?", (jadwal_id,)).fetchone()
            if not jadwal:
                conn.close(); return json.dumps({'success': False, 'message': 'Jadwal tidak ditemukan.'})
            
            jadwal_dict = dict(jadwal)
            if jadwal_dict['pengguna'] != current_user:
                conn.close(); return json.dumps({'success': False, 'message': 'Akses Ditolak: Anda TIDAK ditugaskan pada jadwal ini!'})
            
            user = conn.execute("SELECT nama FROM users WHERE username=?", (current_user,)).fetchone()
            nama_user = user['nama']
            
            dt_obj = datetime.strptime(jadwal_dict['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
            kegiatan = f"{jadwal_dict['acara']} Pkl {jadwal_dict['waktu']}"
            scan_before, scan_after = jadwal_dict.get('scan_before'), jadwal_dict.get('scan_after')

        if scan_before is None or scan_after is None:
            scan_before = int(settings_dict.get('scan_window_before', 60))
            scan_after = int(settings_dict.get('scan_window_after', 180))
            
        waktu_buka = dt_obj - timedelta(minutes=scan_before)
        waktu_tutup = dt_obj + timedelta(minutes=scan_after)
        
        months_id = {1: 'Juni', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}
        def format_indo(dt): return f"{dt.day} {months_id[dt.month]} {dt.year} pukul {dt.strftime('%H.%M')}"
        
        if fitur_scan == 'on':
            if now < waktu_buka:
                conn.close()
                return json.dumps({'success': False, 'message': f'Belum waktunya! Absen dibuka pada {format_indo(waktu_buka)}.'})
            if now > waktu_tutup:
                conn.close()
                return json.dumps({'success': False, 'message': f'Terlambat! Absen ditutup pada {format_indo(waktu_tutup)}.'})
            
        tanggal_absen = dt_obj.strftime('%Y-%m-%d')
        exist = conn.execute("SELECT * FROM kehadiran WHERE username=? AND tanggal=? AND kegiatan=?", (current_user, tanggal_absen, kegiatan)).fetchone()
        if exist:
            conn.close()
            return json.dumps({'success': True, 'message': f"Info: Kehadiran {nama_user} SUDAH TERABSEN sebelumnya!"})
            
        waktu_scan_str = now.strftime('%d %b %Y, Pkl %H:%M:%S')
        conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan, waktu_scan) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                     (current_user, nama_user, tanggal_absen, kegiatan, 'Hadir', 'Scan QR Berhasil', waktu_scan_str))
        conn.commit(); conn.close()
        return json.dumps({'success': True, 'message': f"Berhasil! Kehadiran {nama_user} telah dicatat."})
    except Exception as e:
        return json.dumps({'success': False, 'message': f"Error Sistem: {str(e)}"})

@app.route('/kehadiran', methods=['GET', 'POST'])
@login_required
def kehadiran():
    user_id, user_role = session.get('user_id'), session.get('role')
    conn = get_db_connection()
    process_auto_absent(conn)
    now_time = datetime.now()
    
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        item_id = request.form.get('id', '')
        target_username = request.form.get('username') or request.form.get('username_hidden')
        
        if action == 'hapus_riwayat_izin':
            conn.execute("DELETE FROM izin_jadwal WHERE status != 'Menunggu'")
            conn.commit()
            flash("Riwayat perizinan yang sudah selesai berhasil dibersihkan.", "success")
            return redirect(url_for('kehadiran'))
            
        if action == 'tanggapi_izin':
            izin_id = request.form.get('izin_id')
            status_tanggapan = request.form.get('status_tanggapan')
            pesan_admin = request.form.get('tanggapan_admin', '')
            pengganti_username = request.form.get('pengganti_username', '') 
            
            izin_data = conn.execute("SELECT * FROM izin_jadwal WHERE id=?", (izin_id,)).fetchone()
            if izin_data:
                iz_dict = dict(izin_data)
                conn.execute("UPDATE izin_jadwal SET status=?, tanggapan_admin=? WHERE id=?", (status_tanggapan, pesan_admin, izin_id))
                
                if status_tanggapan == 'Disetujui':
                    if iz_dict.get('jenis_izin') == 'Non-Jadwal':
                        conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan, waktu_scan) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                                     (iz_dict['username'], iz_dict['nama'], iz_dict['tanggal_misa'], iz_dict['acara'], 'Izin', f"Izin Kegiatan Disetujui: {iz_dict['alasan']}", 'Sistem (ACC)'))
                        create_notification(conn, iz_dict['username'], f"Izin kegiatan {iz_dict['acara']} telah Disetujui.", url_for('kehadiran'))
                    else:
                        jadwal_target = conn.execute("SELECT * FROM jadwal WHERE id=?", (iz_dict['jadwal_id'],)).fetchone()
                        if jadwal_target:
                            j_dict = dict(jadwal_target)
                            dt_obj = datetime.strptime(j_dict['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
                            tgl = dt_obj.strftime('%Y-%m-%d')
                            keg = f"{j_dict['acara']} Pkl {j_dict['waktu']}"
                            
                            conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan, waktu_scan) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                                         (iz_dict['username'], iz_dict['nama'], tgl, keg, 'Izin', f"Izin Disetujui: {iz_dict['alasan']}", 'Sistem (ACC)'))
                            
                            if pengganti_username:
                                user_pg = conn.execute("SELECT nama FROM users WHERE username=?", (pengganti_username,)).fetchone()
                                if user_pg:
                                    nama_pg = dict(user_pg)['nama']
                                    conn.execute("UPDATE jadwal SET pengguna=?, nama_pengguna=? WHERE id=?", (pengganti_username, nama_pg, iz_dict['jadwal_id']))
                                    create_notification(conn, iz_dict['username'], f"Izin Disetujui! Untuk Misa {keg}, kamu sudah diganti oleh {nama_pg}.", url_for('jadwal', view='private'))
                                    create_notification(conn, pengganti_username, f"Anda ditugaskan pada Misa {keg} menggantikan {iz_dict['nama']}.", url_for('jadwal', view='private'))
                            else:
                                create_notification(conn, iz_dict['username'], f"Pengajuan izin Anda untuk Misa {keg} telah Disetujui.", url_for('jadwal', view='private'))
                else:
                    create_notification(conn, iz_dict['username'], f"Pengajuan izin Anda untuk {iz_dict['acara']} Ditolak. {pesan_admin}", url_for('jadwal', view='private'))
                conn.commit()
            return redirect(url_for('kehadiran'))

        if target_username == user_id and action != 'hapus':
            flash("Keamanan Sistem: Anda tidak diizinkan mengedit status absensi milik Anda sendiri.", "error")
            return redirect(url_for('kehadiran'))
        
        if action == 'tambah' or action == 'edit':
            status_baru = request.form.get('status')
            keterangan_baru = request.form.get('keterangan', '')
            
            if action == 'edit' and str(item_id).startswith('j_') and status_baru in ['Tidak Hadir', 'Izin']:
                jadwal_id = item_id.split('_')[1]
                j = conn.execute("SELECT * FROM jadwal WHERE id=?", (jadwal_id,)).fetchone()
                if j:
                    j_dict = dict(j)
                    kategori = j_dict.get('kategori_misa') or 'Harian'
                    settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
                    prefix = 'alpa' if status_baru == 'Tidak Hadir' else 'izin'
                    weight = int(settings.get(f"sanksi_{prefix}_{kategori.lower()}", 0))
                    fitur_sanksi = settings.get('fitur_sanksi', 'on')
                    
                    if weight > 0 and fitur_sanksi == 'on':
                        pelanggaran = f"{status_baru} - {kategori}"
                        nama_target = request.form.get('nama_hidden') or target_username
                        
                        exist_hk = conn.execute("SELECT * FROM hukuman WHERE username=? AND status='Belum Selesai' ORDER BY id DESC LIMIT 1", (target_username,)).fetchone()
                        if exist_hk:
                            try: current_weight = int(exist_hk['tindakan'].split()[0])
                            except: current_weight = 0
                            new_weight = current_weight + weight
                            new_pelanggaran = exist_hk['pelanggaran'] + f" + {pelanggaran}"
                            conn.execute("UPDATE hukuman SET pelanggaran=?, tindakan=? WHERE id=?", (new_pelanggaran, f"{new_weight} Kali Berlutut", exist_hk['id']))
                        else:
                            conn.execute('INSERT INTO hukuman (username, nama, tanggal, pelanggaran, tindakan, status) VALUES (?, ?, ?, ?, ?, ?)',
                                        (target_username, nama_target, request.form.get('tanggal'), pelanggaran, f"{weight} Kali Berlutut", 'Belum Selesai'))

            if action == 'tambah':
                target = conn.execute("SELECT nama FROM users WHERE username=?", (request.form.get('username'),)).fetchone()
                nama = target['nama'] if target else request.form.get('username')
                conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan, waktu_scan) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                             (request.form.get('username'), nama, request.form.get('tanggal'), request.form.get('kegiatan'), status_baru, keterangan_baru, 'Manual Admin'))
            elif action == 'edit':
                if str(item_id).startswith('j_'):
                    username_hidden = request.form.get('username_hidden')
                    target = conn.execute("SELECT nama FROM users WHERE username=?", (username_hidden,)).fetchone()
                    nama = target['nama'] if target else username_hidden
                    conn.execute('INSERT INTO kehadiran (username, nama, tanggal, kegiatan, status, keterangan, waktu_scan) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                                 (username_hidden, nama, request.form.get('tanggal'), request.form.get('kegiatan'), status_baru, keterangan_baru, 'Diubah Manual Admin'))
                else:
                    conn.execute('UPDATE kehadiran SET status=?, keterangan=?, waktu_scan=? WHERE id=?', 
                                 (status_baru, keterangan_baru, 'Diubah Manual Admin', item_id))
                             
        elif action == 'hapus':
            if not str(item_id).startswith('j_'): 
                conn.execute('DELETE FROM kehadiran WHERE id=?', (item_id,))
                
        conn.commit(); return redirect(url_for('kehadiran'))

    users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else []
    
    data_izin = []
    if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        jadwals = conn.execute("SELECT * FROM jadwal WHERE status='Bertugas' AND nama_pengguna != ''").fetchall()
        kehadirans = conn.execute("SELECT * FROM kehadiran").fetchall()
        data_izin = conn.execute("SELECT * FROM izin_jadwal ORDER BY id DESC").fetchall()
    else:
        jadwals = conn.execute("SELECT * FROM jadwal WHERE status='Bertugas' AND pengguna = ?", (user_id,)).fetchall()
        kehadirans = conn.execute("SELECT * FROM kehadiran WHERE username=?", (user_id,)).fetchall()

    keh_dict = {(k['username'], k['tanggal'], k['kegiatan']): dict(k) for k in kehadirans}
    combined = []

    for j in jadwals:
        j_dict = dict(j)
        dt_obj = datetime.strptime(j_dict['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
        tgl = dt_obj.strftime('%Y-%m-%d')
        keg = f"{j_dict['acara']} Pkl {j_dict['waktu']}"
        usr = j_dict['pengguna']
        key = (usr, tgl, keg)
        
        is_past = dt_obj < now_time

        if key in keh_dict:
            item = keh_dict[key]
            if not item.get('waktu_scan'): item['waktu_scan'] = '-'
            item['is_past'] = is_past 
            combined.append(item)
            del keh_dict[key]
        else:
            status_k = 'Tidak Hadir' if is_past else 'Belum Absen'
            combined.append({
                'id': f"j_{j_dict['id']}", 'username': usr, 'nama': j_dict['nama_pengguna'],
                'tanggal': tgl, 'kegiatan': keg, 'status': status_k,
                'keterangan': '-', 'waktu_scan': '-', 'is_past': is_past
            })

    for k in keh_dict.values():
        item = dict(k)
        if not item.get('waktu_scan'): item['waktu_scan'] = '-'
        item['is_past'] = False
        combined.append(item)

    combined = sorted(combined, key=lambda x: (x['tanggal'], x['kegiatan']), reverse=True)
    conn.close()
    return render_template('kehadiran.html', kehadiran=combined, data_izin=data_izin, users=users_list, role=user_role)

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
        elif action == 'selesai': conn.execute('UPDATE hukuman SET status="Selesai" WHERE id=?', (request.form.get('id'),))
        conn.commit(); return redirect(url_for('hukuman'))

    users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else []
    
    if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']: data_hukuman = conn.execute('SELECT * FROM hukuman ORDER BY id DESC').fetchall()
    else: data_hukuman = conn.execute('SELECT * FROM hukuman WHERE username=? ORDER BY id DESC', (user_id,)).fetchall()
    
    tunggakan_dict = {}
    for h in data_hukuman:
        if h['status'] != 'Selesai' and 'Kali Berlutut' in h['tindakan']:
            try:
                amount = int(h['tindakan'].split()[0])
                tunggakan_dict[h['username']] = tunggakan_dict.get(h['username'], 0) + amount
            except: pass
            
    conn.close()
    return render_template('hukuman.html', hukuman=data_hukuman, users=users_list, role=user_role, tunggakan=tunggakan_dict, current_user=user_id)

@app.route('/pengaturan', methods=['GET', 'POST'])
@login_required
def pengaturan():
    user_id = session.get('user_id')
    conn = get_db_connection()
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'profile':
            nama_lengkap, nama_panggilan = request.form.get('nama_lengkap'), request.form.get('nama_panggilan')
            email, tanggal_lahir = request.form.get('email'), request.form.get('tanggal_lahir')
            no_hp, nama_ortu = request.form.get('no_hp'), request.form.get('nama_ortu')
            no_hp_ortu, alamat = request.form.get('no_hp_ortu'), request.form.get('alamat')
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
    conn.close(); return render_template('pendaftaran.html', fields=fields)

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
        conn.commit(); return redirect(url_for('kelola_pendaftaran'))

    fields = conn.execute('SELECT * FROM form_fields ORDER BY id ASC').fetchall()
    pendaftar_list = []
    for p in conn.execute('SELECT * FROM pendaftaran ORDER BY id DESC').fetchall():
        p_dict = dict(p)
        try: p_dict['data_parsed'] = json.loads(p['data_respon'])
        except: p_dict['data_parsed'] = {}
        pendaftar_list.append(p_dict)
    conn.close()
    return render_template('kelola_pendaftaran.html', fields=fields, pendaftar=pendaftar_list)

@app.route('/pengumuman', methods=['GET', 'POST'])
def pengumuman():
    user_id, user_role = session.get('user_id'), session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        conn = get_db_connection()
        nama_pengurus = session.get('nama_user', 'Admin')
        now_str = datetime.now().strftime('%d %b %Y, %H:%M')
        
        if action in ['tambah', 'edit']:
            target_str = 'semua' if 'semua' in request.form.getlist('target') else ','.join(request.form.getlist('target'))
            judul_info = request.form.get('judul')
            tgl_pelaksanaan = request.form.get('tanggal_pelaksanaan')
            wkt_pelaksanaan = request.form.get('waktu_pelaksanaan')
            tempat = request.form.get('tempat')
            
            if action == 'tambah': 
                conn.execute('INSERT INTO pengumuman (judul, deskripsi, tanggal_pelaksanaan, waktu_pelaksanaan, tempat, tanggal_dibuat, target, pembuat, editor_terakhir, waktu_edit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                             (judul_info, request.form.get('deskripsi', ''), tgl_pelaksanaan, wkt_pelaksanaan, tempat, datetime.now().strftime("%d %b %Y"), target_str, user_id, nama_pengurus, now_str))
                create_notification(conn, target_str, f"Ada pengumuman baru: {judul_info}", url_for('pengumuman'))
            else: 
                conn.execute('UPDATE pengumuman SET judul=?, deskripsi=?, tanggal_pelaksanaan=?, waktu_pelaksanaan=?, tempat=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                             (judul_info, request.form.get('deskripsi', ''), tgl_pelaksanaan, wkt_pelaksanaan, tempat, target_str, nama_pengurus, now_str, request.form.get('id')))
                create_notification(conn, target_str, f"Pengumuman '{judul_info}' baru saja diperbarui.", url_for('pengumuman'))
                
        elif action == 'hapus': 
            conn.execute('DELETE FROM pengumuman WHERE id=?', (request.form.get('id'),))
        conn.commit(); conn.close()
        return redirect(url_for('pengumuman'))
    
    return render_template('pengumuman.html', pengumuman=get_filtered_items('pengumuman', user_id, user_role), role=user_role, users_by_role=get_grouped_users())

@app.route('/dokumen', methods=['GET', 'POST'])
def dokumen():
    user_id, user_role = session.get('user_id'), session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        conn = get_db_connection()
        nama_pengurus = session.get('nama_user', 'Admin')
        now_str = datetime.now().strftime('%d %b %Y, %H:%M')
        
        if action in ['tambah', 'edit']:
            target_str = 'semua' if 'semua' in request.form.getlist('target') else ','.join(request.form.getlist('target'))
            file_paths = []
            judul_info = request.form.get('judul')
            
            for idx, file in enumerate(request.files.getlist('file')):
                if file and file.filename != '':
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{idx}_{file.filename}")
                    file.save(os.path.join(UPLOAD_DOKUMEN, filename))
                    file_paths.append(f"uploads/dokumen/{filename}")
                    
            if action == 'tambah': 
                conn.execute('INSERT INTO dokumen (judul, file_path, tanggal_dibuat, target, pembuat, editor_terakhir, waktu_edit) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                             (judul_info, ','.join(file_paths), datetime.now().strftime("%d %b %Y"), target_str, user_id, nama_pengurus, now_str))
                create_notification(conn, target_str, f"Ada dokumen baru yang dibagikan: {judul_info}", url_for('dokumen'))
            else:
                p_id = request.form.get('id')
                if file_paths:
                    old_doc = conn.execute('SELECT file_path FROM dokumen WHERE id=?', (p_id,)).fetchone()
                    if old_doc and old_doc['file_path']:
                        for p in old_doc['file_path'].split(','):
                            if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
                    conn.execute('UPDATE dokumen SET judul=?, file_path=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, ','.join(file_paths), target_str, nama_pengurus, now_str, p_id))
                else: 
                    conn.execute('UPDATE dokumen SET judul=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, target_str, nama_pengurus, now_str, p_id))
                create_notification(conn, target_str, f"Dokumen '{judul_info}' baru saja diperbarui.", url_for('dokumen'))
                
        elif action == 'hapus':
            p_id = request.form.get('id')
            old_doc = conn.execute('SELECT file_path FROM dokumen WHERE id=?', (p_id,)).fetchone()
            if old_doc and old_doc['file_path']:
                for p in old_doc['file_path'].split(','):
                    if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
            conn.execute('DELETE FROM dokumen WHERE id=?', (p_id,))
        conn.commit(); conn.close()
        return redirect(url_for('dokumen'))
        
    return render_template('dokumen.html', dokumen=get_filtered_items('dokumen', user_id, user_role), role=user_role, users_by_role=get_grouped_users())

@app.route('/galeri', methods=['GET', 'POST'])
def galeri():
    user_id, user_role = session.get('user_id'), session.get('role')
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        conn = get_db_connection()
        nama_pengurus = session.get('nama_user', 'Admin')
        now_str = datetime.now().strftime('%d %b %Y, %H:%M')
        
        if action in ['tambah', 'edit']:
            target_str = 'semua' if 'semua' in request.form.getlist('target') else ','.join(request.form.getlist('target'))
            foto_paths = []
            judul_info = request.form.get('judul')
            
            for idx, foto in enumerate(request.files.getlist('foto')):
                if foto and foto.filename != '':
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{idx}_{foto.filename}")
                    foto.save(os.path.join(UPLOAD_GALERI, filename))
                    foto_paths.append(f"uploads/galeri/{filename}")
                    
            if action == 'tambah': 
                conn.execute('INSERT INTO galeri (judul, foto_path, tanggal_dibuat, target, pembuat, editor_terakhir, waktu_edit) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                             (judul_info, ','.join(foto_paths), datetime.now().strftime("%d %b %Y"), target_str, user_id, nama_pengurus, now_str))
                create_notification(conn, target_str, f"Album foto baru telah diupload: {judul_info}", url_for('galeri'))
            else:
                p_id = request.form.get('id')
                if foto_paths:
                    old_gal = conn.execute('SELECT foto_path FROM galeri WHERE id=?', (p_id,)).fetchone()
                    if old_gal and old_gal['foto_path']:
                        for p in old_gal['foto_path'].split(','):
                            if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
                    conn.execute('UPDATE galeri SET judul=?, foto_path=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, ','.join(foto_paths), target_str, nama_pengurus, now_str, p_id))
                else: 
                    conn.execute('UPDATE galeri SET judul=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, target_str, nama_pengurus, now_str, p_id))
                create_notification(conn, target_str, f"Album foto '{judul_info}' telah diperbarui.", url_for('galeri'))
                
        elif action == 'hapus':
            p_id = request.form.get('id')
            old_gal = conn.execute('SELECT foto_path FROM galeri WHERE id=?', (p_id,)).fetchone()
            if old_gal and old_gal['foto_path']:
                for p in old_gal['foto_path'].split(','):
                    if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
            conn.execute('DELETE FROM galeri WHERE id=?', (p_id,))
        conn.commit(); conn.close()
        return redirect(url_for('galeri'))
        
    return render_template('galeri.html', galeri=get_filtered_items('galeri', user_id, user_role), role=user_role, users_by_role=get_grouped_users())

@app.route('/kontak')
def kontak():
    conn = get_db_connection()
    pengurus_db = conn.execute("SELECT nama, role, no_hp FROM users WHERE role IN ('bph', 'penjadwalan', 'pelatihan') ORDER BY role ASC, nama ASC").fetchall()
    conn.close()
    pengurus_by_role = {}
    for p in pengurus_db: pengurus_by_role.setdefault(p['role'], []).append(dict(p))
    return render_template('kontak.html', pengurus_by_role=pengurus_by_role)

@app.route('/penjadwalan', methods=['GET', 'POST'])
@login_required
def penjadwalan():
    if session.get('role') not in ['super admin', 'penjadwalan', 'bph', 'pelatihan']: return redirect(url_for('index'))
    conn = get_db_connection()
    users_db = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall()
    user_names = [u['nama'] for u in users_db]
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_sanksi_settings':
            keys = ['sanksi_alpa_harian', 'sanksi_izin_harian', 'sanksi_alpa_mingguan', 'sanksi_izin_mingguan', 'sanksi_alpa_besar', 'sanksi_izin_besar']
            for k in keys:
                val = request.form.get(k, '0')
                conn.execute("UPDATE settings SET value=? WHERE key=?", (val, k))
                
            f_sanksi = request.form.get('fitur_sanksi')
            conn.execute("UPDATE settings SET value=? WHERE key='fitur_sanksi'", ('on' if f_sanksi else 'off',))
            conn.commit()
            flash("Pengaturan Sanksi & Hukuman berhasil diperbarui!", "success")
            return redirect(url_for('penjadwalan'))
        
        elif action == 'update_global_scan_window':
            sb = request.form.get('scan_window_before', '60')
            sa = request.form.get('scan_window_after', '180')
            conn.execute("UPDATE settings SET value=? WHERE key='scan_window_before'", (sb,))
            conn.execute("UPDATE settings SET value=? WHERE key='scan_window_after'", (sa,))
            
            f_scan = request.form.get('fitur_scan_window')
            conn.execute("UPDATE settings SET value=? WHERE key='fitur_scan_window'", ('on' if f_scan else 'off',))
            conn.commit()
            flash("Pengaturan Waktu Absensi berhasil diperbarui!", "success")
            return redirect(url_for('penjadwalan'))
            
        elif action == 'update_shift_scan_window':
            dt_val = request.form.get('shift_dt')
            ac_val = request.form.get('shift_ac')
            jn_val = request.form.get('shift_jn')
            sb = request.form.get('scan_before')
            sa = request.form.get('scan_after')
            sb = sb if sb and sb.strip() != '' else None
            sa = sa if sa and sa.strip() != '' else None
            conn.execute("UPDATE jadwal SET scan_before=?, scan_after=? WHERE jadwal_datetime=? AND acara=? AND jenis=?", (sb, sa, dt_val, ac_val, jn_val))
            conn.commit()
            flash(f"Pengaturan waktu absensi KHUSUS untuk jadwal {ac_val} berhasil diterapkan!", "success")
            return redirect(url_for('penjadwalan'))
            
        elif action == 'edit_jadwal_group':
            old_dt = request.form.get('old_dt')
            old_ac = request.form.get('old_ac')
            old_jn = request.form.get('old_jn')
            tgl_str = request.form.get('tanggal')
            wkt_raw = request.form.get('waktu') 
            acara = request.form.get('acara')
            kategori = request.form.get('kategori', 'Besar')
            petugas_list = request.form.getlist('petugas')
            
            if old_dt and old_ac and old_jn and tgl_str and wkt_raw and acara:
                old_row = conn.execute("SELECT status, scan_before, scan_after FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND jenis = ? LIMIT 1", (old_dt, old_ac, old_jn)).fetchone()
                status = old_row['status'] if old_row else 'Bertugas'
                sb = old_row['scan_before'] if old_row else None
                sa = old_row['scan_after'] if old_row else None
                
                existing_rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND jenis = ?", (old_dt, old_ac, old_jn)).fetchall()
                existing_map = {}
                for r in existing_rows:
                    usr = dict(r).get('pengguna')
                    if usr not in existing_map: existing_map[usr] = []
                    existing_map[usr].append(dict(r))
                
                wkt = wkt_raw.replace(':', '.')
                dt = datetime.strptime(tgl_str, '%Y-%m-%d')
                try: jadwal_dt = datetime.strptime(f"{tgl_str} {wkt_raw}:00", '%Y-%m-%d %H:%M:%S')
                except: jadwal_dt = dt
                months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
                days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
                hari = days_id[dt.weekday()]
                
                petugas_list = [p for p in petugas_list if p]
                unique_petugas = []
                for p in petugas_list:
                    if p not in unique_petugas: unique_petugas.append(p)
                if not unique_petugas: unique_petugas = ['']
                
                for p_id in unique_petugas:
                    username, nama_pengguna = '', ''
                    if p_id:
                        user_db = conn.execute("SELECT username, nama FROM users WHERE username = ?", (p_id,)).fetchone()
                        if user_db: username, nama_pengguna = user_db['username'], user_db['nama']
                        else: username, nama_pengguna = p_id, p_id
                    
                    if username in existing_map and len(existing_map[username]) > 0:
                        old_r = existing_map[username].pop(0)
                        conn.execute('UPDATE jadwal SET jadwal_datetime=?, tanggal=?, bulan=?, hari=?, waktu=?, acara=?, kategori_misa=?, nama_pengguna=? WHERE id=?', 
                                     (jadwal_dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%d'), months_id[dt.month], hari, wkt, acara, kategori, nama_pengguna, old_r['id']))
                        
                        if old_r['pengguna'] != username and old_r['pengguna']:
                            create_notification(conn, old_r['pengguna'], f"Untuk tugas Misa {old_ac}, kamu sudah diganti oleh {nama_pengguna}.", url_for('jadwal', view='private'))
                            create_notification(conn, username, f"Anda ditugaskan pada Misa {acara} menggantikan {old_r['nama_pengguna']}.", url_for('jadwal', view='private'))
                    else:
                        conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna, jenis, kategori_misa, scan_before, scan_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                                     (jadwal_dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%d'), months_id[dt.month], hari, wkt, acara, status, username, nama_pengguna, old_jn, kategori, sb, sa))
                
                for u_key, leftover in existing_map.items():
                    for r in leftover: 
                        if r['pengguna']:
                            create_notification(conn, r['pengguna'], f"Jadwal Anda untuk Misa {old_ac} telah dibatalkan/dihapus oleh pengurus.", url_for('jadwal', view='private'))
                        conn.execute("DELETE FROM jadwal WHERE id=?", (r['id'],))
                        
                conn.commit()
                flash("Jadwal berhasil diperbarui! Notifikasi otomatis terkirim ke anggota yang diganti.", "success")
            return redirect(url_for('penjadwalan'))
        
        elif action == 'buat_matriks':
            start_str, end_str = request.form.get('start_date'), request.form.get('end_date')
            if not start_str or not end_str: return redirect(url_for('penjadwalan'))
            start_time, end_time = f"{start_str} 00:00:00", f"{end_str} 23:59:59"
            existing_rows = conn.execute('SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND jadwal_datetime <= ? AND jenis="Matriks" ORDER BY id ASC', (start_time, end_time)).fetchall()
            existing_wkt, existing_data, acara_data = {}, {}, {}
            for r in existing_rows:
                dt = datetime.strptime(r['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
                d_str = dt.strftime('%Y-%m-%d')
                wkt = r['waktu']
                if d_str not in existing_wkt: existing_wkt[d_str] = []
                if wkt not in existing_wkt[d_str]: existing_wkt[d_str].append(wkt)
                if r['acara'] not in ['Misa Pagi', 'Misa Siang', 'Misa Sore', 'Misa Vigili', 'Misa']:
                    ket = r['acara'].replace('Misa ', '', 1) if r['acara'].startswith('Misa ') else r['acara']
                    acara_data[d_str] = ket
                if r['nama_pengguna'] != '':
                    wkt_key = f"{d_str}|{wkt}"
                    if wkt_key not in existing_data: existing_data[wkt_key] = []
                    existing_data[wkt_key].append(r['nama_pengguna'])
            for d in existing_wkt: existing_wkt[d] = sorted(existing_wkt[d])
            start_dt, end_dt = datetime.strptime(start_str, '%Y-%m-%d'), datetime.strptime(end_str, '%Y-%m-%d')
            days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
            matrix_data = []
            curr = start_dt
            while curr <= end_dt:
                hari_idx = curr.weekday()
                d_str = curr.strftime('%Y-%m-%d')
                if d_str in existing_wkt and existing_wkt[d_str]: wkt_list = existing_wkt[d_str]
                else:
                    if hari_idx == 5: wkt_list = ['05.30', '17.00']
                    elif hari_idx == 6: wkt_list = ['06.00', '08.00', '10.00', '17.00']
                    else: wkt_list = ['05.30', '18.00']
                matrix_data.append({'date_str': d_str, 'hari': days_id[hari_idx], 'tanggal_format': f"{days_id[hari_idx].upper()}, {curr.day} {curr.strftime('%b %Y').upper()}", 'wkt_list': wkt_list})
                curr += timedelta(days=1)
            conn.close()
            return render_template('penjadwalan.html', matrix=matrix_data, users=users_db, user_names=user_names, start=start_str, end=end_str, existing_data=existing_data, acara_data=acara_data)

        elif action == 'simpan_matriks':
            months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
            parsed_data = []
            rendered_dates_raw = request.form.get('rendered_dates')
            if rendered_dates_raw:
                s_str, e_str = rendered_dates_raw.split('|')
                s_dt, e_dt = datetime.strptime(s_str, '%Y-%m-%d'), datetime.strptime(e_str, '%Y-%m-%d')
                all_dates = []
                c = s_dt
                while c <= e_dt:
                    all_dates.append(c.strftime('%Y-%m-%d'))
                    c += timedelta(days=1)
                placeholders = ','.join('?' for _ in all_dates)
                conn.execute(f"DELETE FROM jadwal WHERE status='Draft' AND jenis='Matriks' AND date(jadwal_datetime) IN ({placeholders})", all_dates)
            
            for key in request.form.keys():
                if key.startswith('ptgs|'):
                    parts = key.split('|')
                    tgl_str, wkt_idx, hari = parts[1], parts[2], parts[3]
                    wkt = request.form.get(f"wkt|{tgl_str}|{wkt_idx}", "00.00").strip()
                    kat = request.form.get(f"kat|{tgl_str}|{wkt_idx}", "Harian").strip()
                    acara_tambahan = request.form.get(f"ket|{tgl_str}", "").strip()
                    acara_final = f"Misa {acara_tambahan}" if acara_tambahan else "Misa"
                    acara_final = acara_final.replace('(', '').replace(')', '')
                    dt = datetime.strptime(tgl_str, '%Y-%m-%d')
                    try: jadwal_dt = datetime.strptime(f"{tgl_str} {wkt.replace('.', ':')}:00", '%Y-%m-%d %H:%M:%S')
                    except: jadwal_dt = dt
                    values = request.form.getlist(key)
                    has_entry = False
                    unique_names_in_shift = set()
                    for val in values:
                        if val and val.strip():
                            names = [n.strip() for n in val.split(',') if n.strip()]
                            for n in names:
                                n_lower = n.lower()
                                if n_lower not in unique_names_in_shift:
                                    unique_names_in_shift.add(n_lower)
                                    parsed_data.append({'jadwal_dt': jadwal_dt, 'dt': dt, 'hari': hari, 'wkt': wkt, 'acara': acara_final, 'kat': kat, 'nama': n})
                                    has_entry = True
                    if not has_entry: parsed_data.append({'jadwal_dt': jadwal_dt, 'dt': dt, 'hari': hari, 'wkt': wkt, 'acara': acara_final, 'kat': kat, 'nama': ''})
            
            for p in parsed_data:
                username, nama_pengguna = '', ''
                if p['nama'] != '':
                    user_db = conn.execute("SELECT username, nama FROM users WHERE nama LIKE ? OR nama_panggilan LIKE ? OR username = ?", (f"%{p['nama']}%", f"%{p['nama']}%", p['nama'])).fetchone()
                    username = user_db['username'] if user_db else p['nama']
                    nama_pengguna = user_db['nama'] if user_db else p['nama']
                conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna, jenis, kategori_misa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "Matriks", ?)', 
                             (p['jadwal_dt'].strftime('%Y-%m-%d %H:%M:%S'), p['dt'].strftime('%d'), months_id[p['dt'].month], p['hari'], p['wkt'], p['acara'], 'Draft', username, nama_pengguna, p['kat']))
            conn.commit(); conn.close()
            return redirect(url_for('cetak_jadwal', target_start=s_str, target_end=e_str))

        elif action == 'tambah_khusus':
            tgl_str = request.form.get('tanggal')
            wkt_raw = request.form.get('waktu') 
            acara = request.form.get('acara')
            kategori = request.form.get('kategori', 'Besar')
            petugas_list = request.form.getlist('petugas')
            status = request.form.get('status', 'Bertugas')
            
            if tgl_str and wkt_raw and acara:
                wkt = wkt_raw.replace(':', '.')
                dt = datetime.strptime(tgl_str, '%Y-%m-%d')
                try: jadwal_dt = datetime.strptime(f"{tgl_str} {wkt_raw}:00", '%Y-%m-%d %H:%M:%S')
                except: jadwal_dt = dt
                months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
                days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
                hari = days_id[dt.weekday()]
                
                petugas_list = [p for p in petugas_list if p]
                unique_petugas = []
                for p in petugas_list:
                    if p not in unique_petugas: unique_petugas.append(p)
                if not unique_petugas: unique_petugas = ['']
                    
                for p_id in unique_petugas:
                    username, nama_pengguna = '', ''
                    if p_id:
                        user_db = conn.execute("SELECT username, nama FROM users WHERE username = ?", (p_id,)).fetchone()
                        if user_db: username, nama_pengguna = user_db['username'], user_db['nama']
                        else: username, nama_pengguna = p_id, p_id
                    conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna, jenis, kategori_misa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "Khusus", ?)', 
                                 (jadwal_dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%d'), months_id[dt.month], hari, wkt, acara, status, username, nama_pengguna, kategori))
                conn.commit()
                flash("Jadwal khusus berhasil ditambahkan!", "success")
            return redirect(url_for('penjadwalan'))

        elif action == 'hapus_jadwal_bulk':
            hapus_items = request.form.getlist('hapus_items')
            if hapus_items:
                for item in hapus_items:
                    parts = item.split('|')
                    if len(parts) == 3:
                        dt_val, acara_val, jenis_val = parts
                        conn.execute("DELETE FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND jenis = ?", (dt_val, acara_val, jenis_val))
                conn.commit()
                flash(f"{len(hapus_items)} Jadwal berhasil dihapus secara permanen!", "success")
            return redirect(url_for('penjadwalan'))

    settings_data = dict(conn.execute('SELECT key, value FROM settings').fetchall())
    global_before = int(settings_data.get('scan_window_before', 60))
    global_after = int(settings_data.get('scan_window_after', 180))

    history_rows = conn.execute('''
        SELECT jadwal_datetime, hari, waktu, acara, status, jenis, MAX(scan_before) as scan_before, MAX(scan_after) as scan_after, MAX(kategori_misa) as kategori_misa,
        GROUP_CONCAT(NULLIF(nama_pengguna, ''), ', ') as petugas, GROUP_CONCAT(NULLIF(pengguna, ''), ',') as pengguna_list
        FROM jadwal 
        GROUP BY jadwal_datetime, acara, status, jenis
        ORDER BY jadwal_datetime DESC 
        LIMIT 100
    ''').fetchall()
    
    history = []
    for r in history_rows:
        d = dict(r)
        try:
            dt_obj = datetime.strptime(d['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
            d['waktu_format'] = f"{dt_obj.strftime('%d %b %Y')} - {d['waktu']}"
            d['tanggal_raw'] = dt_obj.strftime('%Y-%m-%d')
            d['waktu_raw'] = dt_obj.strftime('%H:%M')
        except: 
            d['waktu_format'] = d['jadwal_datetime']
            d['tanggal_raw'] = ''
            d['waktu_raw'] = ''
        history.append(d)

    conn.close()
    return render_template('penjadwalan.html', users=users_db, user_names=user_names, history=history, global_before=global_before, global_after=global_after, settings=settings_data)

@app.route('/cetak-jadwal')
@login_required
def cetak_jadwal():
    if session.get('role') not in ['super admin', 'penjadwalan']: return redirect(url_for('index'))
    target_start, target_end = request.args.get('target_start'), request.args.get('target_end')
    conn = get_db_connection()
    if target_start and target_end:
        start_time, end_time = f"{target_start} 00:00:00", f"{target_end} 23:59:59"
        rows_draft = conn.execute("SELECT * FROM jadwal WHERE status='Draft' AND jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC", (start_time, end_time)).fetchall()
        if rows_draft: rows = rows_draft
        else: rows = conn.execute("SELECT * FROM jadwal WHERE status='Bertugas' AND jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC", (start_time, end_time)).fetchall()
    else:
        threshold_time = datetime.now().strftime('%Y-%m-%d 00:00:00')
        end_limit = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d 23:59:59')
        rows = conn.execute('SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC', (threshold_time, end_limit)).fetchall()
    conn.close()

    valid_dts = [datetime.strptime(r['jadwal_datetime'], '%Y-%m-%d %H:%M:%S') for r in rows if r['nama_pengguna'] != '']
    if not valid_dts and rows: valid_dts = [datetime.strptime(rows[0]['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')]
    if valid_dts: min_date, max_date = min(valid_dts), max(valid_dts)
    else: min_date, max_date = datetime.now(), datetime.now()
    s_str = target_start if target_start else min_date.strftime('%Y-%m-%d')
    e_str = target_end if target_end else max_date.strftime('%Y-%m-%d')
    if not rows: return render_template('cetak_jadwal.html', weeks=[], s_str=s_str, e_str=e_str, periode="-")

    months_id = {1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'}
    periode_str = f"{min_date.day} {months_id[min_date.month]} {min_date.year} - {max_date.day} {months_id[max_date.month]} {max_date.year}"

    jadwal_dict = {}
    for r in rows:
        dt = datetime.strptime(r['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
        date_key = dt.strftime('%Y-%m-%d')
        if date_key not in jadwal_dict:
            judul_teks = f"{r['hari'].upper()}, {dt.day} {r['bulan'].upper()} {dt.year}"
            if r['acara'] not in ['Misa Pagi', 'Misa Siang', 'Misa Sore', 'Misa Vigili', 'Misa']:
                keterangan = r['acara'].replace('Misa ', '', 1) if r['acara'].startswith('Misa ') else r['acara']
                judul_teks = f"{judul_teks} ({keterangan})"
            jadwal_dict[date_key] = {'hari': r['hari'], 'tanggal_teks': judul_teks, 'misa': {}, 'has_petugas': False}
        wkt = r['waktu']
        if wkt not in jadwal_dict[date_key]['misa']: jadwal_dict[date_key]['misa'][wkt] = []
        if r['nama_pengguna'] != '':
            jadwal_dict[date_key]['misa'][wkt].append({'nama': r['nama_pengguna'], 'username': r['pengguna'], 'jadwal_id': r['id']})
            jadwal_dict[date_key]['has_petugas'] = True

    for d_key in jadwal_dict: jadwal_dict[d_key]['misa'] = dict(sorted(jadwal_dict[d_key]['misa'].items()))
    weeks = []
    current_week = {'senin_kamis': [], 'jumat_minggu': []}
    sorted_dates = sorted(jadwal_dict.keys())
    for d in sorted_dates:
        if not jadwal_dict[d]['has_petugas']: continue
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
        max_sk = 0
        for day in w['senin_kamis']:
            for wkt, ptgs in day['misa'].items():
                if len(ptgs) > max_sk: max_sk = len(ptgs)
        w['max_slots_sk'] = max_sk
        max_jm = 0
        for day in w['jumat_minggu']:
            for wkt, ptgs in day['misa'].items():
                if len(ptgs) > max_jm: max_jm = len(ptgs)
        w['max_slots_jm'] = max_jm
        for day in w['senin_kamis']:
            for wkt, ptgs in day['misa'].items():
                while len(ptgs) < max_sk: ptgs.append("")
        for day in w['jumat_minggu']:
            for wkt, ptgs in day['misa'].items():
                while len(ptgs) < max_jm: ptgs.append("")
        final_weeks.append(w)
    return render_template('cetak_jadwal.html', weeks=final_weeks, s_str=s_str, e_str=e_str, periode=periode_str)

@app.route('/publikasi-jadwal', methods=['POST'])
@login_required
def publikasi_jadwal():
    if session.get('role') not in ['super admin', 'penjadwalan']: return redirect(url_for('index'))
    target_start = request.form.get('target_start')
    target_end = request.form.get('target_end')
    conn = get_db_connection()
    if target_start and target_end:
        start_time, end_time = f"{target_start} 00:00:00", f"{target_end} 23:59:59"
        conn.execute("DELETE FROM jadwal WHERE status='Bertugas' AND jenis='Matriks' AND jadwal_datetime >= ? AND jadwal_datetime <= ?", (start_time, end_time))
        conn.execute("UPDATE jadwal SET status='Bertugas' WHERE status='Draft' AND jadwal_datetime >= ? AND jadwal_datetime <= ?", (start_time, end_time))
        conn.execute("DELETE FROM jadwal WHERE status='Draft' AND jadwal_datetime >= ? AND jadwal_datetime <= ?", (start_time, end_time))
    else:
        conn.execute("UPDATE jadwal SET status='Bertugas' WHERE status='Draft'") 
    conn.commit()
    conn.close()
    flash("Jadwal Pelayanan berhasil dipublikasikan!", "success")
    return redirect(url_for('jadwal'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)