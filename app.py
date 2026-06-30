import os
import json
import random
import string
import sqlite3
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# PENGAMANAN: Jika library pywebpush belum diinstal, aplikasi tidak akan crash
try:
    from pywebpush import webpush, WebPushException
    WEBPUSH_AVAILABLE = True
except ImportError:
    WEBPUSH_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'misdinar-secure-key-2026-production'
app.permanent_session_lifetime = timedelta(days=7)

# KUNCI VAPID UNTUK NOTIFIKASI HP
# PENTING: kunci ini HARUS unik untuk aplikasi ini, jangan dipakai bersama project lain.
# Kunci lama yang sebelumnya ada di sini adalah contoh demo yang beredar luas di banyak
# tutorial Web Push di internet, sehingga private key-nya bukan benar-benar rahasia.
# Sebaiknya disimpan sebagai environment variable di server produksi, bukan hardcode.
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "BCYTS0Pb7vTMSjK0ZYuco8ckOr7qs5OM48BMxQhRDBnjd2pgp0kr0iB7jY-Rv6ni327hRsCIR7snYqqol3_JTU0")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "_RiB0dDlSUzb77dcK0fBLQ4dFCvmLjOK4Q6_Hm6I6oM")
VAPID_CLAIMS = {"sub": "mailto:admin@misdinar.com"}

DB_NAME = 'misdinar.db'
UPLOAD_DOKUMEN = 'static/uploads/dokumen'
UPLOAD_GALERI = 'static/uploads/galeri'
UPLOAD_PROFIL = 'static/uploads/profil'
UPLOAD_FORM = 'static/uploads/form_files'

