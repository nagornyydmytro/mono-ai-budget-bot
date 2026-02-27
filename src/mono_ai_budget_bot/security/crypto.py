import os

from cryptography.fernet import Fernet


def get_master_key() -> bytes:
    key = os.getenv("MASTER_KEY")
    if not key:
        raise RuntimeError("MASTER_KEY env variable is not set")
    return key.encode()


def get_fernet() -> Fernet:
    return Fernet(get_master_key())


def encrypt_token(token: str) -> str:
    f = get_fernet()
    return f.encrypt(token.encode()).decode()


def decrypt_token(token_enc: str) -> str:
    f = get_fernet()
    return f.decrypt(token_enc.encode()).decode()
