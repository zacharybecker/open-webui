"""
Credential encryption/decryption utilities for external data sources.

Uses Fernet symmetric encryption with a key derived from the application's secret key.
"""

import base64
import hashlib
import json
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from open_webui.config import WEBUI_SECRET_KEY

log = logging.getLogger(__name__)


def _get_fernet_key() -> bytes:
    """
    Derive a Fernet-compatible key from the application secret key.
    Fernet requires a 32-byte key that is base64 url-safe encoded.
    """
    # Use SHA-256 to get a consistent 32-byte key from the secret
    key_bytes = hashlib.sha256(WEBUI_SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def _get_fernet() -> Fernet:
    """Get a Fernet instance using the derived key."""
    return Fernet(_get_fernet_key())


def encrypt_credentials(credentials: dict) -> str:
    """
    Encrypt a credentials dictionary.
    
    Args:
        credentials: Dictionary containing credential data (API keys, tokens, etc.)
        
    Returns:
        Base64-encoded encrypted string
    """
    try:
        fernet = _get_fernet()
        json_bytes = json.dumps(credentials).encode("utf-8")
        encrypted = fernet.encrypt(json_bytes)
        return encrypted.decode("utf-8")
    except Exception as e:
        log.exception(f"Error encrypting credentials: {e}")
        raise ValueError("Failed to encrypt credentials")


def decrypt_credentials(encrypted_data: str) -> Optional[dict]:
    """
    Decrypt an encrypted credentials string.
    
    Args:
        encrypted_data: Base64-encoded encrypted string
        
    Returns:
        Decrypted credentials dictionary, or None if decryption fails
    """
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted_data.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except InvalidToken:
        log.error("Invalid token - credentials may have been encrypted with a different key")
        return None
    except Exception as e:
        log.exception(f"Error decrypting credentials: {e}")
        return None


