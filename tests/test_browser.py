import json
import subprocess
import time
from pathlib import Path
from src.browser_service import (
    generate_fingerprint_config,
    prepare_profile_dir,
    build_browser_launch_args,
)
from src.totp_service import generate_totp


def test_generate_unique_paired_fingerprints():
    fp1 = generate_fingerprint_config(1, "user1@example.com")
    fp2 = generate_fingerprint_config(2, "user2@example.com")

    assert fp1["profile_code"] == "FP-001"
    assert fp2["profile_code"] == "FP-002"
    assert fp1["canvas_seed"] != fp2["canvas_seed"]
    assert fp1["audio_seed"] != fp2["audio_seed"]
    assert "webgl_renderer" in fp1
    assert fp1["cpu_cores"] in (8, 12, 16, 20, 24)
    assert fp1["memory_gb"] in (8, 16, 32)


def test_prepare_profile_dir_and_extension(tmp_path: Path):
    data_dir = tmp_path / "data"
    fp = generate_fingerprint_config(10, "demo_account10@example.com", proxy="http://127.0.0.1:7890")
    secret = "JBSWY3DPEHPK3PXP"
    account = {
        "id": 10,
        "account_type": "ChatGPT",
        "account": "demo_account10@example.com",
        "password": "TestPassword123!",
        "secret_key": secret,
        "fp_config": fp,
    }

    profile_dir = prepare_profile_dir(data_dir, account)
    assert profile_dir == data_dir / "browsers" / "acc_10"
    ext_dir = profile_dir / "fp_ext"
    assert (ext_dir / "manifest.json").exists()
    assert (ext_dir / "inject.js").exists()
    assert (ext_dir / "autologin.js").exists()

    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["content_scripts"][0]["world"] == "MAIN"
    assert manifest["content_scripts"][0]["run_at"] == "document_start"
    assert manifest["content_scripts"][1]["js"] == ["autologin.js"]

    inject_code = (ext_dir / "inject.js").read_text(encoding="utf-8")
    assert str(fp["canvas_seed"]) in inject_code
    assert fp["webgl_renderer"] in inject_code

    autologin_code = (ext_dir / "autologin.js").read_text(encoding="utf-8")
    assert "demo_account10@example.com" in autologin_code
    assert "TestPassword123!" in autologin_code
    assert secret in autologin_code

    # Verify JS TOTP implementation in autologin.js matches Python pyotp 100%
    now_ms = int(time.time() * 1000)
    expected_code = generate_totp(secret)["code"]
    js_runner = f"""
    const fs = require('fs');
    const code = fs.readFileSync({json.dumps(str(ext_dir / "autologin.js"))}, 'utf8');
    eval(code);
    process.stdout.write(globalThis.__kvComputeTotp({json.dumps(secret)}, {now_ms}));
    """
    proc = subprocess.run(["node", "-e", js_runner], capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == expected_code

    args = build_browser_launch_args(account, profile_dir, exe_path="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
    assert any(a.startswith("--user-data-dir=") for a in args)
    assert any(a.startswith("--load-extension=") for a in args)
    assert any(a == "--proxy-server=http://127.0.0.1:7890" for a in args)
    assert args[-1] == "https://chatgpt.com/"
