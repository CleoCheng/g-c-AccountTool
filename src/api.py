import json
import time
from pathlib import Path
from src.browser_service import launch_isolated_browser
from src.db_service import DatabaseService, compute_usage_info
from src.parser import parse_account_text
from src.proxy_service import detect_proxy_environment
from src.totp_service import generate_totp, mask_secret, normalize_secret


DEFAULT_SETTINGS = {
    "theme": "dark",
    "view_mode": "compact",
}


class AccountApi:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = DatabaseService(self.data_dir / "accounts.db")
        self.settings_path = self.data_dir / "settings.json"
        self._ensure_settings()

    def _ensure_settings(self) -> dict:
        if not self.settings_path.exists():
            self.settings_path.write_text(
                json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return dict(DEFAULT_SETTINGS)
        try:
            loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SETTINGS, **loaded}
            return merged
        except Exception:
            return dict(DEFAULT_SETTINGS)

    def get_dashboard(self, account_type: str = "All", search: str = "", status: str = "All") -> dict:
        status_filter = "" if status in ("", "All") else status
        accounts = self.db.list_accounts(account_type=account_type, search=search, status=status_filter)
        stats = self.db.get_stats()
        settings = self._ensure_settings()
        now = int(time.time())
        return {
            "accounts": accounts,
            "stats": stats,
            "settings": settings,
            "server_time": now,
            "remaining": 30 - (now % 30),
        }

    def get_proxy_nodes(self) -> dict:
        return detect_proxy_environment()

    def bind_proxy_node(
        self,
        account_id: int,
        proxy_url: str,
        proxy_node: str,
        locked: bool = True,
    ) -> dict:
        return self.db.bind_account_proxy_node(
            int(account_id),
            proxy_url=proxy_url,
            proxy_node=proxy_node,
            locked=bool(locked),
        )

    def set_node_lock(self, account_id: int, locked: bool) -> dict:
        return self.db.set_account_node_lock(int(account_id), bool(locked))

    def smart_parse(self, raw_text: str) -> dict:
        import re
        from src.parser import _is_likely_base32_secret
        records = parse_account_text(raw_text)
        if not records and raw_text and raw_text.strip():
            stripped = raw_text.strip()
            m_new = re.match(r"^(?:新2FA|new\s*2fa)\s*-*\s*(.+)$", stripped, flags=re.IGNORECASE)
            candidate = m_new.group(1) if m_new else stripped
            if "@" not in candidate and _is_likely_base32_secret(candidate):
                cleaned = normalize_secret(candidate)
                return {
                    "records": [],
                    "count": 0,
                    "only_secret": {
                        "secret_key": cleaned,
                        "twofa_modified": 1 if m_new else 0,
                        "masked_secret": mask_secret(cleaned),
                        "totp": generate_totp(cleaned),
                    },
                }

        for rec in records:
            rec["secret_key"] = normalize_secret(rec.get("secret_key", ""))
            rec["initial_secret_key"] = normalize_secret(rec.get("initial_secret_key", ""))
            rec["totp"] = generate_totp(rec.get("secret_key", ""))
            rec["masked_secret"] = mask_secret(rec.get("secret_key", ""))
            rec["masked_initial_secret"] = mask_secret(rec.get("initial_secret_key", ""))
            rec["usage"] = compute_usage_info(
                rec.get("purchase_date", ""),
                rec.get("deactivated_date", ""),
            )
        return {
            "records": records,
            "count": len(records),
        }

    def preview_totp(self, secret_key: str) -> dict:
        cleaned = normalize_secret(secret_key)
        return {
            "cleaned_secret": cleaned,
            "masked_secret": mask_secret(cleaned),
            "totp": generate_totp(cleaned),
        }

    def save_account(self, data: dict) -> dict:
        account_val = (data.get("account") or "").strip()
        if not account_val:
            return {"ok": False, "error": "账号不能为空"}

        acc_id = data.get("id")
        if acc_id:
            updated = self.db.update_account(int(acc_id), data)
            return {"ok": True, "account": updated}
        else:
            created = self.db.add_account(data)
            return {"ok": True, "account": created}

    def toggle_twofa_modified(self, account_id: int, modified: bool | int) -> dict:
        updated = self.db.set_twofa_modified(int(account_id), modified)
        if not updated:
            return {"ok": False, "error": "账号不存在"}
        return {"ok": True, "account": updated}

    def toggle_password_modified(self, account_id: int, modified: bool | int) -> dict:
        updated = self.db.set_password_modified(int(account_id), modified)
        if not updated:
            return {"ok": False, "error": "账号不存在"}
        return {"ok": True, "account": updated}

    def launch_browser(self, account_id: int) -> dict:
        import importlib
        import src.browser_service as bs
        importlib.reload(bs)
        account = self.db.get_account(int(account_id))
        if not account:
            return {"ok": False, "error": "账号不存在"}
        return bs.launch_isolated_browser(self.data_dir, account)

    def regenerate_fingerprint(self, account_id: int) -> dict:
        updated = self.db.regenerate_fingerprint(int(account_id), salt=str(time.time()))
        if not updated:
            return {"ok": False, "error": "账号不存在"}
        return {"ok": True, "account": updated}

    def batch_import(self, raw_text: str) -> dict:
        records = parse_account_text(raw_text)
        if not records:
            return {"ok": False, "imported": 0, "error": "未识别到有效账号数据"}
        count = self.db.batch_add_accounts(records)
        return {"ok": True, "imported": count}

    def delete_account(self, account_id: int) -> dict:
        deleted = self.db.delete_account(int(account_id))
        return {"ok": deleted}

    def refresh_totp(self) -> dict:
        now = int(time.time())
        codes = self.db.refresh_totp_codes()
        return {
            "codes": {str(k): v for k, v in codes.items()},
            "remaining": 30 - (now % 30),
        }

    def export_text(self, account_type: str = "All") -> dict:
        text = self.db.export_accounts_text(account_type=account_type)
        return {"text": text}

    def save_settings(self, new_settings: dict) -> dict:
        current = self._ensure_settings()
        current.update(new_settings or {})
        self.settings_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return current
