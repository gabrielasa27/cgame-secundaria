"""Servidor real de CGAME (API que espera client/src/index.template.html vía ?api=).

Envuelve exactamente el mismo código de backend/recommender/ que ya se probó y
entrenó (compute_result, recommend, LinearSVM) — no reimplementa esa lógica.

Ejecutar en desarrollo:
    cd backend/server
    pip install -r requirements.txt
    python app.py                      # sirve en http://127.0.0.1:5057

Variables de entorno:
    CGAME_SECRET_KEY   clave para firmar los tokens (genera una propia en producción)
    CGAME_DB_PATH      ruta del archivo SQLite (por defecto: server/cgame.db)
    CGAME_CORS_ORIGIN  origen permitido para CORS (por defecto: *)
    PORT               puerto (por defecto: 5057)

Nota de seguridad: este es un prototipo académico. El puntaje de cada intento se
calcula en el navegador y se envía ya calculado (no se reenvían los eventos crudos),
así que un cliente malicioso podría falsificarlo. Para un despliegue real con
consecuencias académicas, habría que reenviar los eventos (aciertos/fallos, no solo
el resultado) y recalcular `compute_result` en el servidor antes de guardar.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import jwt
from flask import Flask, g, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/  -> import recommender
from recommender.levels import LEVELS  # noqa: E402
from recommender.model import LinearSVM  # noqa: E402
from recommender.recommend import recommend  # noqa: E402
from recommender.scoring import PASS_SCORE  # noqa: E402

SECRET_KEY = os.environ.get("CGAME_SECRET_KEY") or secrets.token_hex(32)
DB_PATH = os.environ.get("CGAME_DB_PATH", str(Path(__file__).resolve().parent / "cgame.db"))
CORS_ORIGIN = os.environ.get("CGAME_CORS_ORIGIN", "*")
TOKEN_DAYS = 30
ATTEMPT_FIELDS = ["attempt_id", "user_id", "game_id", "level_id", "attempt_number", "date",
                  "score", "accuracy", "time", "movements", "errors", "hints_used",
                  "completed", "approved", "result"]

ADMIN_KEY = os.environ.get("CGAME_ADMIN_KEY")
if not ADMIN_KEY:
    ADMIN_KEY = secrets.token_hex(16)
    print(f"[cgame] AVISO: CGAME_ADMIN_KEY no está definida; se generó una temporal para "
          f"esta sesión: {ADMIN_KEY}  (cámbiala/fíjala con una variable de entorno en producción, "
          f"o se te olvidará y cambiará en cada reinicio).", file=sys.stderr)

if not os.environ.get("CGAME_SECRET_KEY"):
    print("[cgame] AVISO: CGAME_SECRET_KEY no está definida; se generó una clave temporal "
          "que cambiará cada reinicio (los tokens dejarán de servir). Defínela en producción.",
          file=sys.stderr)

app = Flask(__name__)
MODEL = LinearSVM.load()  # mismos coeficientes que ve el juego (svm_model.json)


# ---------- Base de datos ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL, hash TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
            game_id TEXT NOT NULL, level_id TEXT NOT NULL, attempt_number INTEGER,
            date TEXT NOT NULL, score INTEGER, accuracy INTEGER, time INTEGER,
            movements INTEGER, errors INTEGER, hints_used INTEGER,
            completed INTEGER NOT NULL, approved INTEGER, result TEXT
        );
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id),
            attempt_id TEXT, level_id TEXT, action TEXT, prediction TEXT, area TEXT,
            game_id TEXT, decision REAL, reason TEXT, date TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id, date);
        """)
        conn.commit()


# ---------- Utilidades ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def make_token(user_id: str) -> str:
    payload = {"sub": user_id, "iat": int(time.time()), "exp": int(time.time()) + TOKEN_DAYS * 86400}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def error(code: str, status: int):
    return jsonify({"error": code}), status


