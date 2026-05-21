import os
import time
from collections import defaultdict
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fidownloader_super_secret_key_123")

# ==============================================================================
# KONFIGURASI SUPABASE
# ==============================================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bxrhngglojieizyzkcvv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_5PzZlyLIqQx6RYt74vWgxw__obBRhq4")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

START_TIME = time.time()

# Rate Limiter tetap di Memory untuk performa (mencegah DB kelebihan beban)
request_history = defaultdict(list)
REQUEST_LIMIT = 5       
TIME_WINDOW = 10        
BLOCK_DURATION = 60     

# ==============================================================================
# FUNGSI DATABASE HELPER
# ==============================================================================
def add_to_logs(ip, path, method, status):
    """Mencatat aktivitas ke Supabase"""
    try:
        supabase.table("system_logs").insert({
            "ip": ip, "path": path, "method": method, "status": status
        }).execute()
    except Exception as e:
        print(f"Log Error: {e}")

@app.before_request
def anti_ddos_and_logging():
    if request.path.startswith('/static') or request.path == '/favicon.ico':
        return
        
    user_ip = request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip() if request.headers.getlist("X-Forwarded-For") else request.remote_addr
    current_time = int(time.time())
    
    # Cek Blokir dari Supabase
    try:
        block_check = supabase.table("blocked_ips").select("*").eq("ip", user_ip).execute()
        if block_check.data:
            block_data = block_check.data[0]
            if block_data['block_type'] == "MANUAL":
                add_to_logs(user_ip, request.path, request.method, "BLOCKED (Manual)")
                if request.path in ["/download", "/api/stats"]:
                    return jsonify({"status": False, "message": "IP Anda diblokir secara permanen oleh Administrator."}), 403
                return f"<h1>403 Forbidden. IP Anda diblokir permanen.</h1>", 403
            else:
                expires_at = int(block_data.get('expires_at', 0))
                if current_time < expires_at:
                    remaining = expires_at - current_time
                    add_to_logs(user_ip, request.path, request.method, f"BLOCKED (Auto: {remaining}s)")
                    if request.path in ["/download", "/api/stats"]:
                        return jsonify({"status": False, "message": f"IP diblokir karena spam. Sisa waktu: {remaining}s"}), 429
                    return f"<h1>429 Terlalu banyak permintaan. Sisa waktu: {remaining}s</h1>", 429
                else:
                    supabase.table("blocked_ips").delete().eq("ip", user_ip).execute()
    except: pass

    if not request.path.startswith('/admin') and not request.path.startswith('/api/admin'):
        add_to_logs(user_ip, request.path, request.method, "SUCCESS")

    if request.path == "/download":
        request_history[user_ip].append(current_time)
        request_history[user_ip] = [t for t in request_history[user_ip] if current_time - t < TIME_WINDOW]
        
        if len(request_history[user_ip]) > REQUEST_LIMIT:
            expires = current_time + BLOCK_DURATION
            supabase.table("blocked_ips").insert({
                "ip": user_ip, "block_type": "AUTO", "expires_at": expires
            }).execute()
            add_to_logs(user_ip, request.path, request.method, "TRIGGERED AUTO-BLOCK")
            return jsonify({"status": False, "message": "Spam terdeteksi! Diblokir otomatis 60 detik."}), 429

