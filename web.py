import os
import json
import queue
import logging
import threading
from flask import (
    Flask, render_template_string, send_from_directory, jsonify, Response,
    request, redirect
)
from config import WEB_HOST, WEB_PORT, BASE_DIR
from auth import require_auth

logger = logging.getLogger(__name__)

app     = Flask(__name__)
storage = None

# ── SSE event queue ───────────────────────────────────────────────────
_event_listeners      = []
_event_listeners_lock = threading.Lock()


def push_event(event_type, data):
    """Send SSE event to all connected clients."""
    message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _event_listeners_lock:
        dead = []
        for q in _event_listeners:
            try:
                q.put_nowait(message)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _event_listeners.remove(q)


# ── HTML Template ─────────────────────────────────────────────────────
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Security Camera</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;background:#0f0f0f;color:#eee;padding:20px}
    h1{color:#fff;margin-bottom:4px;font-size:1.6em}
    .subtitle{color:#666;font-size:.85em;margin-bottom:20px}
    h2{color:#ccc;margin:24px 0 10px;border-bottom:1px solid #222;padding-bottom:5px;font-size:1.1em}

    .statusbar{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
    .stat{background:#1a1a1a;border-radius:8px;padding:10px 16px;font-size:.82em;color:#aaa}
    .stat span{color:#fff;font-weight:bold}
    .dot{display:inline-block;width:8px;height:8px;border-radius:50%;
         background:#4caf50;margin-right:6px;animation:pulse 2s infinite}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

    #toast{position:fixed;top:20px;right:20px;background:#1e3a1e;border:1px solid #4caf50;
           border-radius:8px;padding:12px 18px;font-size:.85em;color:#a5d6a7;
           display:none;z-index:999;max-width:min(300px,calc(100vw - 40px))}
    #toast.show{display:block;animation:fadein .3s}
    @keyframes fadein{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:none}}

    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
    /* recordings hold a full video player + control bar — keep them wide enough */
    #rec-container{grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
    .card{background:#1a1a1a;border-radius:8px;overflow:hidden;transition:transform .2s}
    .card:hover{transform:scale(1.02)}
    .card img{width:100%;display:block;aspect-ratio:16/9;object-fit:cover;cursor:pointer}
    .player{background:#000}
    .player video{width:100%;display:block;aspect-ratio:16/9;background:#000}
    .player:fullscreen,.player:-webkit-full-screen{display:flex;flex-direction:column;justify-content:center}
    .player:fullscreen video,.player:-webkit-full-screen video{flex:1;min-height:0;aspect-ratio:auto;object-fit:contain}
    .vbar{display:flex;align-items:center;gap:6px;padding:6px 8px;background:#111}
    .vbtn{background:none;border:none;color:#ddd;cursor:pointer;padding:2px;display:flex;align-items:center}
    .vbtn:hover{color:#fff}
    .vbtn svg{width:18px;height:18px;fill:currentColor}
    .vseek{flex:1;min-width:30px;accent-color:#4a9eff;cursor:pointer}
    .vtime{color:#aaa;font-size:.72em;white-space:nowrap}
    .card-info{padding:8px 12px;font-size:.78em;color:#888}
    .card-info .label{color:#fff;font-weight:bold;text-transform:capitalize}
    .card-info a{color:#4a9eff;text-decoration:none;font-size:.85em}
    .rec-noimg{width:100%;aspect-ratio:16/9;display:flex;align-items:center;
               justify-content:center;background:#222;font-size:.85em;color:#555}
    .new-badge{background:#4caf50;color:#000;font-size:.7em;
               padding:2px 6px;border-radius:4px;margin-left:6px;font-weight:bold}

    .rec-list{list-style:none}
    .rec-list li{background:#1a1a1a;margin-bottom:6px;padding:10px 14px;
                 border-radius:6px;display:flex;justify-content:space-between;align-items:center}
    .rec-list a{color:#4a9eff;text-decoration:none;font-size:.82em}
    .rec-list a:hover{text-decoration:underline}

    .disk-bar-bg{background:#333;border-radius:4px;height:6px;margin-top:4px;width:120px;display:inline-block}
    .disk-bar-fill{height:6px;border-radius:4px;background:#4caf50;transition:width .5s}
    .disk-bar-fill.warn{background:#ff9800}
    .disk-bar-fill.danger{background:#f44336}

    .empty{color:#444;font-style:italic;padding:12px 0;font-size:.9em}

    #lightbox{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;
              align-items:center;justify-content:center;z-index:1000;cursor:zoom-out;padding:20px}
    #lightbox.show{display:flex}
    #lightbox img{max-width:95%;max-height:95%;border-radius:8px;box-shadow:0 0 40px rgba(0,0,0,.8);
                  cursor:grab}
    #lightbox img:active{cursor:grabbing}

    @media (max-width: 600px) {
      body{padding:12px}
      h1{font-size:1.3em}
      .statusbar{gap:10px}
      .stat{padding:8px 12px;font-size:.78em}
      .grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
      /* one recording per row on phones so the control bar always fits */
      #rec-container{grid-template-columns:1fr}
      .vseek{min-width:20px}
    }
  </style>
</head>
<body>
<div id="toast"></div>
<div id="lightbox"><img id="lightbox-img" src="" alt=""></div>

<h1>Security Camera</h1>
<p class="subtitle">Live updates via Server-Sent Events &nbsp;·&nbsp;
  <a href="/settings" style="color:#4a9eff;text-decoration:none">Settings</a></p>

<div class="statusbar">
  <div class="stat"><span class="dot"></span>System running</div>
  <div class="stat">Snapshots: <span id="snap-count">{{ stats.snapshots }}</span></div>
  <div class="stat">Recordings: <span id="rec-count">{{ stats.recordings }}</span></div>
  <div class="stat">
    Disk: <span id="disk-pct">{{ stats.disk_percent }}%</span>
    ({{ stats.disk_used_gb }} / {{ stats.disk_total_gb }} GB)
    <div class="disk-bar-bg">
      <div class="disk-bar-fill {% if stats.disk_percent > 85 %}danger{% elif stats.disk_percent > 70 %}warn{% endif %}"
           id="disk-bar" style="width:{{ stats.disk_percent }}%"></div>
    </div>
  </div>
</div>

<h2>Recent snapshots</h2>
<div class="grid" id="snap-grid">
  {% if snapshots %}
    {% for snap in snapshots[:12] %}
    <div class="card">
      <img src="/snapshots/{{ snap }}" alt="{{ snap }}" loading="lazy">
      <div class="card-info">
        {% set parts = snap.replace('.jpg','').split('_') %}
        <span class="label">{{ parts[2] if parts|length > 2 else '' }}</span>
        &nbsp;·&nbsp; {{ parts[1][:2] }}:{{ parts[1][2:4] }}:{{ parts[1][4:6] }}
      </div>
    </div>
    {% endfor %}
  {% else %}
    <p class="empty">No snapshots yet. The first detection will appear here.</p>
  {% endif %}
</div>

<h2>Recordings</h2>
<div id="rec-container" class="grid"><p class="empty">Loading…</p></div>

<script>
const toast = document.getElementById('toast');

const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightbox-img');
let lbScale = 1, lbX = 0, lbY = 0;
let lbDragging = false, lbMoved = false, lbStartX = 0, lbStartY = 0;

function lbApply() {
  lightboxImg.style.transform =
    'translate(' + lbX + 'px,' + lbY + 'px) scale(' + lbScale + ')';
}

function openLightbox(src) {
  lbScale = 1; lbX = 0; lbY = 0;
  lbApply();
  lightboxImg.src = src;
  lightbox.classList.add('show');
}

document.getElementById('snap-grid').addEventListener('click', e => {
  if (e.target.tagName === 'IMG') openLightbox(e.target.src);
});
document.getElementById('rec-container').addEventListener('click', e => {
  if (e.target.tagName === 'IMG') openLightbox(e.target.src);
});

// Wheel zooms (1x-5x); drag pans when zoomed; click closes (unless dragging).
lightbox.addEventListener('wheel', e => {
  e.preventDefault();
  lbScale = Math.max(1, Math.min(5, lbScale + (e.deltaY < 0 ? 0.25 : -0.25)));
  if (lbScale === 1) { lbX = 0; lbY = 0; }
  lbApply();
}, { passive: false });

lightboxImg.addEventListener('mousedown', e => {
  if (lbScale <= 1) return;
  e.preventDefault();
  lbDragging = true; lbMoved = false;
  lbStartX = e.clientX - lbX;
  lbStartY = e.clientY - lbY;
});
window.addEventListener('mousemove', e => {
  if (!lbDragging) return;
  lbX = e.clientX - lbStartX;
  lbY = e.clientY - lbStartY;
  lbMoved = true;
  lbApply();
});
window.addEventListener('mouseup', () => { lbDragging = false; });

lightbox.addEventListener('click', () => {
  if (lbMoved) { lbMoved = false; return; }
  lightbox.classList.remove('show');
});

// Touch: pinch to zoom (1x-5x), one finger to pan when zoomed, tap to close.
function lbTouchDist(t) {
  return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
}
let lbPinch = 0;
lightbox.addEventListener('touchstart', e => {
  if (e.touches.length === 2) {
    lbPinch = lbTouchDist(e.touches);
    lbMoved = true;
  } else if (e.touches.length === 1 && lbScale > 1) {
    lbDragging = true; lbMoved = false;
    lbStartX = e.touches[0].clientX - lbX;
    lbStartY = e.touches[0].clientY - lbY;
  }
}, { passive: false });
lightbox.addEventListener('touchmove', e => {
  if (e.touches.length === 2 && lbPinch) {
    e.preventDefault();
    const d = lbTouchDist(e.touches);
    lbScale = Math.max(1, Math.min(5, lbScale * (d / lbPinch)));
    if (lbScale === 1) { lbX = 0; lbY = 0; }
    lbPinch = d; lbMoved = true;
    lbApply();
  } else if (e.touches.length === 1 && lbDragging) {
    e.preventDefault();
    lbX = e.touches[0].clientX - lbStartX;
    lbY = e.touches[0].clientY - lbStartY;
    lbMoved = true;
    lbApply();
  }
}, { passive: false });
lightbox.addEventListener('touchend', e => {
  if (e.touches.length === 0) { lbPinch = 0; lbDragging = false; }
});

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 4000);
}

function addSnapshot(filename) {
  const grid = document.getElementById('snap-grid');
  const empty = grid.querySelector('.empty');
  if (empty) empty.remove();

  const cards = grid.querySelectorAll('.card');
  if (cards.length >= 12) cards[cards.length - 1].remove();

  const parts = filename.replace('.jpg','').split('_');
  const label = parts[2] || '';
  const time  = parts[1]
    ? `${parts[1].slice(0,2)}:${parts[1].slice(2,4)}:${parts[1].slice(4,6)}`
    : '';

  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = `
    <img src="/snapshots/${filename}" alt="${filename}" loading="lazy">
    <div class="card-info">
      <span class="label">${label}</span>
      <span class="new-badge">NEW</span>
      &nbsp;·&nbsp; ${time}
    </div>`;
  grid.insertBefore(card, grid.firstChild);

  setTimeout(() => {
    const badge = card.querySelector('.new-badge');
    if (badge) badge.remove();
  }, 5000);
}

const evtSource = new EventSource('/stream');

evtSource.addEventListener('detection', e => {
  const data = JSON.parse(e.data);
  const labels = data.labels.join(', ');
  showToast('Detected: ' + labels);
});

evtSource.addEventListener('snapshot', e => {
  const data = JSON.parse(e.data);
  addSnapshot(data.filename);
  document.getElementById('snap-count').textContent = data.total;
});

evtSource.addEventListener('recording_start', e => {
  showToast('Recording started');
  refreshRecordings();
});

evtSource.addEventListener('recording_stop', e => {
  const data = JSON.parse(e.data);
  document.getElementById('rec-count').textContent = data.total;
  showToast('Recording stopped');
  refreshRecordings();
});

const SVG_PLAY  = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
const SVG_PAUSE = '<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>';
const SVG_BACK  = '<svg viewBox="0 0 24 24"><path d="M11 7L5 12l6 5V7zm7 0l-6 5 6 5V7z"/></svg>';
const SVG_FWD   = '<svg viewBox="0 0 24 24"><path d="M13 7l6 5-6 5V7zM6 7l6 5-6 5V7z"/></svg>';
const SVG_FULL  = '<svg viewBox="0 0 24 24"><path d="M7 7h4V5H5v6h2V7zm10 0v4h2V5h-6v2h4zM7 17v-4H5v6h6v-2H7zm10 0h-4v2h6v-6h-2v4z"/></svg>';

function fmtTime(s) {
  s = Math.floor(s || 0);
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

// the video the user last interacted with — the Space key controls this one
let activeVideo = null;

function togglePlay(v) {
  if (!v) return;
  if (v.paused) v.play(); else v.pause();
}
function skip(v, secs) {
  if (!v || !v.duration) return;
  v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + secs));
}
// Same button enters AND exits fullscreen. Desktop/Android/iPad fullscreen the
// player box; iPhone can only fullscreen the <video> (it has its own exit).
function toggleFullscreen(p, v) {
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    (document.exitFullscreen || document.webkitExitFullscreen).call(document);
  } else if (p.requestFullscreen) {
    p.requestFullscreen();
  } else if (p.webkitRequestFullscreen) {
    p.webkitRequestFullscreen();
  } else if (v.webkitEnterFullscreen) {
    v.webkitEnterFullscreen();
  }
}

// Space toggles play/pause on the active video (or the first one).
// Ignored while typing in an input or dragging the seek bar.
document.addEventListener('keydown', e => {
  if (e.code !== 'Space' && e.key !== ' ') return;
  const t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
  const v = activeVideo || document.querySelector('#rec-container video');
  if (!v) return;
  e.preventDefault();
  togglePlay(v);
});

// hook up the custom controls after each render
function wirePlayers() {
  document.querySelectorAll('#rec-container .player').forEach(p => {
    const v = p.querySelector('video');
    const seek = p.querySelector('.vseek');
    const time = p.querySelector('.vtime');
    const playBtn = p.querySelector('[data-act="play"]');

    p.querySelectorAll('.vbtn').forEach(b => b.addEventListener('click', () => {
      const a = b.dataset.act;
      activeVideo = v;
      if (a === 'play') togglePlay(v);
      else if (a === 'back') skip(v, -10);
      else if (a === 'fwd')  skip(v, 10);
      else if (a === 'full') toggleFullscreen(p, v);
    }));

    // single click = play/pause; double click = skip ±10s.
    // delay the single click briefly so a double click can cancel it.
    let clickTimer = null;
    v.addEventListener('click', () => {
      activeVideo = v;
      if (clickTimer) return;
      clickTimer = setTimeout(() => { clickTimer = null; togglePlay(v); }, 220);
    });
    v.addEventListener('dblclick', e => {
      if (clickTimer) { clearTimeout(clickTimer); clickTimer = null; }
      e.preventDefault();
      const rect = v.getBoundingClientRect();
      const back = (e.clientX - rect.left) < rect.width / 2;
      skip(v, back ? -10 : 10);
    });

    v.addEventListener('play',  () => { activeVideo = v; playBtn.innerHTML = SVG_PAUSE; });
    v.addEventListener('pause', () => { playBtn.innerHTML = SVG_PLAY; });
    v.addEventListener('timeupdate', () => {
      if (v.duration) {
        seek.value = (v.currentTime / v.duration) * 1000;
        time.textContent = fmtTime(v.currentTime) + ' / ' + fmtTime(v.duration);
      }
    });
    seek.addEventListener('input', () => {
      if (v.duration) v.currentTime = (seek.value / 1000) * v.duration;
    });
  });
}

function renderRecordings(list) {
  const c = document.getElementById('rec-container');
  if (!c) return;
  if (!list.length) {
    c.innerHTML = '<p class="empty">No recordings yet.</p>';
    return;
  }
  c.innerHTML = list.slice(0, 24).map(rec => {
    const ts = rec.file.split('_').slice(0, 2).join('_');
    const d = ts.slice(0, 8), t = ts.slice(9, 15);
    const date = d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8);
    const time = t.slice(0,2)+':'+t.slice(2,4)+':'+t.slice(4,6);
    const poster = rec.thumb ? ' poster="/snapshots/'+rec.thumb+'"' : '';
    const media = rec.file.endsWith('.mp4')
      ? '<div class="player"><video playsinline webkit-playsinline preload="none"'+poster+' src="/recordings/'+rec.file+'"></video>'
        + '<div class="vbar">'
        +   '<button class="vbtn" data-act="play" title="Play/pause">'+SVG_PLAY+'</button>'
        +   '<button class="vbtn" data-act="back" title="Back 10s">'+SVG_BACK+'</button>'
        +   '<button class="vbtn" data-act="fwd" title="Forward 10s">'+SVG_FWD+'</button>'
        +   '<input type="range" class="vseek" min="0" max="1000" value="0">'
        +   '<span class="vtime">0:00</span>'
        +   '<button class="vbtn" data-act="full" title="Fullscreen">'+SVG_FULL+'</button>'
        + '</div></div>'
      : (rec.thumb
          ? '<img src="/snapshots/'+rec.thumb+'" loading="lazy" alt="">'
          : '<div class="rec-noimg">no preview</div>');
    return '<div class="card">'+media+
      '<div class="card-info"><span class="label">'+date+' '+time+'</span>'+
      '<div><a href="/recordings/'+rec.file+'" download>Download</a></div>'+
      '</div></div>';
  }).join('');
  wirePlayers();
}

function refreshRecordings() {
  fetch('/api/recordings').then(r => r.json()).then(renderRecordings).catch(() => {});
}

evtSource.addEventListener('disk', e => {
  const data = JSON.parse(e.data);
  document.getElementById('disk-pct').textContent = data.percent + '%';
  const bar = document.getElementById('disk-bar');
  bar.style.width = data.percent + '%';
  bar.className = 'disk-bar-fill' +
    (data.percent > 85 ? ' danger' : data.percent > 70 ? ' warn' : '');
});

evtSource.onerror = () => {
  console.warn('SSE connection lost — retrying...');
};

refreshRecordings();
</script>
</body>
</html>
'''


SETTINGS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Settings - Security Camera</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;background:#0f0f0f;color:#eee;padding:20px;max-width:560px;margin:0 auto}
    a.back{color:#4a9eff;text-decoration:none;font-size:.9em}
    h1{font-size:1.4em;margin:14px 0 4px}
    .sub{color:#666;font-size:.85em;margin-bottom:18px}
    .card{background:#1a1a1a;border-radius:8px;padding:20px}
    label{display:block;margin:14px 0 4px;font-size:.85em;color:#ccc}
    input[type=text],input[type=password]{width:100%;padding:10px;border-radius:6px;
      border:1px solid #333;background:#111;color:#eee;font-size:.9em}
    input::placeholder{color:#555}
    .row{display:flex;align-items:center;gap:8px;margin:18px 0 4px}
    .row input{width:auto}
    .hint{color:#777;font-size:.75em;margin-top:4px}
    .saved-token{color:#4caf50;font-size:.78em;margin-top:6px}
    button{margin-top:20px;background:#2a8a4a;border:none;color:#fff;padding:11px 22px;
      border-radius:6px;font-size:.9em;cursor:pointer}
    button:hover{background:#33a557}
    .note{background:#16242f;border:1px solid #2d4a6a;border-radius:6px;padding:12px 14px;
      font-size:.78em;color:#9cc;margin-top:16px;line-height:1.5}
    .ok{background:#1e3a1e;border:1px solid #4caf50;border-radius:6px;padding:12px 14px;
      font-size:.85em;color:#a5d6a7;margin-bottom:16px;line-height:1.5}
    code{background:#000;padding:1px 5px;border-radius:3px;font-size:.92em}
  </style>
</head>
<body>
<a class="back" href="/">&larr; Back to dashboard</a>
<h1>Telegram alerts</h1>
<p class="sub">Receive a photo alert on detection and control the camera from the bot.</p>

{% if saved %}
<div class="ok">Saved. Apply it by restarting the service on the Pi:<br>
  <code>sudo systemctl restart security-camera</code></div>
{% endif %}

<form method="POST" action="/settings" autocomplete="off">
  <div class="card">
    <label for="bot_token">Bot token</label>
    <input type="password" id="bot_token" name="bot_token" autocomplete="new-password"
      placeholder="{{ 'Leave blank to keep the saved token' if has_token else 'Paste the token from @BotFather' }}">
    {% if has_token %}<div class="saved-token">A token is already saved. Leave this blank to keep it.</div>{% endif %}

    <label for="chat_id">Chat ID</label>
    <input type="text" id="chat_id" name="chat_id" value="{{ chat_id }}"
      placeholder="e.g. 123456789 (from @userinfobot)">

    <div class="row">
      <input type="checkbox" id="enabled" name="enabled" {{ 'checked' if enabled else '' }}>
      <label for="enabled" style="margin:0">Enable Telegram alerts</label>
    </div>
    <div class="hint">Enabling needs both a saved token and a chat ID.</div>

    <button type="submit">Save</button>
  </div>
</form>

<div class="note">
  Stored on the Pi in <code>telegram_settings.json</code> (never committed to the repository),
  and applied on the next service restart. For security the token is never shown back here once saved.
</div>
</body>
</html>
'''


def _tg_settings_path():
    return os.path.join(BASE_DIR, 'telegram_settings.json')


def _load_tg_settings():
    """Read the saved Telegram form settings; {} if the file is missing/unreadable."""
    try:
        with open(_tg_settings_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_tg_settings(data):
    path = _tg_settings_path()
    with open(path, 'w') as f:
        json.dump(data, f)
    try:
        os.chmod(path, 0o600)   # credentials file — owner read/write only
    except Exception:
        pass


# ── Routes ────────────────────────────────────────────────────────────

@app.route('/')
@require_auth
def index():
    snapshots  = storage.list_snapshots()  if storage else []
    recordings = storage.list_recordings() if storage else []
    stats      = storage.get_stats()       if storage else {}
    resp = app.make_response(render_template_string(
        HTML_TEMPLATE,
        snapshots=snapshots,
        recordings=recordings,
        stats=stats
    ))
    # don't cache the page so UI changes always show up
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/stream')
@require_auth
def stream():
    """SSE endpoint — clients wait for real-time events."""
    def event_generator():
        q = queue.Queue(maxsize=50)
        with _event_listeners_lock:
            _event_listeners.append(q)
        try:
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            with _event_listeners_lock:
                if q in _event_listeners:
                    _event_listeners.remove(q)

    return Response(
        event_generator(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':     'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/snapshots/<filename>')
@require_auth
def serve_snapshot(filename):
    return send_from_directory(storage.snapshots_dir, filename)


@app.route('/recordings/<filename>')
@require_auth
def serve_recording(filename):
    return send_from_directory(storage.recordings_dir, filename)


@app.route('/api/status')
@require_auth
def api_status():
    stats = storage.get_stats() if storage else {}
    return jsonify(stats)


@app.route('/api/recordings')
@require_auth
def api_recordings():
    return jsonify(storage.list_recordings_with_thumbs() if storage else [])


@app.route('/settings', methods=['GET', 'POST'])
@require_auth
def settings_page():
    if request.method == 'POST':
        s = _load_tg_settings()
        token = request.form.get('bot_token', '').strip()
        chat  = request.form.get('chat_id', '').strip()
        enabled = request.form.get('enabled') == 'on'
        if token:                       # blank = keep the existing token
            s['bot_token'] = token
        s['chat_id'] = chat
        # only store enabled=true if we actually have both credentials
        s['enabled'] = bool(enabled and s.get('bot_token') and chat)
        _save_tg_settings(s)
        logger.info("Telegram settings updated via web form")
        return redirect('/settings?saved=1')

    s = _load_tg_settings()
    resp = app.make_response(render_template_string(
        SETTINGS_TEMPLATE,
        enabled=bool(s.get('enabled')),
        chat_id=s.get('chat_id', ''),
        has_token=bool(s.get('bot_token')),
        saved=request.args.get('saved') == '1',
    ))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


# ── Startup ───────────────────────────────────────────────────────────
def start_web(storage_manager):
    global storage
    storage = storage_manager

    from config import SSL_ENABLED, SSL_CERT, SSL_KEY
    if SSL_ENABLED and os.path.exists(SSL_CERT) and os.path.exists(SSL_KEY):
        protocol = "https"
        ssl_context = (SSL_CERT, SSL_KEY)
    else:
        protocol = "http"
        ssl_context = None
        logger.warning("SSL not configured — running over plain HTTP")

    logger.info(f"Web interface: {protocol}://raspberrypi.local:{WEB_PORT}")
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(
        host=WEB_HOST,
        port=WEB_PORT,
        threaded=True,
        use_reloader=False,
        ssl_context=ssl_context
    )
