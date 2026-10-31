from pathlib import Path
from src.proxy_service import (
    find_clash_config_files,
    is_valid_proxy_node_name,
    parse_clash_yaml_summary,
)
from src.db_service import DatabaseService


def test_filter_valid_proxy_node_names():
    assert is_valid_proxy_node_name("🇸🇬 Singapore | 04") is True
    assert is_valid_proxy_node_name("🇺🇸 United States | 01") is True
    assert is_valid_proxy_node_name("Traffic: 0 GB / 200 GB") is False
    assert is_valid_proxy_node_name("Expire: 2027-10-29") is False
    assert is_valid_proxy_node_name("DIRECT") is False


def test_parse_clash_yaml_summary(tmp_path: Path):
    sample_yaml = tmp_path / "clash-verge.yaml"
    sample_yaml.write_text(
        """
mixed-port: 17898
secret: my-secret
listeners:
  - name: ai-fixed-sg
    type: mixed
    listen: 127.0.0.1
    port: 7897
    proxy: SG
proxies:
  - name: "Traffic: 10 GB / 200 GB"
    type: trojan
  - name: "🇸🇬 Singapore | 01"
    type: trojan
  - name: "🇺🇸 United States | 01"
    type: trojan
""",
        encoding="utf-8",
    )
    info = parse_clash_yaml_summary(sample_yaml)
    assert info["mixed_port"] == 17898
    assert any(p["port"] == 17898 for p in info["ports"])
    assert any(p["port"] == 7897 for p in info["ports"])
    node_names = [n["name"] for n in info["nodes"]]
    assert "🇸🇬 Singapore | 01" in node_names
    assert "🇺🇸 United States | 01" in node_names
    assert "Traffic: 10 GB / 200 GB" not in node_names


def test_account_node_lock_prevents_modification_until_unlocked(tmp_path: Path):
    db = DatabaseService(tmp_path / "data" / "accounts.db")
    acc = db.add_account(
        {
            "account_type": "ChatGPT",
            "account": "lock_test@icloud.com",
            "password": "pwd",
        }
    )
    acc_id = acc["id"]

    # Bind and lock node
    res1 = db.bind_account_proxy_node(
        acc_id,
        proxy_url="http://127.0.0.1:17898",
        proxy_node="🇸🇬 Singapore | 04",
        locked=True,
    )
    assert res1["ok"] is True
    assert res1["account"]["fp_config"]["proxy_node"] == "🇸🇬 Singapore | 04"
    assert res1["account"]["fp_config"]["node_locked"] is True

    # Attempt to change to US node while locked -> MUST be rejected!
    res2 = db.bind_account_proxy_node(
        acc_id,
        proxy_url="http://127.0.0.1:17898",
        proxy_node="🇺🇸 United States | 01",
        locked=True,
    )
    assert res2["ok"] is False
    assert "已锁定" in res2["error"]
    assert db.get_account(acc_id)["fp_config"]["proxy_node"] == "🇸🇬 Singapore | 04"

    # Unlock first -> succeeds
    res_unlock = db.set_account_node_lock(acc_id, False)
    assert res_unlock["ok"] is True
    assert res_unlock["account"]["fp_config"]["node_locked"] is False

    # Now changing to US node succeeds and locks again
    res3 = db.bind_account_proxy_node(
        acc_id,
        proxy_url="http://127.0.0.1:17898",
        proxy_node="🇺🇸 United States | 01",
        locked=True,
    )
    assert res3["ok"] is True
    assert res3["account"]["fp_config"]["proxy_node"] == "🇺🇸 United States | 01"
    assert res3["account"]["fp_config"]["node_locked"] is True


def test_env_override_clash_config_takes_priority(tmp_path: Path, monkeypatch):
    custom_yaml = tmp_path / "my-custom-clash.yaml"
    custom_yaml.write_text("mixed-port: 7890\n", encoding="utf-8")
    monkeypatch.setenv("KEYVAULT_CLASH_CONFIG", str(custom_yaml))

    found = find_clash_config_files()
    assert found, "custom config should be discovered"
    label, path = found[0]
    assert Path(path).resolve() == custom_yaml.resolve()
    assert "KEYVAULT_CLASH_CONFIG" in label


def test_env_override_clash_config_missing_file_is_ignored(tmp_path: Path, monkeypatch):
    missing = tmp_path / "does-not-exist.yaml"
    monkeypatch.setenv("KEYVAULT_CLASH_CONFIG", str(missing))
    found = find_clash_config_files()
    assert all(Path(p).resolve() != missing.resolve() for _, p in found)