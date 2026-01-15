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


def is_encrypted(data: str) -> bool:
    """
    Check if a string appears to be Fernet-encrypted data.
    
    Args:
        data: String to check
        
    Returns:
        True if the string appears to be encrypted
    """
    try:
        # Fernet tokens are base64 encoded and start with 'gAAAAA'
        return data.startswith("gAAAAA") and len(data) > 100
    except Exception:
        return False


def encrypt_field(value: str) -> str:
    """
    Encrypt a single string value.
    
    Args:
        value: String to encrypt
        
    Returns:
        Encrypted string
    """
    return encrypt_credentials({"value": value})


def decrypt_field(encrypted_data: str) -> Optional[str]:
    """
    Decrypt a single encrypted string value.
    
    Args:
        encrypted_data: Encrypted string
        
    Returns:
        Decrypted string, or None if decryption fails
    """
    result = decrypt_credentials(encrypted_data)
    if result:
        return result.get("value")
    return None


def mask_credentials(credentials: dict) -> dict:
    """
    Mask sensitive credential values for display purposes.
    Shows only the first and last few characters.
    
    Args:
        credentials: Dictionary of credentials
        
    Returns:
        Dictionary with masked values
    """
    masked = {}
    for key, value in credentials.items():
        if isinstance(value, str) and len(value) > 8:
            masked[key] = f"{value[:3]}...{value[-3:]}"
        elif isinstance(value, str):
            masked[key] = "***"
        else:
            masked[key] = value
    return masked
