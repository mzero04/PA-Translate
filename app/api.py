import io
from pathlib import Path

from flask import Blueprint, g, jsonify, request, send_file, session
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import USERNAME_RE, admin_required, login_required, validate_password
from .db import DATA_DIR, INTEGRITY_ERRORS, get_db, utcnow
from .translator import translate_text

bp = Blueprint("api", __name__, url_prefix="/api")

MAX_TERM = 200
MAX_SOURCE = 300_000
MAX_LINES = 5000
HEADER_FILL = PatternFill("solid", fgColor="4F81BD")
HEADER_FONT = Font(bold=True, color="FFFFFF", name="Calibri")


def err(message, status=400):
    return jsonify(error=message), status


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def rules():
    rows = get_db().execute(
        "SELECT remove_text, replace_text FROM dictionary ORDER BY position, id"
    ).fetchall()
    return [(r["remove_text"], r["replace_text"]) for r in rows]


def check_source(source):
    if not isinstance(source, str):
        return "Teks tidak valid."
    if len(source) > MAX_SOURCE or source.count("\n") + 1 > MAX_LINES:
        return f"Teks terlalu besar (maks {MAX_LINES} baris)."
    return None


def xlsx_response(wb, filename):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def style_header(ws, widths):
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def append_text(ws, values):
    """Tambah baris sebagai teks murni (nilai berawalan '=' tidak dijalankan sebagai formula)."""
    ws.append(list(values))
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


# ---------------------------------------------------------------- terjemah
@bp.post("/translate")
@login_required
def translate():
    source = body().get("text", "")
    problem = check_source(source)
    if problem:
        return err(problem)
    return jsonify(result=translate_text(source, rules()))


@bp.get("/sample")
@login_required
def sample():
    return jsonify(text=(DATA_DIR / "sample_input.txt").read_text(encoding="utf-8"))


@bp.post("/export")
@login_required
def export_translation():
    source = body().get("text", "")
    problem = check_source(source)
    if problem:
        return err(problem)
    result = translate_text(source, rules())
    wb = Workbook()
    ws = wb.active
    ws.title = "Translate"
    ws.append(["TEXT COPAS", "Revised Text"])
    for src, out in zip(source.splitlines() or [""], result.splitlines() or [""]):
        append_text(ws, [src, out])
    style_header(ws, {"A": 55, "B": 55})
    return xlsx_response(wb, "translate-form.xlsx")


# ----------------------------------------------------------------- kamus
def dict_rows():
    return [dict(r) for r in get_db().execute(
        "SELECT id, position, remove_text, replace_text, updated_at FROM dictionary "
        "ORDER BY position, id")]


def move_to(db, entry_id, new_pos):
    ids = [r["id"] for r in db.execute("SELECT id FROM dictionary ORDER BY position, id")]
    if entry_id in ids:
        ids.remove(entry_id)
    new_pos = max(1, min(int(new_pos), len(ids) + 1))
    ids.insert(new_pos - 1, entry_id)
    db.executemany("UPDATE dictionary SET position = ? WHERE id = ?",
                   [(i, eid) for i, eid in enumerate(ids, 1)])


def clean_term(value, label):
    if not isinstance(value, str) or not value.strip():
        return None, f"{label} tidak boleh kosong."
    value = value.strip()
    if len(value) > MAX_TERM or "\n" in value:
        return None, f"{label} maksimal {MAX_TERM} karakter dan satu baris."
    return value, None


@bp.get("/dictionary")
@login_required
def dictionary_list():
    return jsonify(items=dict_rows())


@bp.post("/dictionary")
@login_required
def dictionary_create():
    data = body()
    remove, e1 = clean_term(data.get("remove_text"), "Text To Remove")
    replace, e2 = clean_term(data.get("replace_text"), "Text To Replace")
    if e1 or e2:
        return err(e1 or e2)
    db = get_db()
    count = db.scalar("SELECT COUNT(*) FROM dictionary")
    new_id = db.insert(
        "INSERT INTO dictionary (position, remove_text, replace_text, updated_by) VALUES (?,?,?,?)",
        (count + 1, remove, replace, g.user["id"]))
    pos = data.get("position")
    if isinstance(pos, int) and not isinstance(pos, bool):
        move_to(db, new_id, pos)
    db.commit()
    return jsonify(items=dict_rows()), 201


