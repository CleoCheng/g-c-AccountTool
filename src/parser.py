from datetime import datetime
import re
from src.totp_service import normalize_secret


def _is_likely_base32_secret(val: str) -> bool:
    cleaned = normalize_secret(val)
    return len(cleaned) >= 16 and bool(re.fullmatch(r"[A-Z2-7]+=*", cleaned))


def _is_likely_year(val: str) -> bool:
    return bool(re.fullmatch(r"(199\d|20[0-3]\d)", val.strip()))


def normalize_date_str(val: str, default_year: int | None = None) -> str:
    val = (val or "").strip()
    if not val:
        return ""
    if default_year is None:
        default_year = datetime.now().year

    # YYYY-MM-DD or YYYY/MM/DD
    m_full = re.fullmatch(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", val)
    if m_full:
        y, m, d = int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"

    # MMDD (4 digits, e.g. 1021 -> Oct 21)
    m_short = re.fullmatch(r"(\d{2})(\d{2})", val)
    if m_short:
        m, d = int(m_short.group(1)), int(m_short.group(2))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{default_year:04d}-{m:02d}-{d:02d}"

    return val


def _is_mmdd_or_date(val: str) -> bool:
    val = val.strip()
    if re.fullmatch(r"\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}", val):
        return True
    m_short = re.fullmatch(r"(\d{2})(\d{2})", val)
    if m_short:
        m, d = int(m_short.group(1)), int(m_short.group(2))
        return 1 <= m <= 12 and 1 <= d <= 31
    return False


def _default_record() -> dict:
    return {
        "account_type": "ChatGPT",
        "account": "",
        "password": "",
        "recovery_email": "",
        "secret_key": "",
        "initial_secret_key": "",
        "twofa_modified": 0,
        "purchase_date": "",
        "deactivated_date": "",
        "reg_year": "",
        "reg_region": "",
        "note": "",
    }


def parse_single_line(line: str, default_year: int | None = None) -> dict | None:
    line = line.strip()
    if not line:
        return None

    # Support ----, ---, |, or tab delimiters
    if "---" in line:
        parts = [p.strip() for p in re.split(r"-{3,}", line)]
    elif "|" in line:
        parts = [p.strip() for p in line.split("|")]
    elif "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    else:
        # Collapse space-grouped 4-char Base32 chunks (e.g. 'abcd efgh ijkl mnop') before splitting
        collapsed = re.sub(
            r"\b([A-Za-z2-7]{4})(?:[\s\-]+([A-Za-z2-7]{4})){3,}\b",
            lambda m: re.sub(r"[\s\-]+", "", m.group(0)).upper(),
            line,
        )
        parts = [p.strip() for p in re.split(r"\s{2,}", collapsed)]

    parts = [p for p in parts if p != ""]
    if not parts:
        return None
    # Do not treat a standalone Base32 secret line as an account username
    if len(parts) == 1 and "@" not in parts[0] and _is_likely_base32_secret(parts[0]):
        return None

    result = _default_record()
    result["account"] = parts[0] if len(parts) >= 1 else ""
    result["password"] = parts[1] if len(parts) >= 2 else ""

    if len(parts) == 3:
        third = parts[2]
        if "@" in third and not _is_likely_base32_secret(third):
            result["recovery_email"] = third
        else:
            result["secret_key"] = normalize_secret(third)
        if result["account"].lower().endswith("@gmail.com") and result["recovery_email"]:
            result["account_type"] = "Google"
        return result

    if len(parts) >= 6:
        # Format B: Account ---- Password ---- Recovery ---- 2FA ---- Year ---- Region
        result["account_type"] = "Google"
        result["recovery_email"] = parts[2]
        result["secret_key"] = normalize_secret(parts[3])
        result["reg_year"] = parts[4]
        result["reg_region"] = parts[5]
        if len(parts) > 6:
            result["note"] = " | ".join(parts[6:])
        return result

    # Heuristic fallback for 2, 4, or 5 fields
    extra_notes = []
    for token in parts[2:]:
        if "@" in token and not result["recovery_email"]:
            result["recovery_email"] = token
            result["account_type"] = "Google"
        elif _is_likely_base32_secret(token):
            cleaned_tok = normalize_secret(token)
            if not result["secret_key"]:
                result["secret_key"] = cleaned_tok
            else:
                result["initial_secret_key"] = result["secret_key"]
                result["secret_key"] = cleaned_tok
                result["twofa_modified"] = 1
        elif _is_likely_year(token) and not result["reg_year"]:
            result["reg_year"] = token
            result["account_type"] = "Google"
        elif not result["reg_region"] and len(token) <= 32:
            result["reg_region"] = token
        else:
            extra_notes.append(token)

    if result["account"].lower().endswith("@gmail.com") and (
        result["recovery_email"] or result["reg_year"] or result["reg_region"]
    ):
        result["account_type"] = "Google"

    if extra_notes:
        result["note"] = " | ".join(extra_notes)

    return result


def _parse_structured_block(block_text: str, default_year: int | None = None) -> dict | None:
    lines = [ln.strip() for ln in block_text.split("\n") if ln.strip()]
    if not lines:
        return None

    # Stitch credential continuation lines (e.g. email on line 1, ----password----2fa or |password|2fa on line 2)
    # BUT do NOT stitch standalone deactivation date lines like '----1029', '|1029', '新2FA----...' or '新2FA|...'
    stitched_lines: list[str] = []
    for ln in lines:
        if re.match(r"^[-|]+\s*(\d{4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})\s*$", ln):
            stitched_lines.append(ln)
        elif re.match(r"^(?:新2FA|new\s*2fa)\s*[-|]+", ln, flags=re.IGNORECASE):
            stitched_lines.append(ln)
        elif (ln.startswith("---") or ln.startswith("|")) and stitched_lines:
            stitched_lines[-1] = stitched_lines[-1] + ln
        elif stitched_lines and (stitched_lines[-1].endswith("---") or stitched_lines[-1].endswith("|")):
            stitched_lines[-1] = stitched_lines[-1] + ln
        else:
            stitched_lines.append(ln)

    record = _default_record()
    notes: list[str] = []
    new_2fa_secret = ""

    for ln in stitched_lines:
        # Skip pure index lines like '1.' or '20.'
        if re.fullmatch(r"\d+\.", ln):
            continue

        # Standalone trailing deactivation date: '----1029' or '|1029'
        m_deact_only = re.fullmatch(r"[-|]+\s*(\d{4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})", ln)
        if m_deact_only and _is_mmdd_or_date(m_deact_only.group(1)):
            record["deactivated_date"] = normalize_date_str(m_deact_only.group(1), default_year)
            continue

        # Date line: '1021', '1019----1029', or '1019|1029'
        m_dates = re.fullmatch(
            r"(\d{4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})(?:\s*[-|]+\s*(\d{4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}))?",
            ln,
        )
        if m_dates and _is_mmdd_or_date(m_dates.group(1)):
            record["purchase_date"] = normalize_date_str(m_dates.group(1), default_year)
            if m_dates.group(2) and _is_mmdd_or_date(m_dates.group(2)):
                record["deactivated_date"] = normalize_date_str(m_dates.group(2), default_year)
            continue

        # New 2FA line: '新2FA----...' or '新2FA|...'
        m_new2fa = re.match(r"^(?:新2FA|new\s*2fa)\s*[-|]+\s*(.+)$", ln, flags=re.IGNORECASE)
        if m_new2fa:
            new_2fa_secret = normalize_secret(m_new2fa.group(1))
            continue

        # Main credential line containing '---' or '|' or '@'
        if "---" in ln or "|" in ln or ("@" in ln and not record["account"]):
            parsed_cred = parse_single_line(ln, default_year=default_year)
            if parsed_cred and parsed_cred["account"]:
                record["account_type"] = parsed_cred["account_type"]
                record["account"] = parsed_cred["account"]
                record["password"] = parsed_cred["password"]
                record["recovery_email"] = parsed_cred["recovery_email"]
                record["secret_key"] = parsed_cred["secret_key"]
                record["reg_year"] = parsed_cred["reg_year"]
                record["reg_region"] = parsed_cred["reg_region"]
                if parsed_cred["note"]:
                    notes.append(parsed_cred["note"])
                continue

        notes.append(ln)

    if not record["account"]:
        return None

    if new_2fa_secret:
        record["initial_secret_key"] = record["secret_key"]
        record["secret_key"] = new_2fa_secret
        record["twofa_modified"] = 1

    if notes:
        record["note"] = " | ".join(notes)

    return record


def parse_account_text(raw_text: str, default_year: int | None = None) -> list[dict]:
    if not raw_text or not raw_text.strip():
        return []

    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Case 1: Numbered blocks (e.g. '1.\n1021\n...')
    if re.search(r"(?m)^\s*\d+\.\s*$", normalized):
        blocks = re.split(r"(?m)^\s*\d+\.\s*$", normalized)
        records = []
        for blk in blocks:
            if not blk.strip():
                continue
            rec = _parse_structured_block(blk, default_year=default_year)
            if rec and rec["account"]:
                records.append(rec)
        if records:
            return records

    # Case 2: Single structured block containing '新2FA' or standalone MMDD date line
    if re.search(r"(?i)新2FA|new\s*2fa", normalized) or re.search(r"(?m)^\s*\d{4}(?:\s*[-|]+\s*\d{4})?\s*$", normalized):
        rec = _parse_structured_block(normalized, default_year=default_year)
        if rec and rec["account"]:
            return [rec]

    # Case 3: Standard line-by-line or cross-line wrapped records (support ---- or |)
    stitched = re.sub(r"\n\s*(-{3,}|\|+)", r"\1", normalized)
    stitched = re.sub(r"(-{3,}|\|+)\s*\n\s*", r"\1", stitched)

    records = []
    for line in stitched.split("\n"):
        parsed = parse_single_line(line, default_year=default_year)
        if parsed and parsed["account"]:
            records.append(parsed)
    return records
