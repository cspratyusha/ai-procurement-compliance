"""User accounts, sessions, API keys, the activity trail and saved projects.

Everything the workbench needs to be used by more than one person lives here,
in one SQLite file. SQLite because the service already runs as a single
process next to its indexes, and a separate database server would be the only
moving part in the deployment that is not needed for the work.

Design points worth knowing before changing anything:

* **No default account.** A fresh install has no users and reports
  `setup_required`; the first person to open it creates the administrator for
  their organisation. A shipped default password is the most common way a
  deployment like this gets walked into, so there is none.
* **Passwords are hashed with scrypt** (stdlib `hashlib.scrypt`), with a
  per-password salt. The parameters are stored with the hash so they can be
  raised later without invalidating existing passwords.
* **Tokens are stored hashed.** A session token or API key is shown once and
  only its SHA-256 is kept, so a copy of the database does not hand anyone a
  working credential. Tokens are long random strings, so a fast hash is the
  right tool here (unlike passwords).
* **Failed sign-ins are throttled per email**, so the sign-in form cannot be
  used to guess passwords at speed.
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB = Path(__file__).resolve().parent / "storage" / "accounts.db"

ROLES = {
    "admin": "Department administrator",
    "officer": "Procurement officer",
    "integrator": "Agency integrator",
    "private": "Private organisation user",
}
ORG_TYPES = {
    "ministry": "Central government ministry",
    "pse": "Public sector enterprise",
    "state": "State department",
    "private": "Private organisation",
}
# Roles that may hold API keys: an integrator's whole job, and the admin
# who answers for them.
KEY_ROLES = {"admin", "integrator"}

SESSION_TTL_S = 7 * 24 * 3600
# However active a session is, it ends after this; sign in again then. A
# stolen token cannot be kept alive forever by using it.
SESSION_MAX_AGE_S = 30 * 24 * 3600
MIN_PASSWORD_LENGTH = 10
# scrypt's cost grows with the input; a megabyte "password" would tie up the
# server. Nobody types more than this.
MAX_PASSWORD_LENGTH = 256
_MAX_META_BYTES = 4000
_MAX_FAILURES = 5
_LOCKOUT_S = 15 * 60

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1

# The principal for the request being served, set by the auth middleware.
# A context variable rather than a function argument so that code deep in a
# request (the search endpoint recording what was searched) can attribute the
# work without every signature growing a `user` parameter.
current_principal: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "current_principal", default=None
)


class AccountError(Exception):
    """A request the caller can fix. `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# --- storage ---------------------------------------------------------------

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None
_conn_path: Optional[Path] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'ministry',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id                    INTEGER PRIMARY KEY,
    org_id                INTEGER NOT NULL REFERENCES orgs(id),
    email                 TEXT NOT NULL UNIQUE,
    name                  TEXT NOT NULL,
    role                  TEXT NOT NULL,
    password_hash         TEXT NOT NULL,
    language              TEXT NOT NULL DEFAULT 'auto',
    must_change_password  INTEGER NOT NULL DEFAULT 0,
    disabled              INTEGER NOT NULL DEFAULT 0,
    active_project_id     INTEGER,
    created_at            TEXT NOT NULL,
    last_login_at         TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash    TEXT PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at    REAL NOT NULL,
    expires_at    REAL NOT NULL,
    last_seen_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id        INTEGER NOT NULL REFERENCES orgs(id),
    name          TEXT NOT NULL,
    prefix        TEXT NOT NULL,
    key_hash      TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT,
    calls         INTEGER NOT NULL DEFAULT 0,
    revoked_at    TEXT
);
CREATE TABLE IF NOT EXISTS activity (
    id       INTEGER PRIMARY KEY,
    user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    org_id   INTEGER,
    at       TEXT NOT NULL,
    action   TEXT NOT NULL,
    detail   TEXT NOT NULL DEFAULT '',
    meta     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS activity_user ON activity(user_id, id);
CREATE INDEX IF NOT EXISTS activity_org ON activity(org_id, id);
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    spec        TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS projects_user ON projects(user_id, updated_at);
"""


def _db_path() -> Path:
    return Path(os.environ.get("ACCOUNTS_DB") or _DEFAULT_DB)


def _db() -> sqlite3.Connection:
    """One shared connection, reopened if ACCOUNTS_DB changes (tests do this)."""
    global _conn, _conn_path
    path = _db_path()
    if _conn is None or _conn_path != path:
        if _conn is not None:
            _conn.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(_SCHEMA)
        _conn, _conn_path = conn, path
    return _conn


def _q(sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    with _lock:
        return _db().execute(sql, params).fetchall()


def _x(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = _db().execute(sql, params)
        return cur.lastrowid


def reset_for_tests() -> None:
    """Close the connection so the next call opens ACCOUNTS_DB afresh."""
    global _conn, _conn_path
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn, _conn_path = None, None
        _failures.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- passwords and tokens ---------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_password_rules(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(f"Use a password of at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AccountError(f"Use a password of at most {MAX_PASSWORD_LENGTH} characters.")
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        raise AccountError("Use upper and lower case letters and at least one number in the password.")


def _clean_email(email: str) -> str:
    email = (email or "").strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain or " " in email or len(email) > 254:
        raise AccountError("Enter a valid email address.")
    return email


def _clean_name(name: str, what: str = "name") -> str:
    name = " ".join((name or "").split())
    if not name:
        raise AccountError(f"Enter a {what}.")
    if len(name) > 120:
        raise AccountError(f"Keep the {what} under 120 characters.")
    return name


# --- shapes returned to the API ---------------------------------------------

def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _user_out(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "initials": _initials(row["name"]),
        "role": row["role"],
        "role_label": ROLES.get(row["role"], row["role"]),
        "language": row["language"],
        "must_change_password": bool(row["must_change_password"]),
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
        "org_id": row["org_id"],
    }


def _org_out(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "type_label": ORG_TYPES.get(row["type"], row["type"]),
        "created_at": row["created_at"],
    }


def _user_row(user_id: int) -> sqlite3.Row:
    rows = _q("SELECT * FROM users WHERE id = ?", (user_id,))
    if not rows:
        raise AccountError("No such user.", 404)
    return rows[0]


def get_org(org_id: int) -> Dict[str, Any]:
    return _org_out(_q("SELECT * FROM orgs WHERE id = ?", (org_id,))[0])


def me(principal: Dict[str, Any]) -> Dict[str, Any]:
    user = _user_out(_user_row(principal["user_id"]))
    return {"user": user, "org": get_org(user["org_id"])}


# --- first run, sign in, sessions -------------------------------------------

def setup_required() -> bool:
    return not _q("SELECT 1 FROM users LIMIT 1")


def registration_open() -> bool:
    """Whether anyone may create a new organisation. REGISTRATION=closed turns it off."""
    return os.environ.get("REGISTRATION", "open").lower() != "closed"


def setup(org_name: str, org_type: str, name: str, email: str, password: str) -> Dict[str, Any]:
    """Create the organisation and its first administrator. Only on an empty install."""
    with _lock:
        if not setup_required():
            raise AccountError("This installation is already set up. Sign in instead.", 409)
        return _create_org_with_admin(org_name, org_type, name, email, password, "account.setup")


def register(org_name: str, org_type: str, name: str, email: str, password: str) -> Dict[str, Any]:
    """Self-service sign-up: a new organisation, with the registrant as its administrator.

    Registration never joins an existing organisation. Letting a stranger
    attach themselves to a ministry's workspace would hand them its members,
    keys and activity; joining one is by an administrator's invitation only.
    """
    if not registration_open():
        raise AccountError("Registration is closed on this installation. Ask an administrator to add you.", 403)
    with _lock:
        return _create_org_with_admin(org_name, org_type, name, email, password, "account.register")


def _create_org_with_admin(org_name, org_type, name, email, password, action) -> Dict[str, Any]:
    with _lock:
        org_name = _clean_name(org_name, "organisation name")
        if org_type not in ORG_TYPES:
            raise AccountError("Choose an organisation type.")
        name = _clean_name(name)
        email = _clean_email(email)
        _check_password_rules(password)
        if _q("SELECT 1 FROM users WHERE email = ?", (email,)):
            raise AccountError("An account with that email already exists. Sign in instead.", 409)
        org_id = _x("INSERT INTO orgs (name, type, created_at) VALUES (?, ?, ?)", (org_name, org_type, _now()))
        user_id = _x(
            "INSERT INTO users (org_id, email, name, role, password_hash, created_at) VALUES (?, ?, ?, 'admin', ?, ?)",
            (org_id, email, name, hash_password(password), _now()),
        )
    verb = "Set up" if action == "account.setup" else "Registered"
    record(user_id, org_id, action, f"{verb} {org_name} with {email} as administrator")
    return _start_session(user_id)


_failures: Dict[str, List[float]] = {}

# Per client address as well as per email: without it one address can try
# one password against thousands of emails (password spraying), or create
# organisations without limit.
_IP_MAX_FAILURES = 30
_IP_MAX_REGISTRATIONS = 5
_REGISTRATION_WINDOW_S = 3600

# A login for an email with no account still runs the password hash, against
# this, so the response time does not reveal which emails have accounts.
# Made on first use, so importing the module stays fast.
_DUMMY_HASH: Optional[str] = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    return _DUMMY_HASH


def _count_recent(key: str, window: float) -> int:
    cutoff = time.time() - window
    recent = [t for t in _failures.get(key, []) if t > cutoff]
    _failures[key] = recent
    return len(recent)


def _throttled(email: str) -> bool:
    return _count_recent(email, _LOCKOUT_S) >= _MAX_FAILURES


def _note(key: str) -> None:
    _failures.setdefault(key, []).append(time.time())


def check_registration_allowed(client: Optional[str]) -> None:
    if client and _count_recent(f"register:{client}", _REGISTRATION_WINDOW_S) >= _IP_MAX_REGISTRATIONS:
        raise AccountError("Too many accounts created from this address. Try again in an hour.", 429)


def note_registration(client: Optional[str]) -> None:
    if client:
        _note(f"register:{client}")


def login(email: str, password: str, client: Optional[str] = None) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    if _throttled(email) or (client and _count_recent(f"ip:{client}", _LOCKOUT_S) >= _IP_MAX_FAILURES):
        raise AccountError("Too many failed attempts. Wait 15 minutes, then try again.", 429)
    if len(password or "") > MAX_PASSWORD_LENGTH:
        raise AccountError("That email and password do not match an account.", 401)
    rows = _q("SELECT * FROM users WHERE email = ?", (email,))
    # The same message, and the same work, whether the email or the password
    # is wrong, so the form cannot be used to find out who has an account.
    stored = rows[0]["password_hash"] if rows else _dummy_hash()
    if not verify_password(password or "", stored) or not rows:
        _note(email)
        if client:
            _note(f"ip:{client}")
        raise AccountError("That email and password do not match an account.", 401)
    user = rows[0]
    if user["disabled"]:
        raise AccountError("This account has been disabled. Ask your administrator.", 403)
    _failures.pop(email, None)
    _x("UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), user["id"]))
    record(user["id"], user["org_id"], "account.sign_in", "Signed in")
    return _start_session(user["id"])


def _start_session(user_id: int) -> Dict[str, Any]:
    token = "ses_" + secrets.token_urlsafe(32)
    now = time.time()
    _x(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
        (_token_hash(token), user_id, now, now + SESSION_TTL_S, now),
    )
    _x("DELETE FROM sessions WHERE expires_at < ?", (now,))
    principal = {"user_id": user_id, "kind": "session"}
    return {"token": token, **me(principal)}


def logout(token: str) -> None:
    _x("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def authenticate(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Resolve a bearer token (session or API key) to a principal, or None."""
    if not token:
        return None
    digest = _token_hash(token)
    now = time.time()
    if token.startswith("ses_"):
        rows = _q(
            "SELECT s.expires_at, s.created_at, u.id, u.org_id, u.role, u.disabled FROM sessions s "
            "JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (digest,),
        )
        if not rows or rows[0]["expires_at"] < now or rows[0]["disabled"]:
            return None
        row = rows[0]
        # Sliding expiry, so a session in daily use does not lapse mid-week,
        # but never past SESSION_MAX_AGE_S from sign-in.
        hard_end = row["created_at"] + SESSION_MAX_AGE_S
        _x("UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?",
           (now, min(now + SESSION_TTL_S, hard_end), digest))
        return {"user_id": row["id"], "org_id": row["org_id"], "role": row["role"], "kind": "session"}
    if token.startswith("sk_"):
        rows = _q(
            "SELECT k.id AS key_id, k.revoked_at, u.id, u.org_id, u.role, u.disabled FROM api_keys k "
            "JOIN users u ON u.id = k.user_id WHERE k.key_hash = ?",
            (digest,),
        )
        if not rows or rows[0]["revoked_at"] or rows[0]["disabled"]:
            return None
        row = rows[0]
        _x("UPDATE api_keys SET calls = calls + 1, last_used_at = ? WHERE id = ?", (_now(), row["key_id"]))
        return {"user_id": row["id"], "org_id": row["org_id"], "role": row["role"],
                "kind": "api_key", "key_id": row["key_id"]}
    return None


# --- profile and password ---------------------------------------------------

def update_profile(principal: Dict[str, Any], name: Optional[str], language: Optional[str]) -> Dict[str, Any]:
    user = _user_row(principal["user_id"])
    new_name = _clean_name(name) if name is not None else user["name"]
    new_lang = language if language is not None else user["language"]
    if len(new_lang) > 8:
        raise AccountError("Unknown language.")
    _x("UPDATE users SET name = ?, language = ? WHERE id = ?", (new_name, new_lang, user["id"]))
    record(user["id"], user["org_id"], "account.profile", "Updated profile")
    return me(principal)


def change_password(principal: Dict[str, Any], current: str, new: str, keep_token: Optional[str]) -> None:
    user = _user_row(principal["user_id"])
    if not verify_password(current or "", user["password_hash"]):
        raise AccountError("The current password is not correct.", 403)
    _check_password_rules(new)
    if current == new:
        raise AccountError("Choose a password different from the current one.")
    _x("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
       (hash_password(new), user["id"]))
    # Sign out every other session: a password change is often a response
    # to a password having leaked.
    _x("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
       (user["id"], _token_hash(keep_token or "")))
    record(user["id"], user["org_id"], "account.password", "Changed password")


# --- organisation and members -----------------------------------------------

def _require_admin(principal: Dict[str, Any]) -> None:
    if principal.get("role") != "admin":
        raise AccountError("Only a department administrator can do this.", 403)


def update_org(principal: Dict[str, Any], name: Optional[str], org_type: Optional[str]) -> Dict[str, Any]:
    _require_admin(principal)
    org = get_org(principal["org_id"])
    new_name = _clean_name(name, "organisation name") if name is not None else org["name"]
    new_type = org_type if org_type is not None else org["type"]
    if new_type not in ORG_TYPES:
        raise AccountError("Choose an organisation type.")
    _x("UPDATE orgs SET name = ?, type = ? WHERE id = ?", (new_name, new_type, org["id"]))
    record(principal["user_id"], org["id"], "org.update", f"Updated organisation to {new_name}")
    return get_org(org["id"])


def list_members(principal: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _q("SELECT * FROM users WHERE org_id = ? ORDER BY disabled, name", (principal["org_id"],))
    return [_user_out(r) for r in rows]


def invite_member(principal: Dict[str, Any], name: str, email: str, role: str) -> Dict[str, Any]:
    """Create an account with a one-time password the admin passes on.

    There is no mail server in the deployment, so the admin hands the
    temporary password over themselves; the new member must replace it at
    first sign-in.
    """
    _require_admin(principal)
    name = _clean_name(name)
    email = _clean_email(email)
    if role not in ROLES:
        raise AccountError("Choose a role.")
    if _q("SELECT 1 FROM users WHERE email = ?", (email,)):
        raise AccountError("An account with that email already exists.", 409)
    temporary = _temporary_password()
    user_id = _x(
        "INSERT INTO users (org_id, email, name, role, password_hash, must_change_password, created_at) "
        "VALUES (?, ?, ?, ?, ?, 1, ?)",
        (principal["org_id"], email, name, role, hash_password(temporary), _now()),
    )
    record(principal["user_id"], principal["org_id"], "org.invite", f"Added {name} ({email}) as {ROLES[role]}")
    return {"user": _user_out(_user_row(user_id)), "temporary_password": temporary}


def _temporary_password() -> str:
    # Readable to pass on by phone, and satisfies the password rules.
    words = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
    return f"Tmp{words}{secrets.randbelow(90) + 10}"


def update_member(principal: Dict[str, Any], user_id: int, role: Optional[str],
                  disabled: Optional[bool], reset_password: bool = False) -> Dict[str, Any]:
    _require_admin(principal)
    target = _user_row(user_id)
    if target["org_id"] != principal["org_id"]:
        raise AccountError("No such user.", 404)
    if user_id == principal["user_id"] and (role not in (None, "admin") or disabled):
        # Otherwise the last admin can lock the whole organisation out.
        raise AccountError("You cannot remove your own administrator access.")
    out: Dict[str, Any] = {}
    if role is not None:
        if role not in ROLES:
            raise AccountError("Choose a role.")
        _x("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    if disabled is not None:
        _x("UPDATE users SET disabled = ? WHERE id = ?", (1 if disabled else 0, user_id))
        if disabled:
            _x("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    if reset_password:
        temporary = _temporary_password()
        _x("UPDATE users SET password_hash = ?, must_change_password = 1 WHERE id = ?",
           (hash_password(temporary), user_id))
        _x("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        out["temporary_password"] = temporary
    changes = [c for c, on in (
        (f"role {ROLES.get(role, role)}", role is not None),
        ("disabled" if disabled else "enabled", disabled is not None),
        ("password reset", reset_password),
    ) if on]
    record(principal["user_id"], principal["org_id"], "org.member",
           f"Changed {target['name']}: {', '.join(changes) or 'no change'}")
    out["user"] = _user_out(_user_row(user_id))
    return out


# --- API keys ---------------------------------------------------------------

def _key_out(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "prefix": row["prefix"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
        "calls": row["calls"],
        "owner": row["owner"] if "owner" in row.keys() else None,
    }


def list_keys(principal: Dict[str, Any]) -> List[Dict[str, Any]]:
    if principal.get("role") not in KEY_ROLES:
        return []
    # An admin sees every key in the organisation; an integrator their own.
    if principal["role"] == "admin":
        rows = _q("SELECT k.*, u.name AS owner FROM api_keys k JOIN users u ON u.id = k.user_id "
                  "WHERE k.org_id = ? AND k.revoked_at IS NULL ORDER BY k.id DESC", (principal["org_id"],))
    else:
        rows = _q("SELECT k.*, u.name AS owner FROM api_keys k JOIN users u ON u.id = k.user_id "
                  "WHERE k.user_id = ? AND k.revoked_at IS NULL ORDER BY k.id DESC", (principal["user_id"],))
    return [_key_out(r) for r in rows]


def create_key(principal: Dict[str, Any], name: str) -> Dict[str, Any]:
    if principal.get("role") not in KEY_ROLES:
        raise AccountError("Only administrators and integrators can create API keys.", 403)
    if principal.get("kind") == "api_key":
        raise AccountError("Sign in to create API keys; a key cannot mint another key.", 403)
    name = _clean_name(name, "key name")
    secret = "sk_" + secrets.token_urlsafe(32)
    key_id = _x(
        "INSERT INTO api_keys (user_id, org_id, name, prefix, key_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (principal["user_id"], principal["org_id"], name, secret[:10], _token_hash(secret), _now()),
    )
    record(principal["user_id"], principal["org_id"], "api_key.create", f"Created API key {name}")
    row = _q("SELECT k.*, u.name AS owner FROM api_keys k JOIN users u ON u.id = k.user_id WHERE k.id = ?",
             (key_id,))[0]
    return {"key": _key_out(row), "secret": secret}


def revoke_key(principal: Dict[str, Any], key_id: int) -> None:
    rows = _q("SELECT * FROM api_keys WHERE id = ? AND revoked_at IS NULL", (key_id,))
    if not rows or rows[0]["org_id"] != principal["org_id"]:
        raise AccountError("No such key.", 404)
    if principal.get("role") != "admin" and rows[0]["user_id"] != principal["user_id"]:
        raise AccountError("You can revoke only your own keys.", 403)
    _x("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (_now(), key_id))
    record(principal["user_id"], principal["org_id"], "api_key.revoke", f"Revoked API key {rows[0]['name']}")


# --- activity trail ---------------------------------------------------------

def record(user_id: Optional[int], org_id: Optional[int], action: str, detail: str = "",
           meta: Optional[Dict[str, Any]] = None) -> None:
    """Append to the activity trail. Never raises: bookkeeping must not fail a request."""
    try:
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        if len(meta_json) > _MAX_META_BYTES:
            meta_json = json.dumps({"truncated": True})
        _x("INSERT INTO activity (user_id, org_id, at, action, detail, meta) VALUES (?, ?, ?, ?, ?, ?)",
           (user_id, org_id, _now(), action[:60], (detail or "")[:500], meta_json))
    except Exception:  # noqa: BLE001
        pass


def record_current(action: str, detail: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
    """Record against whoever is making the current request, if anyone."""
    principal = current_principal.get()
    if principal is not None:
        if principal.get("kind") == "api_key":
            meta = {**(meta or {}), "via": "api_key", "key_id": principal.get("key_id")}
        record(principal["user_id"], principal.get("org_id"), action, detail, meta)


def list_activity(principal: Dict[str, Any], scope: str = "me", action: Optional[str] = None,
                  limit: int = 50, before: Optional[int] = None) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    where, params = [], []
    if scope == "org":
        _require_admin(principal)
        where.append("a.org_id = ?")
        params.append(principal["org_id"])
    else:
        where.append("a.user_id = ?")
        params.append(principal["user_id"])
    if action:
        where.append("a.action LIKE ?")
        params.append(action.rstrip("*") + "%")
    if before:
        where.append("a.id < ?")
        params.append(int(before))
    rows = _q(
        "SELECT a.*, u.name AS user_name FROM activity a LEFT JOIN users u ON u.id = a.user_id "
        f"WHERE {' AND '.join(where)} ORDER BY a.id DESC LIMIT ?",
        (*params, limit + 1),
    )
    items = [{
        "id": r["id"], "at": r["at"], "action": r["action"], "detail": r["detail"],
        "meta": json.loads(r["meta"] or "{}"), "user": r["user_name"],
    } for r in rows[:limit]]
    return {"items": items, "has_more": len(rows) > limit}


# --- projects (the saved spec basket) ---------------------------------------

_MAX_SPEC_BYTES = 512_000


def _project_out(row: sqlite3.Row, full: bool = True) -> Dict[str, Any]:
    spec = json.loads(row["spec"] or "{}")
    out = {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "item_count": len(spec.get("order", [])),
        "frozen": spec.get("frozen"),
    }
    if full:
        out["spec"] = spec
    return out


def _own_project(principal: Dict[str, Any], project_id: int) -> sqlite3.Row:
    rows = _q("SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, principal["user_id"]))
    if not rows:
        raise AccountError("No such project.", 404)
    return rows[0]


def list_projects(principal: Dict[str, Any]) -> Dict[str, Any]:
    rows = _q("SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (principal["user_id"],))
    active = _user_row(principal["user_id"])["active_project_id"]
    return {"projects": [_project_out(r, full=False) for r in rows], "active_id": active}


def create_project(principal: Dict[str, Any], name: str, spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    name = _clean_name(name, "project name")
    now = _now()
    project_id = _x("INSERT INTO projects (user_id, name, spec, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (principal["user_id"], name, json.dumps(spec or {}), now, now))
    _x("UPDATE users SET active_project_id = ? WHERE id = ?", (project_id, principal["user_id"]))
    record(principal["user_id"], principal.get("org_id"), "project.create", f"Created project {name}")
    return _project_out(_own_project(principal, project_id))


def active_project(principal: Dict[str, Any]) -> Dict[str, Any]:
    """The project the basket edits, creating a first one for a new account."""
    active = _user_row(principal["user_id"])["active_project_id"]
    if active:
        rows = _q("SELECT * FROM projects WHERE id = ? AND user_id = ?", (active, principal["user_id"]))
        if rows:
            return _project_out(rows[0])
    rows = _q("SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1", (principal["user_id"],))
    if rows:
        _x("UPDATE users SET active_project_id = ? WHERE id = ?", (rows[0]["id"], principal["user_id"]))
        return _project_out(rows[0])
    return create_project(principal, "Untitled specification")


def get_project(principal: Dict[str, Any], project_id: int) -> Dict[str, Any]:
    return _project_out(_own_project(principal, project_id))


def save_project(principal: Dict[str, Any], project_id: int, name: Optional[str],
                 spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    row = _own_project(principal, project_id)
    new_name = _clean_name(name, "project name") if name is not None else row["name"]
    new_spec = row["spec"]
    if spec is not None:
        new_spec = json.dumps(spec)
        if len(new_spec) > _MAX_SPEC_BYTES:
            raise AccountError("This specification is too large to save.", 413)
        old = json.loads(row["spec"] or "{}")
        if spec.get("frozen") and spec.get("frozen") != old.get("frozen"):
            record(principal["user_id"], principal.get("org_id"), "project.freeze",
                   f"Froze {new_name} with {len(spec.get('order', []))} standards",
                   {"project_id": project_id, "standards": spec.get("order", [])})
    _x("UPDATE projects SET name = ?, spec = ?, updated_at = ? WHERE id = ?",
       (new_name, new_spec, _now(), project_id))
    if name is not None and new_name != row["name"]:
        record(principal["user_id"], principal.get("org_id"), "project.rename",
               f"Renamed {row['name']} to {new_name}")
    return _project_out(_own_project(principal, project_id))


def activate_project(principal: Dict[str, Any], project_id: int) -> Dict[str, Any]:
    row = _own_project(principal, project_id)
    _x("UPDATE users SET active_project_id = ? WHERE id = ?", (project_id, principal["user_id"]))
    return _project_out(row)


def delete_project(principal: Dict[str, Any], project_id: int) -> None:
    row = _own_project(principal, project_id)
    _x("DELETE FROM projects WHERE id = ?", (project_id,))
    _x("UPDATE users SET active_project_id = NULL WHERE id = ? AND active_project_id = ?",
       (principal["user_id"], project_id))
    record(principal["user_id"], principal.get("org_id"), "project.delete", f"Deleted project {row['name']}")
