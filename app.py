import os
import time
from collections import defaultdict
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for

app = Flask(__name__)
# Ganti secret key ini untuk keamanan session login Anda
app.secret_key = os.environ.get("SECRET_KEY", "fidownloader_super_secret_key_123")

# ==============================================================================
# GLOBAL DATA STORE (In-Memory)
# ==============================================================================
START_TIME = time.time()
TOTAL_DOWNLOADS = 0
SYSTEM_LOGS = [] # Menyimpan log aktivitas terakhir untuk halaman admin

# ==============================================================================
# KONFIGURASI ANTI-DDOS (RATE LIMITER)
# ==============================================================================
request_history = defaultdict(list)
blocked_ips = {}

REQUEST_LIMIT = 5       
TIME_WINDOW = 10        
BLOCK_DURATION = 60     

def add_to_logs(ip, path, method, status):
    """Mencatat aktivitas ke dalam memory log (maksimal 50 log terakhir)"""
    waktu_log = time.strftime('%Y-%m-%d %H:%M:%S')
    SYSTEM_LOGS.insert(0, {
        "waktu": waktu_log,
        "ip": ip,
        "path": path,
        "method": method,
        "status": status
    })
    if len(SYSTEM_LOGS) > 50:
        SYSTEM_LOGS.pop()

@app.before_request
def anti_ddos_and_logging():
    # Abaikan logging untuk file statis internal/assets jika ada
    if request.path.startswith('/static') or request.path == '/favicon.ico':
        return
        
    # Mengambil IP asli user di Railway (menggunakan X-Forwarded-For)
    if request.headers.getlist("X-Forwarded-For"):
        user_ip = request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    else:
        user_ip = request.remote_addr
        
    current_time = time.time()
    
    # Cek status blokir manual maupun otomatis
    if user_ip in blocked_ips:
        # Jika nilai berupa int/float masa depan berarti blokir otomatis berdurasi
        if isinstance(blocked_ips[user_ip], (int, float)):
            if current_time < blocked_ips[user_ip]:
                remaining_time = int(blocked_ips[user_ip] - current_time)
                add_to_logs(user_ip, request.path, request.method, f"BLOCKED (Auto: {remaining_time}s)")
                if request.path in ["/download", "/api/stats"]:
                    return jsonify({"status": False, "message": f"IP Anda diblokir otomatis karena spamming. Sisa waktu: {remaining_time}s"}), 429
                return f"<h1>429 Too Many Requests. Diblokir otomatis karena spam. Sisa waktu: {remaining_time}s</h1>", 429
            else:
                del blocked_ips[user_ip]
        # Jika nilainya "MANUAL", berarti diblokir permanen dari halaman admin
        elif blocked_ips[user_ip] == "MANUAL":
            add_to_logs(user_ip, request.path, request.method, "BLOCKED (Manual)")
            if request.path in ["/download", "/api/stats"]:
                return jsonify({"status": False, "message": "IP Anda diblokir secara permanen oleh Administrator."}), 403
            return f"<h1>403 Forbidden. IP Anda diblokir permanen oleh Administrator.</h1>", 403

    # Jangan masukkan aktivitas halaman admin ke log agar tidak penuh oleh admin sendiri
    if not request.path.startswith('/admin') and not request.path.startswith('/api/admin'):
        add_to_logs(user_ip, request.path, request.method, "SUCCESS")

    # Tracker spamming khusus endpoint /download
    if request.path == "/download":
        request_history[user_ip].append(current_time)
        request_history[user_ip] = [t for t in request_history[user_ip] if current_time - t < TIME_WINDOW]
        
        if len(request_history[user_ip]) > REQUEST_LIMIT:
            blocked_ips[user_ip] = current_time + BLOCK_DURATION
            add_to_logs(user_ip, request.path, request.method, "TRIGGERED AUTO-BLOCK")
            print(f"\n[⚠️ SECURITY] IP {user_ip} DIBLOKIR otomatis karena spamming!\n")
            return jsonify({"status": False, "message": "Aktivitas mencurigakan terdeteksi! Anda diblokir otomatis 60 detik."}), 429

# ==============================================================================
# TEMPLATE FRONTEND UTAMA (Fidownloader Premium UI)
# ==============================================================================
HTML_USER = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fidownloader - TikTok Downloader Premium</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Poppins', sans-serif; }
        .active-nav { background: rgba(255, 255, 255, 0.1); border-color: rgba(168, 85, 247, 0.4); }
    </style>
