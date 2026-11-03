from pathlib import Path
from src.api import AccountApi


def test_api_smart_parse_and_save_and_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    api = AccountApi(data_dir=data_dir)

    raw = (
        "bob_google99@gmail.com----GoogleDemo#888----recovery_demo@example.org\n"
        "----gezdgnbvgy3tqojqgezdgnbvgy3tqojq----2024----US"
    )
    parsed = api.smart_parse(raw)
    assert parsed["count"] == 1
    assert parsed["records"][0]["account_type"] == "Google"
    assert parsed["records"][0]["totp"]["valid"] is True

    saved = api.save_account(parsed["records"][0])
    assert saved["ok"] is True
    acc_id = saved["account"]["id"]

    dash = api.get_dashboard()
    assert dash["stats"]["total"] == 1
    assert dash["stats"]["google"] == 1
    assert dash["accounts"][0]["id"] == acc_id
    assert "dicts" in dash

    updated_payload = dict(dash["accounts"][0])
    updated_payload["note"] = "主力谷歌号"
    res_up = api.save_account(updated_payload)
    assert res_up["account"]["note"] == "主力谷歌号"

    s = api.save_settings({"theme": "light", "view_mode": "table"})
    assert s["theme"] == "light"
    assert (data_dir / "settings.json").exists()

    totp_res = api.refresh_totp()
    assert str(acc_id) in totp_res["codes"]

    del_res = api.delete_account(acc_id)
    assert del_res["ok"] is True
    assert api.get_dashboard()["stats"]["total"] == 0


def test_2fa_secret_auto_strip_spaces_and_uppercase(tmp_path: Path):
    data_dir = tmp_path / "data"
    api = AccountApi(data_dir=data_dir)

    only_sec = api.smart_parse("jbsw y3dp ehpk 3pxp")
    assert "only_secret" in only_sec
    assert only_sec["only_secret"]["secret_key"] == "JBSWY3DPEHPK3PXP"
    assert only_sec["only_secret"]["totp"]["valid"] is True

    saved = api.save_account(
        {
            "account_type": "ChatGPT",
            "account": "user@example.com",
            "password": "pw",
            "secret_key": "gezd gnbv gy3t qojq gezd gnbv gy3t qojq",
            "initial_secret_key": "jbsw y3dp ehpk 3pxp jbsw y3dp ehpk 3pxp",
        }
    )
    assert saved["ok"] is True
    assert saved["account"]["secret_key"] == "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert saved["account"]["initial_secret_key"] == "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def test_api_health_status_lifecycle_and_dashboard_filter(tmp_path: Path):
    data_dir = tmp_path / "data"
    api = AccountApi(data_dir=data_dir)

    res = api.save_account({
        "account_type": "ChatGPT",
        "account": "user1@openai.com",
        "password": "Password999",
        "health_status": "可用",
    })
    assert res["ok"] is True
    acc_id = res["account"]["id"]
    assert res["account"]["health_status"] == "可用"

    set_res = api.set_health_status(acc_id, "验证")
    assert set_res["ok"] is True
    assert set_res["account"]["health_status"] == "验证"

    api.save_account({
        "account_type": "Google",
        "account": "user2@gmail.com",
        "password": "Password888",
        "health_status": "封号",
    })

    dash_verify = api.get_dashboard(health_status="验证")
    assert len(dash_verify["accounts"]) == 1
    assert dash_verify["accounts"][0]["account"] == "user1@openai.com"

    dash_banned = api.get_dashboard(health_status="封号")
    assert len(dash_banned["accounts"]) == 1
    assert dash_banned["accounts"][0]["account"] == "user2@gmail.com"

    dash_all = api.get_dashboard(health_status="All")
    assert len(dash_all["accounts"]) == 2
    assert dash_all["stats"]["health"]["验证"] == 1
    assert dash_all["stats"]["health"]["封号"] == 1
    assert dash_all["stats"]["available"] == 0
    assert dash_all["stats"]["unavailable"] == 2

    dash_unavail = api.get_dashboard(health_status="不可用")
    assert len(dash_unavail["accounts"]) == 2

    dash_avail = api.get_dashboard(health_status="可用")
    assert len(dash_avail["accounts"]) == 0


def test_api_antigravity_tier_lifecycle_and_dashboard_filter(tmp_path: Path):
    data_dir = tmp_path / "data"
    api = AccountApi(data_dir=data_dir)

    res1 = api.save_account({
        "account_type": "Google",
        "account": "ag_user1@gmail.com",
        "password": "Password999",
        "antigravity_tier": "蓝色Pro",
    })
    assert res1["ok"] is True
    acc_id = res1["account"]["id"]
    assert res1["account"]["antigravity_tier"] == "蓝色Pro"

    set_res = api.set_antigravity_tier(acc_id, "金色Pro")
    assert set_res["ok"] is True
    assert set_res["account"]["antigravity_tier"] == "金色Pro"

    api.save_account({
        "account_type": "Google",
        "account": "ag_user2@gmail.com",
        "password": "Password888",
        "antigravity_tier": "蓝色Pro",
    })

    dash_gold = api.get_dashboard(antigravity_tier="金色Pro")
    assert len(dash_gold["accounts"]) == 1
    assert dash_gold["accounts"][0]["account"] == "ag_user1@gmail.com"

    dash_blue = api.get_dashboard(antigravity_tier="蓝色Pro")
    assert len(dash_blue["accounts"]) == 1
    assert dash_blue["accounts"][0]["account"] == "ag_user2@gmail.com"

    dash_all = api.get_dashboard(antigravity_tier="All")
    assert len(dash_all["accounts"]) == 2
    assert dash_all["stats"]["antigravity"]["金色Pro"] == 1
    assert dash_all["stats"]["antigravity"]["蓝色Pro"] == 1


def test_api_dict_and_device_management(tmp_path: Path):
    data_dir = tmp_path / "data"
    api = AccountApi(data_dir=data_dir)

    dicts = api.get_system_dicts()
    assert len(dicts) >= 15

    add_res = api.save_system_dict({
        "dict_type": "device_tag",
        "dict_key": "MacBook",
        "dict_label": "MacBook",
        "icon": "💻",
        "sort_order": 4,
    })
    assert add_res["ok"] is True
    d_id = add_res["dict"]["id"]

    dev_dicts = api.get_system_dicts("device_tag")
    assert any(d["dict_key"] == "MacBook" for d in dev_dicts)

    acc = api.save_account({
        "account_type": "WorkBuddy",
        "account": "mac_user@workbuddy.ai",
        "password": "Password123",
        "device_tag": "MacBook",
    })
    assert acc["ok"] is True
    acc_id = acc["account"]["id"]
    assert acc["account"]["device_tag"] == "MacBook"

    set_dev = api.set_device_tag(acc_id, "iPhone")
    assert set_dev["ok"] is True
    assert set_dev["account"]["device_tag"] == "iPhone"

    dash = api.get_dashboard(device_tag="iPhone")
    assert len(dash["accounts"]) == 1

    del_res = api.delete_system_dict(d_id)
    assert del_res["ok"] is True
