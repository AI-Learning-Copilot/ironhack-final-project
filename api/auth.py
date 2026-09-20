"""Who is calling. Supabase Auth issues the token; this module checks it.

The frontend signs the student in with Supabase (Google, or email) and sends the session
token on every call:

    Authorization: Bearer <supabase access token>

Verification is local — no round trip to Supabase per request. A Supabase project signs
tokens either with a shared secret (HS256, the "legacy JWT secret" in the dashboard) or
with a key pair published at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` (ES256 or
RS256, "JWT signing keys"). Both are handled: the token's own header says which.

Configuration, all from the environment:

    SUPABASE_URL          required for JWKS verification
    SUPABASE_JWT_SECRET   only for projects still on the legacy HS256 secret
    AUTH_REQUIRED         "true" to reject calls without a valid token. Default "false":
                          a valid token is honoured when present, a missing one means
                          `anonymous`. This is the switch to flip once the frontend
                          sends tokens, so the two sides can move independently.

Access list: the `allowlist` table in Supabase. Empty table = every signed-in account is
allowed (so the first login works). Rows can be an exact email or "@domain.com". Cached
for a minute so the table is not read on every request.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import supa

log = logging.getLogger("api.auth")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").strip().lower() in {"1", "true", "yes"}

ALLOWLIST_TTL_SECONDS = 60

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    id: str
    email: str

    @property
    def anonymous(self) -> bool:
        return self.id == "anonymous"


ANONYMOUS = User(id="anonymous", email="")


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"message": message, "kind": "auth"})


@lru_cache(maxsize=1)
def _jwks_client():
    # PyJWKClient caches keys and refreshes on an unknown kid, so rotation just works.
    return jwt.PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json", cache_keys=True)


def decode_token(token: str) -> dict:
    """The verified claims, or raise jwt.PyJWTError."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")
    options = {"require": ["sub", "exp"]}

    if alg.startswith("HS"):
        if not JWT_SECRET:
            raise jwt.PyJWTError("token is HS256 but SUPABASE_JWT_SECRET is not set")
        return jwt.decode(token, JWT_SECRET, algorithms=[alg], audience="authenticated",
                          options=options)

    if not SUPABASE_URL:
        raise jwt.PyJWTError("token is asymmetric but SUPABASE_URL is not set")
    key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=[alg], audience="authenticated",
                      options=options)


_allowlist_cache: tuple[float, list[str]] = (0.0, [])


def _allowlist() -> list[str]:
    """Lower-cased entries from the `allowlist` table, cached for a minute."""
    global _allowlist_cache
    fetched_at, entries = _allowlist_cache
    if time.time() - fetched_at < ALLOWLIST_TTL_SECONDS:
        return entries
    if not supa.configured():
        return []
    try:
        rows = supa.client().table("allowlist").select("email").execute().data or []
        entries = [r["email"].strip().lower() for r in rows if r.get("email")]
    except Exception:  # noqa: BLE001 — a DB hiccup must not lock everyone out
        log.exception("could not read allowlist; keeping the previous one")
        return entries
    _allowlist_cache = (time.time(), entries)
    return entries


def is_allowed(email: str) -> bool:
    entries = _allowlist()
    if not entries:
        return True  # bootstrap mode: nobody listed yet
    email = email.strip().lower()
    domain = "@" + email.split("@")[-1]
    return email in entries or domain in entries


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    """FastAPI dependency. Put `user: User = Depends(current_user)` on a route."""
    if creds is None or not creds.credentials:
        if AUTH_REQUIRED:
            raise _unauthorized("Sign in to use the copilot.")
        return ANONYMOUS

    try:
        claims = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session has expired. Sign in again.")
    except jwt.PyJWTError as exc:
        log.warning("rejected token: %s", exc)
        raise _unauthorized("Sign in to use the copilot.")

    email = (claims.get("email") or "").strip().lower()
    user = User(id=str(claims["sub"]), email=email)

    if not is_allowed(email):
        raise HTTPException(
            status_code=403,
            detail={
                "message": "This account is not on the access list. Ask Casilda or Felipe to add it.",
                "kind": "forbidden",
            },
        )
    return user