</head>
<body class="bg-slate-950 min-h-screen text-slate-100 relative overflow-x-hidden pb-12">

    <div class="absolute top-[-10%] left-[-10%] w-96 h-96 bg-purple-600 rounded-full mix-blend-multiply filter blur-[128px] opacity-30 fixed pointer-events-none"></div>
    <div class="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-blue-600 rounded-full mix-blend-multiply filter blur-[128px] opacity-30 fixed pointer-events-none"></div>

    <!-- NAVBAR -->
    <nav class="sticky top-0 z-50 w-full bg-slate-950/70 backdrop-blur-md border-b border-white/10 px-6 py-4 mb-10">
        <div class="max-w-5xl mx-auto flex items-center justify-between">
            <div class="flex items-center gap-2 cursor-pointer" onclick="switchPage('home')">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-blue-600 flex items-center justify-center font-bold text-white text-xl shadow-md shadow-purple-600/20">
                    Fi
                </div>
                <span class="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">Fidownloader</span>
            </div>
            <div class="flex gap-2 sm:gap-4 text-sm font-medium">
                <button id="nav-home" onclick="switchPage('home')" class="px-4 py-2 rounded-xl border border-transparent transition-all duration-300 hover:bg-white/5 active-nav">Home</button>
                <button id="nav-stats" onclick="switchPage('stats')" class="px-4 py-2 rounded-xl border border-transparent transition-all duration-300 hover:bg-white/5">Statistik</button>
                <button id="nav-about" onclick="switchPage('about')" class="px-4 py-2 rounded-xl border border-transparent transition-all duration-300 hover:bg-white/5">Tentang</button>
            </div>
        </div>
    </nav>

    <main class="relative z-10 w-full max-w-4xl mx-auto px-4">
        
        <!-- PAGE 1: HOME -->
        <section id="page-home" class="space-y-8">
            <div class="text-center max-w-lg mx-auto mb-4">
                <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 via-pink-400 to-blue-400 mb-3">
                    TikTok Multi Downloader
                </h1>
                <p class="text-slate-400 text-sm">Unduh Video No-Watermark, Audio MP3, atau Slideshow Foto kualitas HD secara instan.</p>
            </div>

            <div class="w-full max-w-2xl mx-auto bg-white/5 backdrop-blur-xl border border-white/10 rounded-[2rem] p-6 sm:p-8 shadow-2xl">
                <div class="flex flex-col sm:flex-row gap-3">
                    <input type="text" id="url" placeholder="Tempel link video atau foto TikTok di sini..." class="flex-1 bg-slate-900/50 border border-slate-700 rounded-2xl px-5 py-4 text-white text-sm outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-all placeholder-slate-500">
                    <button onclick="downloadContent()" class="bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 transition-all duration-300 px-8 py-4 rounded-2xl text-white font-semibold shadow-lg shadow-blue-500/25 active:scale-95 flex justify-center items-center gap-2">
                        <span>Proses</span>
                    </button>
                </div>

                <div id="loading" class="hidden mt-8 flex flex-col items-center justify-center gap-3">
                    <svg class="animate-spin h-8 w-8 text-purple-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <p class="text-slate-400 text-sm animate-pulse">Menghubungkan ke server TikTok...</p>
                </div>

                <div id="error" class="hidden mt-6">
                    <div class="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-xl text-center text-sm font-medium">
                        <span id="errorMessage"></span>
                    </div>
                </div>

                <!-- RESULT -->
                <div id="result" class="hidden mt-8 border-t border-white/10 pt-6">
                    <h3 id="videoTitle" class="text-white text-base font-semibold mb-4 text-center line-clamp-2"></h3>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="bg-black/40 border border-slate-800 rounded-2xl p-3 flex flex-col justify-center items-center min-h-[220px]">
                            <video id="videoPreview" controls class="hidden w-full max-h-[300px] rounded-xl object-contain"></video>
                            
                            <div id="audioPreviewContainer" class="hidden w-full px-2 text-center">
                                <div class="w-16 h-16 bg-purple-500/10 text-purple-400 rounded-full flex items-center justify-center mx-auto mb-3 border border-purple-500/20">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                                </div>
                                <p class="text-xs text-slate-400 mb-3 truncate" id="audioName">Audio Track</p>
                                <audio id="audioPreview" controls class="w-full"></audio>
                            </div>

                            <div id="photoPreviewContainer" class="hidden w-full space-y-3">
                                <p class="text-xs font-semibold text-purple-400 text-center">📸 Postingan Foto Terdeteksi (<span id="photoCount">0</span> Gambar)</p>
                                <div id="photoGrid" class="grid grid-cols-2 gap-2 max-h-[280px] overflow-y-auto p-1"></div>
                            </div>
                        </div>

                        <div class="flex flex-col justify-center gap-3">
                            <span class="text-xs font-semibold text-slate-400 tracking-wider uppercase">Opsi Unduhan:</span>
                            <a id="btnVideoNoWm" href="#" target="_blank" class="hidden items-center justify-center gap-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white py-3 px-4 rounded-xl font-bold text-sm transition-all shadow-md">📥 Video (Tanpa Watermark)</a>
                            <a id="btnVideoWm" href="#" target="_blank" class="hidden items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 py-3 px-4 rounded-xl font-medium text-sm transition-all">📥 Video (Dengan Watermark)</a>
                            <a id="btnAudio" href="#" target="_blank" class="hidden items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white py-3 px-4 rounded-xl font-bold text-sm transition-all shadow-md">🎵 Unduh Audio MP3</a>
                            <div id="photoDownloadAllMsg" class="hidden text-xs text-slate-400 italic text-center p-2 border border-dashed border-slate-700 rounded-xl">Gunakan tombol unduh pada setiap gambar di sebelah kiri.</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- HISTORY -->
            <div class="w-full max-w-2xl mx-auto bg-white/5 backdrop-blur-xl border border-white/10 rounded-[2rem] p-6 shadow-xl">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="font-bold text-base flex items-center gap-2 text-slate-300">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        Riwayat Unduhan Anda
                    </h3>
                    <button onclick="clearHistory()" class="text-xs text-red-400 hover:underline">Hapus Semua</button>
                </div>
                <div id="historyList" class="space-y-2 max-h-[200px] overflow-y-auto pr-1 text-sm text-slate-400">
                    <p class="text-center py-4 text-xs italic">Belum ada riwayat unduhan.</p>
                </div>
            </div>
        </section>

        <!-- PAGE 2: STATISTIK -->
        <section id="page-stats" class="hidden max-w-2xl mx-auto bg-white/5 backdrop-blur-xl border border-white/10 rounded-[2rem] p-8 shadow-2xl space-y-6">
            <h2 class="text-2xl font-bold text-white mb-2 flex items-center gap-2">📊 Live Server Dashboard</h2>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
                <div class="bg-slate-900/60 p-4 rounded-2xl border border-slate-800 text-center">
                    <span class="block text-xs text-slate-400 font-medium">Total Unduhan</span>
                    <span id="stat-downloads" class="text-2xl font-bold text-purple-400 mt-1 block">-</span>
                </div>
                <div class="bg-slate-900/60 p-4 rounded-2xl border border-slate-800 text-center">
                    <span class="block text-xs text-slate-400 font-medium">IP Diblokir (Spam)</span>
                    <span id="stat-blocked" class="text-2xl font-bold text-red-400 mt-1 block">-</span>
                </div>
                <div class="bg-slate-900/60 p-4 rounded-2xl border border-slate-800 text-center">
                    <span class="block text-xs text-slate-400 font-medium">Uptime Server</span>
                    <span id="stat-uptime" class="text-sm font-semibold text-blue-400 mt-2 block">-</span>
                </div>
            </div>
        </section>

        <!-- PAGE 3: ABOUT -->
        <section id="page-about" class="hidden max-w-2xl mx-auto bg-white/5 backdrop-blur-xl border border-white/10 rounded-[2rem] p-8 shadow-2xl space-y-6">
            <h2 class="text-2xl font-bold text-white mb-2">💡 Mengenal Fidownloader</h2>
            <p class="text-slate-300 text-sm leading-relaxed">Fidownloader adalah alat premium berbasis web yang dirancang khusus untuk mengunduh aset media dari TikTok secara bersih, cepat, dan efisien tanpa iklan pop-up mengganggu.</p>
        </section>
    </main>