@bp.put("/dictionary/<int:entry_id>")
@login_required
def dictionary_update(entry_id):
    db = get_db()
    row = db.execute("SELECT * FROM dictionary WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        return err("Data tidak ditemukan.", 404)
    data = body()
    remove, e1 = clean_term(data.get("remove_text", row["remove_text"]), "Text To Remove")
    replace, e2 = clean_term(data.get("replace_text", row["replace_text"]), "Text To Replace")
    if e1 or e2:
        return err(e1 or e2)
    db.execute(
        "UPDATE dictionary SET remove_text=?, replace_text=?, updated_by=?, "
        "updated_at=? WHERE id=?", (remove, replace, g.user["id"], utcnow(), entry_id))
    pos = data.get("position")
    if isinstance(pos, int) and not isinstance(pos, bool):
        move_to(db, entry_id, pos)
    db.commit()
    return jsonify(items=dict_rows())


@bp.delete("/dictionary/<int:entry_id>")
@login_required
def dictionary_delete(entry_id):
    db = get_db()
    if db.execute("DELETE FROM dictionary WHERE id = ?", (entry_id,)).rowcount == 0:
        return err("Data tidak ditemukan.", 404)
    for i, r in enumerate(db.execute("SELECT id FROM dictionary ORDER BY position, id").fetchall(), 1):
        db.execute("UPDATE dictionary SET position = ? WHERE id = ?", (i, r["id"]))
    db.commit()
    return jsonify(items=dict_rows())


@bp.get("/dictionary/export")
@login_required
def dictionary_export():
    wb = Workbook()
    ws = wb.active
    ws.title = "Kamus"
    ws.append(["Text To Remove", "Text To Replace"])
    for r in dict_rows():
        append_text(ws, [r["remove_text"], r["replace_text"]])
    style_header(ws, {"A": 28, "B": 28})
    return xlsx_response(wb, "kamus-translate.xlsx")


@bp.post("/dictionary/import")
@admin_required
def dictionary_import():
    """Impor kamus dari .xlsx: kolom 1 = Text To Remove, kolom 2 = Text To Replace."""
    f = request.files.get("file")
    mode = request.form.get("mode", "append")
    if f is None or not f.filename.lower().endswith(".xlsx"):
        return err("Unggah file .xlsx (simpan file .xlsb sebagai .xlsx dulu).")
    if mode not in ("append", "replace"):
        return err("Mode tidak valid.")
    try:
        ws = load_workbook(f, read_only=True, data_only=True).worksheets[0]
        pairs = []
        for row in ws.iter_rows(values_only=True):
            a, b = (row + (None, None))[:2] if row else (None, None)
            if isinstance(a, str) and isinstance(b, str) and a.strip() and b.strip():
                if a.strip().lower() == "text to remove":
                    continue
                pairs.append((a.strip()[:MAX_TERM], b.strip()[:MAX_TERM]))
    except Exception:
        return err("File tidak dapat dibaca. Pastikan formatnya .xlsx yang valid.")
    if not pairs:
        return err("Tidak ada pasangan kata yang ditemukan di kolom 1 dan 2.")
    db = get_db()
    if mode == "replace":
        db.execute("DELETE FROM dictionary")
    start = db.scalar("SELECT COUNT(*) FROM dictionary")
    db.executemany(
        "INSERT INTO dictionary (position, remove_text, replace_text, updated_by) VALUES (?,?,?,?)",
        [(start + i, a, b, g.user["id"]) for i, (a, b) in enumerate(pairs, 1)])
    db.commit()
    return jsonify(items=dict_rows(), imported=len(pairs))


# --------------------------------------------------------------- riwayat
@bp.get("/history")
@login_required
def history_list():
    rows = get_db().execute(
        "SELECT id, title, line_count, created_at FROM history WHERE user_id = ? "
        "ORDER BY id DESC LIMIT 200", (g.user["id"],)).fetchall()
    return jsonify(items=[dict(r) for r in rows])


@bp.post("/history")
@login_required
def history_create():
    data = body()
    source = data.get("text", "")
    problem = check_source(source)
    if problem or not source.strip():
        return err(problem or "Tidak ada teks untuk disimpan.")
    title = (data.get("title") or "").strip()[:120] or "Tanpa judul"
    result = translate_text(source, rules())
    db = get_db()
    new_id = db.insert(
        "INSERT INTO history (user_id, title, source, result, line_count) VALUES (?,?,?,?,?)",
        (g.user["id"], title, source, result, source.count("\n") + 1))
    db.commit()
    return jsonify(id=new_id), 201


@bp.get("/history/<int:hid>")
@login_required
def history_get(hid):
    row = get_db().execute(
        "SELECT id, title, source, result, created_at FROM history WHERE id = ? AND user_id = ?",
        (hid, g.user["id"])).fetchone()
    return jsonify(dict(row)) if row else err("Riwayat tidak ditemukan.", 404)


@bp.delete("/history/<int:hid>")
@login_required
def history_delete(hid):
    db = get_db()
    n = db.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (hid, g.user["id"])).rowcount
    db.commit()
    return jsonify(ok=True) if n else err("Riwayat tidak ditemukan.", 404)


