"""Sign in with Google: ID tokens are verified against the issuer's keys; first sign-in creates a verified account."""
import dataclasses
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.routers import auth

ISS, AUD = "https://accounts.google.com", "test-client.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeJWKS:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(auth, "settings", dataclasses.replace(
        auth.settings, oidc_issuer=ISS, oidc_client_id=AUD, oidc_jwks_url="https://example.test/certs"))
    monkeypatch.setattr(auth, "_jwks", lambda url: FakeJWKS())


def token(email, verified=True, aud=AUD, sub=None, name="Test Person"):
    now = int(time.time())
    return jwt.encode({"iss": ISS, "aud": aud, "sub": sub or uuid.uuid4().hex, "email": email,
                       "email_verified": verified, "name": name, "iat": now, "exp": now + 600}, KEY, algorithm="RS256")


def test_providers_hidden_until_configured(client):
    assert client.get("/v1/auth/providers").json()["google"] is None


def test_providers_lists_google_client_id(client, google):
    assert client.get("/v1/auth/providers").json()["google"] == {"client_id": AUD}


def test_first_google_signin_creates_verified_account(client, google):
    email = f"g-{uuid.uuid4().hex[:8]}@gmail.com"
    r = client.post("/v1/auth/oidc", json={"id_token": token(email)})
    assert r.status_code == 200, r.text
    assert r.json()["created"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get("/v1/auth/me", headers=h).json()
    assert me["email"] == email and me["email_verified"] is True and len(me["tenants"]) == 1
    h["X-Tenant-Id"] = me["tenants"][0]["tenant_id"]
    assert client.get("/v1/devices", headers=h).status_code == 200
    # Second sign-in reuses the account
    again = client.post("/v1/auth/oidc", json={"id_token": token(email)}).json()
    assert again["created"] is False


def test_google_signin_confirms_existing_password_account(client, google, admin_sql):
    email = f"pw-{uuid.uuid4().hex[:8]}@gmail.com"
    client.post("/v1/auth/register", json={"email": email, "password": "a sufficiently long pw", "organisation": "O"})
    r = client.post("/v1/auth/oidc", json={"id_token": token(email.upper())})
    assert r.status_code == 200 and r.json()["created"] is False
    assert admin_sql("SELECT email_verified FROM aav.users WHERE email = %s", email)[0]["email_verified"] is True


def test_unverified_google_email_is_refused(client, google):
    r = client.post("/v1/auth/oidc", json={"id_token": token("u@example.com", verified=False)})
    assert r.status_code == 403


def test_token_for_another_app_is_refused(client, google):
    r = client.post("/v1/auth/oidc", json={"id_token": token("x@gmail.com", aud="someone-else")})
    assert r.status_code == 401
