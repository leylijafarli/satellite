import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

KEY_ENV_VAR = "TELEMETRY_SHARED_KEY"                  
KEY_FILE = Path(__file__).with_name("shared_key.hex") 
MIN_KEY_BYTES = 16


def make_seal(packet, key):
    """Make the seal for a packet: a code made from the packet + the secret key."""
    packet_text = json.dumps(packet, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, packet_text.encode("utf-8"), hashlib.sha256).hexdigest()


def _parse_key(hex_text, source):
    """Turn hex text like 'a3f9...' into bytes, with clear errors."""
    try:
        key = bytes.fromhex(hex_text.strip())
    except ValueError:
        raise ValueError(f"{source} must contain the key as hex digits (0-9, a-f)") from None
    if len(key) < MIN_KEY_BYTES:
        raise ValueError(
            f"{source} is too short: need at least {MIN_KEY_BYTES} bytes "
            f"({MIN_KEY_BYTES * 2} hex characters)"
        )
    return key


def load_shared_key(key_file=KEY_FILE):
    env_value = os.environ.get(KEY_ENV_VAR)
    if env_value:
        return _parse_key(env_value, f"environment variable {KEY_ENV_VAR}")

    key_file = Path(key_file)
    if key_file.exists():
        return _parse_key(key_file.read_text(), str(key_file))

    key = secrets.token_bytes(32)
    descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(key.hex() + "\n")
    print(f"Created a new shared key file: {key_file}")
    print("Keep it out of Git (add it to .gitignore).\n")
    return key