# --------------------------------------------------------------- pengguna
USER_COLS = "id, username, full_name, role, is_active, created_at, last_login"


def user_rows():
    return [dict(r) for r in get_db().execute(f"SELECT {USER_COLS} FROM users ORDER BY username")]


def other_active_admins(db, exclude_id):
    return db.scalar(
        "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1 AND id != ?",
        (exclude_id,))


@bp.get("/users")
@admin_required
def users_list():
    return jsonify(items=user_rows(), me=g.user["id"])


@bp.post("/users")
@admin_required
def users_create():
    data = body()
    username = (data.get("username") or "").strip()
    full_name = (data.get("full_name") or "").strip()[:80] or username
    role = data.get("role", "user")
    if not USERNAME_RE.match(username):
        return err("Username 3–32 karakter: huruf, angka, titik, strip, underscore.")
    if role not in ("admin", "user"):
        return err("Role tidak valid.")
    problem = validate_password(data.get("password"))
    if problem:
        return err(problem)
    try:
        get_db().execute(
            "INSERT INTO users (username, full_name, password_hash, role) VALUES (?,?,?,?)",
            (username, full_name, generate_password_hash(data["password"]), role))
        get_db().commit()
    except INTEGRITY_ERRORS:
        get_db().rollback()
        return err("Username sudah dipakai.", 409)
    return jsonify(items=user_rows()), 201


@bp.put("/users/<int:uid>")
@admin_required
def users_update(uid):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        return err("Pengguna tidak ditemukan.", 404)
    data = body()
    full_name = (data.get("full_name", row["full_name"]) or "").strip()[:80] or row["username"]
    role = data.get("role", row["role"])
    active = 1 if data.get("is_active", bool(row["is_active"])) else 0
    if role not in ("admin", "user"):
        return err("Role tidak valid.")
    if row["role"] == "admin" and (role != "admin" or not active) and not other_active_admins(db, uid):
        return err("Harus ada minimal satu admin aktif.")
    if uid == g.user["id"] and not active:
        return err("Anda tidak bisa menonaktifkan akun sendiri.")
    new_pw = data.get("password")
    if new_pw:
        problem = validate_password(new_pw)
        if problem:
            return err(problem)
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(new_pw), uid))
    db.execute("UPDATE users SET full_name=?, role=?, is_active=? WHERE id=?",
               (full_name, role, active, uid))
    db.commit()
    return jsonify(items=user_rows())


@bp.delete("/users/<int:uid>")
@admin_required
def users_delete(uid):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        return err("Pengguna tidak ditemukan.", 404)
    if uid == g.user["id"]:
        return err("Anda tidak bisa menghapus akun sendiri.")
    if row["role"] == "admin" and row["is_active"] and not other_active_admins(db, uid):
        return err("Harus ada minimal satu admin aktif.")
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    db.commit()
    return jsonify(items=user_rows())


@bp.post("/account/password")
@login_required
def change_password():
    data = body()
    if not check_password_hash(g.user["password_hash"], data.get("current") or ""):
        return err("Password saat ini salah.", 403)
    problem = validate_password(data.get("new"))
    if problem:
        return err(problem)
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(data["new"]), g.user["id"]))
    db.commit()
    return jsonify(ok=True)
