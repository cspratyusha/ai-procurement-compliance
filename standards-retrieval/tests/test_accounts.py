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

    assert client.get("/languages", headers={"X-API-Key": secret}).status_code == 200
    assert client.get("/keys", headers=auth(admin)).json()["keys"][0]["calls"] == 1
    # A key cannot mint another key.
    assert client.post("/keys", headers={"X-API-Key": secret}, json={"name": "child"}).status_code == 403

    client.delete(f"/keys/{created['key']['id']}", headers=auth(admin))
    assert client.get("/languages", headers={"X-API-Key": secret}).status_code == 401


def test_an_administrators_key_reaches_the_engine_only(client):
    """A widget key sits in a portal's page source. Made by an administrator,
    it must still not add members, read the organisation or manage keys."""
    admin = setup_admin(client)
    secret = client.post("/keys", headers=auth(admin), json={"name": "Widget"}).json()["secret"]
    key = {"X-API-Key": secret}
    assert client.get("/standards/search?q=cement", headers=key).status_code == 200
    assert client.get("/certification-rules", headers=key).status_code == 200
    for method, path, body in [
        ("post", "/org/members", {"name": "Intruder", "email": "x@evil.test", "role": "admin"}),
        ("get", "/org/members", None),
        ("patch", "/org", {"name": "Taken"}),
        ("get", "/keys", None),
        ("get", "/activity?scope=org", None),
        ("get", "/projects", None),
        ("get", "/auth/me", None),
        ("get", "/stats", None),
        ("get", "/logs", None),
    ]:
        call = getattr(client, method)
        response = call(path, headers=key, json=body) if body is not None else call(path, headers=key)
        assert response.status_code == 403, (method, path, response.status_code)
    members = client.get("/org/members", headers=auth(admin)).json()
    assert all(m.get("email") != "x@evil.test" for m in members.get("members", members))


def test_a_key_issued_for_a_portal_refuses_other_web_addresses(client):
    admin = setup_admin(client)
    created = client.post("/keys", headers=auth(admin),
                          json={"name": "Widget", "origins": ["https://Eproc.Example.gov.in/"]}).json()
    assert created["key"]["origins"] == ["https://eproc.example.gov.in"]
    key = {"X-API-Key": created["secret"]}
    assert client.get("/languages", headers={**key, "Origin": "https://eproc.example.gov.in"}).status_code == 200
    assert client.get("/languages", headers={**key, "Origin": "https://copycat.example.com"}).status_code == 403
    assert client.get("/languages", headers=key).status_code == 403

    bad = client.post("/keys", headers=auth(admin), json={"name": "W2", "origins": ["eproc.example.gov.in/form"]})
    assert bad.status_code == 400


def test_a_key_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(accounts, "KEY_RATE_PER_MINUTE", 3)
    admin = setup_admin(client)
    key = {"X-API-Key": client.post("/keys", headers=auth(admin), json={"name": "Portal"}).json()["secret"]}
    assert [client.get("/languages", headers=key).status_code for _ in range(4)] == [200, 200, 200, 429]
    limited = client.get("/languages", headers=key)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
    # A signed-in person is not held to a key's limit.
    assert client.get("/languages", headers=auth(admin)).status_code == 200


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


def test_login_does_the_same_work_for_an_unknown_email(client, monkeypatch):
    """No shortcut for a missing account, so timing cannot reveal who has one."""
    setup_admin(client)
    calls = []
    real = accounts.verify_password
    monkeypatch.setattr(accounts, "verify_password", lambda p, s: calls.append(s) or real(p, s))
    client.post("/auth/login", json={"email": "nobody@test.gov.in", "password": "Whatever-Pass-1"})
    assert len(calls) == 1


def test_one_address_cannot_spray_passwords(client, monkeypatch):
    setup_admin(client)
    monkeypatch.setattr(accounts, "_IP_MAX_FAILURES", 3)
    for i in range(3):
        client.post("/auth/login", json={"email": f"user{i}@x.gov.in", "password": "Wrong-pass-1"})
    # A different, never-tried email from the same address is now refused.
    assert client.post("/auth/login", json={"email": "fresh@x.gov.in", "password": "Wrong-pass-1"}).status_code == 429


def test_registrations_per_address_are_limited(client, monkeypatch):
    setup_admin(client)
    monkeypatch.setattr(accounts, "_IP_MAX_REGISTRATIONS", 2)
    for i in range(2):
        body = {**ADMIN, "org_name": f"Org {i}", "email": f"r{i}@x.gov.in"}
        assert client.post("/auth/register", json=body).status_code == 200
    body = {**ADMIN, "org_name": "Org 3", "email": "r3@x.gov.in"}
    assert client.post("/auth/register", json=body).status_code == 429


