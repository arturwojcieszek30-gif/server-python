import os
import secrets
import sqlite3
import tempfile
import uuid

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_file,
    session,
)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

HOST = "0.0.0.0"  # nasłuchuje w całej sieci, czyli też pod 192.168.1.108
PORT = 5000       # adres: http://192.168.1.108:5000

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")
TEMP_DIR = os.path.join(BASE, "tmp")
DB_PATH = os.path.join(BASE, "chomik.db")
KEY_PATH = os.path.join(BASE, "secret.key")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
tempfile.tempdir = TEMP_DIR


def load_secret_key():
    # klucz sesji zapisany raz w pliku, żeby logowanie przeżyło restart serwera
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(KEY_PATH, "w") as f:
        f.write(key)
    return key


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024 * 1024  # 50 GB


def fmt_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


app.add_template_filter(fmt_size, "size")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT
    );
    CREATE TABLE IF NOT EXISTS files(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        original_name TEXT,
        stored_name TEXT,
        size INTEGER,
        downloads INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()


# ----------------------------------------------------------------- wygląd

LAYOUT = """
<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} · Mini Chomik</title>
<style>
  :root{
    --bg:#e9efec;
    --paper:#f8faf9;
    --ink:#143532;
    --muted:#5d7571;
    --line:#cbd8d4;
    --seed:#f0b429;
    --seed-soft:#fbe6aa;
    --teal:#14544e;
    --danger:#b3392f;
    --radius:14px;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --bg:#0f1f1d;
      --paper:#162a27;
      --ink:#e6f0ed;
      --muted:#93aca7;
      --line:#2a423e;
      --seed-soft:#3b3213;
      --teal:#5fc4b8;
      --danger:#ff8a7e;
    }
  }
  *{box-sizing:border-box}
  html{background:var(--bg)}
  body{
    margin:0;color:var(--ink);background:var(--bg);
    font-family:ui-rounded,"SF Pro Rounded","Nunito","Segoe UI",system-ui,sans-serif;
    font-size:16px;line-height:1.5;
  }
  a{color:var(--teal)}
  .wrap{max-width:760px;margin:0 auto;padding:0 20px 80px}

  header{
    display:flex;align-items:center;justify-content:space-between;
    gap:16px;padding:22px 0 18px;flex-wrap:wrap;
  }
  .brand{
    display:flex;align-items:center;gap:10px;
    font-size:24px;font-weight:800;letter-spacing:-.02em;
    color:var(--ink);text-decoration:none;
  }
  .brand .logo{
    width:42px;height:42px;border-radius:50%;
    background:var(--seed);display:grid;place-items:center;font-size:23px;
  }
  nav{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  nav a{
    padding:8px 14px;border-radius:999px;text-decoration:none;
    color:var(--ink);font-weight:600;font-size:15px;
  }
  nav a:hover{background:var(--paper)}
  nav a.primary{background:var(--teal);color:var(--bg)}
  nav .who{color:var(--muted);font-size:14px;padding-right:6px}

  h1{font-size:30px;line-height:1.15;letter-spacing:-.02em;margin:26px 0 6px}
  .lead{color:var(--muted);margin:0 0 26px}

  .flash{
    background:var(--seed-soft);border-left:4px solid var(--seed);
    padding:12px 16px;border-radius:8px;margin:0 0 18px;font-weight:600;
  }

  /* strefa upuszczania plików */
  .dropzone{
    display:block;cursor:pointer;text-align:center;
    border:2.5px dashed var(--teal);border-radius:22px;
    padding:46px 20px;background:var(--paper);
    transition:background .15s,border-color .15s,transform .15s;
  }
  .dropzone:hover{background:var(--seed-soft)}
  .dropzone.over{
    background:var(--seed);border-color:var(--ink);border-style:solid;
    transform:scale(1.015);color:#143532;
  }
  .dropzone .big{font-size:44px;line-height:1;margin-bottom:10px;display:block}
  .dropzone strong{font-size:19px;display:block}
  .dropzone span.sub{color:var(--muted);font-size:14px}
  .dropzone.over span.sub{color:#143532}
  .dropzone input{display:none}

  /* kolejka wysyłania */
  #queue{margin:18px 0 0;display:grid;gap:10px}
  .up{
    background:var(--paper);border-radius:10px;padding:12px 14px;
    border:1px solid var(--line);
  }
  .up .top{display:flex;justify-content:space-between;gap:12px;font-size:15px}
  .up .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
  .up .state{color:var(--muted);white-space:nowrap}
  .bar{height:8px;border-radius:99px;background:var(--line);margin-top:9px;overflow:hidden}
  .bar i{display:block;height:100%;width:0;background:var(--teal);transition:width .1s}
  .up.done .bar i{background:var(--seed)}
  .up.fail .bar i{background:var(--danger)}
  .up.fail .state{color:var(--danger)}

  /* lista plików */
  .section-title{
    display:flex;justify-content:space-between;align-items:baseline;
    margin:38px 0 8px;font-size:20px;font-weight:800;
  }
  .section-title small{color:var(--muted);font-weight:600;font-size:14px}
  .list{border-top:1px solid var(--line)}
  .row{
    display:flex;align-items:center;gap:14px;
    padding:14px 4px;border-bottom:1px solid var(--line);
  }
  .row .info{flex:1;min-width:0}
  .row .fname{
    display:block;font-weight:700;color:var(--ink);text-decoration:none;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  }
  .row .fname:hover{color:var(--teal);text-decoration:underline}
  .row .meta{color:var(--muted);font-size:13.5px}
  .row .actions{display:flex;gap:6px;align-items:center}
  .row form{margin:0}

  button,.btn{
    font:inherit;font-weight:700;font-size:14px;cursor:pointer;
    padding:8px 14px;border-radius:999px;border:1.5px solid var(--line);
    background:transparent;color:var(--ink);text-decoration:none;
  }
  button:hover,.btn:hover{border-color:var(--teal);color:var(--teal)}
  button.danger:hover{border-color:var(--danger);color:var(--danger)}
  button.solid{background:var(--teal);color:var(--bg);border-color:var(--teal)}
  button.solid:hover{opacity:.9;color:var(--bg)}
  :focus-visible{outline:3px solid var(--seed);outline-offset:2px}

  .empty{
    text-align:center;color:var(--muted);padding:40px 10px;
    border-bottom:1px solid var(--line);
  }

  /* formularze */
  .form{max-width:380px;margin-top:20px}
  label{display:block;font-weight:700;font-size:14px;margin:16px 0 6px}
  input[type=text],input[type=password]{
    width:100%;font:inherit;padding:12px 14px;border-radius:10px;
    border:1.5px solid var(--line);background:var(--paper);color:var(--ink);
  }
  input[type=text]:focus,input[type=password]:focus{outline:3px solid var(--seed);border-color:var(--teal)}
  .form button.solid{margin-top:22px;width:100%;padding:12px}
  .alt{color:var(--muted);margin-top:18px;font-size:15px}

  @media (max-width:520px){
    .row{flex-wrap:wrap}
    .row .actions{width:100%}
    .dropzone{padding:34px 14px}
  }
  @media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <a class="brand" href="/"><span class="logo">🐹</span>Mini Chomik</a>
    <nav>
      {% if session.get('user_id') %}
        <span class="who">{{ session['username'] }}</span>
        <a href="/me" class="primary">Moje pliki</a>
        <a href="/logout">Wyloguj</a>
      {% else %}
        <a href="/login">Zaloguj</a>
        <a href="/register" class="primary">Załóż konto</a>
      {% endif %}
    </nav>
  </header>

  {% for message in get_flashed_messages() %}
    <div class="flash">{{ message }}</div>
  {% endfor %}

  {{ body }}
</div>
</body>
</html>
"""


def page(title, body_tpl, **ctx):
    body = Markup(render_template_string(body_tpl, **ctx))
    return render_template_string(LAYOUT, title=title, body=body)


# ----------------------------------------------------------------- strony

INDEX_TPL = """
<h1>Wszystkie pliki</h1>
<p class="lead">Ostatnio wrzucone przez użytkowników. Kliknij nazwę, żeby pobrać.</p>

<div class="list">
{% for f in files %}
  <div class="row">
    <div class="info">
      <a class="fname" href="/download/{{ f['id'] }}">{{ f['original_name'] }}</a>
      <div class="meta">{{ f['size']|size }} · {{ f['username'] }} · {{ f['created_at'][:10] }} · pobrań: {{ f['downloads'] }}</div>
    </div>
    <div class="actions">
      <button type="button" class="copy" data-path="/download/{{ f['id'] }}">Kopiuj link</button>
      <a class="btn" href="/download/{{ f['id'] }}">Pobierz</a>
    </div>
  </div>
{% else %}
  <div class="empty">Na razie pusto. Załóż konto i wrzuć pierwszy plik.</div>
{% endfor %}
</div>

<script>
document.querySelectorAll('.copy').forEach(function(btn){
  btn.addEventListener('click', function(){
    var url = location.origin + btn.dataset.path;
    var done = function(){ var t = btn.textContent; btn.textContent = 'Skopiowano'; setTimeout(function(){ btn.textContent = t; }, 1500); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(done);
    } else {
      var ta = document.createElement('textarea');
      ta.value = url; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch(e) {}
      document.body.removeChild(ta);
    }
  });
});
</script>
"""

AUTH_TPL = """
<h1>{{ heading }}</h1>
<form method="post" class="form">
  <label for="username">Login</label>
  <input id="username" name="username" type="text" autocomplete="username" required autofocus>
  <label for="password">Hasło</label>
  <input id="password" name="password" type="password" autocomplete="{{ 'new-password' if register else 'current-password' }}" required>
  <button class="solid">{{ button }}</button>
</form>
<p class="alt">{{ alt|safe }}</p>
"""

ME_TPL = """
<h1>Moje pliki</h1>
<p class="lead">Przeciągnij pliki na pole poniżej albo kliknij, żeby wybrać je z dysku.</p>

<label class="dropzone" id="dz" for="picker">
  <span class="big">📦</span>
  <strong>Upuść pliki tutaj</strong>
  <span class="sub">albo kliknij i wybierz z komputera · bez limitu na liczbę plików</span>
  <input id="picker" type="file" multiple>
</label>

<div id="queue"></div>

<div class="section-title">Wrzucone przez ciebie <small>{{ files|length }} plików</small></div>
<div class="list">
{% for f in files %}
  <div class="row">
    <div class="info">
      <a class="fname" href="/download/{{ f['id'] }}">{{ f['original_name'] }}</a>
      <div class="meta">{{ f['size']|size }} · {{ f['created_at'][:10] }} · pobrań: {{ f['downloads'] }}</div>
    </div>
    <div class="actions">
      <button type="button" class="copy" data-path="/download/{{ f['id'] }}">Kopiuj link</button>
      <form action="/delete/{{ f['id'] }}" method="post" onsubmit="return confirm('Usunąć ten plik na stałe?');">
        <button class="danger">Usuń</button>
      </form>
    </div>
  </div>
{% else %}
  <div class="empty">Nic jeszcze nie wrzuciłeś.</div>
{% endfor %}
</div>

<script>
(function(){
  var dz = document.getElementById('dz');
  var picker = document.getElementById('picker');
  var queue = document.getElementById('queue');
  var pending = 0, failed = 0;

  // żeby przeglądarka nie otwierała pliku, gdy ktoś upuści go obok strefy
  ['dragover','drop'].forEach(function(e){
    window.addEventListener(e, function(ev){ ev.preventDefault(); });
  });

  ['dragenter','dragover'].forEach(function(e){
    dz.addEventListener(e, function(ev){ ev.preventDefault(); dz.classList.add('over'); });
  });
  ['dragleave','drop'].forEach(function(e){
    dz.addEventListener(e, function(ev){ ev.preventDefault(); dz.classList.remove('over'); });
  });
  dz.addEventListener('drop', function(ev){ send(ev.dataTransfer.files); });
  picker.addEventListener('change', function(){ send(picker.files); picker.value = ''; });

  function human(n){
    var u = ['B','KB','MB','GB'], i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i ? n.toFixed(1) : n.toFixed(0)) + ' ' + u[i];
  }

  function send(list){
    Array.prototype.forEach.call(list, upload);
  }

  function upload(file){
    var row = document.createElement('div');
    row.className = 'up';
    row.innerHTML = '<div class="top"><span class="name"></span><span class="state">w kolejce</span></div><div class="bar"><i></i></div>';
    row.querySelector('.name').textContent = file.name + ' (' + human(file.size) + ')';
    queue.appendChild(row);
    var state = row.querySelector('.state');
    var bar = row.querySelector('.bar i');

    var fd = new FormData();
    fd.append('file', file);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload');
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    pending++;

    xhr.upload.onprogress = function(e){
      if (!e.lengthComputable) return;
      var p = Math.round(e.loaded / e.total * 100);
      bar.style.width = p + '%';
      state.textContent = p + '%';
    };
    xhr.onload = function(){
      var ok = xhr.status === 200;
      row.classList.add(ok ? 'done' : 'fail');
      bar.style.width = '100%';
      if (ok) { state.textContent = 'gotowe'; }
      else {
        failed++;
        var msg = 'błąd';
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch(e) {}
        state.textContent = msg;
      }
      finish();
    };
    xhr.onerror = function(){
      failed++;
      row.classList.add('fail');
      state.textContent = 'brak połączenia';
      finish();
    };
    xhr.send(fd);
  }

  function finish(){
    pending--;
    if (pending === 0 && failed === 0) setTimeout(function(){ location.reload(); }, 700);
  }

  document.querySelectorAll('.copy').forEach(function(btn){
    btn.addEventListener('click', function(){
      var url = location.origin + btn.dataset.path;
      var done = function(){ var t = btn.textContent; btn.textContent = 'Skopiowano'; setTimeout(function(){ btn.textContent = t; }, 1500); };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(url).then(done);
      } else {
        var ta = document.createElement('textarea');
        ta.value = url; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); done(); } catch(e) {}
        document.body.removeChild(ta);
      }
    });
  });
})();
</script>
"""


# ----------------------------------------------------------------- trasy

@app.route("/")
def index():
    conn = db()
    files = conn.execute("""
        SELECT files.*, users.username
        FROM files
        JOIN users ON users.id = files.user_id
        ORDER BY files.id DESC
        LIMIT 100
    """).fetchall()
    conn.close()
    return page("Pliki", INDEX_TPL, files=files)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not (3 <= len(username) <= 32):
            flash("Login musi mieć od 3 do 32 znaków.")
        elif len(password) < 6:
            flash("Hasło musi mieć co najmniej 6 znaków.")
        else:
            try:
                conn = db()
                conn.execute(
                    "INSERT INTO users(username, password_hash) VALUES(?, ?)",
                    (username, generate_password_hash(password)),
                )
                conn.commit()
                conn.close()
                flash("Konto gotowe. Możesz się zalogować.")
                return redirect("/login")
            except sqlite3.IntegrityError:
                flash("Ten login jest już zajęty.")

    return page(
        "Rejestracja", AUTH_TPL,
        heading="Załóż konto", button="Zarejestruj", register=True,
        alt="Masz już konto? <a href='/login'>Zaloguj się</a>",
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect("/me")

        flash("Zły login lub hasło.")

    return page(
        "Logowanie", AUTH_TPL,
        heading="Zaloguj się", button="Zaloguj", register=False,
        alt="Nie masz konta? <a href='/register'>Załóż je</a>",
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/me")
def me():
    if "user_id" not in session:
        return redirect("/login")

    conn = db()
    files = conn.execute(
        "SELECT * FROM files WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return page("Moje pliki", ME_TPL, files=files)


@app.route("/upload", methods=["POST"])
def upload():
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if "user_id" not in session:
        if wants_json:
            return jsonify(error="zaloguj się ponownie"), 401
        return redirect("/login")

    file = request.files.get("file")
    if not file or not file.filename:
        if wants_json:
            return jsonify(error="brak pliku"), 400
        flash("Nie wybrano pliku.")
        return redirect("/me")

    original_name = secure_filename(file.filename) or "plik"
    stored_name = uuid.uuid4().hex
    path = os.path.join(UPLOAD_DIR, stored_name)

    file.save(path)
    size = os.path.getsize(path)

    conn = db()
    conn.execute(
        "INSERT INTO files(user_id, original_name, stored_name, size) VALUES(?,?,?,?)",
        (session["user_id"], original_name, stored_name, size),
    )
    conn.commit()
    conn.close()

    if wants_json:
        return jsonify(ok=True, name=original_name, size=size)
    return redirect("/me")


@app.route("/download/<int:file_id>")
def download(file_id):
    conn = db()
    file = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()

    if not file:
        conn.close()
        abort(404)

    conn.execute("UPDATE files SET downloads = downloads + 1 WHERE id=?", (file_id,))
    conn.commit()
    conn.close()

    return send_file(
        os.path.join(UPLOAD_DIR, file["stored_name"]),
        as_attachment=True,
        download_name=file["original_name"],
    )


@app.route("/delete/<int:file_id>", methods=["POST"])
def delete(file_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = db()
    file = conn.execute(
        "SELECT * FROM files WHERE id=? AND user_id=?",
        (file_id, session["user_id"]),
    ).fetchone()

    if not file:
        conn.close()
        abort(404)

    try:
        os.remove(os.path.join(UPLOAD_DIR, file["stored_name"]))
    except FileNotFoundError:
        pass

    conn.execute("DELETE FROM files WHERE id=?", (file_id,))
    conn.commit()
    conn.close()

    return redirect("/me")


if __name__ == "__main__":
    init_db()
    print(f"\n  Mini Chomik działa: http://192.168.1.108:{PORT}\n")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
