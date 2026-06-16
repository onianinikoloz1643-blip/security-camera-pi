import os
import json
import queue
import logging
import threading
from flask import Flask, render_template_string, send_from_directory, jsonify, Response
from config import WEB_HOST, WEB_PORT
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
           display:none;z-index:999;max-width:300px}
    #toast.show{display:block;animation:fadein .3s}
    @keyframes fadein{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:none}}

    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
    .card{background:#1a1a1a;border-radius:8px;overflow:hidden;transition:transform .2s}
    .card:hover{transform:scale(1.02)}
    .card img{width:100%;display:block;aspect-ratio:16/9;object-fit:cover;cursor:pointer}
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
  </style>
</head>
<body>
<div id="toast"></div>
<div id="lightbox"><img id="lightbox-img" src="" alt=""></div>

<h1>Security Camera</h1>
<p class="subtitle">Live updates via Server-Sent Events</p>

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
    const thumb = rec.thumb
      ? '<img src="/snapshots/'+rec.thumb+'" loading="lazy" alt="">'
      : '<div class="rec-noimg">no preview</div>';
    return '<div class="card">'+thumb+
      '<div class="card-info"><span class="label">'+date+' '+time+'</span>'+
      '<div><a href="/recordings/'+rec.file+'" download>Download</a></div>'+
      '</div></div>';
  }).join('');
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


# ── Routes ────────────────────────────────────────────────────────────

@app.route('/')
@require_auth
def index():
    snapshots  = storage.list_snapshots()  if storage else []
    recordings = storage.list_recordings() if storage else []
    stats      = storage.get_stats()       if storage else {}
    return render_template_string(
        HTML_TEMPLATE,
        snapshots=snapshots,
        recordings=recordings,
        stats=stats
    )


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
