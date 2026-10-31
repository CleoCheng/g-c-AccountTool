# Account Manager Desktop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight (~35MB RAM, 0% idle CPU), modern desktop application for managing Google and ChatGPT accounts with courier-style smart paste recognition, field masking, 1-click copy, and live 2FA/TOTP generation.

**Architecture:** Python 3 backend (`sqlite3` in WAL mode + `pyotp` + heuristic string parser) bridged via `pywebview` (Windows native Edge WebView2) to a 100% offline, zero-CDN modern SPA (`web/index.html`, `web/style.css`, `web/app.js`). All persistent files (`accounts.db`, `settings.json`, and WebView runtime cache) are strictly confined to the `data/` folder.

**Tech Stack:** Python 3.14, `pywebview` 6.2+, `pyotp` 2.10+, `sqlite3`, `pytest`, Vanilla HTML5/CSS3/ES6+.

**Spec:** `docs/superpowers/specs/2026-10-30-account-manager-desktop-design.md`

## Global Constraints

- All user data, SQLite databases (`accounts.db`), config (`settings.json`), and WebView2 runtime cache (`runtime/`) MUST reside inside `data/`.
- Zero external network/CDN requests: all styles and SVG icons must be self-contained locally in `web/`.
- Masking rules:
  - Email: `local[:3] + "***" + local[-2:] + "@" + domain` (for `len(local) > 5`).
  - Password: Always `"••••••••"`.
  - 2FA Secret: `secret[:4] + "****" + secret[-4:]` (for `len(secret) > 8`).
- Copy buttons always copy the **unmasked raw plaintext** (and 6-digit TOTP without spaces).
- TOTP recalculation only occurs on 30-second epoch boundaries (`epoch % 30 == 0`) or account load/update; per-second countdown ring runs purely on client timestamp math (`0%` idle backend CPU).

## Review Focus

1. **Cross-line broken paste strings** (e.g., `bob_google99@gmail.com----GoogleDemo#888----recovery_demo@example.org\n----gezdgnbvgy3tqojqgezdgnbvgy3tqojq----2024----US`): Must stitch lines starting or ending with `----` before splitting records, rather than treating the second line as a separate broken account.
2. **2FA secret keys with spaces, lowercase, or unpadded Base32** (e.g., `gezd gnbv gy3t qojq gezd gnbv gy3t qojq` or lengths not divisible by 8): Must strip spaces/hyphens, uppercase, and pad `=` before generating TOTP codes.
3. **Invalid/corrupted 2FA secret key**: Must never crash the app or fail account creation; `generate_totp` returns `{"code": "", "valid": False}` while still preserving and masking the stored raw secret string.
4. **Identical-prefix emails in list** (e.g. `alice_demo.15+nxuw@example.com` vs `alice_demo.15+abcd@example.com`): Masking must preserve both the first 3 chars and last 2 chars before `@` (`ali***uw@example.com` vs `ali***cd@example.com`) so accounts remain distinguishable.
5. **Partial or 4/5-segment Google account strings**: Heuristic fallback must still assign `@` fields to `recovery_email`, Base32 strings to `secret_key`, and 4-digit years to `reg_year`.

---

### Task 1: Masking & TOTP Service (`src/totp_service.py`)

**Files:**
- Create: `src/__init__.py`
- Create: `src/totp_service.py`
- Test: `tests/test_totp.py`

**Interfaces:**
- Produces:
  - `normalize_secret(secret: str) -> str`
  - `mask_email(email: str) -> str`
  - `mask_password(password: str) -> str`
  - `mask_secret(secret: str) -> str`
  - `generate_totp(secret: str, at_time: int | None = None) -> dict` returning `{"code": str, "remaining": int, "valid": bool}`

- [ ] **Step 1: Write the failing test in `tests/test_totp.py`**