def require_auth(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return error("unauthorized", 401)
        try:
            payload = jwt.decode(auth[7:], SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return error("unauthorized", 401)
        row = db().execute("SELECT * FROM users WHERE id=?", (payload["sub"],)).fetchone()
        if not row:
            return error("unauthorized", 401)
        g.user = row
        return fn(*a, **kw)
    return wrapper


def public_user(row) -> dict:
    return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}


def row_to_attempt(row) -> dict:
    d = {k: row[k] for k in row.keys()}
    d["completed"] = bool(d["completed"])
    d["approved"] = bool(d["approved"])
    return d


def user_attempts(user_id: str) -> list[dict]:
    rows = db().execute("SELECT * FROM attempts WHERE user_id=? ORDER BY date ASC", (user_id,)).fetchall()
    return [row_to_attempt(r) for r in rows]


# ---------- CORS ----------
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Vary"] = "Origin"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return "", 204


# ---------- Rutas ----------
@app.get("/api/health")
def health():
    return jsonify({"ok": True, "model": MODEL.meta, "levels": len(LEVELS)})


@app.post("/api/register")
def register():
    body = request.get_json(silent=True) or {}
    name, email, password = (body.get("name") or "").strip(), (body.get("email") or "").strip().lower(), body.get("password") or ""
    if not name or "@" not in email or len(password) < 6:
        return error("invalid_input", 400)
    if db().execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        return error("email_taken", 409)
    salt = secrets.token_hex(16)
    user_id = "U-" + secrets.token_hex(8)
    row = (user_id, name, email, salt, hash_password(password, salt), now_iso())
    db().execute("INSERT INTO users (id,name,email,salt,hash,created_at) VALUES (?,?,?,?,?,?)", row)
    db().commit()
    return jsonify({"user": {"id": user_id, "name": name, "email": email, "created_at": row[5]}})


@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    email, password = (body.get("email") or "").strip().lower(), body.get("password") or ""
    urow = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not urow or hash_password(password, urow["salt"]) != urow["hash"]:
        return error("bad_credentials", 401)
    return jsonify({"user": public_user(urow), "token": make_token(urow["id"])})


@app.get("/api/me")
@require_auth
def me():
    return jsonify({"user": public_user(g.user)})


@app.get("/api/attempts")
@require_auth
def list_attempts():
    return jsonify({"attempts": user_attempts(g.user["id"])})


@app.post("/api/attempts")
@require_auth
def save_attempt():
    body = request.get_json(silent=True) or {}
    if body.get("level_id") not in LEVELS:
        return error("invalid_level", 400)
    attempt_id = body.get("attempt_id") or ("A-" + secrets.token_hex(8))
    completed = bool(body.get("completed"))
    score = int(body.get("score") or 0)
    approved = bool(completed and score >= PASS_SCORE)
    row = (attempt_id, g.user["id"], body.get("game_id", ""), body["level_id"],
           int(body.get("attempt_number") or 0), body.get("date") or now_iso(),
           score, int(body.get("accuracy") or 0), int(body.get("time") or 0),
           int(body.get("movements") or 0), int(body.get("errors") or 0),
           int(body.get("hints_used") or 0), int(completed), int(approved),
           body.get("result") or ("Aprobado" if approved else ("No aprobado" if completed else "Incompleto")))
    db().execute("""INSERT OR REPLACE INTO attempts
        (attempt_id,user_id,game_id,level_id,attempt_number,date,score,accuracy,time,
         movements,errors,hints_used,completed,approved,result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
    db().commit()

    saved = row_to_attempt(db().execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone())
    reco = None
    if completed:
        history = user_attempts(g.user["id"])  # ya incluye el intento recién guardado
        reco = recommend(MODEL, history)  # <-- el mismo SVM entrenado, ejecutándose en el servidor
        db().execute("""INSERT INTO recommendations
            (user_id,attempt_id,level_id,action,prediction,area,game_id,decision,reason,date)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (g.user["id"], attempt_id, reco["level_id"], reco["action"], reco["prediction"],
             reco["area"], reco["game_id"], float(reco["decision"]), reco["reason"], now_iso()))
        db().commit()
    return jsonify({"attempt": saved, "recommendation": reco})


@app.get("/api/recommendation")
@require_auth
def latest_recommendation():
    row = db().execute("SELECT * FROM recommendations WHERE user_id=? ORDER BY id DESC LIMIT 1",
                       (g.user["id"],)).fetchone()
    if not row:
        return jsonify({"recommendation": None})
    return jsonify({"recommendation": {
        "level_id": row["level_id"], "action": row["action"], "prediction": row["prediction"],
        "area": row["area"], "game_id": row["game_id"], "decision": row["decision"], "reason": row["reason"],
    }})


# ---------- Panel de administración (todos los estudiantes, protegido por clave) ----------
def check_admin_key():
    key = request.args.get("key") or request.headers.get("X-Admin-Key")
    return bool(key) and secrets.compare_digest(key, ADMIN_KEY)


@app.get("/api/admin/attempts")
def admin_attempts():
    if not check_admin_key():
        return error("forbidden", 403)
    rows = db().execute("""
        SELECT a.*, u.name AS user_name, u.email AS user_email
        FROM attempts a JOIN users u ON u.id = a.user_id
        ORDER BY a.date ASC
    """).fetchall()
    attempts = [dict(r) for r in rows]
    for a in attempts:
        a["completed"] = bool(a["completed"])
        a["approved"] = bool(a["approved"])
    students = db().execute("""
        SELECT u.id, u.name, u.email, u.created_at, COUNT(a.attempt_id) AS attempts,
               SUM(CASE WHEN a.approved THEN 1 ELSE 0 END) AS approved
        FROM users u LEFT JOIN attempts a ON a.user_id = u.id
        GROUP BY u.id ORDER BY u.created_at ASC
    """).fetchall()
    return jsonify({"attempts": attempts, "students": [dict(s) for s in students], "model": MODEL.meta})


ADMIN_PAGE = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CGAME · Panel del docente</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#F5F8FF;color:#1B2140}
header{background:#2F6BFF;color:#fff;padding:18px 22px}
header h1{margin:0;font-size:1.3rem}
main{max-width:1100px;margin:0 auto;padding:20px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}
input{flex:1;min-width:220px;padding:10px 14px;border:2px solid #C9D3F0;border-radius:10px;font-size:1rem}
button{padding:10px 18px;border:2px solid #1B2140;border-radius:10px;background:#14A768;color:#fff;font-weight:600;cursor:pointer}
button.secondary{background:#fff;color:#1B2140}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;margin-bottom:24px;font-size:.92rem}
th,td{padding:8px 12px;border-bottom:1px solid #E5EAFB;text-align:left;white-space:nowrap}
th{background:#EAF0FF}
.badge{padding:1px 10px;border-radius:999px;font-size:.8rem;font-weight:600}
.ok{background:#DDF6EA}.no{background:#FFE3E0}.inc{background:#FFF1CC}
.muted{color:#4B557D;font-size:.9rem}
#msg{margin-bottom:12px}
.cardsrow{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.card{background:#fff;border:2px solid #1B2140;border-radius:12px;padding:12px 18px;min-width:120px}
.card b{display:block;font-size:1.4rem}
</style>
<header><h1>CGAME · Panel del docente (todos los estudiantes)</h1></header>
<main>
  <div class="row">
    <input id="key" type="password" placeholder="Clave de administrador (CGAME_ADMIN_KEY)">
    <button onclick="load()">Cargar datos</button>
    <button class="secondary" onclick="downloadCsv()">Descargar CSV</button>
  </div>
  <p id="msg" class="muted">Pide la clave a quien desplegó el servidor (variable de entorno CGAME_ADMIN_KEY en Render).</p>
  <div id="cards" class="cardsrow"></div>
  <div id="out"></div>
</main>
<script>
let lastAttempts = [];
const params = new URLSearchParams(location.search);
if (params.get('key')) document.getElementById('key').value = params.get('key');

async function load() {
  const key = document.getElementById('key').value.trim();
  const msg = document.getElementById('msg');
  msg.textContent = 'Cargando...';
  try {
    const res = await fetch('/api/admin/attempts?key=' + encodeURIComponent(key));
    if (!res.ok) { msg.textContent = res.status === 403 ? 'Clave incorrecta.' : 'Error al cargar.'; return; }
    const data = await res.json();
    lastAttempts = data.attempts;
    msg.textContent = data.attempts.length + ' intentos de ' + data.students.length + ' estudiantes. Modelo: ' + data.model.kernel + ', C=' + data.model.C + '.';
    renderCards(data.students);
    renderTable(data.attempts);
  } catch (e) { msg.textContent = 'No se pudo conectar: ' + e; }
}
function renderCards(students) {
  const totalApproved = students.reduce((s,x)=>s+(x.approved||0),0);
  const totalAttempts = students.reduce((s,x)=>s+(x.attempts||0),0);
  document.getElementById('cards').innerHTML = `
    <div class="card"><b>${students.length}</b>estudiantes</div>
    <div class="card"><b>${totalAttempts}</b>intentos totales</div>
    <div class="card"><b>${totalApproved}</b>niveles aprobados</div>`;
}
function renderTable(rows) {
  const cols = ['user_name','user_email','game_id','level_id','attempt_number','score','accuracy','time','movements','errors','hints_used','result','date'];
  document.getElementById('out').innerHTML = '<table><thead><tr>' + cols.map(c=>`<th>${c}</th>`).join('') +
    '</tr></thead><tbody>' + rows.map(r => '<tr>' + cols.map(c=>{
      if (c==='result') { const cls = r.result==='Aprobado'?'ok':r.result==='Incompleto'?'inc':'no'; return `<td><span class="badge ${cls}">${r.result}</span></td>`; }
      if (c==='date') return `<td>${(r.date||'').replace('T',' ').slice(0,16)}</td>`;
      return `<td>${r[c] ?? ''}</td>`;
    }).join('') + '</tr>').join('') + '</tbody></table>';
}
function downloadCsv() {
  if (!lastAttempts.length) return alert('Primero pulsa "Cargar datos".');
  const cols = ['user_id','user_name','user_email','game_id','level_id','attempt_id','attempt_number','score','accuracy','time','movements','errors','hints_used','completed','result','date'];
  const csv = [cols.join(',')].concat(lastAttempts.map(r=>cols.map(c=>String(r[c] ?? '')).join(','))).join('\\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'cgame_todos_los_estudiantes.csv'; a.click();
}
</script>"""


@app.get("/admin")
def admin_page():
    return ADMIN_PAGE


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5057))
    print(f"[cgame] SVM cargado: {MODEL.meta}")
    print(f"[cgame] Base de datos: {DB_PATH}")
    print(f"[cgame] Escuchando en http://0.0.0.0:{port}/api  (health: /api/health)")
    print(f"[cgame] Panel del docente: http://0.0.0.0:{port}/admin  (clave: {ADMIN_KEY})")
    app.run(host="0.0.0.0", port=port, debug=False)
