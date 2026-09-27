"""Accounts: first-run setup, sign-in, the auth gate, roles, keys, activity, projects.

Each test gets its own empty database, and turns the auth gate on, since the
rest of the suite runs with it off.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import accounts  # noqa: E402
import main  # noqa: E402

ADMIN = {"org_name": "Ministry of Testing", "org_type": "ministry", "name": "Asha Rao",
         "email": "Asha.Rao@test.gov.in", "password": "Correct-Horse-9"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCOUNTS_DB", str(tmp_path / "accounts.db"))
    monkeypatch.setenv("AUTH_REQUIRED", "1")
    accounts.reset_for_tests()
    yield TestClient(main.app)
    accounts.reset_for_tests()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def setup_admin(client):
    resp = client.post("/auth/setup", json=ADMIN)
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_fresh_install_asks_for_setup_and_has_no_default_account(client):
    status = client.get("/auth/status").json()
    assert status["setup_required"] is True
    for email, password in [("admin@admin.com", "admin"), ("demo@gmail.com", "demo-password")]:
        assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 401


def test_engine_routes_refuse_anonymous_callers(client):
    assert client.get("/health").status_code == 200  # public, the sign-in page uses it
    for path in ("/stats", "/standards/search", "/alerts?summary=true"):
        assert client.get(path).status_code == 401, path
    assert client.post("/retrieve", json={"query": "cement"}).status_code == 401


def test_setup_once_then_sign_in(client):
    token = setup_admin(client)
    me = client.get("/auth/me", headers=auth(token)).json()
    assert me["user"]["email"] == "asha.rao@test.gov.in"  # stored lower case
    assert me["user"]["role"] == "admin"
    assert me["org"]["name"] == "Ministry of Testing"
    assert client.post("/auth/setup", json=ADMIN).status_code == 409

    resp = client.post("/auth/login", json={"email": "ASHA.RAO@test.gov.in", "password": ADMIN["password"]})
    assert resp.status_code == 200
    assert client.get("/stats", headers=auth(resp.json()["token"])).status_code == 200


def test_register_creates_a_separate_organisation(client):
    admin = setup_admin(client)
    resp = client.post("/auth/register", json={
        "org_name": "State PWD", "org_type": "state", "name": "Kiran Das",
        "email": "kiran@pwd.gov.in", "password": "Another-Pass-42"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["role"] == "admin"
    assert data["org"]["name"] == "State PWD"
    # Never joins someone else's organisation: each sees only its own members.
    theirs = client.get("/org/members", headers=auth(data["token"])).json()["members"]
    assert [m["email"] for m in theirs] == ["kiran@pwd.gov.in"]
    ours = client.get("/org/members", headers=auth(admin)).json()["members"]
    assert "kiran@pwd.gov.in" not in [m["email"] for m in ours]


def test_register_refuses_a_taken_email_and_can_be_closed(client, monkeypatch):
    setup_admin(client)
    body = {**ADMIN, "org_name": "Duplicate"}
    assert client.post("/auth/register", json=body).status_code == 409
    monkeypatch.setenv("REGISTRATION", "closed")
    assert client.get("/auth/status").json()["registration_open"] is False
    body = {**ADMIN, "email": "new@x.gov.in"}
    assert client.post("/auth/register", json=body).status_code == 403


def test_weak_passwords_are_refused(client):
    for weak in ("short1A", "alllowercase123", "NoDigitsInThisOne"):
        resp = client.post("/auth/setup", json={**ADMIN, "password": weak})
        assert resp.status_code == 400, weak


def test_passwords_are_not_stored_in_clear(client):
    setup_admin(client)
    row = accounts._q("SELECT password_hash FROM users")[0]
    assert ADMIN["password"] not in row["password_hash"]
    assert row["password_hash"].startswith("scrypt$")


def test_wrong_password_is_throttled(client):
    setup_admin(client)
    for _ in range(5):
        assert client.post("/auth/login", json={"email": ADMIN["email"], "password": "Wrong-pass-1"}).status_code == 401
    # Locked even with the right password now.
    assert client.post("/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]}).status_code == 429


def test_logout_ends_the_session(client):
    token = setup_admin(client)
    assert client.post("/auth/logout", headers=auth(token)).status_code == 200
    assert client.get("/auth/me", headers=auth(token)).status_code == 401


def test_invited_member_must_change_password_and_cannot_admin(client):
    admin = setup_admin(client)
    resp = client.post("/org/members", headers=auth(admin),
                       json={"name": "Ravi Kumar", "email": "ravi@test.gov.in", "role": "officer"})
    assert resp.status_code == 200, resp.text
    temporary = resp.json()["temporary_password"]

    login = client.post("/auth/login", json={"email": "ravi@test.gov.in", "password": temporary}).json()
    assert login["user"]["must_change_password"] is True
    officer = login["token"]

    changed = client.post("/auth/password", headers=auth(officer),
                          json={"current_password": temporary, "new_password": "Brand-New-Pass-7"})
    assert changed.status_code == 200
    assert client.get("/auth/me", headers=auth(officer)).json()["user"]["must_change_password"] is False

    # Officers cannot manage the organisation or hold API keys.
    assert client.post("/org/members", headers=auth(officer),
                       json={"name": "X Y", "email": "x@test.gov.in"}).status_code == 403
    assert client.patch("/org", headers=auth(officer), json={"name": "Hijack"}).status_code == 403
    assert client.post("/keys", headers=auth(officer), json={"name": "mine"}).status_code == 403


def test_admin_cannot_lock_themselves_out(client):
    admin = setup_admin(client)
    me = client.get("/auth/me", headers=auth(admin)).json()["user"]
    resp = client.patch(f"/org/members/{me['id']}", headers=auth(admin), json={"role": "officer"})
    assert resp.status_code == 400


def test_disabling_a_member_signs_them_out(client):
    admin = setup_admin(client)
    invited = client.post("/org/members", headers=auth(admin),
                          json={"name": "Meera Iyer", "email": "meera@test.gov.in", "role": "officer"}).json()
    token = client.post("/auth/login", json={"email": "meera@test.gov.in",
                                             "password": invited["temporary_password"]}).json()["token"]
    client.patch(f"/org/members/{invited['user']['id']}", headers=auth(admin), json={"disabled": True})
    assert client.get("/auth/me", headers=auth(token)).status_code == 401


def test_api_key_works_once_and_stops_when_revoked(client):
    admin = setup_admin(client)
    created = client.post("/keys", headers=auth(admin), json={"name": "GeM integration"}).json()
    secret = created["secret"]
    assert secret.startswith("sk_")
    # The secret is shown once: the list carries only a prefix.
    listed = client.get("/keys", headers=auth(admin)).json()["keys"]
    assert listed[0]["prefix"] == secret[:10]
    assert "secret" not in listed[0]

    assert client.get("/stats", headers={"X-API-Key": secret}).status_code == 200
    assert client.get("/keys", headers=auth(admin)).json()["keys"][0]["calls"] == 1
    # A key cannot mint another key.
    assert client.post("/keys", headers={"X-API-Key": secret}, json={"name": "child"}).status_code == 403

    client.delete(f"/keys/{created['key']['id']}", headers=auth(admin))
    assert client.get("/stats", headers={"X-API-Key": secret}).status_code == 401


def test_activity_records_what_the_user_did(client):
    admin = setup_admin(client)
    client.post("/keys", headers=auth(admin), json={"name": "Portal"})
    client.post("/activity", headers=auth(admin),
                json={"action": "spec.export", "detail": "Copied clause text"})
    items = client.get("/activity", headers=auth(admin)).json()["items"]
    actions = [i["action"] for i in items]
    assert actions[:3] == ["spec.export", "api_key.create", "account.setup"]
    # Only the workbench's own event kinds can be posted from the client.
    assert client.post("/activity", headers=auth(admin),
                       json={"action": "account.sign_in", "detail": "forged"}).status_code == 422


def test_projects_are_private_to_their_owner(client):
    admin = setup_admin(client)
    active = client.get("/projects/active", headers=auth(admin)).json()
    assert active["name"] == "Untitled specification"

    spec = {"items": {"IS 269:2015": {"code": "IS 269:2015", "role": "primary"}}, "order": ["IS 269:2015"]}
    saved = client.put(f"/projects/{active['id']}", headers=auth(admin),
                       json={"name": "Cement supply 2026", "spec": spec}).json()
    assert saved["item_count"] == 1

    other = client.post("/projects", headers=auth(admin), json={"name": "Second"}).json()
    listing = client.get("/projects", headers=auth(admin)).json()
    assert listing["active_id"] == other["id"]
    assert {p["name"] for p in listing["projects"]} == {"Cement supply 2026", "Second"}

    invited = client.post("/org/members", headers=auth(admin),
                          json={"name": "Ravi Kumar", "email": "ravi@test.gov.in", "role": "officer"}).json()
    officer = client.post("/auth/login", json={"email": "ravi@test.gov.in",
                                               "password": invited["temporary_password"]}).json()["token"]
    assert client.get(f"/projects/{active['id']}", headers=auth(officer)).status_code == 404