<script>
function switchPage(pageId) {
    ['home', 'stats', 'about'].forEach(p => {
        document.getElementById(`page-${p}`).classList.add('hidden');
        document.getElementById(`nav-${p}`).classList.remove('active-nav');
    });
    document.getElementById(`page-${pageId}`).classList.remove('hidden');
    document.getElementById(`nav-${pageId}`).classList.add('active-nav');
    if(pageId === 'stats') fetchStats();
}

async function fetchStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        if(data.status !== false) {
            document.getElementById('stat-downloads').innerText = data.total_downloads;
            document.getElementById('stat-blocked').innerText = data.blocked_ips_count;
            document.getElementById('stat-uptime').innerText = data.uptime;
        }
    } catch(err) { console.error("Gagal memuat statistik"); }
}

async function downloadContent() {
    const url = document.getElementById("url").value;
    if (!url) { showError("Mohon masukkan tautan TikTok terlebih dahulu!"); return; }

    document.getElementById("loading").classList.remove("hidden");
    document.getElementById("result").classList.add("hidden");
    document.getElementById("error").classList.add("hidden");

    ['videoPreview','audioPreviewContainer','photoPreviewContainer','btnVideoNoWm','btnVideoWm','btnAudio','photoDownloadAllMsg'].forEach(id=>document.getElementById(id).classList.add("hidden"));

    try {
        const response = await fetch("/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url })
        });

        const data = await response.json();
        document.getElementById("loading").classList.add("hidden");

        if (response.status === 429 || response.status === 403 || data.status === false) {
            showError(data.message || "Permintaan ditolak oleh server.");
            return;
        }

        document.getElementById("result").classList.remove("hidden");
        document.getElementById("videoTitle").innerText = data.title;

        if (data.type === "images" && data.images && data.images.length > 0) {
            document.getElementById("photoPreviewContainer").classList.remove("hidden");
            document.getElementById("photoCount").innerText = data.images.length;
            document.getElementById("photoDownloadAllMsg").classList.remove("hidden");
            const photoGrid = document.getElementById("photoGrid");
            photoGrid.innerHTML = "";
            data.images.forEach((imgUrl, idx) => {
                const item = document.createElement("div");
                item.className = "relative rounded-lg overflow-hidden group border border-slate-800 bg-slate-900";
                item.innerHTML = `<img src="${imgUrl}" class="w-full h-24 object-cover" /><a href="${imgUrl}" target="_blank" class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center text-[10px] text-white font-bold transition-opacity">Unduh #${idx+1}</a>`;
                photoGrid.appendChild(item);
            });
            if (data.audio) setupAudioOption(data.audio);
        } else {
            if (data.video_nowm) {
                document.getElementById("videoPreview").classList.remove("hidden");
                document.getElementById("videoPreview").src = data.video_nowm;
                document.getElementById("btnVideoNoWm").classList.remove("hidden");
                document.getElementById("btnVideoNoWm").href = data.video_nowm;
                if(data.video_wm){
                    document.getElementById("btnVideoWm").classList.remove("hidden");
                    document.getElementById("btnVideoWm").href = data.video_wm;
                }
            }
            if (data.audio) setupAudioOption(data.audio);
        }
        saveToLocalStorage(data.title, url);
    } catch (err) {
        document.getElementById("loading").classList.add("hidden");
        showError("Terjadi kendala jaringan atau IP Anda sedang diblokir.");
    }
}

