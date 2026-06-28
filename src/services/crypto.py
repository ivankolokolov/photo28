"""Шифрование секретов студий (Fernet)."""
import os
from cryptography.fernet import Fernet


def get_fernet() -> Fernet:
    key = os.environ.get("FERNET_KEY")
    if not key:
        raise RuntimeError("FERNET_KEY не задан в окружении")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    """Шифрует строку, возвращает urlsafe-токен."""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Расшифровывает строку, зашифрованную encrypt_secret."""
    return get_fernet().decrypt(ciphertext.encode()).decode()