```python
import pytest
from src.totp_service import (
    normalize_secret,
    mask_email,
    mask_password,
    mask_secret,
    generate_totp,
)


def test_mask_email_distinguishable():
    assert mask_email("alice_demo01@example.com") == "ali***01@example.com"
    assert mask_email("bob_google99@gmail.com") == "bob***99@gmail.com"
    assert mask_email("ab@test.com") == "a***b@test.com"
    assert mask_email("a@test.com") == "a***@test.com"
    assert mask_email("plainusername") == "pla***me"


def test_mask_password_fixed():
    assert mask_password("DemoPass#2026!") == "••••••••"
    assert mask_password("") == ""


def test_mask_secret():
    assert mask_secret("JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP") == "JBSW****3PXP"
    assert mask_secret("gezd gnbv gy3t qojq gezd gnbv gy3t qojq") == "GEZD****QOJQ"
    assert mask_secret("SHORT") == "****"
    assert mask_secret("") == ""


def test_generate_totp_valid_and_spaced():
    s1 = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    res1 = generate_totp(s1, at_time=1700000000)
    assert res1["valid"] is True
    assert len(res1["code"]) == 6
    assert res1["code"].isdigit()
    assert 1 <= res1["remaining"] <= 30

    # Lowercase + spaces (like Google 2FA keys)
    s2 = "gezd gnbv gy3t qojq gezd gnbv gy3t qojq"
    res2 = generate_totp(s2, at_time=1700000000)
    assert res2["valid"] is True
    assert len(res2["code"]) == 6


def test_generate_totp_invalid_secret_graceful():
    res = generate_totp("NOT_BASE32_999!!!", at_time=1700000000)
    assert res["valid"] is False
    assert res["code"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_totp.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation in `src/totp_service.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_totp.py -v`
Expected: PASS (5 passed)

---

### Task 2: Smart Express-Style Paste Parser (`src/parser.py`)

**Files:**
- Create: `src/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: `normalize_secret` from `src.totp_service`
- Produces:
  - `parse_account_text(raw_text: str) -> list[dict]`

- [ ] **Step 1: Write the failing test in `tests/test_parser.py`**

```python
from src.parser import parse_account_text


def test_parse_chatgpt_3_field():
    raw = "alice_demo01@example.com----DemoPass#2026!----JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    items = parse_account_text(raw)
    assert len(items) == 1
    item = items[0]
    assert item["account_type"] == "ChatGPT"
    assert item["account"] == "alice_demo01@example.com"
    assert item["password"] == "DemoPass#2026!"
    assert item["secret_key"] == "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    assert item["recovery_email"] == ""


def test_parse_google_6_field_with_line_wrap():
    raw = (
        "bob_google99@gmail.com----GoogleDemo#888----recovery_demo@example.org\n"
        "----gezdgnbvgy3tqojqgezdgnbvgy3tqojq----2024----US"
    )
    items = parse_account_text(raw)
    assert len(items) == 1
    item = items[0]
    assert item["account_type"] == "Google"
    assert item["account"] == "bob_google99@gmail.com"
    assert item["password"] == "GoogleDemo#888"
    assert item["recovery_email"] == "recovery_demo@example.org"
    assert item["secret_key"] == "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert item["reg_year"] == "2024"
    assert item["reg_region"] == "US"


def test_parse_batch_mixed_records():
    raw = """
    alice_demo01@example.com----DemoPass#2026!----JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP
    bob_google99@gmail.com----GoogleDemo#888----recovery_demo@example.org----gezdgnbvgy3tqojqgezdgnbvgy3tqojq----2024----US
    """
    items = parse_account_text(raw)
    assert len(items) == 2
    assert items[0]["account_type"] == "ChatGPT"
    assert items[1]["account_type"] == "Google"


def test_parse_heuristic_4_fields_google():
    raw = "user123@gmail.com----pass123----backup@mail.com----GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    items = parse_account_text(raw)
    assert len(items) == 1
    assert items[0]["account_type"] == "Google"
    assert items[0]["recovery_email"] == "backup@mail.com"
    assert items[0]["secret_key"] == "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation in `src/parser.py`**

```python
import re
from src.totp_service import normalize_secret


def _is_likely_base32_secret(val: str) -> bool:
    cleaned = normalize_secret(val)
    return len(cleaned) >= 16 and bool(re.fullmatch(r"[A-Z2-7]+=*", cleaned))


def _is_likely_year(val: str) -> bool:
    return bool(re.fullmatch(r"(199\d|20[0-3]\d)", val.strip()))


def parse_single_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None

    # Support ----, ---, |, or tab delimiters
    if "----" in line:
        parts = [p.strip() for p in re.split(r"-{3,}", line)]
    elif "|" in line:
        parts = [p.strip() for p in line.split("|")]
    elif "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    else:
        parts = [p.strip() for p in re.split(r"\s{2,}", line)]

    parts = [p for p in parts if p != ""]
    if not parts:
        return None

    result = {
        "account_type": "ChatGPT",
        "account": parts[0] if len(parts) >= 1 else "",
        "password": parts[1] if len(parts) >= 2 else "",
        "recovery_email": "",
        "secret_key": "",
        "reg_year": "",
        "reg_region": "",
        "note": "",
    }

    if len(parts) == 3:
        # Format A: Account ---- Password ---- 2FA Secret (or Recovery Email)
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
        elif _is_likely_base32_secret(token) and not result["secret_key"]:
            result["secret_key"] = normalize_secret(token)
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