# ==============================================================================
# TEMPLATE HTML
# ==============================================================================
HTML_USER = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fidownloader - TikTok Downloader Premium</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>.active-nav { background: rgba(255,255,255,0.1); border-color: rgba(168,85,247,0.4); }</style>
</head>
<body class="bg-slate-950 min-h-screen text-slate-100 pb-12">
    <nav class="sticky top-0 z-50 bg-slate-950/70 backdrop-blur-md border-b border-white/10 px-6 py-4 mb-10">
        <div class="max-w-5xl mx-auto flex items-center justify-between">
            <div class="flex items-center gap-2 text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-400">Fi-Downloader</div>
            <div class="flex gap-2 text-sm font-medium">
                <button onclick="switchPage('home')" id="nav-home" class="px-4 py-2 rounded-xl active-nav">Home</button>
                <button onclick="switchPage('stats')" id="nav-stats" class="px-4 py-2 rounded-xl">Statistik</button>
                {% if session.get('user_id') %}
                    <button onclick="switchPage('profile')" id="nav-profile" class="px-4 py-2 rounded-xl text-purple-400">Akunku</button>
                    {% if session.get('role') == 'admin' %}
                        <a href="/admin" class="px-4 py-2 rounded-xl text-red-400 border border-red-500/30">Admin</a>
                    {% endif %}
                    <a href="/logout" class="px-4 py-2 rounded-xl text-red-400 hover:bg-white/5">Logout</a>
                {% else %}
                    <button onclick="switchPage('auth')" id="nav-auth" class="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500">Login / Daftar</button>
                {% endif %}
            </div>
        </div>
    </nav>

    <main class="w-full max-w-4xl mx-auto px-4">
        <!-- PAGE: HOME -->
        <section id="page-home" class="space-y-8">
            <div class="text-center"><h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-blue-400 mb-3">TikTok Multi Downloader</h1></div>
            
            <div class="bg-white/5 backdrop-blur-xl border border-white/10 rounded-3xl p-6 shadow-2xl">
                <div class="flex gap-3">
                    <input type="text" id="url" placeholder="Tempel link video/foto TikTok..." class="flex-1 bg-slate-900/50 border border-slate-700 rounded-2xl px-5 py-4 text-white outline-none focus:border-purple-500">
                    <button onclick="downloadContent()" class="bg-gradient-to-r from-purple-600 to-blue-600 px-8 py-4 rounded-2xl font-bold">Proses</button>
                </div>
                <div id="loading" class="hidden mt-6 text-center text-purple-400">Memproses tautan...</div>
                <div id="error" class="hidden mt-4 text-red-400 bg-red-500/10 p-3 rounded-xl text-center"></div>

                <!-- RESULT -->
                <div id="result" class="hidden mt-8 border-t border-white/10 pt-6">
                    <h3 id="videoTitle" class="text-white text-center font-bold mb-4"></h3>
                    <div class="flex flex-col gap-3">
                        <a id="btnVideoNoWm" href="#" target="_blank" class="hidden bg-purple-600 p-3 rounded-xl text-center font-bold">Unduh Video (Tanpa Watermark)</a>
                        <a id="btnAudio" href="#" target="_blank" class="hidden bg-emerald-600 p-3 rounded-xl text-center font-bold">Unduh Audio (MP3)</a>
                        <button id="btnBookmark" onclick="bookmarkItem()" class="hidden bg-slate-800 p-3 rounded-xl text-center font-bold hover:text-yellow-400">⭐ Simpan ke Favorit</button>
                    </div>
                </div>
            </div>
        </section>

        <!-- PAGE: AUTH -->
        <section id="page-auth" class="hidden max-w-md mx-auto bg-white/5 border border-white/10 rounded-3xl p-8">
            <h2 class="text-2xl font-bold text-center mb-6">Masuk / Daftar</h2>
            <form id="authForm" onsubmit="handleAuth(event)" class="space-y-4">
                <input type="text" id="authUsername" placeholder="Username" required class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white outline-none">
                <input type="password" id="authPassword" placeholder="Password" required class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-white outline-none">
                <div class="flex gap-2">
                    <button type="submit" onclick="authMode='login'" class="flex-1 bg-purple-600 py-3 rounded-xl font-bold">Login</button>
                    <button type="submit" onclick="authMode='register'" class="flex-1 bg-slate-800 py-3 rounded-xl font-bold">Daftar</button>
                </div>
            </form>
            <p id="authMsg" class="mt-4 text-center text-sm"></p>
        </section>

        <!-- PAGE: PROFILE & BOOKMARKS -->
        <section id="page-profile" class="hidden space-y-6">
            <div class="bg-white/5 border border-white/10 rounded-3xl p-6">
                <h2 class="text-xl font-bold mb-4">⭐ Favorit & Riwayat Saya</h2>
                <div id="userHistory" class="space-y-3">Memuat data...</div>
            </div>
        </section>

        <!-- PAGE: STATS -->
        <section id="page-stats" class="hidden bg-white/5 border border-white/10 rounded-3xl p-6">
            <h2 class="text-xl font-bold mb-4">📊 Statistik Global</h2>
            <div class="grid grid-cols-2 gap-4">
                <div class="bg-slate-900 p-4 rounded-xl text-center"><span class="block text-slate-400 text-sm">Total Unduhan</span><strong id="stat-dl" class="text-2xl text-purple-400">-</strong></div>
                <div class="bg-slate-900 p-4 rounded-xl text-center"><span class="block text-slate-400 text-sm">Uptime Server</span><strong id="stat-up" class="text-xl text-blue-400">-</strong></div>
            </div>
        </section>
    </main>

