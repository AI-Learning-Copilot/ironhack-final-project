"""Login gate for the Streamlit app, built on `st.login()` (native since Streamlit 1.42).

    from auth import require_login
    email = require_login()   # stops the script on the sign-in page until logged in

Configuration lives in Streamlit secrets, never in the repo. Locally that is
`.streamlit/secrets.toml` (gitignored); on Community Cloud it is the Secrets box in the
app settings.

    [auth]
    redirect_uri        = "https://<app>.streamlit.app/oauth2callback"   # or http://localhost:8501/oauth2callback
    cookie_secret       = "<random string, 32+ chars>"
    client_id           = "<Google OAuth client id>"
    client_secret       = "<Google OAuth client secret>"
    server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

    [access]
    emails  = ["felipe@example.com", "student@example.com"]   # exact addresses
    domains = ["ironhack.com"]                                # or whole domains

When `[auth]` is absent the gate is skipped and every turn is logged as "local". That
keeps `streamlit run app/app.py` working on a laptop with no OAuth client, and it means
a misconfigured deployment fails open only in the sense of not gating — the API key is
still needed, so nothing is exposed that was not exposed before the gate existed.

`Authlib` must be installed for `st.login()`; it is pinned in requirements.txt.
"""

from __future__ import annotations

import logging

import streamlit as st

log = logging.getLogger(__name__)

LOCAL_USER = "local"


def _secret_section(name: str) -> dict:
    try:
        section = st.secrets[name]
    except Exception:  # noqa: BLE001 — no secrets file, or no such section
        return {}
    return dict(section)


def auth_configured() -> bool:
    return bool(_secret_section("auth").get("client_id"))


def _allowed(email: str) -> bool:
    access = _secret_section("access")
    emails = {e.strip().lower() for e in access.get("emails", [])}
    domains = {d.strip().lower().lstrip("@") for d in access.get("domains", [])}
    if not emails and not domains:
        # No allowlist configured: any Google account that completes the login is in.
        return True
    email = email.lower()
    return email in emails or email.split("@")[-1] in domains


def _sign_in_page() -> None:
    st.markdown(
        """
        <div class="vc-hero">
          <h1>Ironhack AI Course Copilot</h1>
          <p>A study assistant grounded in the AI Engineering bootcamp recordings and
          notebooks. Sign in to try it.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button("Sign in with Google", on_click=st.login, type="primary")
    st.caption(
        "Access is by invitation. If your account is not on the list, ask Casilda or Felipe."
    )


def require_login() -> str:
    """Return the signed-in user's email, or stop the script on the sign-in page.

    Returns "local" without gating when no `[auth]` secrets exist.
    """
    if not auth_configured():
        if not st.session_state.get("_auth_warned"):
            log.warning("no [auth] secrets configured; login gate disabled")
            st.session_state["_auth_warned"] = True
        return LOCAL_USER

    if not st.user.is_logged_in:
        _sign_in_page()
        st.stop()

    email = st.user.get("email") or ""
    if not email or not _allowed(email):
        st.error("This account is not on the access list. Ask Casilda or Felipe to add it.")
        st.button("Sign out", on_click=st.logout)
        st.stop()

    return email
