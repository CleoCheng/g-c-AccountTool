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
