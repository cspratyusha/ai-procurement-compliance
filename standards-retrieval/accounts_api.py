"""HTTP layer for accounts: the auth middleware and the /auth, /org, /keys,
/activity and /projects routes. The rules themselves live in accounts.py.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import accounts

# Reachable without signing in: the docs, the health check the sign-in page
# uses to say whether the engine is up, and the routes that produce a session.
PUBLIC_PATHS = {
    "/", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json", "/favicon.ico",
    "/health", "/auth/status", "/auth/setup", "/auth/register", "/auth/login",
}


def auth_required() -> bool:
    """On unless AUTH_REQUIRED=0 (the unit tests switch it off for engine tests)."""
    return os.environ.get("AUTH_REQUIRED", "1") != "0"


def _bearer(headers: Dict[bytes, bytes]) -> Optional[str]:
    value = headers.get(b"authorization", b"").decode("latin-1").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    key = headers.get(b"x-api-key", b"").decode("latin-1").strip()
    return key or None


class AuthMiddleware:
    """Resolve the caller for every request, and refuse anonymous ones.

    Pure ASGI rather than BaseHTTPMiddleware so the principal it sets in the
    context variable is visible to the endpoint (and to the threadpool that
    runs sync endpoints).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        principal = accounts.authenticate(_bearer(headers))
        path = scope.get("path", "")

        if principal is None and auth_required() and path not in PUBLIC_PATHS:
            body = json.dumps({"detail": "Sign in to use the standards engine."}).encode()
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode()),
            ]})
            await send({"type": "http.response.body", "body": body})
            return

        scope.setdefault("state", {})["principal"] = principal
        token = accounts.current_principal.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            accounts.current_principal.reset(token)


router = APIRouter()


def _principal(request: Request) -> Dict[str, Any]:
    principal = request.scope.get("state", {}).get("principal")
    if principal is None:
        raise HTTPException(status_code=401, detail="Sign in first.")
    return principal


def _token(request: Request) -> Optional[str]:
    return _bearer(dict(request.scope.get("headers") or []))


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except accounts.AccountError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


# --- models -----------------------------------------------------------------

class SetupRequest(BaseModel):
    org_name: str
    org_type: str = "ministry"
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None


class InviteRequest(BaseModel):
    name: str
    email: str
    role: str = "officer"


class MemberUpdate(BaseModel):
    role: Optional[str] = None
    disabled: Optional[bool] = None
    reset_password: bool = False


class KeyCreate(BaseModel):
    name: str


class ProjectCreate(BaseModel):
    name: str = "Untitled specification"
    spec: Optional[Dict[str, Any]] = None


class ProjectSave(BaseModel):
    name: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None


class ActivityEvent(BaseModel):
    action: str = Field(..., pattern=r"^(spec|result|export)\.[a-z_]+$")
    detail: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)


# --- auth -------------------------------------------------------------------

@router.get("/auth/status", tags=["accounts"], summary="Whether first-run setup is needed")
def auth_status(request: Request):
    principal = request.scope.get("state", {}).get("principal")
    return {
        "setup_required": accounts.setup_required(),
        "registration_open": accounts.registration_open(),
        "signed_in": principal is not None,
        "roles": accounts.ROLES,
        "org_types": accounts.ORG_TYPES,
        "min_password_length": accounts.MIN_PASSWORD_LENGTH,
    }


@router.post("/auth/setup", tags=["accounts"], summary="Create the first administrator")
def auth_setup(body: SetupRequest):
    return _run(accounts.setup, body.org_name, body.org_type, body.name, body.email, body.password)


@router.post("/auth/register", tags=["accounts"], summary="Create an account and a new organisation")
def auth_register(body: SetupRequest):
    return _run(accounts.register, body.org_name, body.org_type, body.name, body.email, body.password)


@router.post("/auth/login", tags=["accounts"], summary="Sign in")
def auth_login(body: LoginRequest):
    return _run(accounts.login, body.email, body.password)


@router.post("/auth/logout", tags=["accounts"], summary="Sign out this session")
def auth_logout(request: Request):
    principal = _principal(request)
    token = _token(request)
    if token and principal.get("kind") == "session":
        accounts.logout(token)
        accounts.record(principal["user_id"], principal.get("org_id"), "account.sign_out", "Signed out")
    return {"status": "signed_out"}


