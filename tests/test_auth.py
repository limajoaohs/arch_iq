"""Testes da autenticacao Cognito (get_current_user) com tokens assinados localmente."""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import importlib

app_module = importlib.import_module("src.api.app")

POOL = "us-east-1_TESTPOOL"
CLIENT = "test-client-id"
ISSUER = f"https://cognito-idp.us-east-1.amazonaws.com/{POOL}"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

client = TestClient(app_module.app, raise_server_exceptions=False)


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": KEY.public_key()})()


@pytest.fixture(autouse=True)
def cognito_on(monkeypatch):
    monkeypatch.setattr(app_module.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(app_module.settings, "cognito_user_pool_id", POOL)
    monkeypatch.setattr(app_module.settings, "cognito_client_id", CLIENT)
    monkeypatch.setattr(app_module, "_jwks_client", FakeJwks())


def make_token(key=KEY, **overrides):
    claims = {"sub": "u1", "iss": ISSUER, "token_use": "access", "client_id": CLIENT,
              "exp": int(time.time()) + 300}
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


def audit(token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/audit", json={"code_or_prompt": ""}, headers=headers)


def test_valid_token_passes_auth():
    # Payload vazio -> 400 da rota, ou seja, passou pela autenticacao
    assert audit(make_token()).status_code == 400


@pytest.mark.parametrize("token", [
    None,
    "nao-e-jwt",
    make_token(key=OTHER_KEY),
    make_token(exp=int(time.time()) - 10),
    make_token(iss="https://cognito-idp.us-east-1.amazonaws.com/outro-pool"),
    make_token(token_use="id"),
    make_token(client_id="outro-client"),
])
def test_invalid_tokens_rejected(token):
    assert audit(token).status_code == 401


def test_extract_text_requires_auth():
    r = client.post("/api/extract-text", files={"file": ("a.png", b"x")})
    assert r.status_code == 401