def parse_account_text(raw_text: str) -> list[dict]:
    if not raw_text or not raw_text.strip():
        return []

    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    # Stitch broken lines where newline occurs right before or after '----'
    normalized = re.sub(r"\n\s*(-{3,})", r"\1", normalized)
    normalized = re.sub(r"(-{3,})\s*\n\s*", r"\1", normalized)

    records = []
    for line in normalized.split("\n"):
        parsed = parse_single_line(line)
        if parsed and parsed["account"]:
            records.append(parsed)
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_parser.py -v`
Expected: PASS (4 passed)

---

### Task 3: SQLite Database Service (`src/db_service.py`)

**Files:**
- Create: `src/db_service.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `normalize_secret`, `mask_email`, `mask_password`, `mask_secret`, `generate_totp` from `src.totp_service`
- Produces: `DatabaseService(db_path: Path)` with methods `list_accounts`, `add_account`, `batch_add_accounts`, `update_account`, `delete_account`, `export_accounts_text`

- [ ] **Step 1: Write the failing test in `tests/test_db.py`**

```python
from pathlib import Path
from src.db_service import DatabaseService


def test_db_crud_and_export(tmp_path: Path):
    db_file = tmp_path / "data" / "accounts.db"
    svc = DatabaseService(db_file)

    acc1 = svc.add_account(
        {
            "account_type": "ChatGPT",
            "account": "alice_demo01@example.com",
            "password": "DemoPass#2026!",
            "secret_key": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
        }
    )
    assert acc1["id"] > 0
    assert acc1["masked_account"] == "ali***01@example.com"
    assert acc1["masked_password"] == "••••••••"
    assert acc1["masked_secret"] == "JBSW****3PXP"
    assert len(acc1["totp"]["code"]) == 6

    acc2 = svc.add_account(
        {
            "account_type": "Google",
            "account": "bob_google99@gmail.com",
            "password": "GoogleDemo#888",
            "recovery_email": "recovery_demo@example.org",
            "secret_key": "gezdgnbvgy3tqojqgezdgnbvgy3tqojq",
            "reg_year": "2024",
            "reg_region": "US",
        }
    )

    all_items = svc.list_accounts()
    assert len(all_items) == 2

    google_only = svc.list_accounts(account_type="Google")
    assert len(google_only) == 1
    assert google_only[0]["account"] == "bob_google99@gmail.com"

    exported = svc.export_accounts_text()
    assert "alice_demo01@example.com----DemoPass#2026!----JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP" in exported
    assert "bob_google99@gmail.com----GoogleDemo#888----recovery_demo@example.org----GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ----2024----US" in exported

    svc.delete_account(acc1["id"])
    assert len(svc.list_accounts()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation in `src/db_service.py`**

```python
import sqlite3
from pathlib import Path
from src.totp_service import (
    normalize_secret,
    mask_email,
    mask_password,
    mask_secret,
    generate_totp,
)


