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


def test_account_health_status_and_filtering(tmp_path: Path):
    db_file = tmp_path / "data" / "accounts.db"
    svc = DatabaseService(db_file)

    # 1. Default health_status is '可用'
    a1 = svc.add_account({
        "account_type": "ChatGPT",
        "account": "normal@chatgpt.com",
        "password": "Password123!",
    })
    assert a1["health_status"] == "可用"

    # 2. Add with explicit health_status
    a2 = svc.add_account({
        "account_type": "ChatGPT",
        "account": "banned@chatgpt.com",
        "password": "Password123!",
        "health_status": "封号",
    })
    assert a2["health_status"] == "封号"

    a3 = svc.add_account({
        "account_type": "Google",
        "account": "captcha@gmail.com",
        "password": "Password123!",
        "health_status": "人机",
    })
    assert a3["health_status"] == "人机"

    # 3. Quick toggle via set_health_status
    up1 = svc.set_health_status(a1["id"], "短信")
    assert up1["health_status"] == "短信"

    up1_back = svc.set_health_status(a1["id"], "可用")
    assert up1_back["health_status"] == "可用"

    # 4. Filter by health_status
    availables = svc.list_accounts(health_status="可用")
    assert len(availables) == 1
    assert availables[0]["account"] == "normal@chatgpt.com"

    banned_list = svc.list_accounts(health_status="封号")
    assert len(banned_list) == 1
    assert banned_list[0]["account"] == "banned@chatgpt.com"

    captcha_list = svc.list_accounts(health_status="人机")
    assert len(captcha_list) == 1
    assert captcha_list[0]["account"] == "captcha@gmail.com"

    # 5. Stats breakdown
    stats = svc.get_stats()
    assert stats["total"] == 3
    assert stats["available"] == 1
    assert stats["unavailable"] == 2
    assert stats["health"]["可用"] == 1
    assert stats["health"]["封号"] == 1
    assert stats["health"]["人机"] == 1
    assert stats["health"]["短信"] == 0

    # 6. Deactivated accounts count as unavailable and are excluded from 可用
    a4 = svc.add_account({
        "account_type": "ChatGPT",
        "account": "deactivated_acc@example.com",
        "password": "Password123!",
        "health_status": "可用",
        "deactivated_date": "2026-10-25",
    })
    stats2 = svc.get_stats()
    assert stats2["total"] == 4
    assert stats2["available"] == 1
    assert stats2["unavailable"] == 3
    assert stats2["health"]["可用"] == 1
    assert stats2["health"]["不可用"] == 3

    avail_filtered = svc.list_accounts(health_status="可用")
    assert len(avail_filtered) == 1
    assert avail_filtered[0]["account"] == "normal@chatgpt.com"

    unavail_filtered = svc.list_accounts(health_status="不可用")
    unavail_accounts = [a["account"] for a in unavail_filtered]
    assert "deactivated_acc@example.com" in unavail_accounts
    assert len(unavail_filtered) == 3


def test_antigravity_tier_and_filtering(tmp_path: Path):
    db_file = tmp_path / "data" / "accounts.db"
    svc = DatabaseService(db_file)

    # 1. Default antigravity_tier is '无'
    a1 = svc.add_account({
        "account_type": "Google",
        "account": "free_user@gmail.com",
        "password": "Password123!",
    })
    assert a1["antigravity_tier"] == "无"

    # 2. Add with explicit antigravity_tier
    a2 = svc.add_account({
        "account_type": "Google",
        "account": "blue_pro@gmail.com",
        "password": "Password123!",
        "antigravity_tier": "蓝色背景色Pro",
    })
    assert a2["antigravity_tier"] == "蓝色背景色Pro"

    a3 = svc.add_account({
        "account_type": "Google",
        "account": "gold_pro@gmail.com",
        "password": "Password123!",
        "antigravity_tier": "金色背景色Pro",
    })
    assert a3["antigravity_tier"] == "金色背景色Pro"

    # 3. Quick toggle via set_antigravity_tier
    up1 = svc.set_antigravity_tier(a1["id"], "蓝色背景色Pro")
    assert up1["antigravity_tier"] == "蓝色背景色Pro"

    up1_back = svc.set_antigravity_tier(a1["id"], "无")
    assert up1_back["antigravity_tier"] == "无"

    # 4. Filter by antigravity_tier
    blue_list = svc.list_accounts(antigravity_tier="蓝色背景色Pro")
    assert len(blue_list) == 1
    assert blue_list[0]["account"] == "blue_pro@gmail.com"

    gold_list = svc.list_accounts(antigravity_tier="金色背景色Pro")
    assert len(gold_list) == 1
    assert gold_list[0]["account"] == "gold_pro@gmail.com"

    none_list = svc.list_accounts(antigravity_tier="无")
    assert len(none_list) == 1
    assert none_list[0]["account"] == "free_user@gmail.com"

    # 5. Stats breakdown
    stats = svc.get_stats()
    assert stats["antigravity"]["无"] == 1
    assert stats["antigravity"]["蓝色背景色Pro"] == 1
    assert stats["antigravity"]["金色背景色Pro"] == 1
