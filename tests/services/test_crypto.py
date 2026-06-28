"""Тесты шифрования секретов."""
import os
from cryptography.fernet import Fernet
import pytest

from src.services.crypto import encrypt_secret, decrypt_secret


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())


def test_roundtrip():
    token = "8244811300:AAGnKMaBpdPdnHughXOvggH61XDFqS0RncE"
    enc = encrypt_secret(token)
    assert enc != token
    assert decrypt_secret(enc) == token


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("FERNET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        encrypt_secret("x")