class DatabaseService:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_type TEXT NOT NULL DEFAULT 'ChatGPT',
                    account TEXT NOT NULL,
                    password TEXT NOT NULL,
                    recovery_email TEXT DEFAULT '',
                    secret_key TEXT DEFAULT '',
                    reg_year TEXT DEFAULT '',
                    reg_region TEXT DEFAULT '',
                    note TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def _enrich_row(self, row: sqlite3.Row) -> dict:
        item = dict(row)
        item["masked_account"] = mask_email(item["account"])
        item["masked_password"] = mask_password(item["password"])
        item["masked_recovery_email"] = mask_email(item["recovery_email"]) if item["recovery_email"] else ""
        item["masked_secret"] = mask_secret(item["secret_key"])
        item["totp"] = generate_totp(item["secret_key"])
        return item

    def list_accounts(self, account_type: str = "", search: str = "") -> list[dict]:
        query = "SELECT * FROM accounts WHERE 1=1"
        params: list = []
        if account_type and account_type != "All":
            query += " AND account_type = ?"
            params.append(account_type)
        if search and search.strip():
            kw = f"%{search.strip()}%"
            query += " AND (account LIKE ? OR recovery_email LIKE ? OR reg_region LIKE ? OR reg_year LIKE ? OR note LIKE ?)"
            params.extend([kw, kw, kw, kw, kw])
        query += " ORDER BY id DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._enrich_row(r) for r in rows]

    def get_account(self, account_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._enrich_row(row) if row else None

    def add_account(self, data: dict) -> dict:
        account_type = (data.get("account_type") or "ChatGPT").strip()
        account = (data.get("account") or "").strip()
        password = (data.get("password") or "").strip()
        recovery_email = (data.get("recovery_email") or "").strip()
        secret_key = normalize_secret(data.get("secret_key") or "")
        reg_year = (data.get("reg_year") or "").strip()
        reg_region = (data.get("reg_region") or "").strip()
        note = (data.get("note") or "").strip()

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO accounts (
                    account_type, account, password, recovery_email,
                    secret_key, reg_year, reg_region, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (account_type, account, password, recovery_email, secret_key, reg_year, reg_region, note),
            )
            new_id = cur.lastrowid
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (new_id,)).fetchone()
        return self._enrich_row(row)

    def batch_add_accounts(self, items: list[dict]) -> int:
        count = 0
        with self._connect() as conn:
            for data in items:
                account = (data.get("account") or "").strip()
                if not account:
                    continue
                conn.execute(
                    """
                    INSERT INTO accounts (
                        account_type, account, password, recovery_email,
                        secret_key, reg_year, reg_region, note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (data.get("account_type") or "ChatGPT").strip(),
                        account,
                        (data.get("password") or "").strip(),
                        (data.get("recovery_email") or "").strip(),
                        normalize_secret(data.get("secret_key") or ""),
                        (data.get("reg_year") or "").strip(),
                        (data.get("reg_region") or "").strip(),
                        (data.get("note") or "").strip(),
                    ),
                )
                count += 1
        return count

    def update_account(self, account_id: int, data: dict) -> dict | None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE accounts SET
                    account_type = ?,
                    account = ?,
                    password = ?,
                    recovery_email = ?,
                    secret_key = ?,
                    reg_year = ?,
                    reg_region = ?,
                    note = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    (data.get("account_type") or "ChatGPT").strip(),
                    (data.get("account") or "").strip(),
                    (data.get("password") or "").strip(),
                    (data.get("recovery_email") or "").strip(),
                    normalize_secret(data.get("secret_key") or ""),
                    (data.get("reg_year") or "").strip(),
                    (data.get("reg_region") or "").strip(),
                    (data.get("note") or "").strip(),
                    account_id,
                ),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._enrich_row(row) if row else None

    def delete_account(self, account_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            return cur.rowcount > 0

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
            google = conn.execute("SELECT COUNT(*) FROM accounts WHERE account_type = 'Google'").fetchone()[0]
            chatgpt = conn.execute("SELECT COUNT(*) FROM accounts WHERE account_type = 'ChatGPT'").fetchone()[0]
        return {"total": total, "google": google, "chatgpt": chatgpt, "other": total - google - chatgpt}

    def refresh_totp_codes(self) -> dict[int, dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, secret_key FROM accounts WHERE secret_key != ''").fetchall()
        return {row["id"]: generate_totp(row["secret_key"]) for row in rows}

    def export_accounts_text(self, account_type: str = "") -> str:
        items = self.list_accounts(account_type=account_type)
        lines = []
        for item in reversed(items):
            if item["account_type"] == "Google" or item["recovery_email"] or item["reg_year"] or item["reg_region"]:
                parts = [
                    item["account"],
                    item["password"],
                    item["recovery_email"],
                    item["secret_key"],
                    item["reg_year"],
                    item["reg_region"],
                ]
                while parts and parts[-1] == "":
                    parts.pop()
                lines.append("----".join(parts))
            else:
                parts = [item["account"], item["password"]]
                if item["secret_key"]:
                    parts.append(item["secret_key"])
                lines.append("----".join(parts))
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS

---

### Task 4: Bridge API, Modern UI & Desktop Entrypoint (`src/api.py`, `web/*`, `main.py`)

**Files:**
- Create: `src/api.py`
- Create: `web/index.html`
- Create: `web/style.css`
- Create: `web/app.js`
- Create: `main.py`
- Create: `requirements.txt`
- Create: `run.bat`

- [ ] **Step 1: Implement `src/api.py` and `main.py` with `data/` confinement**
- [ ] **Step 2: Build the sleek dark/light UI in `web/index.html`, `web/style.css`, and `web/app.js`**
- [ ] **Step 3: Run full test suite and verify application launch**