<script>
let authMode = 'login';
let currentDownloadId = null;

function switchPage(page) {
    ['home', 'auth', 'profile', 'stats'].forEach(p => {
        let el = document.getElementById(`page-${p}`);
        if(el) el.classList.add('hidden');
        let nav = document.getElementById(`nav-${p}`);
        if(nav) nav.classList.remove('active-nav');
    });
    document.getElementById(`page-${page}`).classList.remove('hidden');
    let activeNav = document.getElementById(`nav-${page}`);
    if(activeNav) activeNav.classList.add('active-nav');
    
    if(page === 'stats') fetchStats();
    if(page === 'profile') fetchProfile();
}

async function handleAuth(e) {
    e.preventDefault();
    const u = document.getElementById('authUsername').value;
    const p = document.getElementById('authPassword').value;
    const res = await fetch(`/${authMode}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: u, password: p})
    });
    const data = await res.json();
    document.getElementById('authMsg').innerText = data.message;
    document.getElementById('authMsg').className = data.status ? "mt-4 text-center text-sm text-emerald-400" : "mt-4 text-center text-sm text-red-400";
    if(data.status) setTimeout(() => window.location.reload(), 1000);
}

async function fetchStats() {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('stat-dl').innerText = data.total_downloads;
    document.getElementById('stat-up').innerText = data.uptime;
}

async function fetchProfile() {
    const res = await fetch('/api/profile');
    const data = await res.json();
    const container = document.getElementById('userHistory');
    container.innerHTML = '';
    if(data.data.length === 0) container.innerHTML = '<p class="text-slate-400">Belum ada riwayat atau favorit.</p>';
    data.data.forEach(item => {
        let star = item.is_bookmarked ? '⭐' : '📄';
        container.innerHTML += `<div class="bg-slate-900 p-3 rounded-xl flex justify-between items-center"><div class="truncate pr-4"><b>${star}</b> <span class="text-sm">${item.title}</span></div><a href="${item.url}" target="_blank" class="text-xs bg-purple-600 px-3 py-1 rounded-lg">Buka Asli</a></div>`;
    });
}

async function downloadContent() {
    const url = document.getElementById("url").value;
    document.getElementById("loading").classList.remove("hidden");
    document.getElementById("result").classList.add("hidden");
    document.getElementById("error").classList.add("hidden");

    try {
        const res = await fetch("/download", {
            method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({url})
        });
        const data = await res.json();
        document.getElementById("loading").classList.add("hidden");

        if(!data.status) {
            document.getElementById("error").classList.remove("hidden");
            document.getElementById("error").innerText = data.message;
            return;
        }

        document.getElementById("result").classList.remove("hidden");
        document.getElementById("videoTitle").innerText = data.title;
        currentDownloadId = data.download_id;

        if(data.video_nowm) {
            document.getElementById("btnVideoNoWm").classList.remove("hidden");
            document.getElementById("btnVideoNoWm").href = data.video_nowm;
        }
        if(data.audio) {
            document.getElementById("btnAudio").classList.remove("hidden");
            document.getElementById("btnAudio").href = data.audio;
        }
        {% if session.get('user_id') %}
            document.getElementById("btnBookmark").classList.remove("hidden");
        {% endif %}
    } catch(err) {
        document.getElementById("loading").classList.add("hidden");
        document.getElementById("error").classList.remove("hidden");
        document.getElementById("error").innerText = "Gagal memproses permintaan.";
    }
}

async function bookmarkItem() {
    if(!currentDownloadId) return;
    const res = await fetch('/api/bookmark', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: currentDownloadId})
    });
    const data = await res.json();
    if(data.status) {
        document.getElementById("btnBookmark").innerText = "✅ Tersimpan di Favorit";
        document.getElementById("btnBookmark").classList.add("text-emerald-400");
    }
}
</script>
</body>
</html>
"""

HTML_ADMIN = """
<!DOCTYPE html>
<html lang="id">
<head><title>Admin Panel</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-950 text-white p-8">
    <div class="max-w-6xl mx-auto space-y-8">
        <div class="flex justify-between items-center bg-white/5 p-6 rounded-2xl border border-white/10">
            <h1 class="text-2xl font-bold">Admin Panel - Supabase Connected</h1>
            <div class="flex gap-4">
                <a href="/" class="bg-slate-800 px-4 py-2 rounded-xl">Ke Web</a>
            </div>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="bg-white/5 p-6 rounded-2xl border border-white/10 space-y-4">
                <h3 class="font-bold">Ban IP Manual</h3>
                <input type="text" id="banIp" placeholder="192.168.1.1" class="w-full bg-slate-900 p-3 rounded-xl outline-none">
                <button onclick="blockManual()" class="w-full bg-red-600 p-3 rounded-xl font-bold">Blokir Permanen</button>
                <div class="mt-4"><h4 class="text-sm text-slate-400 mb-2">Daftar Terblokir:</h4><div id="blockedList" class="space-y-2 text-sm"></div></div>
            </div>

            <div class="md:col-span-2 bg-white/5 p-6 rounded-2xl border border-white/10">
                <div class="flex justify-between items-center mb-4"><h3 class="font-bold">Live System Logs (Database)</h3><button onclick="loadData()" class="bg-purple-600 px-3 py-1 rounded-lg text-sm">Refresh</button></div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm"><thead class="text-slate-400 border-b border-slate-800"><tr><th class="pb-2">Waktu</th><th class="pb-2">IP</th><th class="pb-2">Path</th><th class="pb-2">Status</th></tr></thead>
                    <tbody id="logsTable"></tbody></table>
                </div>
            </div>
        </div>
    </div>
<script>
async function loadData() {
    const res = await fetch('/api/admin/data');
    const data = await res.json();
    
    document.getElementById('blockedList').innerHTML = data.blocked_ips.map(b => `<div class="flex justify-between bg-slate-900 p-2 rounded-lg"><span>${b.ip} <span class="text-xs text-red-400">(${b.block_type})</span></span><button onclick="unblock('${b.ip}')" class="text-emerald-400 text-xs">Lepas</button></div>`).join('');
    
    document.getElementById('logsTable').innerHTML = data.logs.map(l => `<tr class="border-b border-slate-900/50"><td class="py-2 text-xs text-slate-400">${new Date(l.created_at).toLocaleString()}</td><td class="py-2 font-mono">${l.ip}</td><td class="py-2">${l.path}</td><td class="py-2 font-bold ${l.status.includes('BLOCKED')?'text-red-400':'text-emerald-400'}">${l.status}</td></tr>`).join('');
}
async function blockManual() {
    const ip = document.getElementById('banIp').value;
    if(ip) { await fetch('/api/admin/block', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ip})}); loadData(); }
}
async function unblock(ip) {
    await fetch('/api/admin/unblock', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ip})}); loadData();
}
window.onload = loadData;
</script>
</body>
</html>
"""

# ==============================================================================
# ROUTES AUTHENTICATION
# ==============================================================================
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username, password = data.get("username"), data.get("password")
    
    cek = supabase.table("users").select("id").eq("username", username).execute()
    if cek.data: return jsonify({"status": False, "message": "Username sudah digunakan!"})
    
    hashed = generate_password_hash(password)
    res = supabase.table("users").insert({"username": username, "password_hash": hashed}).execute()
    
    session['user_id'] = res.data[0]['id']
    session['username'] = res.data[0]['username']
    session['role'] = res.data[0]['role']
    return jsonify({"status": True, "message": "Registrasi berhasil, sedang masuk..."})

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user = supabase.table("users").select("*").eq("username", data.get("username")).execute()
    
    if user.data and check_password_hash(user.data[0]['password_hash'], data.get("password")):
        session['user_id'] = user.data[0]['id']
        session['username'] = user.data[0]['username']
        session['role'] = user.data[0]['role']
        return jsonify({"status": True, "message": "Login sukses!"})
    return jsonify({"status": False, "message": "Username atau Password salah."})

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ==============================================================================
# ROUTES CORE FITUR
# ==============================================================================
@app.route("/")
def home():
    return render_template_string(HTML_USER)

@app.route("/download", methods=["POST"])
def download():
    url = request.json.get("url")
    if not url: return jsonify({"status": False, "message": "Link kosong!"}), 400
        
    try:
        import requests
        res = requests.get(f"https://www.tikwm.com/api/?url={url}", timeout=10).json()
        if res.get("code") != 0: return jsonify({"status": False, "message": "Video tidak ditemukan."})
            
        data = res.get("data", {})
        title = data.get("title", "Aset Media TikTok")
        
        # Simpan ke DB Supabase
        db_insert = supabase.table("downloads").insert({
            "url": url, "title": title, "media_type": "video",
            "user_id": session.get("user_id") # None jika belum login
        }).execute()
        download_id = db_insert.data[0]['id'] if db_insert.data else None

        return jsonify({
            "status": True,
            "title": title,
            "download_id": download_id,
            "video_nowm": data.get("play"),
            "audio": data.get("music")
        })
    except Exception as e:
        return jsonify({"status": False, "message": f"Server Error."})

@app.route("/api/bookmark", methods=["POST"])
def bookmark():
    if 'user_id' not in session: return jsonify({"status": False, "message": "Harus login!"}), 401
    dl_id = request.json.get("id")
    supabase.table("downloads").update({"is_bookmarked": True}).eq("id", dl_id).eq("user_id", session['user_id']).execute()
    return jsonify({"status": True})

@app.route("/api/profile")
def profile():
    if 'user_id' not in session: return jsonify({"status": False})
    history = supabase.table("downloads").select("*").eq("user_id", session['user_id']).order("created_at", desc=True).limit(20).execute()
    return jsonify({"status": True, "data": history.data})

@app.route("/api/stats")
def server_stats():
    uptime = int(time.time() - START_TIME)
    h, r = divmod(uptime, 3600); m, s = divmod(r, 60)
    
    # Menghitung dari Supabase
    dl_count = supabase.table("downloads").select("id", count="exact").execute().count
    
    return jsonify({"status": True, "total_downloads": dl_count, "uptime": f"{h}j {m}m {s}d"})

# ==============================================================================
# ROUTES ADMIN
# ==============================================================================
@app.route("/admin")
def admin_panel():
    if session.get('role') != 'admin': return redirect("/")
    return render_template_string(HTML_ADMIN)

@app.route("/api/admin/data")
def admin_data():
    if session.get('role') != 'admin': return jsonify({"status": False}), 401
    blocks = supabase.table("blocked_ips").select("*").execute()
    logs = supabase.table("system_logs").select("*").order("created_at", desc=True).limit(50).execute()
    return jsonify({"status": True, "blocked_ips": blocks.data, "logs": logs.data})

@app.route("/api/admin/block", methods=["POST"])
def admin_block():
    if session.get('role') != 'admin': return jsonify({"status": False}), 401
    supabase.table("blocked_ips").upsert({"ip": request.json.get("ip"), "block_type": "MANUAL", "expires_at": None}).execute()
    return jsonify({"status": True})

@app.route("/api/admin/unblock", methods=["POST"])
def admin_unblock():
    if session.get('role') != 'admin': return jsonify({"status": False}), 401
    supabase.table("blocked_ips").delete().eq("ip", request.json.get("ip")).execute()
    return jsonify({"status": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)), debug=True)