def test_huge_passwords_are_refused(client):
    assert client.post("/auth/setup", json={**ADMIN, "password": "Aa1" + "x" * 300}).status_code == 400


def test_sessions_end_at_their_maximum_age(client, monkeypatch):
    token = setup_admin(client)
    accounts._x("UPDATE sessions SET created_at = created_at - ?", (accounts.SESSION_MAX_AGE_S + 60,))
    client.get("/auth/me", headers=auth(token))          # expiry is capped at the hard end
    assert client.get("/auth/me", headers=auth(token)).status_code == 401


def test_recent_searches_are_the_callers_own(client):
    """Another organisation's queries must never appear on your dashboard."""
    mine = setup_admin(client)
    theirs = client.post("/auth/register", json={**ADMIN, "org_name": "Other", "email": "o@x.gov.in"}).json()["token"]
    accounts.record(2, 2, "search.query", '"secret tender for radar parts"', {"query": "secret tender for radar parts"})
    recent = client.get("/stats", headers=auth(mine)).json()["recent_queries"]
    assert all("radar" not in q["query"] for q in recent)
    recent_theirs = client.get("/stats", headers=auth(theirs)).json()["recent_queries"]
    assert any("radar" in q["query"] for q in recent_theirs)


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


@pytest.fixture
def outbox(monkeypatch):
    """Email switched on, with messages captured instead of sent."""
    import mailer
    sent = []
    monkeypatch.setattr(mailer, "available", lambda: True)
    monkeypatch.setattr(mailer, "public_url", lambda: "https://standards.example.gov.in")
    monkeypatch.setattr(mailer, "send", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def _reset_token(body):
    import re
    return re.search(r"token=(rst_[\w-]+)", body).group(1)


def test_without_email_the_reset_form_points_to_the_administrator(client):
    setup_admin(client)
    assert client.get("/auth/status").json()["password_reset_by_email"] is False
    response = client.post("/auth/forgot", json={"email": ADMIN["email"]})
    assert response.status_code == 503
    assert "administrator" in response.json()["detail"]


def test_a_forgotten_password_is_reset_by_an_emailed_link_once(client, outbox):
    admin = setup_admin(client)
    assert client.get("/auth/status").json()["password_reset_by_email"] is True

    known = client.post("/auth/forgot", json={"email": "ASHA.RAO@test.gov.in"})
    unknown = client.post("/auth/forgot", json={"email": "nobody@test.gov.in"})
    # The same answer either way, and mail only to the real account.
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [to for to, _, _ in outbox] == ["asha.rao@test.gov.in"]
    token = _reset_token(outbox[0][2])
    assert "https://standards.example.gov.in/reset-password?token=" in outbox[0][2]

    weak = client.post("/auth/reset", json={"token": token, "new_password": "short"})
    assert weak.status_code == 400
    assert client.post("/auth/reset", json={"token": token, "new_password": "New-Horse-42"}).status_code == 200
    # Single use, and every session signed out.
    assert client.post("/auth/reset", json={"token": token, "new_password": "Other-Horse-42"}).status_code == 400
    assert client.get("/auth/me", headers=auth(admin)).status_code == 401
    assert client.post("/auth/login", json={"email": ADMIN["email"], "password": "New-Horse-42"}).status_code == 200


def test_reset_links_expire_and_requests_are_limited(client, outbox, monkeypatch):
    setup_admin(client)
    client.post("/auth/forgot", json={"email": ADMIN["email"]})
    token = _reset_token(outbox[0][2])
    monkeypatch.setattr(accounts, "RESET_TTL_S", -1)
    client.post("/auth/forgot", json={"email": ADMIN["email"]})
    expired = _reset_token(outbox[1][2])
    assert client.post("/auth/reset", json={"token": expired, "new_password": "New-Horse-42"}).status_code == 400
    assert client.post("/auth/reset", json={"token": "rst_made-up", "new_password": "New-Horse-42"}).status_code == 400
    # The first, unexpired link still works.
    assert client.post("/auth/reset", json={"token": token, "new_password": "New-Horse-42"}).status_code == 200

    statuses = [client.post("/auth/forgot", json={"email": ADMIN["email"]}).status_code for _ in range(3)]
    assert statuses[-1] == 429