for folder in [UPLOAD_DOKUMEN, UPLOAD_GALERI, UPLOAD_PROFIL, UPLOAD_FORM]:
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
        'alamat': 'TEXT', 'foto_profil': 'TEXT', 'push_sub': 'TEXT'
    }
    existing_columns = [col[1] for col in conn.execute('PRAGMA table_info(users)').fetchall()]
    for col_name, col_type in new_user_columns.items():
        if col_name not in existing_columns:
            conn.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')

    conn.execute('''CREATE TABLE IF NOT EXISTS pengumuman (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, deskripsi TEXT DEFAULT "", tanggal_pelaksanaan TEXT DEFAULT "-", waktu_pelaksanaan TEXT NOT NULL, tempat TEXT DEFAULT "-", tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL, editor_terakhir TEXT, waktu_edit TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS dokumen (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, deskripsi TEXT DEFAULT "", file_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL, editor_terakhir TEXT, waktu_edit TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS galeri (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, deskripsi TEXT DEFAULT "", foto_path TEXT NOT NULL, tanggal_dibuat TEXT NOT NULL, target TEXT NOT NULL, pembuat TEXT NOT NULL, editor_terakhir TEXT, waktu_edit TEXT)''')
    
    for table in ['pengumuman', 'dokumen', 'galeri']:
        cols = [col[1] for col in conn.execute(f'PRAGMA table_info({table})').fetchall()]
        if 'editor_terakhir' not in cols: conn.execute(f'ALTER TABLE {table} ADD COLUMN editor_terakhir TEXT')
        if 'waktu_edit' not in cols: conn.execute(f'ALTER TABLE {table} ADD COLUMN waktu_edit TEXT')
        if table in ['dokumen', 'galeri'] and 'deskripsi' not in cols: conn.execute(f'ALTER TABLE {table} ADD COLUMN deskripsi TEXT DEFAULT ""')

    pengumuman_cols = [col[1] for col in conn.execute('PRAGMA table_info(pengumuman)').fetchall()]
    if 'tempat' not in pengumuman_cols: conn.execute('ALTER TABLE pengumuman ADD COLUMN tempat TEXT DEFAULT "-"')
    if 'tanggal_pelaksanaan' not in pengumuman_cols: conn.execute('ALTER TABLE pengumuman ADD COLUMN tanggal_pelaksanaan TEXT DEFAULT "-"')

    conn.execute('''CREATE TABLE IF NOT EXISTS jadwal (id INTEGER PRIMARY KEY AUTOINCREMENT, jadwal_datetime TIMESTAMP NOT NULL, tanggal TEXT NOT NULL, bulan TEXT NOT NULL, hari TEXT NOT NULL, waktu TEXT NOT NULL, acara TEXT NOT NULL, status TEXT NOT NULL, pengguna TEXT NOT NULL, nama_pengguna TEXT NOT NULL, jenis TEXT DEFAULT "Matriks", FOREIGN KEY(pengguna) REFERENCES users(username))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS kehadiran (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, kegiatan TEXT NOT NULL, status TEXT NOT NULL, keterangan TEXT, waktu_scan TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS hukuman (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, tanggal TEXT NOT NULL, pelanggaran TEXT NOT NULL, tindakan TEXT NOT NULL, status TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS notifikasi (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, pesan TEXT NOT NULL, waktu TEXT NOT NULL, status_baca INTEGER DEFAULT 0, link TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS izin_jadwal (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, nama TEXT NOT NULL, jadwal_id INTEGER NOT NULL, tanggal_misa TEXT NOT NULL, acara TEXT NOT NULL, alasan TEXT NOT NULL, pengganti TEXT DEFAULT "-", status TEXT DEFAULT "Menunggu", waktu_pengajuan TEXT NOT NULL, tanggapan_admin TEXT DEFAULT "-", jenis_izin TEXT DEFAULT "Jadwal")''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS buka_titip (id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, waktu TEXT NOT NULL, acara TEXT NOT NULL, kuota INTEGER DEFAULT 1, pembuat TEXT NOT NULL, waktu_dibuat TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS periode_titip (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, tanggal_mulai TEXT NOT NULL, tanggal_selesai TEXT NOT NULL, status TEXT DEFAULT 'Buka', pembuat TEXT, waktu_dibuat TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS request_titip (id INTEGER PRIMARY KEY AUTOINCREMENT, periode_id INTEGER, username TEXT, nama TEXT, tanggal TEXT, waktu TEXT, keterangan TEXT, waktu_submit TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS pengingat_terkirim (jadwal_id INTEGER, username TEXT, PRIMARY KEY(jadwal_id, username))''')

    conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
    
    default_settings = {
        'scan_window_before': '60',
        'scan_window_after': '180',
        'sanksi_alpa_harian': '5',
        'sanksi_alpa_mingguan': '10',
        'sanksi_alpa_besar': '20',
        'fitur_scan_window': 'on',
        'fitur_sanksi': 'on',
        'fitur_pengingat': 'on',
        'pengingat_waktu': '1440'
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

    if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        hashed_pw = generate_password_hash('super123')
        conn.execute('INSERT INTO users (username, password, nama, role, no_hp, nama_panggilan) VALUES (?, ?, ?, ?, ?, ?)', ('superadmin', hashed_pw, 'Super Admin', 'super admin', '081234567890', 'Admin'))
    
    conn.execute('''CREATE TABLE IF NOT EXISTS formulir (id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, deskripsi TEXT, schema_data TEXT NOT NULL, is_active INTEGER DEFAULT 1, is_default INTEGER DEFAULT 0, target TEXT DEFAULT 'semua')''')
    
    formulir_cols = [col[1] for col in conn.execute('PRAGMA table_info(formulir)').fetchall()]
    if 'target' not in formulir_cols:
        conn.execute('ALTER TABLE formulir ADD COLUMN target TEXT DEFAULT "semua"')

    conn.execute('''CREATE TABLE IF NOT EXISTS pendaftaran (id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, data_respon TEXT NOT NULL, status TEXT DEFAULT 'Menunggu', form_id INTEGER DEFAULT 1)''')
    
    pendaftaran_cols = [col[1] for col in conn.execute('PRAGMA table_info(pendaftaran)').fetchall()]
    if 'form_id' not in pendaftaran_cols:
        conn.execute('ALTER TABLE pendaftaran ADD COLUMN form_id INTEGER DEFAULT 1')

    if conn.execute('SELECT COUNT(*) FROM formulir').fetchone()[0] == 0:
        default_schema = json.dumps({
            "title": "Pendaftaran Calon Misdinar Baru", 
            "description": "Isi formulir ini dengan data yang benar. Setelah submit, Anda akan otomatis mendapatkan Username dan Password untuk login ke Dashboard.", 
            "titleAlignment": "Left Aligned",
            "descAlignment": "Left Aligned",
            "language": "English",
            "labelPlacement": "Top Aligned",
            "questions": [
                {"id": 1, "type": "name", "question": "Nama Lengkap", "options": [], "required": True, "size": "Large"},
                {"id": 2, "type": "short", "question": "Nomor WhatsApp (Aktif)", "options": [], "required": True, "size": "Medium"},
                {"id": 3, "type": "paragraph", "question": "Alasan ingin bergabung menjadi Misdinar?", "options": [], "required": True, "size": "Large"}
            ]
        })
        conn.execute("INSERT INTO formulir (id, judul, deskripsi, schema_data, is_active, is_default, target) VALUES (1, ?, ?, ?, 1, 1, 'semua')", 
                     ("Pendaftaran Calon Misdinar Baru", "Formulir pendaftaran anggota baru otomatis.", default_schema))

    conn.commit()
    conn.close()

init_db()

@app.route('/manifest.json')
def manifest():
    data = {
        "name": "MISDINAR App",
        "short_name": "Misdinar",
        "description": "Sistem Pelayanan Misdinar",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f8fafc",
        "theme_color": "#1e40af",
        "icons": [
            {"src": "https://cdn-icons-png.flaticon.com/192/3075/3075908.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "https://cdn-icons-png.flaticon.com/512/3075/3075908.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    }
    response = make_response(json.dumps(data))
    response.headers['Content-Type'] = 'application/json'
    return response

@app.route('/sw.js')
def service_worker():
    js = """
    self.addEventListener('install', function(e) { self.skipWaiting(); });
    self.addEventListener('activate', function(e) { e.waitUntil(clients.claim()); });
    self.addEventListener('fetch', function(e) { 
        e.respondWith(fetch(e.request).catch(() => caches.match(e.request))); 
    });
    
    self.addEventListener('push', function(event) {
        let title = "PENGINGAT TUGAS MISDINAR";
        let body = "Ada jadwal tugas Misa mendekati waktu dimulai!";
        let url = "/jadwal?view=private";
        
        if (event.data) {
            try {
                // Cek apakah data merupakan valid JSON string
                const data = event.data.json();
                title = data.title || title;
                body = data.body || body;
                url = data.url || url;
            } catch(e) {
                // Jika data dikirim dalam bentuk teks mentah oleh browser fallback kesini
                const txt = event.data.text();
                if (txt) {
                    try {
                        const dataParsed = JSON.parse(txt);
                        title = dataParsed.title || title;
                        body = dataParsed.body || body;
                        url = dataParsed.url || url;
                    } catch(err) {
                        body = txt;
                    }
                }
            }
        }
        
        const options = {
            body: body,
            icon: 'https://cdn-icons-png.flaticon.com/192/3075/3075908.png',
            badge: 'https://cdn-icons-png.flaticon.com/192/3075/3075908.png',
            vibrate: [200, 100, 200],
            requireInteraction: true, // Memaksa spanduk OS melayang di Windows/HP
            silent: false,
            data: { url: url }
        };
        
        event.waitUntil(self.registration.showNotification(title, options));
    });
    
    self.addEventListener('notificationclick', function(event) {
        event.notification.close();
        let targetUrl = '/jadwal?view=private';
        if(event.notification.data && event.notification.data.url) {
            targetUrl = event.notification.data.url;
        }
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
                for (let i = 0; i < clientList.length; i++) {
                    let client = clientList[i];
                    if (client.url.indexOf(targetUrl) !== -1 && 'focus' in client) {
                        return client.focus();
                    }
                }
                if (clients.openWindow) {
                    return clients.openWindow(targetUrl);
                }
            })
        );
    });
    """
    response = make_response(js)
    response.headers['Content-Type'] = 'application/javascript'
    return response

def send_web_push(subscription_info, message_body, username=None):
    if not WEBPUSH_AVAILABLE:
        print("WEBPUSH SKIPPED: library pywebpush belum terpasang. Jalankan: pip install pywebpush")
        return
    try:
        vapid_claims = {"sub": "mailto:admin@misdinar.com"}

        # Pastikan message_body selalu diubah ke format JSON string yang bersih
        webpush(
            subscription_info=json.loads(subscription_info),
            data=json.dumps(message_body),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=vapid_claims,
            ttl=86400,
            headers={"Topic": "misdinar-notif", "Urgency": "high"}
        )
        print("Sinyal push notification berhasil ditembakkan ke browser!")
    except WebPushException as ex:
        status_code = getattr(ex.response, 'status_code', None)
        print("Web Push SERVER ERROR:", repr(ex), "| status_code:", status_code)
        # 404/410 = subscription sudah tidak valid lagi (browser uninstall/clear data/token expired).
        # Kalau tidak dibersihkan, server akan terus mencoba kirim ke token mati ini selamanya.
        if status_code in (404, 410) and username:
            try:
                conn2 = get_db_connection()
                conn2.execute("UPDATE users SET push_sub=NULL WHERE username=?", (username,))
                conn2.commit()
                conn2.close()
                print(f"Subscription push milik '{username}' sudah kadaluarsa, dihapus dari DB.")
            except Exception as cleanup_err:
                print("Gagal membersihkan subscription kadaluarsa:", repr(cleanup_err))
    except Exception as ex:
        print("Web Push SERVER ERROR:", repr(ex))

def create_notification(conn, target_str, pesan, link_url):
    waktu_sekarang = datetime.now().strftime('%d %b %Y, %H:%M')
    target_list = [t.strip() for t in target_str.split(',')]
    
    # Standarisasi payload objek agar terbaca oleh sw.js di semua OS
    push_payload = {
        "title": "PENGINGAT TUGAS MISDINAR", 
        "body": pesan, 
        "url": link_url
    }
    
    if 'semua' in target_list:
        users = conn.execute("SELECT username, push_sub FROM users").fetchall()
        for u in users: 
            conn.execute('INSERT INTO notifikasi (username, pesan, waktu, link) VALUES (?, ?, ?, ?)', (u['username'], pesan, waktu_sekarang, link_url))
            if u['push_sub']: send_web_push(u['push_sub'], push_payload, u['username'])
    else:
        users = conn.execute("SELECT username, role, push_sub FROM users").fetchall()
        for u in users:
            if u['username'] in target_list or u['role'] in target_list:
                conn.execute('INSERT INTO notifikasi (username, pesan, waktu, link) VALUES (?, ?, ?, ?)', (u['username'], pesan, waktu_sekarang, link_url))
                if u['push_sub']: send_web_push(u['push_sub'], push_payload, u['username'])

@app.route('/subscribe-push', methods=['POST'])
def subscribe_push():
    if 'user_id' not in session: return json.dumps({"success": False})
    subscription_info = request.json
    if subscription_info:
        conn = get_db_connection()
        conn.execute("UPDATE users SET push_sub=? WHERE username=?", (json.dumps(subscription_info), session['user_id']))
        conn.commit()
        conn.close()
        return json.dumps({"success": True})
    return json.dumps({"success": False})

@app.route('/vapid-public-key')
def vapid_public_key():
    return VAPID_PUBLIC_KEY

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
        if j_dict['nama_pengguna'].replace('.', '').replace('-', '').strip() == '':
            continue
            
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
                        pelanggaran = f"Tidak Hadir Bertugas ({kategori})"
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
def process_pengingat_jadwal(conn):
    settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    if settings.get('fitur_pengingat', 'on') != 'on': return
    
    waktu_str = settings.get('pengingat_waktu', '1440')
    if not waktu_str: return
        
    waktu_list = [int(w.strip()) for w in waktu_str.split(',') if w.strip().isdigit()]
    if not waktu_list: return

    conn.execute('''CREATE TABLE IF NOT EXISTS log_pengingat (jadwal_id INTEGER, username TEXT, menit TEXT)''')
    
    now = datetime.now()
    # Deteksi hari ini untuk menyaring query SQLite agar ringan
    hari_ini_str = now.strftime('%Y-%m-%d')
    besok_str = (now + timedelta(days=2)).strftime('%Y-%m-%d')

    # Ambil jadwal dalam rentang hari ini s/d besok yang statusnya Bertugas
    query = '''
        SELECT id, jadwal_datetime, acara, waktu, pengguna 
        FROM jadwal 
        WHERE status = 'Bertugas' 
          AND pengguna != '' 
          AND (substr(jadwal_datetime, 1, 10) >= ? AND substr(jadwal_datetime, 1, 10) <= ?)
    '''
    jadwal_mendekati = conn.execute(query, (hari_ini_str, besok_str)).fetchall()
    
    for j in jadwal_mendekati:
        try:
            dt_obj = datetime.strptime(j['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')
        except:
            continue
            
        # Hitung selisih waktu riil antara jam misa dengan waktu saat ini dalam menit
        selisih_menit = int((dt_obj - now).total_seconds() / 60)
        
        for menit_sebelum in waktu_list:
            # Jika waktu misa sudah dekat (selisih menit berada di bawah target pengingat pengurus)
            if 0 < selisih_menit <= menit_sebelum:
                # Cek apakah pengingat untuk menit ini sudah pernah dikirim
                exist = conn.execute(
                    "SELECT 1 FROM log_pengingat WHERE jadwal_id=? AND username=? AND menit=?", 
                    (j['id'], j['pengguna'], str(menit_sebelum))
                ).fetchone()
                
                if not exist:
                    if menit_sebelum >= 1440 and menit_sebelum % 1440 == 0:
                        waktu_teks = f"{menit_sebelum // 1440} Hari"
                    elif menit_sebelum >= 60 and menit_sebelum % 60 == 0:
                        waktu_teks = f"{menit_sebelum // 60} Jam"
                    else:
                        waktu_teks = f"{menit_sebelum} Menit"
                        
                    pesan = f"PENGINGAT: Misa {j['acara']} akan dimulai dalam {waktu_teks} lagi ({j['waktu']})."
                    
                    # Kirim ke Pusat Pemberitahuan
                    create_notification(conn, j['pengguna'], pesan, url_for('jadwal', view='private'))
                    # Catat log agar tidak terkirim berulang-ulang
                    conn.execute("INSERT INTO log_pengingat (jadwal_id, username, menit) VALUES (?, ?, ?)", (j['id'], j['pengguna'], str(menit_sebelum)))
    conn.commit()

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
                
                next_url = request.args.get('next')
                if next_url: return redirect(next_url)
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
    process_auto_absent(conn)
    process_pengingat_jadwal(conn)
    threshold_time = (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    quotes = ["Melayani dengan hati, bukan karena ingin dipuji.", "Kasih itu sabar; kasih itu murah hati.", "Lakukan segala pekerjaanmu dalam kasih."]
    quote = quotes[datetime.now().timetuple().tm_yday % len(quotes)]
    
    if user_id:
        rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND status = 'Bertugas' AND pengguna = ? ORDER BY jadwal_datetime ASC LIMIT 4", (threshold_time, user_id)).fetchall()
        user_jadwal = [dict(r) for r in rows if dict(r)['nama_pengguna'].replace('.', '').replace('-', '').strip() != '']
        conn.close()
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=user_jadwal, quote=quote, user_id=user_id, is_logged_in=True)
    else:
        rows = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND status = 'Bertugas' AND nama_pengguna != '' ORDER BY jadwal_datetime ASC LIMIT 8", (threshold_time,)).fetchall()
        valid_jadwal = [dict(r) for r in rows if dict(r)['nama_pengguna'].replace('.', '').replace('-', '').strip() != '']
        conn.close()
        return render_template('index.html', pengumuman=filtered_pengumuman, jadwal=valid_jadwal, quote=quote, is_logged_in=False)

@app.route('/jadwal', methods=['GET', 'POST'])
def jadwal():
    conn = get_db_connection()
    process_auto_absent(conn)
    process_pengingat_jadwal(conn)
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
                    if j['nama_pengguna'].replace('.', '').replace('-', '').strip() == '':
                        continue
                        
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
                if j['nama_pengguna'].replace('.', '').replace('-', '').strip() == '':
                    continue
                    
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
            if j['nama_pengguna'].replace('.', '').replace('-', '').strip() == '':
                continue
                
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
        
        if action == 'buka_periode' and user_role in ['super admin', 'penjadwalan', 'bph']:
            judul = request.form.get('judul')
            tgl_mulai = request.form.get('tanggal_mulai')
            tgl_selesai = request.form.get('tanggal_selesai')
            conn.execute("UPDATE periode_titip SET status='Tutup'")
            conn.execute("INSERT INTO periode_titip (judul, tanggal_mulai, tanggal_selesai, status, pembuat, waktu_dibuat) VALUES (?, ?, ?, 'Buka', ?, ?)", 
                         (judul, tgl_mulai, tgl_selesai, user_id, now_str))
            create_notification(conn, 'semua', f"Periode Titip Ketersediaan Jadwal '{judul}' telah dibuka. Silakan isi form jika ada request jadwal.", url_for('titip'))
            conn.commit()
            flash("Periode Pengisian Jadwal berhasil dibuka!", "success")
            
        elif action == 'tutup_periode' and user_role in ['super admin', 'penjadwalan', 'bph']:
            conn.execute("UPDATE periode_titip SET status='Tutup' WHERE status='Buka'")
            conn.commit()
            flash("Periode Pengisian Jadwal berhasil ditutup.", "success")
            
        elif action == 'ajukan_titip':
            periode_id = request.form.get('periode_id')
            tanggal = request.form.get('tanggal')
            waktu = request.form.get('waktu')
            keterangan = request.form.get('keterangan', '')
            exist = conn.execute("SELECT 1 FROM request_titip WHERE periode_id=? AND username=? AND tanggal=?", (periode_id, user_id, tanggal)).fetchone()
            if exist:
                flash(f"Anda sudah membuat pengajuan untuk tanggal {tanggal}.", "error")
            else:
                conn.execute("INSERT INTO request_titip (periode_id, username, nama, tanggal, waktu, keterangan, waktu_submit) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                             (periode_id, user_id, session.get('nama_user'), tanggal, waktu, keterangan, now_str))
                conn.commit()
                flash("Ketersediaan jadwal Anda berhasil diajukan ke pengurus.", "success")
                
        elif action == 'hapus_pengajuan':
            req_id = request.form.get('req_id')
            conn.execute("DELETE FROM request_titip WHERE id=?", (req_id,))
            conn.commit()
            flash("Pengajuan jadwal dibatalkan.", "success")
            
        elif action == 'buka_slot' and user_role in ['super admin', 'penjadwalan', 'bph']:
            tgl = request.form.get('tanggal')
            wkt = request.form.get('waktu')
            acara = request.form.get('acara')
            kuota = int(request.form.get('kuota', 1))
            conn.execute("INSERT INTO buka_titip (tanggal, waktu, acara, kuota, pembuat, waktu_dibuat) VALUES (?, ?, ?, ?, ?, ?)",
                         (tgl, wkt, acara, kuota, user_id, now_str))
            create_notification(conn, 'semua', f"Slot Misa Khusus baru dibuka untuk {acara} tgl {tgl}! Cepat ambil sebelum penuh.", url_for('titip'))
            conn.commit()
            flash("Slot Misa Khusus berhasil dibuka dan diumumkan!", "success")
            
        elif action == 'hapus_slot' and user_role in ['super admin', 'penjadwalan', 'bph']:
            conn.execute("DELETE FROM buka_titip WHERE id=?", (request.form.get('id'),))
            conn.commit()
            flash("Slot Misa Khusus telah ditutup/dihapus.", "success")
            
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
                        flash("Selamat! Anda berhasil mengamankan slot Misa Khusus.", "success")
                    else:
                        flash("Anda sudah terdaftar di jadwal tersebut.", "error")
                else:
                    flash("Maaf, slot sudah penuh! Anda kalah cepat.", "error")
        return redirect(url_for('titip'))

    periode_aktif = conn.execute("SELECT * FROM periode_titip WHERE status='Buka' ORDER BY id DESC LIMIT 1").fetchone()
    pengajuan_list = []
    
    if periode_aktif:
        if user_role in ['super admin', 'penjadwalan', 'bph']:
            reqs = conn.execute("SELECT * FROM request_titip WHERE periode_id=? ORDER BY tanggal ASC, waktu ASC", (periode_aktif['id'],)).fetchall()
        else:
            reqs = conn.execute("SELECT * FROM request_titip WHERE periode_id=? AND username=? ORDER BY tanggal ASC, waktu ASC", (periode_aktif['id'], user_id)).fetchall()
        pengajuan_list = [dict(r) for r in reqs]
        
    slots = conn.execute("SELECT * FROM buka_titip ORDER BY tanggal DESC, waktu DESC LIMIT 50").fetchall()
    rebutan_slots = []
    for s in slots:
        d = dict(s)
        dt_str = f"{d['tanggal']} {d['waktu']}:00"
        terisi = conn.execute("SELECT pengguna, nama_pengguna FROM jadwal WHERE jadwal_datetime=? AND acara=? AND jenis='Titip'", (dt_str, d['acara'])).fetchall()
        d['terisi'] = len(terisi)
        d['sisa'] = d['kuota'] - len(terisi)
        d['peserta'] = [p['nama_pengguna'] for p in terisi]
        d['sudah_join'] = user_id in [p['pengguna'] for p in terisi]
        d['is_past'] = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S') < datetime.now()
        rebutan_slots.append(d)
        
    conn.close()
    return render_template('titip.html', role=user_role, periode=dict(periode_aktif) if periode_aktif else None, pengajuan=pengajuan_list, rebutan_slots=rebutan_slots)

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
            dt_val, data_ac = data.get('dt'), data.get('ac')
            if not dt_val or not data_ac: return json.dumps({'success': False, 'message': 'Data QR Acara tidak lengkap.'})
            user = conn.execute("SELECT nama FROM users WHERE username=?", (current_user,)).fetchone()
            
            assigned = conn.execute("SELECT * FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND pengguna = ?", (dt_val, data_ac, current_user)).fetchone()
            if not assigned:
                conn.close()
                return json.dumps({'success': False, 'message': 'Akses Ditolak: Anda TIDAK ditugaskan pada jadwal Misa ini!'})
            
            assigned_dict = dict(assigned)
            dt_obj = datetime.strptime(dt_val, '%Y-%m-%d %H:%M:%S')
            kegiatan = f"{data_ac} Pkl {dt_obj.strftime('%H.%M')}"
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
    process_pengingat_jadwal(conn)
    now_time = datetime.now()
    
    selected_month = request.args.get('bulan', now_time.strftime('%Y-%m'))
    
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
            
            if action == 'edit' and str(item_id).startswith('j_') and status_baru == 'Tidak Hadir':
                jadwal_id = item_id.split('_')[1]
                j = conn.execute("SELECT * FROM jadwal WHERE id=?", (jadwal_id,)).fetchone()
                if j:
                    j_dict = dict(j)
                    kategori = j_dict.get('kategori_misa') or 'Harian'
                    settings = dict(conn.execute("SELECT key, value FROM settings").fetchall())
                    weight = int(settings.get(f'sanksi_alpa_{kategori.lower()}', 0))
                    fitur_sanksi = settings.get('fitur_sanksi', 'on')
                    
                    if weight > 0 and fitur_sanksi == 'on':
                        pelanggaran = f"Tidak Hadir Bertugas ({kategori})"
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
                
        conn.commit()
        return redirect(url_for('kehadiran', bulan=selected_month))

    users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else []
    
    if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        jadwals_raw = conn.execute("SELECT * FROM jadwal WHERE status='Bertugas' AND nama_pengguna != '' AND jadwal_datetime LIKE ?", (f"{selected_month}%",)).fetchall()
        jadwals = [j for j in jadwals_raw if dict(j)['nama_pengguna'].replace('.', '').replace('-', '').strip() != '']
        kehadirans = conn.execute("SELECT * FROM kehadiran WHERE tanggal LIKE ?", (f"{selected_month}%",)).fetchall()
        data_izin = conn.execute("SELECT * FROM izin_jadwal ORDER BY id DESC").fetchall()
    else:
        jadwals_raw = conn.execute("SELECT * FROM jadwal WHERE status='Bertugas' AND pengguna = ? AND jadwal_datetime LIKE ?", (user_id, f"{selected_month}%")).fetchall()
        jadwals = [j for j in jadwals_raw if dict(j)['nama_pengguna'].replace('.', '').replace('-', '').strip() != '']
        kehadirans = conn.execute("SELECT * FROM kehadiran WHERE username=? AND tanggal LIKE ?", (user_id, f"{selected_month}%")).fetchall()

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
    return render_template('kehadiran.html', kehadiran=combined, data_izin=data_izin, users=users_list, role=user_role, selected_month=selected_month)

@app.route('/hukuman', methods=['GET', 'POST'])
@login_required
def hukuman():
    user_id, user_role = session.get('user_id'), session.get('role')
    conn = get_db_connection()
    
    selected_month = request.args.get('bulan', datetime.now().strftime('%Y-%m'))
    
    if request.method == 'POST' and user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']:
        action = request.form.get('action')
        if action in ['tambah', 'edit']:
            target = conn.execute("SELECT nama FROM users WHERE username=?", (request.form.get('username'),)).fetchone()
            nama = target['nama'] if target else request.form.get('username')
            if action == 'tambah': conn.execute('INSERT INTO hukuman (username, nama, tanggal, pelanggaran, tindakan, status) VALUES (?, ?, ?, ?, ?, ?)', (request.form.get('username'), nama, request.form.get('tanggal'), request.form.get('pelanggaran'), request.form.get('tindakan'), request.form.get('status')))
            else: conn.execute('UPDATE hukuman SET username=?, nama=?, tanggal=?, pelanggaran=?, tindakan=?, status=? WHERE id=?', (request.form.get('username'), nama, request.form.get('tanggal'), request.form.get('pelanggaran'), request.form.get('tindakan'), request.form.get('status'), request.form.get('id')))
        elif action == 'hapus': conn.execute('DELETE FROM hukuman WHERE id=?', (request.form.get('id'),))
        elif action == 'selesai': conn.execute('UPDATE hukuman SET status="Selesai" WHERE id=?', (request.form.get('id'),))
        conn.commit()
        return redirect(url_for('hukuman', bulan=selected_month))

    users_list = conn.execute("SELECT username, nama FROM users WHERE role != 'super admin' ORDER BY nama ASC").fetchall() if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan'] else []
    
    if user_role in ['super admin', 'bph', 'penjadwalan', 'pelatihan']: 
        data_hukuman = conn.execute('SELECT * FROM hukuman WHERE tanggal LIKE ? ORDER BY id DESC', (f"{selected_month}%",)).fetchall()
    else: 
        data_hukuman = conn.execute('SELECT * FROM hukuman WHERE username=? AND tanggal LIKE ? ORDER BY id DESC', (user_id, f"{selected_month}%")).fetchall()
    
    tunggakan_dict = {}
    for h in data_hukuman:
        if h['status'] != 'Selesai' and 'Kali Berlutut' in h['tindakan']:
            try:
                amount = int(h['tindakan'].split()[0])
                tunggakan_dict[h['username']] = tunggakan_dict.get(h['username'], 0) + amount
            except: pass
            
    conn.close()
    return render_template('hukuman.html', hukuman=data_hukuman, users=users_list, role=user_role, tunggakan=tunggakan_dict, current_user=user_id, selected_month=selected_month)

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
            no_hp_ortu, input_alamat = request.form.get('no_hp_ortu'), request.form.get('alamat')
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
            params = [nama_lengkap, nama_panggilan, email, tanggal_lahir, no_hp, nama_ortu, no_hp_ortu, input_alamat]
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

@app.route('/formulir-saya')
@login_required
def formulir_saya():
    user_role = session.get('role')
    user_id = session.get('user_id')
    nama_user = session.get('nama_user', '')
    conn = get_db_connection()
    
    forms_raw = conn.execute("SELECT * FROM formulir WHERE is_default=0 ORDER BY id DESC").fetchall()
    
    available_forms = []
    for f in forms_raw:
        f_dict = dict(f)
        targets = [t.strip() for t in f_dict.get('target', 'semua').split(',')]
        
        if 'semua' in targets or user_role in targets:
            responses = conn.execute("SELECT data_respon FROM pendaftaran WHERE form_id=?", (f_dict['id'],)).fetchall()
            is_completed = False
            for r in responses:
                try:
                    data = json.loads(r['data_respon'])
                    if data.get('_submitter_id') == user_id:
                        is_completed = True
                        break
                    for k, v in data.items():
                        if isinstance(v, str) and (nama_user.lower() == v.lower() or user_id.lower() == v.lower()):
                            is_completed = True
                            break
                except:
                    pass
                if is_completed:
                    break
                    
            f_dict['is_completed'] = is_completed
            available_forms.append(f_dict)
            
    conn.close()
    return render_template('formulir_saya.html', forms=available_forms)

@app.route('/formulir/<int:form_id>', methods=['GET', 'POST'])
def isi_formulir(form_id):
    conn = get_db_connection()
    form_db = conn.execute("SELECT * FROM formulir WHERE id=?", (form_id,)).fetchone()
    
    if not form_db:
        conn.close()
        return "Formulir tidak ditemukan.", 404
        
    form_dict = dict(form_db)
    form_schema = json.loads(form_dict['schema_data'])
    
    # 1. FORM LIMITER WAKTU & MAX ENTRIES (Menutup/Membuka form otomatis)
    current_entries = conn.execute("SELECT COUNT(*) FROM pendaftaran WHERE form_id=?", (form_id,)).fetchone()[0]
    max_entries_reached = False
    
    limit_entries = form_schema.get('limitEntries')
    if limit_entries and str(limit_entries).strip() != '':
        try:
            max_entries = int(limit_entries)
            if current_entries >= max_entries:
                max_entries_reached = True
                form_dict['is_active'] = 0
                if form_db['is_active'] == 1:
                    conn.execute("UPDATE formulir SET is_active=0 WHERE id=?", (form_id,))
                    conn.commit()
        except: pass

    # CEK JADWAL OTOMATIS
    if form_schema.get('scheduleActivity'):
        now = datetime.now()
        is_started = True
        is_ended = False
        
        start_date, start_time = form_schema.get('schedStartDate'), form_schema.get('schedStartTime')
        if start_date and start_time:
            try:
                dt_start = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
                if now < dt_start: is_started = False
            except: pass
        
        end_date, end_time = form_schema.get('schedEndDate'), form_schema.get('schedEndTime')
        if end_date and end_time:
            try:
                dt_end = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
                if now > dt_end: is_ended = True
            except: pass
            
        if not is_started or is_ended:
            form_dict['is_active'] = 0
            if is_ended and form_db['is_active'] == 1:
                conn.execute("UPDATE formulir SET is_active=0 WHERE id=?", (form_id,))
                conn.commit()
        else:
            if form_db['is_active'] == 0 and not max_entries_reached:
                form_dict['is_active'] = 1
                conn.execute("UPDATE formulir SET is_active=1 WHERE id=?", (form_id,))
                conn.commit()

    # 2. CEK FORM DITUTUP
    if form_dict['is_active'] == 0:
        conn.close()
        if form_schema.get('closedType') == 'redirect' and form_schema.get('closedUrl'):
            return redirect(form_schema.get('closedUrl'))
        closed_msg = form_schema.get('closedMsg', 'Formulir ini telah ditutup dan tidak menerima tanggapan lagi.')
        return render_template('pendaftaran.html', closed=True, schema=form_schema, closed_msg=closed_msg)

    # 3. PENGAMANAN LOGIN & TARGET
    if form_dict['is_default'] == 0:
        if 'user_id' not in session:
            conn.close()
            flash("Silakan login terlebih dahulu untuk mengisi formulir ini.", "error")
            return redirect(url_for('login', next=request.url))
        
        targets = [t.strip() for t in form_dict.get('target', 'semua').split(',')]
        if 'semua' not in targets and session.get('role') not in targets:
            conn.close()
            return "Akses Ditolak: Formulir ini tidak ditujukan untuk jabatan Anda.", 403

    # 4. CEK BATAS: HANYA 1 TANGGAPAN PER USER
    if form_schema.get('limitOnePerUser'):
        if 'user_id' in session:
            user_id = session['user_id']
            exist = conn.execute("SELECT id FROM pendaftaran WHERE form_id=? AND data_respon LIKE ?", (form_id, f'%_submitter_id": "{user_id}"%')).fetchone()
            if exist:
                conn.close()
                return render_template('pendaftaran.html', already_filled=True, schema=form_schema)

    # HITUNG BATAS KUANTITAS
    all_responses = conn.execute("SELECT data_respon FROM pendaftaran WHERE form_id=?", (form_id,)).fetchall()
    usage_counts = {}
    for r in all_responses:
        try:
            resp_data = json.loads(r['data_respon'])
            for k, v in resp_data.items():
                if isinstance(v, str) and not k.startswith('_'):
                    for item in v.split(','):
                        clean_item = item.strip()
                        usage_counts[clean_item] = usage_counts.get(clean_item, 0) + 1
        except: pass
            
    for q in form_schema.get('questions', []):
        if q.get('maxQuantities') and q.get('options'):
            q['processedOptions'] = []
            for i, opt in enumerate(q['options']):
                limit_str = q.get('optionLimits', [])[i] if i < len(q.get('optionLimits', [])) else ''
                
                if not limit_str or str(limit_str).strip() == '':
                    q['processedOptions'].append({'text': opt, 'remaining': '', 'disabled': False, 'unlimited': True})
                else:
                    try:
                        limit = int(limit_str)
                        used = usage_counts.get(opt.strip(), 0)
                        sisa = max(0, limit - used)
                        q['processedOptions'].append({'text': opt, 'remaining': sisa, 'disabled': sisa == 0, 'unlimited': False})
                    except:
                        q['processedOptions'].append({'text': opt, 'remaining': '', 'disabled': False, 'unlimited': True})
    
    if request.method == 'POST':
        respon_data = {}
        nama_pendaftar, no_hp_pendaftar = "User Baru", ""
        
        for q in form_schema.get('questions', []):
            if q['type'] in ['image', 'video', 'section', 'page']: continue
            q_id = str(q['id'])
            val = ""
            
            if q['type'] == 'checkbox': val = ", ".join(request.form.getlist(f'q_{q_id}'))
            elif q['type'] == 'name':
                parts = [request.form.get(f'q_{q_id}_{p}', '').strip() for p in ['title', 'first', 'last', 'suffix'] if request.form.get(f'q_{q_id}_{p}')]
                val = " ".join(parts).strip()
            elif q['type'] == 'address':
                parts = []
                if request.form.get(f'q_{q_id}_street'): parts.append(request.form.get(f'q_{q_id}_street').strip())
                if request.form.get(f'q_{q_id}_line2'): parts.append(request.form.get(f'q_{q_id}_line2').strip())
                csz = ", ".join(filter(None, [request.form.get(f'q_{q_id}_city'), request.form.get(f'q_{q_id}_state'), request.form.get(f'q_{q_id}_zip')]))
                if csz: parts.append(csz)
                if request.form.get(f'q_{q_id}_country'): parts.append(request.form.get(f'q_{q_id}_country').strip())
                val = "\n".join(parts).strip()
            elif q['type'] == 'file':
                file = request.files.get(f'q_{q_id}')
                if file and file.filename != '':
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{file.filename}")
                    file.save(os.path.join(UPLOAD_FORM, filename))
                    val = f"uploads/form_files/{filename}"
            elif q['type'] in ['grid_radio', 'grid_checkbox']:
                grid_responses = {}
                for r_idx, row in enumerate(q.get('rows', [])):
                    if q['type'] == 'grid_radio': grid_responses[row] = request.form.get(f'q_{q_id}_r{r_idx}', '')
                    else: grid_responses[row] = ", ".join(request.form.getlist(f'q_{q_id}_r{r_idx}'))
                val = json.dumps(grid_responses)
            else: val = request.form.get(f'q_{q_id}', '')
                
            respon_data[q['question']] = val
            lbl_lower = q['question'].lower()
            if 'nama' in lbl_lower and nama_pendaftar == "User Baru" and val: nama_pendaftar = val
            elif ('nomor' in lbl_lower or 'hp' in lbl_lower or 'wa' in lbl_lower or 'telepon' in lbl_lower) and no_hp_pendaftar == "" and val: no_hp_pendaftar = val

        if 'user_id' in session:
            respon_data['_submitter_id'] = session['user_id']
            respon_data['_submitter_name'] = session.get('nama_user')
            
        new_username, random_password = None, None
        if form_dict['is_default'] == 1:
            base_username = "".join(e for e in nama_pendaftar.split()[0].lower() if e.isalnum())
            if not base_username: base_username = "user"
            username, counter = base_username, 1
            while conn.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
                username = f"{base_username}{counter}"
                counter += 1
                
            random_password = ''.join(random.choices("abcdefghjkmnpqrstuvwxyz23456789", k=6))
            conn.execute('INSERT INTO users (username, password, nama, role, no_hp, nama_panggilan) VALUES (?, ?, ?, ?, ?, ?)', 
                         (username, generate_password_hash(random_password), nama_pendaftar, 'user', no_hp_pendaftar, nama_pendaftar.split()[0] if nama_pendaftar != "User Baru" else "User"))
            respon_data['[Sistem] Username Dibuat'] = username
            new_username = username

        conn.execute('INSERT INTO pendaftaran (tanggal, data_respon, status, form_id) VALUES (?, ?, ?, ?)', 
                     (datetime.now().strftime('%Y-%m-%d %H:%M'), json.dumps(respon_data), 'Menunggu', form_id))
        conn.commit(); conn.close()
        return render_template('pendaftaran.html', success=True, schema=form_schema, new_username=new_username, new_password=random_password, is_default=form_dict['is_default'])

    conn.close()
    return render_template('pendaftaran.html', schema=form_schema, closed=False)

@app.route('/pendaftaran')
def pendaftaran():
    return redirect(url_for('isi_formulir', form_id=1))

@app.route('/kelola-pendaftaran', methods=['GET', 'POST'])
@login_required
def kelola_pendaftaran():
    if session.get('role') not in ['super admin', 'bph', 'penjadwalan', 'pelatihan']: return redirect(url_for('index'))
    conn = get_db_connection()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'buat_form':
            judul = request.form.get('judul', 'Formulir Baru')
            schema = json.dumps({
                "title": judul, 
                "description": "Deskripsi formulir", 
                "titleAlignment": "Left Aligned",
                "descAlignment": "Left Aligned",
                "language": "English",
                "labelPlacement": "Top Aligned",
                "questions": []
            })
            cursor = conn.execute("INSERT INTO formulir (judul, deskripsi, schema_data, is_active, is_default) VALUES (?, '', ?, 1, 0)", (judul, schema))
            conn.commit()
            new_id = cursor.lastrowid
            return redirect(url_for('kelola_pendaftaran', edit_id=new_id))
            
        elif action == 'save_schema':
            form_id = request.form.get('form_id')
            schema_json = request.form.get('schema_data')
            target_data = request.form.get('target', 'semua')
            try:
                schema_parsed = json.loads(schema_json)
                judul = schema_parsed.get('title', 'Formulir')
            except:
                judul = 'Formulir'
                
            conn.execute("UPDATE formulir SET schema_data=?, judul=?, target=? WHERE id=?", (schema_json, judul, target_data, form_id))
            conn.commit()
            flash("Formulir berhasil disimpan dan diperbarui!", "success")
            return redirect(url_for('kelola_pendaftaran', edit_id=form_id))
            
        elif action == 'hapus_form':
            form_id = request.form.get('form_id')
            form_db = conn.execute("SELECT is_default FROM formulir WHERE id=?", (form_id,)).fetchone()
            if form_db and form_db['is_default'] == 0:
                conn.execute("DELETE FROM formulir WHERE id=?", (form_id,))
                conn.execute("DELETE FROM pendaftaran WHERE form_id=?", (form_id,))
                conn.commit()
                flash("Formulir beserta semua tanggapannya berhasil dihapus.", "success")
            else:
                flash("Formulir default (utama) tidak dapat dihapus!", "error")
            return redirect(url_for('kelola_pendaftaran'))
            
        elif action == 'toggle_form':
            form_id = request.form.get('form_id')
            form_db = conn.execute("SELECT is_active FROM formulir WHERE id=?", (form_id,)).fetchone()
            if form_db:
                new_status = 0 if form_db['is_active'] == 1 else 1
                conn.execute("UPDATE formulir SET is_active=? WHERE id=?", (new_status, form_id))
                conn.commit()
            return redirect(url_for('kelola_pendaftaran'))
            
        elif action == 'update_status':
            conn.execute('UPDATE pendaftaran SET status=? WHERE id=?', (request.form.get('status'), request.form.get('id')))
            conn.commit()
            flash("Status respon diperbarui.", "success")
            return redirect(url_for('kelola_pendaftaran', respon_id=request.form.get('form_id')))
            
        elif action == 'hapus_pendaftar':
            form_id = request.form.get('form_id')
            conn.execute('DELETE FROM pendaftaran WHERE id=?', (request.form.get('id'),))
            conn.commit()
            flash("Respon tanggapan dihapus.", "success")
            return redirect(url_for('kelola_pendaftaran', respon_id=form_id))

    edit_id = request.args.get('edit_id')
    respon_id = request.args.get('respon_id')
    
    if edit_id:
        form_data = conn.execute("SELECT * FROM formulir WHERE id=?", (edit_id,)).fetchone()
        if not form_data: return redirect(url_for('kelola_pendaftaran'))
        conn.close()
        return render_template('kelola_pendaftaran.html', view='edit', form_data=dict(form_data), schema=json.loads(form_data['schema_data']))
        
    elif respon_id:
        form_data = conn.execute("SELECT * FROM formulir WHERE id=?", (respon_id,)).fetchone()
        if not form_data: return redirect(url_for('kelola_pendaftaran'))
        
        pendaftar_list = []
        for p in conn.execute('SELECT * FROM pendaftaran WHERE form_id=? ORDER BY id DESC', (respon_id,)).fetchall():
            p_dict = dict(p)
            try: 
                raw_parsed = json.loads(p['data_respon'])
                clean_parsed = {}
                
                submitter = raw_parsed.get('_submitter_name')
                if not submitter:
                    submitter = raw_parsed.get('Nama Lengkap', raw_parsed.get('Nama', 'User Anonim (Publik)'))
                p_dict['submitter_name'] = submitter
                
                for key, val in raw_parsed.items():
                    if key.startswith('_'): 
                        continue
                        
                    if val and isinstance(val, str) and val.startswith('{') and val.endswith('}'):
                        try:
                            grid_obj = json.loads(val)
                            clean_parsed[key] = "<br>".join([f"- {k}: {v}" for k, v in grid_obj.items()])
                        except:
                            clean_parsed[key] = val
                    elif val and isinstance(val, str) and val.startswith('uploads/'):
                        clean_parsed[key] = f'<a href="/static/{val}" target="_blank" style="color:#1a73e8;">Lihat File <i class="fas fa-external-link-alt"></i></a>'
                    else:
                        clean_parsed[key] = val
                p_dict['data_parsed'] = clean_parsed
            except: 
                p_dict['data_parsed'] = {}
                p_dict['submitter_name'] = 'Error Parsing'
            pendaftar_list.append(p_dict)
        conn.close()
        return render_template('kelola_pendaftaran.html', view='respon', form_data=dict(form_data), pendaftar=pendaftar_list)
        
    else:
        forms = conn.execute("SELECT * FROM formulir ORDER BY is_default DESC, id DESC").fetchall()
        forms_list = []
        for f in forms:
            f_dict = dict(f)
            f_dict['respon_count'] = conn.execute("SELECT COUNT(*) FROM pendaftaran WHERE form_id=?", (f['id'],)).fetchone()[0]
            forms_list.append(f_dict)
        conn.close()
        return render_template('kelola_pendaftaran.html', view='list', forms=forms_list)

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
            deskripsi_info = request.form.get('deskripsi', '')
            
            for idx, file in enumerate(request.files.getlist('file')):
                if file and file.filename != '':
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{idx}_{file.filename}")
                    file.save(os.path.join(UPLOAD_DOKUMEN, filename))
                    file_paths.append(f"uploads/dokumen/{filename}")
                    
            if action == 'tambah': 
                conn.execute('INSERT INTO dokumen (judul, deskripsi, file_path, tanggal_dibuat, target, pembuat, editor_terakhir, waktu_edit) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', 
                             (judul_info, deskripsi_info, ','.join(file_paths), datetime.now().strftime("%d %b %Y"), target_str, user_id, nama_pengurus, now_str))
                create_notification(conn, target_str, f"Ada dokumen baru yang dibagikan: {judul_info}", url_for('dokumen'))
            else:
                p_id = request.form.get('id')
                if file_paths:
                    old_doc = conn.execute('SELECT file_path FROM dokumen WHERE id=?', (p_id,)).fetchone()
                    if old_doc and old_doc['file_path']:
                        for p in old_doc['file_path'].split(','):
                            if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
                    conn.execute('UPDATE dokumen SET judul=?, deskripsi=?, file_path=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, deskripsi_info, ','.join(file_paths), target_str, nama_pengurus, now_str, p_id))
                else: 
                    conn.execute('UPDATE dokumen SET judul=?, deskripsi=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, deskripsi_info, target_str, nama_pengurus, now_str, p_id))
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
            deskripsi_info = request.form.get('deskripsi', '')
            
            for idx, foto in enumerate(request.files.getlist('foto')):
                if foto and foto.filename != '':
                    filename = secure_filename(f"{int(datetime.now().timestamp())}_{idx}_{foto.filename}")
                    foto.save(os.path.join(UPLOAD_GALERI, filename))
                    foto_paths.append(f"uploads/galeri/{filename}")
                    
            if action == 'tambah': 
                conn.execute('INSERT INTO galeri (judul, deskripsi, foto_path, tanggal_dibuat, target, pembuat, editor_terakhir, waktu_edit) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', 
                             (judul_info, deskripsi_info, ','.join(foto_paths), datetime.now().strftime("%d %b %Y"), target_str, user_id, nama_pengurus, now_str))
                create_notification(conn, target_str, f"Album foto baru telah diupload: {judul_info}", url_for('galeri'))
            else:
                p_id = request.form.get('id')
                if foto_paths:
                    old_gal = conn.execute('SELECT foto_path FROM galeri WHERE id=?', (p_id,)).fetchone()
                    if old_gal and old_gal['foto_path']:
                        for p in old_gal['foto_path'].split(','):
                            if os.path.exists(os.path.join('static', p)): os.remove(os.path.join('static', p))
                    conn.execute('UPDATE galeri SET judul=?, deskripsi=?, foto_path=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, deskripsi_info, ','.join(foto_paths), target_str, nama_pengurus, now_str, p_id))
                else: 
                    conn.execute('UPDATE galeri SET judul=?, deskripsi=?, target=?, editor_terakhir=?, waktu_edit=? WHERE id=?', 
                                 (judul_info, deskripsi_info, target_str, nama_pengurus, now_str, p_id))
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
    settings_data = dict(conn.execute('SELECT key, value FROM settings').fetchall())

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_sanksi_settings':
            keys = ['sanksi_alpa_harian', 'sanksi_alpa_mingguan', 'sanksi_alpa_besar']
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
                old_row = conn.execute("SELECT scan_before, scan_after FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND jenis = ? LIMIT 1", (old_dt, old_ac, old_jn)).fetchone()
                sb = old_row['scan_before'] if old_row else None
                sa = old_row['scan_after'] if old_row else None

                existing_rows = conn.execute("SELECT id, pengguna, status FROM jadwal WHERE jadwal_datetime = ? AND acara = ? AND jenis = ?", (old_dt, old_ac, old_jn)).fetchall()
                old_bertugas_users = set(r['pengguna'] for r in existing_rows if r['status'] == 'Bertugas' and r['pengguna'])
                had_bertugas = any(r['status'] == 'Bertugas' for r in existing_rows)

                wkt = wkt_raw.replace(':', '.')
                dt = datetime.strptime(tgl_str, '%Y-%m-%d')
                try: jadwal_dt = datetime.strptime(f"{tgl_str} {wkt_raw}:00", '%Y-%m-%d %H:%M:%S')
                except: jadwal_dt = dt
                jadwal_dt_str = jadwal_dt.strftime('%Y-%m-%d %H:%M:%S')

                months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
                days_id = {0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis', 4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'}
                hari = days_id[dt.weekday()]

                petugas_list = [p for p in petugas_list if p]
                unique_petugas_objs = []
                inserted_new = set()
                for p_id in petugas_list:
                    if p_id and p_id not in inserted_new:
                        user_db = conn.execute("SELECT username, nama FROM users WHERE username = ?", (p_id,)).fetchone()
                        if user_db: unique_petugas_objs.append({'username': user_db['username'], 'nama': user_db['nama']})
                        else: unique_petugas_objs.append({'username': p_id, 'nama': p_id})
                        inserted_new.add(p_id)

                if not unique_petugas_objs: unique_petugas_objs = [{'username': '', 'nama': ''}]

                new_users_set = set(u['username'] for u in unique_petugas_objs if u['username'])
                is_meta_changed = (old_dt != jadwal_dt_str) or (old_ac != acara)

                if not is_meta_changed and new_users_set == old_bertugas_users and had_bertugas:
                    status = 'Bertugas'
                else:
                    status = 'Draft'

                for r in existing_rows:
                    conn.execute("DELETE FROM jadwal WHERE id=?", (r['id'],))

                for u in unique_petugas_objs:
                    conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna, jenis, kategori_misa, scan_before, scan_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                 (jadwal_dt_str, dt.strftime('%d'), months_id[dt.month], hari, wkt, acara, status, u['username'], u['nama'], old_jn, kategori, sb, sa))

                conn.commit()
                if status == 'Draft':
                    flash("Jadwal berhasil diedit! Status diubah menjadi Draft karena ada perubahan data/petugas.", "success")
                else:
                    flash("Jadwal disimpan (Tidak ada perubahan, status tetap Bertugas).", "success")
            return redirect(url_for('penjadwalan'))

        elif action == 'update_pengingat_settings':
            # Mengambil data dari multiple input HTML
            waktu_list = request.form.getlist('pengingat_waktu[]')
            valid_waktu = [w.strip() for w in waktu_list if w.strip().isdigit()]
            waktu_str = ','.join(valid_waktu) if valid_waktu else '1440'

            fitur = request.form.get('fitur_pengingat')
            conn.execute("UPDATE settings SET value=? WHERE key='pengingat_waktu'", (waktu_str,))
            conn.execute("UPDATE settings SET value=? WHERE key='fitur_pengingat'", ('on' if fitur else 'off',))
            conn.commit()
            flash("Pengaturan Pengingat Jadwal berhasil diperbarui!", "success")
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

                    if r['nama_pengguna'] not in existing_data[wkt_key]:
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
            return render_template('penjadwalan.html', matrix=matrix_data, users=users_db, user_names=user_names, start=start_str, end=end_str, existing_data=existing_data, acara_data=acara_data, settings=settings_data, global_before=int(settings_data.get('scan_window_before', 60)), global_after=int(settings_data.get('scan_window_after', 180)))

        elif action == 'simpan_matriks':
            months_id = {1: 'JAN', 2: 'FEB', 3: 'MAR', 4: 'APR', 5: 'MEI', 6: 'JUNI', 7: 'JULI', 8: 'AGUST', 9: 'SEPT', 10: 'OKT', 11: 'NOV', 12: 'DES'}
            rendered_dates_raw = request.form.get('rendered_dates')
            old_bertugas = {}
            s_str, e_str = None, None
            if rendered_dates_raw:
                s_str, e_str = rendered_dates_raw.split('|')
                s_dt, e_dt = datetime.strptime(s_str, '%Y-%m-%d'), datetime.strptime(e_str, '%Y-%m-%d')
                all_dates = []
                c = s_dt
                while c <= e_dt:
                    all_dates.append(c.strftime('%Y-%m-%d'))
                    c += timedelta(days=1)
                placeholders = ','.join('?' for _ in all_dates)

                old_rows = conn.execute(f"SELECT jadwal_datetime, acara, pengguna FROM jadwal WHERE status='Bertugas' AND jenis='Matriks' AND substr(jadwal_datetime, 1, 10) IN ({placeholders})", all_dates).fetchall()
                for r in old_rows:
                    k = f"{r['jadwal_datetime']}|{r['acara']}"
                    if k not in old_bertugas: old_bertugas[k] = set()
                    if r['pengguna']: old_bertugas[k].add(r['pengguna'])

                conn.execute(f"DELETE FROM jadwal WHERE jenis='Matriks' AND substr(jadwal_datetime, 1, 10) IN ({placeholders})", all_dates)

            shifts_to_insert = {}
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
                    jadwal_dt_str = jadwal_dt.strftime('%Y-%m-%d %H:%M:%S')

                    shift_key = f"{jadwal_dt_str}|{acara_final}"
                    if shift_key not in shifts_to_insert:
                        shifts_to_insert[shift_key] = {'dt': dt, 'hari': hari, 'wkt': wkt, 'acara': acara_final, 'kat': kat, 'users': []}

                    values = request.form.getlist(key)
                    for val in values:
                        if val and val.strip():
                            names = [n.strip() for n in val.split(',') if n.strip()]
                            for n in names:
                                if n.strip(): shifts_to_insert[shift_key]['users'].append(n.strip())

            for shift_key, s_data in shifts_to_insert.items():
                final_users = []
                for n in s_data['users']:
                    user_db = conn.execute("SELECT username, nama FROM users WHERE nama LIKE ? OR nama_panggilan LIKE ? OR username = ?", (f"%{n}%", f"%{n}%", n)).fetchone()
                    if user_db: final_users.append({'username': user_db['username'], 'nama': user_db['nama']})
                    else: final_users.append({'username': n, 'nama': n})

                submitted_usernames = set([u['username'] for u in final_users if u['username']])

                if shift_key in old_bertugas and submitted_usernames == old_bertugas[shift_key]:
                    status = 'Bertugas'
                else:
                    status = 'Draft'

                dt = s_data['dt']
                if not final_users:
                    conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna, jenis, kategori_misa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "Matriks", ?)',
                                 (shift_key.split('|')[0], dt.strftime('%d'), months_id[dt.month], s_data['hari'], s_data['wkt'], s_data['acara'], status, '', '', s_data['kat']))
                else:
                    inserted = set()
                    for u in final_users:
                        if u['username'] not in inserted:
                            conn.execute('INSERT INTO jadwal (jadwal_datetime, tanggal, bulan, hari, waktu, acara, status, pengguna, nama_pengguna, jenis, kategori_misa) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "Matriks", ?)',
                                         (shift_key.split('|')[0], dt.strftime('%d'), months_id[dt.month], s_data['hari'], s_data['wkt'], s_data['acara'], status, u['username'], u['nama'], s_data['kat']))
                            inserted.add(u['username'])

            conn.commit(); conn.close()
            if s_str and e_str:
                return redirect(url_for('cetak_jadwal', target_start=s_str, target_end=e_str))
            return redirect(url_for('penjadwalan'))

        elif action == 'tambah_khusus':
            tgl_str = request.form.get('tanggal')
            wkt_raw = request.form.get('waktu')
            acara = request.form.get('acara')
            kategori = request.form.get('kategori', 'Besar')
            petugas_list = request.form.getlist('petugas')
            status = 'Draft'

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
                flash("Jadwal khusus berhasil ditambahkan ke dalam Draf!", "success")
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

    has_draft = False

    history = []
    for r in history_rows:
        d = dict(r)
        if d['status'] == 'Draft':
            has_draft = True

        if d['petugas']:
            plist = [p.strip() for p in d['petugas'].split(',') if p.strip()]
            d['petugas'] = ', '.join(list(dict.fromkeys(plist)))
        if d['pengguna_list']:
            ulist = [u.strip() for u in d['pengguna_list'].split(',') if u.strip()]
            d['pengguna_list'] = ','.join(list(dict.fromkeys(ulist)))

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
    return render_template('penjadwalan.html', users=users_db, user_names=user_names, history=history, global_before=global_before, global_after=global_after, settings=settings_data, has_draft=has_draft)

@app.route('/cetak-jadwal')
@login_required
def cetak_jadwal():
    if session.get('role') not in ['super admin', 'penjadwalan']: return redirect(url_for('index'))
    target_start, target_end = request.args.get('target_start'), request.args.get('target_end')
    conn = get_db_connection()
    
    has_draft = False
    if target_start and target_end:
        start_time, end_time = f"{target_start} 00:00:00", f"{target_end} 23:59:59"
        rows_draft = conn.execute("SELECT * FROM jadwal WHERE status='Draft' AND jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC", (start_time, end_time)).fetchall()
        if rows_draft: 
            rows = rows_draft
            has_draft = True
        else: 
            rows = conn.execute("SELECT * FROM jadwal WHERE status='Bertugas' AND jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC", (start_time, end_time)).fetchall()
    else:
        threshold_time = datetime.now().strftime('%Y-%m-%d 00:00:00')
        end_limit = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d 23:59:59')
        rows = conn.execute('SELECT * FROM jadwal WHERE jadwal_datetime >= ? AND jadwal_datetime <= ? ORDER BY jadwal_datetime ASC', (threshold_time, end_limit)).fetchall()
        for r in rows:
            if r['status'] == 'Draft':
                has_draft = True
                break
                
    conn.close()

    valid_dts = [datetime.strptime(r['jadwal_datetime'], '%Y-%m-%d %H:%M:%S') for r in rows if r['nama_pengguna'] != '']
    if not valid_dts and rows: valid_dts = [datetime.strptime(rows[0]['jadwal_datetime'], '%Y-%m-%d %H:%M:%S')]
    if valid_dts: min_date, max_date = min(valid_dts), max(valid_dts)
    else: min_date, max_date = datetime.now(), datetime.now()
    s_str = target_start if target_start else min_date.strftime('%Y-%m-%d')
    e_str = target_end if target_end else max_date.strftime('%Y-%m-%d')
    if not rows: return render_template('cetak_jadwal.html', weeks=[], s_str=s_str, e_str=e_str, periode="-", has_draft=False)

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
        
    return render_template('cetak_jadwal.html', weeks=final_weeks, s_str=s_str, e_str=e_str, periode=periode_str, has_draft=has_draft)

@app.route('/publikasi-jadwal', methods=['POST'])
@login_required
def publikasi_jadwal():
    if session.get('role') not in ['super admin', 'penjadwalan']: return redirect(url_for('index'))
    conn = get_db_connection()
    conn.execute("UPDATE jadwal SET status='Bertugas' WHERE status='Draft'") 
    conn.commit()
    conn.close()
    flash("Jadwal Draft berhasil dipublikasikan secara langsung ke Anggota!", "success")
    return redirect(url_for('penjadwalan'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)