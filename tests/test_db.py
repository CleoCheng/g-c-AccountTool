from pathlib import Path
from src.db_service import DatabaseService, compute_usage_info


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


def test_usage_duration_and_twofa_modified_toggle(tmp_path: Path):
    # Deactivated account: 2026-10-19 -> 2026-10-29 = 10 days
    u_deact = compute_usage_info("2026-10-19", "2026-10-29", today_str="2026-10-30")
    assert u_deact["status"] == "deactivated"
    assert u_deact["status_label"] == "已停用"
    assert u_deact["days"] == 10
    assert u_deact["duration_text"] == "共使用 10 天"

    # Active account: 2026-10-21 -> today (2026-10-30) = 9 days
    u_act = compute_usage_info("2026-10-21", "", today_str="2026-10-30")
    assert u_act["status"] == "active"
    assert u_act["status_label"] == "使用中"
    assert u_act["days"] == 9
    assert u_act["duration_text"] == "已使用 9 天"

    db_file = tmp_path / "data" / "accounts.db"
    svc = DatabaseService(db_file)
    acc = svc.add_account(
        {
            "account_type": "ChatGPT",
            "account": "test_user@example.com",
            "password": "secretPassword",
            "initial_secret_key": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
            "secret_key": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
            "twofa_modified": 1,
            "purchase_date": "2026-10-19",
            "deactivated_date": "2026-10-29",
        }
    )
    assert acc["twofa_modified"] == 1
    assert acc["masked_initial_secret"] == "JBSW****3PXP"
    assert acc["masked_secret"] == "GEZD****QOJQ"
    assert acc["usage"]["status"] == "deactivated"
    assert acc["usage"]["days"] == 10

    toggled = svc.set_twofa_modified(acc["id"], 0)
    assert toggled["twofa_modified"] == 0

    assert acc["password_modified"] == 0
    pwd_toggled = svc.set_password_modified(acc["id"], 1)
    assert pwd_toggled["password_modified"] == 1
    pwd_toggled_back = svc.set_password_modified(acc["id"], 0)
    assert pwd_toggled_back["password_modified"] == 0

    # Updating password automatically marks password_modified = 1 if not specified
    updated = svc.update_account(
        acc["id"],
        {
            "account_type": "ChatGPT",
            "account": "test_user@example.com",
            "password": "brandNewPassword999",
        },
    )
    assert updated["password_modified"] == 1