function setupAudioOption(audioUrl) {
    document.getElementById("audioPreviewContainer").classList.remove("hidden");
    document.getElementById("audioPreview").src = audioUrl;
    document.getElementById("btnAudio").classList.remove("hidden");
    document.getElementById("btnAudio").href = audioUrl;
}

function showError(msg) {
    document.getElementById("error").classList.remove("hidden");
    document.getElementById("errorMessage").innerText = msg;
}

function saveToLocalStorage(title, url) {
    let history = JSON.parse(localStorage.getItem("fidownloader_history")) || [];
    history = history.filter(item => item.url !== url);
    history.unshift({ title, url, time: new Date().toLocaleTimeString() });
    if(history.length > 10) history.pop();
    localStorage.setItem("fidownloader_history", JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    const historyList = document.getElementById("historyList");
    const history = JSON.parse(localStorage.getItem("fidownloader_history")) || [];
    if (history.length === 0) return;
    historyList.innerHTML = "";
    history.forEach(item => {
        const div = document.createElement("div");
        div.className = "flex justify-between items-center bg-slate-900/40 border border-slate-800 p-3 rounded-xl gap-2";
        div.innerHTML = `<div class="truncate flex-1"><p class="text-xs text-slate-200 font-medium truncate">${item.title}</p><span class="text-[10px] text-slate-500">${item.time}</span></div><button onclick="loadHistoryUrl('${item.url}')" class="text-xs font-semibold text-purple-400 hover:text-purple-300">Gunakan Lagi</button>`;
        historyList.appendChild(div);
    });
}

function loadHistoryUrl(url) {
    document.getElementById("url").value = url;
    downloadContent();
}

function clearHistory() {
    localStorage.removeItem("fidownloader_history");
    document.getElementById("historyList").innerHTML = '<p class="text-center py-4 text-xs italic">Belum ada riwayat unduhan.</p>';
}

window.onload = function() { renderHistory(); };
</script>
</body>
</html>
"""

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - Fidownloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 min-h-screen flex items-center justify-center p-4">
    <div class="w-full max-w-md bg-white/5 border border-white/10 rounded-2xl p-8 backdrop-blur-xl shadow-2xl">
        <div class="text-center mb-6">
            <h2 class="text-2xl font-bold text-white">Admin Gate</h2>
            <p class="text-xs text-slate-400 mt-1">Masukkan kredensial kontrol backend Fidownloader</p>
        </div>
        {% if error %}
        <div class="bg-red-500/10 border border-red-500/30 text-red-400 p-3 rounded-xl text-xs text-center mb-4">{{ error }}</div>
        {% endif %}
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-medium text-slate-400 mb-1">Username</label>
                <input type="text" name="username" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-purple-500">
            </div>
            <div>
                <label class="block text-xs font-medium text-slate-400 mb-1">Password</label>
                <input type="password" name="password" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-purple-500">
            </div>
            <button type="submit" class="w-full bg-purple-600 hover:bg-purple-500 text-white font-semibold py-3 rounded-xl text-sm transition-all">Masuk Kontrol</button>
        </form>
    </div>
</body>
</html>
"""

HTML_ADMIN = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Control Panel Admin - Fidownloader</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body { font-family: 'Poppins', sans-serif; }</style>
</head>
<body class="bg-slate-950 min-h-screen text-slate-100 p-4 sm:p-8">

    <div class="max-w-6xl mx-auto space-y-8">
        <!-- HEADER ADMIN -->
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center bg-white/5 border border-white/10 rounded-2xl p-6 gap-4">
            <div>
                <h1 class="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500">Fidownloader Admin Control</h1>
                <p class="text-xs text-slate-400">Kelola blokir IP Firewall dan pantau Traffic LOG secara Live.</p>
            </div>
            <div class="flex gap-2">
                <a href="/" target="_blank" class="bg-slate-800 hover:bg-slate-700 px-4 py-2 rounded-xl text-xs font-semibold">Buka Web Utama</a>
                <a href="/admin/logout" class="bg-red-600/20 hover:bg-red-600 border border-red-500/30 px-4 py-2 rounded-xl text-xs font-semibold text-red-200 hover:text-white transition-all">Log Out</a>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- LEFT COLUMN: MANAGE IP -->
            <div class="space-y-6">
                <!-- FORM BLOCK MANUAL -->
                <div class="bg-white/5 border border-white/10 rounded-2xl p-6">
                    <h3 class="text-sm font-bold text-slate-200 mb-3">Ban IP Manual</h3>
                    <div class="space-y-3">
                        <input type="text" id="targetIp" placeholder="Contoh: 192.168.1.1" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-xs text-white outline-none focus:border-red-500">
                        <button onclick="blockIp()" class="w-full bg-red-600 hover:bg-red-500 text-white font-semibold py-2.5 rounded-xl text-xs transition-all">Blokir IP Sekarang</button>
                    </div>
                </div>

                <!-- LIST IP BLOCKED -->
                <div class="bg-white/5 border border-white/10 rounded-2xl p-6">
                    <h3 class="text-sm font-bold text-slate-200 mb-3">Daftar IP Diblokir (<span id="countBlock">0</span>)</h3>
                    <div class="overflow-y-auto max-h-[300px] space-y-2 pr-1" id="blockIpList">
                        <!-- Rendered via JS -->
                    </div>
                </div>
            </div>

            <!-- RIGHT COLUMN: LIVE LOGS -->
            <div class="lg:col-span-2 bg-white/5 border border-white/10 rounded-2xl p-6 flex flex-col min-h-[400px]">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-sm font-bold text-slate-200">Live Server Traffic LOG (50 Terakhir)</h3>
                    <button onclick="fetchAdminData()" class="text-xs bg-purple-600/30 hover:bg-purple-600 px-3 py-1.5 rounded-lg text-purple-200 hover:text-white transition-all">Refresh Logs</button>
                </div>
                <div class="overflow-x-auto flex-1">
                    <table class="w-full text-left text-xs border-collapse">
                        <thead>
                            <tr class="border-b border-slate-800 text-slate-400 font-semibold bg-black/20">
                                <th class="p-3">Waktu</th>
                                <th class="p-3">IP Address</th>
                                <th class="p-3">Endpoint</th>
                                <th class="p-3">Method</th>
                                <th class="p-3">Status Middleware</th>
                            </tr>
                        </thead>
                        <tbody id="logTableBody" class="divide-y divide-slate-900 text-slate-300">
                            <!-- Rendered via JS -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

<script>
async function fetchAdminData() {
    try {
        const response = await fetch('/api/admin/data');
        const data = await response.json();
        
        // Render Banned IP
        const ipListDiv = document.getElementById("blockIpList");
        document.getElementById("countBlock").innerText = data.blocked_ips.length;
        if(data.blocked_ips.length === 0){
            ipListDiv.innerHTML = '<p class="text-xs italic text-slate-500 text-center py-4">Tidak ada IP yang terblokir.</p>';
        } else {
            ipListDiv.innerHTML = "";
            data.blocked_ips.forEach(item => {
                const div = document.createElement("div");
                div.className = "flex justify-between items-center bg-slate-900/60 border border-slate-800 px-3 py-2.5 rounded-xl text-xs";
                div.innerHTML = `
                    <div>
                        <span class="font-mono text-slate-200 block">${item.ip}</span>
                        <span class="text-[10px] ${item.type === 'MANUAL' ? 'text-red-400':'text-orange-400'}">${item.type}</span>
                    </div>
                    <button onclick="unblockIp('${item.ip}')" class="text-[11px] font-medium bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600 hover:text-white px-2 py-1 rounded-md transition-all">Lepas</button>
                `;
                ipListDiv.appendChild(div);
            });
        }

        // Render Logs Table
        const tbody = document.getElementById("logTableBody");
        if(data.logs.length === 0){
            tbody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-slate-500 italic">Belum ada logs masuk...</td></tr>';
        } else {
            tbody.innerHTML = "";
            data.logs.forEach(log => {
                const tr = document.createElement("tr");
                tr.className = "hover:bg-white/5 transition-colors";
                let statusColor = "text-emerald-400";
                if(log.status.includes("BLOCKED")) statusColor = "text-red-400 font-semibold";
                if(log.status.includes("TRIGGERED")) statusColor = "text-orange-400 font-bold";
                
                tr.innerHTML = `
                    <td class="p-3 font-mono text-slate-400 text-[11px]">${log.waktu}</td>
                    <td class="p-3 font-mono font-medium">${log.ip}</td>
                    <td class="p-3 text-slate-400">${log.path}</td>
                    <td class="p-3"><span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-800">${log.method}</span></td>
                    <td class="p-3 ${statusColor}">${log.status}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch(err) { console.error("Gagal sinkronisasi data panel admin."); }
}

async function blockIp() {
    const ip = document.getElementById("targetIp").value.trim();
    if(!ip) return;
    const res = await fetch('/api/admin/block', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ip })
    });
    const d = await res.json();
    if(d.status) {
        document.getElementById("targetIp").value = "";
        fetchAdminData();
    }
}

async function unblockIp(ip) {
    const res = await fetch('/api/admin/unblock', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ip })
    });
    const d = await res.json();
    if(d.status) fetchAdminData();
}

// Auto update dashboard admin setiap 5 detik sekali
window.onload = function() {
    fetchAdminData();
    setInterval(fetchAdminData, 5000);
}
</script>
</body>
</html>
"""

# ==============================================================================
# ROUTING CONTROLLER USER & STATS
# ==============================================================================
@app.route("/")
def home():
    return render_template_string(HTML_USER)

@app.route("/download", methods=["POST"])
def download():
    global TOTAL_DOWNLOADS
    data = request.get_json() or {}
    url = data.get("url")
    
    if not url:
        return jsonify({"status": False, "message": "Tautan kosong!"}), 400
        
    try:
        import requests
        api = f"https://www.tikwm.com/api/?url={url}"
        response = requests.get(api, timeout=12).json()
        
        if response.get("code") != 0:
            return jsonify({"status": False, "message": "Video tidak ditemukan atau tautan salah."})
            
        res_data = response.get("data", {})
        TOTAL_DOWNLOADS += 1 
        
        media_type = "video"
        images_list = res_data.get("images", [])
        if images_list:
            media_type = "images"
            
        audio_link = res_data.get("music", res_data.get("music_info", {}).get("play", ""))

        return jsonify({
            "status": True,
            "type": media_type,
            "title": res_data.get("title", "Aset Media TikTok"),
            "video_nowm": res_data.get("play"),
            "video_wm": res_data.get("wmplay"),
            "images": images_list,
            "audio": audio_link
        })
        
    except Exception as e:
        return jsonify({"status": False, "message": f"Server Error: {str(e)}"})

@app.route("/api/stats")
def server_stats():
    uptime_seconds = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_string = f"{hours}j {minutes}m {seconds}d"
    
    # Hitung jumlah IP yang sedang terblokir aktif
    return jsonify({
        "status": True,
        "total_downloads": TOTAL_DOWNLOADS,
        "blocked_ips_count": len(blocked_ips),
        "uptime": uptime_string
    })

# ==============================================================================
# ROUTING ADMIN CONTROLLER (LOGIN, MANAGEMENT & LOG INTERFACES)
# ==============================================================================
@app.route("/admin", methods=["GET", "POST"])
def admin_portal():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == "admin" and password == "admin":
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            return render_template_string(HTML_LOGIN, error="Kredensial Salah! Periksa Username / Password.")
            
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return render_template_string(HTML_LOGIN, error=None)

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin_portal"))
    return render_template_string(HTML_ADMIN)

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_portal"))

# ==============================================================================
# API ENDPOINT INTERNAL ADMIN (XHR REQUESTS)
# ==============================================================================
@app.route("/api/admin/data")
def api_admin_data():
    if not session.get("is_admin"):
        return jsonify({"status": False, "message": "Unauthorized"}), 401
        
    current_time = time.time()
    formatted_banned_ips = []
    
    for ip, val in list(blocked_ips.items()):
        if val == "MANUAL":
            formatted_banned_ips.append({"ip": ip, "type": "MANUAL"})
        else:
            if current_time < val:
                remaining = int(val - current_time)
                formatted_banned_ips.append({"ip": ip, "type": f"AUTO-BAN ({remaining}s)"})
            else:
                del blocked_ips[ip]

    return jsonify({
        "status": True,
        "blocked_ips": formatted_banned_ips,
        "logs": SYSTEM_LOGS
    })

@app.route("/api/admin/block", methods=["POST"])
def api_admin_block():
    if not session.get("is_admin"):
        return jsonify({"status": False, "message": "Unauthorized"}), 401
    data = request.get_json() or {}
    ip = data.get("ip")
    if ip:
        blocked_ips[ip] = "MANUAL"
        return jsonify({"status": True, "message": f"IP {ip} berhasil diblokir manual."})
    return jsonify({"status": False, "message": "IP target kosong"}), 400

@app.route("/api/admin/unblock", methods=["POST"])
def api_admin_unblock():
    if not session.get("is_admin"):
        return jsonify({"status": False, "message": "Unauthorized"}), 401
    data = request.get_json() or {}
    ip = data.get("ip")
    if ip in blocked_ips:
        del blocked_ips[ip]
        # Bersihkan histori spam IP tersebut agar bisa request lagi secara bersih
        if ip in request_history:
            del request_history[ip]
        return jsonify({"status": True, "message": f"IP {ip} berhasil dilepas."})
    return jsonify({"status": False, "message": "IP tidak ditemukan dalam daftar blokir."}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
