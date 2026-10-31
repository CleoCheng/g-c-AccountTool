import re
import time
import pyotp


def normalize_secret(secret: str) -> str:
    if not secret:
        return ""
    cleaned = re.sub(r"[\s\-]+", "", secret).upper()
    return cleaned


def mask_email(email: str) -> str:
    if not email:
        return ""
    email = email.strip()
    if "@" in email:
        local, domain = email.split("@", 1)
        if len(local) > 5:
            masked_local = f"{local[:3]}***{local[-2:]}"
        elif len(local) >= 2:
            masked_local = f"{local[0]}***{local[-1]}"
        else:
            masked_local = f"{local}***"
        return f"{masked_local}@{domain}"
    else:
        if len(email) > 5:
            return f"{email[:3]}***{email[-2:]}"
        return f"{email[:1]}***"


def mask_password(password: str) -> str:
    if not password:
        return ""
    return "••••••••"


def mask_secret(secret: str) -> str:
    cleaned = normalize_secret(secret)
    if not cleaned:
        return ""
    if len(cleaned) > 8:
        return f"{cleaned[:4]}****{cleaned[-4:]}"
    return "****"


def generate_totp(secret: str, at_time: int | None = None) -> dict:
    cleaned = normalize_secret(secret)
    now = int(at_time if at_time is not None else time.time())
    remaining = 30 - (now % 30)
    if not cleaned:
        return {"code": "", "remaining": remaining, "valid": False}

    # Base32 only allows A-Z and 2-7 and optional '='
    if not re.fullmatch(r"[A-Z2-7]+=*", cleaned):
        return {"code": "", "remaining": remaining, "valid": False}

    # Pad to multiple of 8 for strict base32 decoders
    pad_len = (8 - (len(cleaned) % 8)) % 8
    padded = cleaned + ("=" * pad_len)
    try:
        totp = pyotp.TOTP(padded)
        code = totp.at(now)
        return {"code": code, "remaining": remaining, "valid": True}
    except Exception:
        return {"code": "", "remaining": remaining, "valid": False}
