"""Local Sign in with ChatGPT credentials for eligible Responses API usage.

This module never reads project ``.env`` files. Credentials are stored beneath
``~/.tradingagents`` with owner-only permissions and are not included in errors.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import tempfile
import threading
import time
import uuid
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTHORIZATION_ENDPOINT = "https://auth.openai.com/api/accounts/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/api/accounts/oauth/token"
DISCOVERY_ENDPOINT = "https://auth.openai.com/.well-known/openid-configuration"
JWKS_ENDPOINT = "https://auth.openai.com/.well-known/jwks.json"
ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
_TOKEN_LOCK = threading.Lock()


class ChatGPTAuthError(RuntimeError):
    """Safe, user-facing authentication error without credential values."""


def credentials_path() -> Path:
    return Path.home() / ".tradingagents" / "auth" / "chatgpt-plan.json"


def host_id_path() -> Path:
    return Path.home() / ".tradingagents" / "auth" / "chatgpt-host-id"


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write(contents)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _read_credentials() -> dict[str, Any] | None:
    path = credentials_path()
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
        raise ChatGPTAuthError(
            "ChatGPT credentials have unsafe file permissions. Run chmod 600 "
            f"{path} and try again."
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ChatGPTAuthError("The saved ChatGPT connection file is unreadable.") from None
    required = ("client_id", "access_token", "refresh_token", "id_token", "scopes")
    if not isinstance(value, dict) or any(not value.get(key) for key in required):
        raise ChatGPTAuthError("The saved ChatGPT connection is incomplete. Reconnect it.")
    return value


def _save_credentials(value: dict[str, Any]) -> None:
    _atomic_write(credentials_path(), json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def _credential_file_lock():
    """Serialize rotating refresh tokens across CLI processes on one host."""
    path = credentials_path().with_suffix(".lock")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    if os.name == "posix":
        os.fchmod(descriptor, 0o600)
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX)
    else:  # pragma: no cover - Windows-specific lock
        import msvcrt

        os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
    try:
        yield
    finally:
        if os.name == "posix":
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        else:  # pragma: no cover - Windows-specific lock
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        os.close(descriptor)


def _host_id() -> str:
    path = host_id_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value.startswith("urn:uuid:"):
            return value
    except FileNotFoundError:
        pass
    value = f"urn:uuid:{uuid.uuid4()}"
    _atomic_write(path, value + "\n")
    return value


def _safe_http_error(response: requests.Response, action: str) -> ChatGPTAuthError:
    status = response.status_code
    return ChatGPTAuthError(f"ChatGPT {action} failed (HTTP {status}). No credentials were shown.")


def _exchange_code(code: str, client_id: str, verifier: str, redirect_uri: str) -> dict[str, Any]:
    try:
        response = requests.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": RESOURCE,
            },
            timeout=20,
        )
    except requests.RequestException:
        raise ChatGPTAuthError("Could not reach the ChatGPT sign-in service.") from None
    if not response.ok:
        raise _safe_http_error(response, "sign-in")
    try:
        result = response.json()
    except ValueError:
        raise ChatGPTAuthError("ChatGPT sign-in returned an invalid response.") from None
    if not isinstance(result, dict):
        raise ChatGPTAuthError("ChatGPT sign-in returned an invalid response.")
    return result


def _validate_id_token(id_token: str, client_id: str, nonce: str) -> dict[str, Any]:
    try:
        import jwt
    except ImportError:
        raise ChatGPTAuthError(
            'Install the optional dependency with: pip install ".[chatgpt-plan]"'
        ) from None
    try:
        key = jwt.PyJWKClient(JWKS_ENDPOINT, cache_jwk_set=True, timeout=10).get_signing_key_from_jwt(
            id_token
        )
        claims = jwt.decode(
            id_token,
            key.key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            audience=client_id,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except Exception:
        raise ChatGPTAuthError("ChatGPT identity token validation failed.") from None
    if claims.get("nonce") != nonce or not claims.get("sub"):
        raise ChatGPTAuthError("ChatGPT identity token validation failed.")
    return claims


def _wait_for_callback(
    params: dict[str, str], timeout: int
) -> tuple[str, dict[str, list[str]] | None]:
    """Serve one browser redirect on loopback and return its URI and query."""
    callback_result: list[dict[str, list[str]]] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_error(404)
                return
            callback_result.append(parse_qs(parsed.query, keep_blank_values=True))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<!doctype html><title>TradingAgents</title>"
                b"<p>Sign-in received. You can close this tab and return to TradingAgents.</p>"
            )

        def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler API
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), CallbackHandler)
    server.timeout = timeout
    redirect_uri = f"http://127.0.0.1:{server.server_port}/auth/callback"
    params["redirect_uri"] = redirect_uri
    authorization_url = f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"
    try:
        try:
            opened = webbrowser.open(authorization_url)
        except Exception:
            raise ChatGPTAuthError("Could not open a browser for ChatGPT sign-in.") from None
        if not opened:
            raise ChatGPTAuthError("Could not open a browser for ChatGPT sign-in.")
        server.handle_request()
    finally:
        server.server_close()
    return redirect_uri, callback_result[0] if callback_result else None


def connect_chatgpt(timeout: int = 300) -> dict[str, str]:
    """Run a loopback PKCE authorization and save a validated ChatGPT grant."""
    old = _read_credentials()
    host_id = _host_id()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    client_id = old["client_id"] if old else "dynamic_agent_client"
    params = {
        "client_id": client_id,
        "ext_agent_host_id": host_id,
        "response_type": "code",
        "scope": SCOPES,
        "resource": RESOURCE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    if old:
        params["id_token_hint"] = old["id_token"]
        if old.get("email"):
            params["login_hint"] = old["email"]
    else:
        params["agent_name_hint"] = "TradingAgents"
    redirect_uri, callback = _wait_for_callback(params, timeout)
    if not callback:
        raise ChatGPTAuthError("ChatGPT sign-in timed out before the browser callback.")
    if callback.get("state", [None])[0] != state:
        raise ChatGPTAuthError("ChatGPT sign-in state validation failed.")
    if callback.get("error"):
        raise ChatGPTAuthError("ChatGPT sign-in was declined or could not be completed.")
    code = callback.get("code", [None])[0]
    returned_client_id = callback.get("client_id", [None])[0]
    if old:
        if returned_client_id and returned_client_id != old["client_id"]:
            raise ChatGPTAuthError("ChatGPT returned a different account registration.")
        registered_client_id = old["client_id"]
    else:
        registered_client_id = returned_client_id
        if not registered_client_id or registered_client_id == "dynamic_agent_client":
            raise ChatGPTAuthError("ChatGPT did not return a registered client ID.")
    if not code:
        raise ChatGPTAuthError("ChatGPT sign-in did not return an authorization code.")

    token_data = _exchange_code(code, registered_client_id, verifier, redirect_uri)
    scopes = str(token_data.get("scope") or "").split()
    if PLAN_SCOPE not in scopes:
        raise ChatGPTAuthError(
            "ChatGPT plan usage was not authorized. Reconnect and grant the plan usage permission."
        )
    id_token = token_data.get("id_token")
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    if not all(isinstance(value, str) and value for value in (id_token, access_token, refresh_token)):
        raise ChatGPTAuthError("ChatGPT sign-in did not return the required credentials.")
    if token_data.get("token_type", "Bearer").lower() != "bearer":
        raise ChatGPTAuthError("ChatGPT sign-in returned an unsupported token type.")
    claims = _validate_id_token(id_token, registered_client_id, nonce)
    if old and claims.get("sub") != old.get("subject"):
        raise ChatGPTAuthError("The signed-in ChatGPT account does not match the saved connection.")

    saved = {
        "client_id": registered_client_id,
        "ext_agent_host_id": host_id,
        "subject": claims["sub"],
        "email": claims.get("email"),
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_at": int(time.time()) + int(token_data.get("expires_in", 3600)),
        "scopes": scopes,
    }
    _save_credentials(saved)
    return {"email": str(saved.get("email") or ""), "client_id": registered_client_id}


def get_access_token() -> str:
    """Return a valid access token, refreshing once when near expiry."""
    with _TOKEN_LOCK, _credential_file_lock():
        saved = _read_credentials()
        if saved is None:
            raise ChatGPTAuthError(
                "ChatGPT plan is not connected. Run `tradingagents auth connect` first."
            )
        if PLAN_SCOPE not in saved.get("scopes", []):
            raise ChatGPTAuthError("The saved ChatGPT connection lacks plan usage permission.")
        if int(saved.get("expires_at", 0)) > int(time.time()) + 90:
            return saved["access_token"]
        try:
            response = requests.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "refresh_token",
                    "client_id": saved["client_id"],
                    "refresh_token": saved["refresh_token"],
                    "resource": RESOURCE,
                },
                timeout=20,
            )
        except requests.RequestException:
            raise ChatGPTAuthError("Could not reach the ChatGPT token renewal service.") from None
        if not response.ok:
            raise _safe_http_error(response, "token renewal")
        try:
            renewed = response.json()
        except ValueError:
            raise ChatGPTAuthError("ChatGPT token renewal returned an invalid response.") from None
        if not isinstance(renewed, dict) or not renewed.get("access_token"):
            raise ChatGPTAuthError("ChatGPT token renewal returned an invalid response.")
        new_scopes = str(renewed.get("scope") or " ".join(saved["scopes"])).split()
        if PLAN_SCOPE not in new_scopes:
            raise ChatGPTAuthError("ChatGPT token renewal did not retain plan usage permission.")
        saved.update(
            access_token=renewed["access_token"],
            refresh_token=renewed.get("refresh_token") or saved["refresh_token"],
            expires_at=int(time.time()) + int(renewed.get("expires_in", 3600)),
            scopes=new_scopes,
        )
        _save_credentials(saved)
        return saved["access_token"]


def connection_status() -> dict[str, str] | None:
    saved = _read_credentials()
    if saved is None:
        return None
    return {"email": str(saved.get("email") or ""), "client_id": str(saved["client_id"])}


def list_account_models() -> list[tuple[str, str]]:
    token = get_access_token()
    try:
        response = requests.get(
            f"{RESOURCE}/models",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
    except requests.RequestException:
        raise ChatGPTAuthError("Could not retrieve the ChatGPT account model list.") from None
    if not response.ok:
        raise _safe_http_error(response, "model list request")
    try:
        models = response.json().get("models", [])
    except (ValueError, AttributeError):
        raise ChatGPTAuthError("ChatGPT returned an invalid model list.") from None
    return [
        (str(model["display_name"]), str(model["slug"]))
        for model in models
        if isinstance(model, dict)
        and model.get("visibility") == "list"
        and model.get("slug")
    ]


def disconnect_chatgpt() -> bool:
    """Revoke the renewable session when possible, then clear local tokens."""
    saved = _read_credentials()
    if saved is None:
        return True
    revoked = False
    try:
        discovery = requests.get(DISCOVERY_ENDPOINT, timeout=10)
        if discovery.ok:
            endpoint = discovery.json().get("revocation_endpoint")
            if endpoint:
                response = requests.post(
                    endpoint,
                    data={
                        "token": saved["refresh_token"],
                        "token_type_hint": "refresh_token",
                        "client_id": saved["client_id"],
                    },
                    timeout=10,
                )
                revoked = response.status_code == 200
    except (requests.RequestException, ValueError, AttributeError):
        revoked = False
    credentials_path().unlink(missing_ok=True)
    return revoked