@router.get("/auth/me", tags=["accounts"], summary="The signed-in user and organisation")
def auth_me(request: Request):
    return _run(accounts.me, _principal(request))


@router.patch("/auth/me", tags=["accounts"], summary="Update your profile")
def auth_update_me(body: ProfileUpdate, request: Request):
    return _run(accounts.update_profile, _principal(request), body.name, body.language)


@router.post("/auth/password", tags=["accounts"], summary="Change your password")
def auth_password(body: PasswordChange, request: Request):
    _run(accounts.change_password, _principal(request), body.current_password, body.new_password, _token(request))
    return {"status": "changed"}


# --- organisation -----------------------------------------------------------

@router.patch("/org", tags=["accounts"], summary="Update the organisation (admin)")
def org_update(body: OrgUpdate, request: Request):
    return _run(accounts.update_org, _principal(request), body.name, body.type)


@router.get("/org/members", tags=["accounts"], summary="Members of your organisation")
def org_members(request: Request):
    return {"members": _run(accounts.list_members, _principal(request))}


@router.post("/org/members", tags=["accounts"], summary="Add a member (admin)")
def org_invite(body: InviteRequest, request: Request):
    return _run(accounts.invite_member, _principal(request), body.name, body.email, body.role)


@router.patch("/org/members/{user_id}", tags=["accounts"], summary="Change a member (admin)")
def org_member_update(user_id: int, body: MemberUpdate, request: Request):
    return _run(accounts.update_member, _principal(request), user_id, body.role, body.disabled, body.reset_password)


# --- API keys ---------------------------------------------------------------

@router.get("/keys", tags=["accounts"], summary="Active API keys")
def keys_list(request: Request):
    return {"keys": _run(accounts.list_keys, _principal(request))}


@router.post("/keys", tags=["accounts"], summary="Create an API key (secret shown once)")
def keys_create(body: KeyCreate, request: Request):
    return _run(accounts.create_key, _principal(request), body.name)


@router.delete("/keys/{key_id}", tags=["accounts"], summary="Revoke an API key")
def keys_revoke(key_id: int, request: Request):
    _run(accounts.revoke_key, _principal(request), key_id)
    return {"status": "revoked"}


# --- activity ---------------------------------------------------------------

@router.get("/activity", tags=["accounts"], summary="Your activity trail, or the organisation's (admin)")
def activity_list(request: Request, scope: str = "me", action: Optional[str] = None,
                  limit: int = 50, before: Optional[int] = None):
    return _run(accounts.list_activity, _principal(request), scope, action, limit, before)


@router.post("/activity", tags=["accounts"], summary="Record an action taken in the workbench")
def activity_record(body: ActivityEvent, request: Request):
    principal = _principal(request)
    accounts.record(principal["user_id"], principal.get("org_id"), body.action, body.detail, body.meta)
    return {"status": "recorded"}


# --- projects ---------------------------------------------------------------

@router.get("/projects", tags=["projects"], summary="Your saved projects")
def projects_list(request: Request):
    return _run(accounts.list_projects, _principal(request))


@router.post("/projects", tags=["projects"], summary="Start a new project and make it active")
def projects_create(body: ProjectCreate, request: Request):
    return _run(accounts.create_project, _principal(request), body.name, body.spec)


@router.get("/projects/active", tags=["projects"], summary="The project the spec basket edits")
def projects_active(request: Request):
    return _run(accounts.active_project, _principal(request))


@router.get("/projects/{project_id}", tags=["projects"], summary="One project")
def projects_get(project_id: int, request: Request):
    return _run(accounts.get_project, _principal(request), project_id)


@router.put("/projects/{project_id}", tags=["projects"], summary="Save a project")
def projects_save(project_id: int, body: ProjectSave, request: Request):
    return _run(accounts.save_project, _principal(request), project_id, body.name, body.spec)


@router.post("/projects/{project_id}/activate", tags=["projects"], summary="Switch the basket to this project")
def projects_activate(project_id: int, request: Request):
    return _run(accounts.activate_project, _principal(request), project_id)


@router.delete("/projects/{project_id}", tags=["projects"], summary="Delete a project")
def projects_delete(project_id: int, request: Request):
    _run(accounts.delete_project, _principal(request), project_id)
    return {"status": "deleted"}
