import io
import re

import pytest
from openpyxl import Workbook, load_workbook

from app import create_app
from app.translator import translate_text


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "t.sqlite3"), "SECRET_KEY": "x", "DATABASE_URL": None})
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def token(c):
    c.get("/login")
    with c.session_transaction() as s:
        return s["csrf"]


def login(c, user="admin", pw=None):
    t = token(c)
    if pw is None:
        pw = "Passw0rd!"
    r = c.post("/login", data={"username": user, "password": pw, "csrf_token": t})
    with c.session_transaction() as s:
        return r, s.get("csrf")


@pytest.fixture()
def admin(app, client, monkeypatch):
    from werkzeug.security import generate_password_hash
    from app.db import get_db
    with app.app_context():
        get_db().execute("UPDATE users SET password_hash=? WHERE username='admin'",
                         (generate_password_hash("Passw0rd!"),))
        get_db().commit()
    r, csrf = login(client)
    assert r.status_code == 302
    return client, csrf


def H(csrf):
    return {"X-CSRF-Token": csrf}


# ---- mesin terjemah
def test_translator_is_sequential_case_sensitive_substring():
    rules = [("Stitch", "Stik"), ("End", "mati"), ("Stik mati", "Matikan")]
    assert translate_text("Stitch End allowance", rules) == "Matikan allowance"
    assert translate_text("stitch end", rules) == "stitch end"      # peka huruf besar/kecil
    assert translate_text("a\n\nb", [("a", "x")]) == "x\n\nb"        # baris kosong dipertahankan


def test_sample_matches_expected_translation(admin):
    c, csrf = admin
    r = c.post("/api/translate", json={"text": "Topstitch waist inside\nTOTAL\nCut elastic"}, headers=H(csrf))
    out = r.get_json()["result"].split("\n")
    assert out[0].startswith("Topstik") and "dalam" in out[0]
    assert out[1] == "TOTAL"
    assert out[2] == "Potong elastik"


# ---- auth
def test_pages_require_login(client):
    assert client.get("/").status_code == 302
    assert client.get("/kamus").status_code == 302
    assert client.get("/api/dictionary").status_code == 401


def test_login_wrong_password_and_rate_limit(app, client):
    for _ in range(5):
        r, _ = login(client, "admin", "salah")
        assert r.status_code == 401
    r, _ = login(client, "admin", "salah")
    assert r.status_code == 429


def test_open_redirect_blocked(app, client):
    from werkzeug.security import generate_password_hash
    from app.db import get_db
    with app.app_context():
        get_db().execute("UPDATE users SET password_hash=?", (generate_password_hash("Passw0rd!"),))
        get_db().commit()
    t = token(client)
    r = client.post("/login", data={"username": "admin", "password": "Passw0rd!", "csrf_token": t,
                                    "next": "https://evil.example"})
    assert r.headers["Location"] == "/"


def test_csrf_required(admin):
    c, csrf = admin
    assert c.post("/api/translate", json={"text": "x"}).status_code == 400
    assert c.post("/api/translate", json={"text": "x"}, headers=H(csrf)).status_code == 200


def test_logout(admin):
    c, csrf = admin
    assert c.post("/logout", data={"csrf_token": csrf}).status_code == 302
    assert c.get("/api/dictionary").status_code == 401


# ---- kamus
def test_dictionary_seeded_and_crud_and_order(admin):
    c, csrf = admin
    items = c.get("/api/dictionary").get_json()["items"]
    assert len(items) == 243 and items[0]["remove_text"] == "arround"
    r = c.post("/api/dictionary", json={"remove_text": "zipper", "replace_text": "ritsleting", "position": 1}, headers=H(csrf))
    items = r.get_json()["items"]
    assert r.status_code == 201 and items[0]["remove_text"] == "zipper" and len(items) == 244
    assert [i["position"] for i in items] == list(range(1, 245))
    zid = items[0]["id"]
    r = c.put(f"/api/dictionary/{zid}", json={"replace_text": "resleting", "position": 3}, headers=H(csrf))
    items = r.get_json()["items"]
    assert items[2]["id"] == zid and items[2]["replace_text"] == "resleting"
    r = c.delete(f"/api/dictionary/{zid}", headers=H(csrf))
    assert len(r.get_json()["items"]) == 243
    assert c.post("/api/dictionary", json={"remove_text": " ", "replace_text": "x"}, headers=H(csrf)).status_code == 400


def test_dictionary_import_export(admin):
    c, csrf = admin
    wb = Workbook(); ws = wb.active
    ws.append(["Text To Remove", "Text To Replace"]); ws.append(["zipper", "ritsleting"]); ws.append(["pocket", "saku"])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    r = c.post("/api/dictionary/import", data={"file": (buf, "k.xlsx"), "mode": "replace"}, headers=H(csrf))
    assert r.status_code == 200 and r.get_json()["imported"] == 2 and len(r.get_json()["items"]) == 2
    r = c.get("/api/dictionary/export")
    ws = load_workbook(io.BytesIO(r.data)).active
    assert [c.value for c in ws[2]] == ["zipper", "ritsleting"]


def test_export_translation_blocks_formula(admin):
    c, csrf = admin
    r = c.post("/api/export", json={"text": "=1+1\nCut"}, headers=H(csrf))
    ws = load_workbook(io.BytesIO(r.data)).active
    assert ws["A2"].data_type == "s" and ws["A2"].value == "=1+1"
    assert ws["B3"].value == "Potong"


# ---- riwayat & pengguna
def test_history_is_private(app, admin):
    c, csrf = admin
    r = c.post("/api/history", json={"title": "t", "text": "Cut elastic"}, headers=H(csrf))
    hid = r.get_json()["id"]
    assert c.get(f"/api/history/{hid}").get_json()["result"] == "Potong elastik"
    c.post("/api/users", json={"username": "budi", "password": "rahasia123", "role": "user"}, headers=H(csrf))
    c2 = app.test_client()
    t = token(c2)
    c2.post("/login", data={"username": "budi", "password": "rahasia123", "csrf_token": t})
    assert c2.get(f"/api/history/{hid}").status_code == 404
    assert c2.get("/api/users").status_code == 403
    assert c2.get("/pengguna").status_code == 403


def test_user_management_guards(admin):
    c, csrf = admin
    me = c.get("/api/users").get_json()["me"]
    assert c.delete(f"/api/users/{me}", headers=H(csrf)).status_code == 400
    assert c.put(f"/api/users/{me}", json={"role": "user"}, headers=H(csrf)).status_code == 400
    assert c.post("/api/users", json={"username": "a b", "password": "rahasia123"}, headers=H(csrf)).status_code == 400
    assert c.post("/api/users", json={"username": "ok_user", "password": "short"}, headers=H(csrf)).status_code == 400


def test_change_password(admin):
    c, csrf = admin
    assert c.post("/api/account/password", json={"current": "x", "new": "baru12345"}, headers=H(csrf)).status_code == 403
    assert c.post("/api/account/password", json={"current": "Passw0rd!", "new": "baru12345"}, headers=H(csrf)).status_code == 200
