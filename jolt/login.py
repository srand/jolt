"""
Signs in to an OpenID Connect provider with the OAuth device authorization
grant, and keeps a valid ID token that authenticates Jolt with the cache and
scheduler services.

The refresh and ID tokens are stored in the system keyring. The ID token is
refreshed when it is about to expire.
"""

import base64
import json
import threading
import time

from jolt import config
from jolt import log
from jolt.error import raise_error, raise_error_if


NAME = "auth"
KEYRING_SERVICE = "jolt"

# Tokens are refreshed when they expire in less than this many seconds, so
# that they stay valid through calls and tools that receive them.
REFRESH_MARGIN = 300

_lock = threading.Lock()
_id_token = None


def is_configured():
    return bool(config.get(NAME, "issuer"))


def _issuer():
    return config.get(NAME, "issuer").rstrip("/")


def _client_id():
    return config.get(NAME, "client_id", "jolt")


def _client_auth(data):
    secret = config.get(NAME, "client_secret")
    if secret:
        data["client_secret"] = secret
    data["client_id"] = _client_id()
    return data


def _keyring_user(kind):
    return "{}:{}:{}".format(kind, _issuer(), _client_id())


def _keyring_get(kind):
    import keyring
    return keyring.get_password(KEYRING_SERVICE, _keyring_user(kind))


def _keyring_set(kind, value):
    import keyring
    if value:
        keyring.set_password(KEYRING_SERVICE, _keyring_user(kind), value)
    else:
        _keyring_delete(kind)


def _keyring_delete(kind):
    import keyring
    from keyring.errors import PasswordDeleteError
    try:
        keyring.delete_password(KEYRING_SERVICE, _keyring_user(kind))
    except PasswordDeleteError:
        pass


def _verify():
    return config.get_ca_cert() or True


def _discover():
    import requests
    url = _issuer() + "/.well-known/openid-configuration"
    try:
        response = requests.get(url, verify=_verify(), timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise_error("Failed to get the configuration of the OIDC provider from {}: {}", url, exc)


def _post(url, data):
    """ Posts a form and returns the status code and the JSON response. """
    import requests
    try:
        response = requests.post(url, data=data, verify=_verify(), timeout=30)
    except Exception as exc:
        raise_error("Failed to reach the OIDC provider at {}: {}", url, exc)
    try:
        return response.status_code, response.json()
    except ValueError:
        raise_error("Invalid response from the OIDC provider at {}: {} {}", url, response.status_code, response.text[:200])


def _expiry(token):
    """ Returns the expiry time of a JWT, without verifying it. """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))["exp"]
    except Exception:
        return 0


def _valid(token):
    return token and _expiry(token) - time.time() > REFRESH_MARGIN


def _store(tokens):
    """ Stores the tokens of a token response and returns the ID token. """
    global _id_token

    id_token = tokens.get("id_token")
    raise_error_if(not id_token, "The OIDC provider didn't return an ID token, is the openid scope requested?")
    # Providers that don't rotate refresh tokens don't return them again
    if tokens.get("refresh_token"):
        _keyring_set("refresh_token", tokens["refresh_token"])
    _keyring_set("id_token", id_token)
    _id_token = id_token
    return id_token


def login():
    """ Signs in with the device authorization grant and stores the tokens. """
    raise_error_if(not is_configured(), "Configure the OIDC provider with 'jolt config auth.issuer <url>'")

    provider = _discover()
    device_endpoint = provider.get("device_authorization_endpoint")
    raise_error_if(not device_endpoint, "The OIDC provider at {} doesn't support the device authorization grant", _issuer())

    scopes = config.get(NAME, "scopes", "openid profile offline_access")
    status, device = _post(device_endpoint, _client_auth({"scope": scopes}))
    raise_error_if(status != 200, "The OIDC provider refused to start the login: {}",
                   device.get("error_description") or device.get("error"))

    if device.get("verification_uri_complete"):
        log.info("Open this URL to sign in: {}", device["verification_uri_complete"])
    else:
        log.info("Open this URL to sign in: {}", device["verification_uri"])
    log.info("Code: {}", device["user_code"])

    interval = device.get("interval", 5)
    deadline = time.time() + device.get("expires_in", 600)
    while time.time() < deadline:
        time.sleep(interval)
        status, tokens = _post(provider["token_endpoint"], _client_auth({
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device["device_code"],
        }))
        if status == 200:
            with _lock:
                _store(tokens)
            if not tokens.get("refresh_token"):
                log.warning("The OIDC provider didn't return a refresh token, request the offline_access scope to stay logged in")
            return
        error = tokens.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise_error("Login failed: {}", tokens.get("error_description") or error)

    raise_error("Login timed out")


def logout():
    """ Removes the stored tokens. """
    global _id_token
    raise_error_if(not is_configured(), "No OIDC provider is configured")
    with _lock:
        _keyring_delete("refresh_token")
        _keyring_delete("id_token")
        _id_token = None


def _refresh():
    refresh_token = _keyring_get("refresh_token")
    raise_error_if(not refresh_token, "The login has expired, run 'jolt login'")

    provider = _discover()
    status, tokens = _post(provider["token_endpoint"], _client_auth({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }))
    if status != 200:
        # Another Jolt process may have used the refresh token first, if
        # the provider rotates them
        id_token = _keyring_get("id_token")
        if _valid(id_token):
            return id_token
        raise_error("The login has expired, run 'jolt login': {}",
                    tokens.get("error_description") or tokens.get("error"))
    return _store(tokens)


def get_token():
    """
    Returns a valid ID token, refreshed if needed, or None if not logged in.
    """
    global _id_token

    if not is_configured():
        return None

    with _lock:
        if _valid(_id_token):
            return _id_token
        try:
            _id_token = _keyring_get("id_token")
        except Exception as exc:
            log.debug("Failed to read the login from the keyring: {}", exc)
            return None
        if _valid(_id_token):
            return _id_token
        if not _id_token and not _keyring_get("refresh_token"):
            return None
        _id_token = _refresh()
        return _id_token
