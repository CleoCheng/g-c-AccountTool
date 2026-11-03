from datetime import date, datetime
import json
import sqlite3
from pathlib import Path
from src.browser_service import generate_fingerprint_config
from src.parser import normalize_date_str
from src.totp_service import (
    normalize_secret,
    mask_email,
    mask_password,
    mask_secret,
    generate_totp,
)


VALID_HEALTH_STATUSES = ["可用", "不可用", "封号", "人机", "短信", "验证"]
VALID_ANTIGRAVITY_TIERS = ["无", "蓝色背景色Pro", "金色背景色Pro"]


def _parse_date(d_str: str) -> date | None:
    if not d_str or not d_str.strip():
        return None
    norm = normalize_date_str(d_str.strip())
    try:
        return datetime.strptime(norm, "%Y-%m-%d").date()
    except Exception:
        return None


def compute_usage_info(purchase_date: str, deactivated_date: str, today_str: str | None = None) -> dict:
    p_dt = _parse_date(purchase_date)
    d_dt = _parse_date(deactivated_date)
    t_dt = _parse_date(today_str) if today_str else date.today()

    if d_dt is not None:
        status = "deactivated"
        status_label = "已停用"
        if p_dt is not None:
            days = max((d_dt - p_dt).days, 0)
            duration_text = f"共使用 {days} 天" if days > 0 else "共使用 <1 天"
        else:
            days = None
            duration_text = "已停用"
    else:
        status = "active"
        status_label = "使用中"
        if p_dt is not None and t_dt is not None:
            days = max((t_dt - p_dt).days, 0)
            duration_text = f"已使用 {days} 天" if days > 0 else "今日启用"
        else:
            days = None
            duration_text = "使用中"

    return {
        "status": status,
        "status_label": status_label,
        "days": days,
        "duration_text": duration_text,
    }


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
                    health_status TEXT NOT NULL DEFAULT '可用',
                    antigravity_tier TEXT NOT NULL DEFAULT '无',
                    account TEXT NOT NULL,
                    password TEXT NOT NULL,
                    password_modified INTEGER DEFAULT 0,
                    recovery_email TEXT DEFAULT '',
                    secret_key TEXT DEFAULT '',
                    initial_secret_key TEXT DEFAULT '',
                    twofa_modified INTEGER DEFAULT 0,
                    purchase_date TEXT DEFAULT '',
                    deactivated_date TEXT DEFAULT '',
                    reg_year TEXT DEFAULT '',
                    reg_region TEXT DEFAULT '',
                    note TEXT DEFAULT '',
                    fp_config_json TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            existing_cols = {
                row["name"] for row in conn.execute("PRAGMA table_info(accounts);").fetchall()
            }
            migrations = {
                "health_status": "ALTER TABLE accounts ADD COLUMN health_status TEXT DEFAULT '可用'",
                "antigravity_tier": "ALTER TABLE accounts ADD COLUMN antigravity_tier TEXT DEFAULT '无'",
                "password_modified": "ALTER TABLE accounts ADD COLUMN password_modified INTEGER DEFAULT 0",
                "initial_secret_key": "ALTER TABLE accounts ADD COLUMN initial_secret_key TEXT DEFAULT ''",
                "twofa_modified": "ALTER TABLE accounts ADD COLUMN twofa_modified INTEGER DEFAULT 0",
                "purchase_date": "ALTER TABLE accounts ADD COLUMN purchase_date TEXT DEFAULT ''",
                "deactivated_date": "ALTER TABLE accounts ADD COLUMN deactivated_date TEXT DEFAULT ''",
                "fp_config_json": "ALTER TABLE accounts ADD COLUMN fp_config_json TEXT DEFAULT ''",
            }
            for col_name, ddl in migrations.items():
                if col_name not in existing_cols:
                    conn.execute(ddl)

            # Ensure any null or empty health_status gets default '可用'
            conn.execute("UPDATE accounts SET health_status = '可用' WHERE health_status IS NULL OR health_status = ''")
            # Ensure any null or empty antigravity_tier gets default '无'
            conn.execute("UPDATE accounts SET antigravity_tier = '无' WHERE antigravity_tier IS NULL OR antigravity_tier = ''")
            # Deactivated accounts default to '不可用'
            conn.execute("UPDATE accounts SET health_status = '不可用' WHERE deactivated_date IS NOT NULL AND deactivated_date != '' AND health_status = '可用'")

            # Backfill permanent paired fingerprint config for any account missing it
            rows = conn.execute(
                "SELECT id, account, fp_config_json FROM accounts WHERE fp_config_json IS NULL OR fp_config_json = ''"
            ).fetchall()
            for r in rows:
                fp = generate_fingerprint_config(r["id"], r["account"])
                conn.execute(
                    "UPDATE accounts SET fp_config_json = ? WHERE id = ?",
                    (json.dumps(fp, ensure_ascii=False), r["id"]),
                )

            # Normalize all existing 2FA secrets (strip spaces/hyphens and uppercase)
            secret_rows = conn.execute(
                "SELECT id, secret_key, initial_secret_key FROM accounts"
            ).fetchall()
            for r in secret_rows:
                raw_sk = r["secret_key"] or ""
                raw_isk = r["initial_secret_key"] or ""
                clean_sk = normalize_secret(raw_sk)
                clean_isk = normalize_secret(raw_isk)
                if raw_sk != clean_sk or raw_isk != clean_isk:
                    conn.execute(
                        "UPDATE accounts SET secret_key = ?, initial_secret_key = ? WHERE id = ?",
                        (clean_sk, clean_isk, r["id"]),
                    )

    def _enrich_row(self, row: sqlite3.Row) -> dict:
        item = dict(row)
        item["health_status"] = (item.get("health_status") or "可用").strip()
        raw_ag = (item.get("antigravity_tier") or "无").strip()
        item["antigravity_tier"] = raw_ag if raw_ag in VALID_ANTIGRAVITY_TIERS else "无"
        item["password_modified"] = int(item.get("password_modified") or 0)
        item["twofa_modified"] = int(item.get("twofa_modified") or 0)
        item["secret_key"] = normalize_secret(item.get("secret_key") or "")
        item["initial_secret_key"] = normalize_secret(item.get("initial_secret_key") or "")
        item["purchase_date"] = item.get("purchase_date") or ""
        item["deactivated_date"] = item.get("deactivated_date") or ""
        item["masked_account"] = mask_email(item["account"])
        item["masked_password"] = mask_password(item["password"])
        item["masked_recovery_email"] = mask_email(item["recovery_email"]) if item["recovery_email"] else ""
        item["masked_secret"] = mask_secret(item["secret_key"])
        item["masked_initial_secret"] = mask_secret(item["initial_secret_key"]) if item["initial_secret_key"] else ""
        item["totp"] = generate_totp(item["secret_key"])
        item["usage"] = compute_usage_info(item["purchase_date"], item["deactivated_date"])

        raw_fp = item.get("fp_config_json") or ""
        try:
            fp_cfg = json.loads(raw_fp) if raw_fp else None
        except Exception:
            fp_cfg = None
        if not fp_cfg:
            fp_cfg = generate_fingerprint_config(item["id"], item["account"])
        fp_cfg.setdefault("proxy", "")
        fp_cfg.setdefault("proxy_node", "")
        fp_cfg.setdefault("node_locked", False)
        item["fp_config"] = fp_cfg
        return item

    def list_accounts(
        self,
        account_type: str = "",
        search: str = "",
        status: str = "",
        health_status: str = "",
        antigravity_tier: str = "",
    ) -> list[dict]:
        query = "SELECT * FROM accounts WHERE 1=1"
        params: list = []
        if account_type and account_type != "All":
            query += " AND account_type = ?"
            params.append(account_type)
        if status == "active":
            query += " AND (deactivated_date IS NULL OR deactivated_date = '')"
        elif status == "deactivated":
            query += " AND (deactivated_date IS NOT NULL AND deactivated_date != '')"
        if health_status and health_status != "All":
            if health_status == "可用":
                query += " AND health_status = '可用' AND (deactivated_date IS NULL OR deactivated_date = '')"
            elif health_status == "不可用":
                query += " AND (health_status != '可用' OR (deactivated_date IS NOT NULL AND deactivated_date != ''))"
            else:
                query += " AND health_status = ?"
                params.append(health_status)
        if antigravity_tier and antigravity_tier != "All":
            query += " AND antigravity_tier = ?"
            params.append(antigravity_tier)
        if search and search.strip():
            kw = f"%{search.strip()}%"
            query += (
                " AND (account LIKE ? OR recovery_email LIKE ? OR reg_region LIKE ? "
                "OR reg_year LIKE ? OR note LIKE ? OR purchase_date LIKE ? OR deactivated_date LIKE ? OR health_status LIKE ? OR antigravity_tier LIKE ?)"
            )
            params.extend([kw, kw, kw, kw, kw, kw, kw, kw, kw])
        query += " ORDER BY id ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._enrich_row(r) for r in rows]

    def get_account(self, account_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._enrich_row(row) if row else None

    def _prepare_fields(self, data: dict) -> tuple:
        account_type = (data.get("account_type") or "ChatGPT").strip()
        health_status = (data.get("health_status") or "可用").strip()
        if health_status not in VALID_HEALTH_STATUSES:
            health_status = "可用"
        antigravity_tier = (data.get("antigravity_tier") or "无").strip()
        if antigravity_tier not in VALID_ANTIGRAVITY_TIERS:
            antigravity_tier = "无"
        account = (data.get("account") or "").strip()
        password = (data.get("password") or "").strip()
        password_modified = 1 if data.get("password_modified") in (1, True, "1", "true") else 0
        recovery_email = (data.get("recovery_email") or "").strip()
        secret_key = normalize_secret(data.get("secret_key") or "")
        initial_secret_key = normalize_secret(data.get("initial_secret_key") or "")
        twofa_modified = 1 if data.get("twofa_modified") in (1, True, "1", "true") else 0
        if initial_secret_key and secret_key and initial_secret_key != secret_key:
            twofa_modified = 1
        purchase_date = normalize_date_str(data.get("purchase_date") or "")
        deactivated_date = normalize_date_str(data.get("deactivated_date") or "")
        reg_year = (data.get("reg_year") or "").strip()
        reg_region = (data.get("reg_region") or "").strip()
        note = (data.get("note") or "").strip()
        return (
            account_type,
            health_status,
            antigravity_tier,
            account,
            password,
            password_modified,
            recovery_email,
            secret_key,
            initial_secret_key,
            twofa_modified,
            purchase_date,
            deactivated_date,
            reg_year,
            reg_region,
            note,
        )

    def add_account(self, data: dict) -> dict:
        fields = self._prepare_fields(data)
        proxy = (data.get("proxy") or "").strip()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO accounts (
                    account_type, health_status, antigravity_tier, account, password, password_modified, recovery_email,
                    secret_key, initial_secret_key, twofa_modified,
                    purchase_date, deactivated_date, reg_year, reg_region, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                fields,
            )
            new_id = cur.lastrowid
            fp = generate_fingerprint_config(new_id, fields[3], proxy=proxy)
            conn.execute(
                "UPDATE accounts SET fp_config_json = ? WHERE id = ?",
                (json.dumps(fp, ensure_ascii=False), new_id),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (new_id,)).fetchone()
        return self._enrich_row(row)

    def batch_add_accounts(self, items: list[dict]) -> int:
        count = 0
        with self._connect() as conn:
            for data in items:
                account = (data.get("account") or "").strip()
                if not account:
                    continue
                fields = self._prepare_fields(data)
                cur = conn.execute(
                    """
                    INSERT INTO accounts (
                        account_type, health_status, antigravity_tier, account, password, password_modified, recovery_email,
                        secret_key, initial_secret_key, twofa_modified,
                        purchase_date, deactivated_date, reg_year, reg_region, note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    fields,
                )
                new_id = cur.lastrowid
                fp = generate_fingerprint_config(new_id, account)
                conn.execute(
                    "UPDATE accounts SET fp_config_json = ? WHERE id = ?",
                    (json.dumps(fp, ensure_ascii=False), new_id),
                )
                count += 1
        return count

    def update_account(self, account_id: int, data: dict) -> dict | None:
        existing = self.get_account(account_id)
        if not existing:
            return None
        merged = dict(data)
        if "health_status" not in merged:
            merged["health_status"] = existing.get("health_status", "可用")
        if "antigravity_tier" not in merged:
            merged["antigravity_tier"] = existing.get("antigravity_tier", "无")
        if "password_modified" not in merged:
            if merged.get("password") and existing.get("password") and merged["password"].strip() != existing["password"]:
                merged["password_modified"] = 1
            else:
                merged["password_modified"] = existing.get("password_modified", 0)
        fields = self._prepare_fields(merged)
        fp_cfg = existing.get("fp_config") or generate_fingerprint_config(account_id, fields[3])
        if not fp_cfg.get("node_locked"):
            if "proxy" in data:
                fp_cfg["proxy"] = (data.get("proxy") or "").strip()
            if "proxy_node" in data:
                fp_cfg["proxy_node"] = (data.get("proxy_node") or "").strip()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE accounts SET
                    account_type = ?,
                    health_status = ?,
                    antigravity_tier = ?,
                    account = ?,
                    password = ?,
                    password_modified = ?,
                    recovery_email = ?,
                    secret_key = ?,
                    initial_secret_key = ?,
                    twofa_modified = ?,
                    purchase_date = ?,
                    deactivated_date = ?,
                    reg_year = ?,
                    reg_region = ?,
                    note = ?,
                    fp_config_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (*fields, json.dumps(fp_cfg, ensure_ascii=False), account_id),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._enrich_row(row) if row else None

    def bind_account_proxy_node(
        self,
        account_id: int,
        proxy_url: str,
        proxy_node: str,
        locked: bool = True,
    ) -> dict:
        existing = self.get_account(account_id)
        if not existing:
            return {"ok": False, "error": "账号不存在"}
        fp_cfg = dict(existing.get("fp_config") or {})
        new_url = (proxy_url or "").strip()
        new_node = (proxy_node or "").strip()

        if fp_cfg.get("node_locked"):
            if new_url != fp_cfg.get("proxy", "") or new_node != fp_cfg.get("proxy_node", ""):
                return {
                    "ok": False,
                    "error": f"该账号已锁定节点 [{fp_cfg.get('proxy_node') or '直连'}]，不解锁不可变更节点！",
                }

        fp_cfg["proxy"] = new_url
        fp_cfg["proxy_node"] = new_node
        fp_cfg["node_locked"] = bool(locked)

        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET fp_config_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(fp_cfg, ensure_ascii=False), int(account_id)),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (int(account_id),)).fetchone()
        return {"ok": True, "account": self._enrich_row(row)}

    def set_account_node_lock(self, account_id: int, locked: bool) -> dict:
        existing = self.get_account(account_id)
        if not existing:
            return {"ok": False, "error": "账号不存在"}
        fp_cfg = dict(existing.get("fp_config") or {})
        fp_cfg["node_locked"] = bool(locked)
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET fp_config_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(fp_cfg, ensure_ascii=False), int(account_id)),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (int(account_id),)).fetchone()
        return {"ok": True, "account": self._enrich_row(row)}

    def regenerate_fingerprint(self, account_id: int, salt: str = "") -> dict | None:
        existing = self.get_account(account_id)
        if not existing:
            return None
        old_fp = existing.get("fp_config") or {}
        new_fp = generate_fingerprint_config(
            account_id,
            existing["account"],
            proxy=old_fp.get("proxy", ""),
            proxy_node=old_fp.get("proxy_node", ""),
            node_locked=bool(old_fp.get("node_locked", False)),
            salt=salt,
        )
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET fp_config_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(new_fp, ensure_ascii=False), account_id),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._enrich_row(row) if row else None

    def set_twofa_modified(self, account_id: int, modified: int | bool) -> dict | None:
        val = 1 if modified else 0
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET twofa_modified = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (val, account_id),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._enrich_row(row) if row else None

    def set_password_modified(self, account_id: int, modified: int | bool) -> dict | None:
        val = 1 if modified else 0
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET password_modified = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (val, account_id),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._enrich_row(row) if row else None

    def set_health_status(self, account_id: int, health_status: str) -> dict | None:
        status_val = (health_status or "可用").strip()
        if status_val not in VALID_HEALTH_STATUSES:
            status_val = "可用"
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET health_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status_val, int(account_id)),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (int(account_id),)).fetchone()
        return self._enrich_row(row) if row else None

    def set_antigravity_tier(self, account_id: int, antigravity_tier: str) -> dict | None:
        tier_val = (antigravity_tier or "无").strip()
        if tier_val not in VALID_ANTIGRAVITY_TIERS:
            tier_val = "无"
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET antigravity_tier = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (tier_val, int(account_id)),
            )
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (int(account_id),)).fetchone()
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
            available = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE health_status = '可用' AND (deactivated_date IS NULL OR deactivated_date = '')"
            ).fetchone()[0]
            unavailable = total - available
            health_counts = {}
            for hs in VALID_HEALTH_STATUSES:
                if hs == "可用":
                    health_counts[hs] = available
                elif hs == "不可用":
                    health_counts[hs] = unavailable
                else:
                    cnt = conn.execute("SELECT COUNT(*) FROM accounts WHERE health_status = ?", (hs,)).fetchone()[0]
                    health_counts[hs] = cnt
            antigravity_counts = {}
            for ag in VALID_ANTIGRAVITY_TIERS:
                cnt = conn.execute("SELECT COUNT(*) FROM accounts WHERE antigravity_tier = ?", (ag,)).fetchone()[0]
                antigravity_counts[ag] = cnt
        return {
            "total": total,
            "google": google,
            "chatgpt": chatgpt,
            "other": total - google - chatgpt,
            "available": available,
            "unavailable": unavailable,
            "active": available,
            "deactivated": unavailable,
            "health": health_counts,
            "antigravity": antigravity_counts,
        }

    def refresh_totp_codes(self) -> dict[int, dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, secret_key FROM accounts WHERE secret_key != ''").fetchall()
        return {row["id"]: generate_totp(row["secret_key"]) for row in rows}

    def export_accounts_text(self, account_type: str = "") -> str:
        items = self.list_accounts(account_type=account_type)
        lines = []
        for item in items:
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
