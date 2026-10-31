import asyncio
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
import websockets
from src.proxy_service import activate_proxy_node


GPU_PROFILES = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 4070"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 4060 Ti"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 3080"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 3070"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 4080S"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 3060 Ti"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 4070S"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)", "RTX 3090"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 7800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)", "RX 7800 XT"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)", "RX 6800 XT"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 7900 GRE Direct3D11 vs_5_0 ps_5_0, D3D11)", "RX 7900 GRE"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", "Arc A770"),
]

CPU_OPTIONS = [8, 12, 16, 20, 24]
MEMORY_OPTIONS = [8, 16, 32]
SCREEN_OPTIONS = [
    (1920, 1080),
    (2560, 1440),
    (1920, 1200),
    (2560, 1600),
    (3440, 1440),
    (3840, 2160),
]
CHROME_VERSIONS = [
    "131.0.6778.86",
    "131.0.6778.140",
    "132.0.6834.84",
    "132.0.6834.111",
    "133.0.6943.54",
    "133.0.6943.99",
    "134.0.6998.45",
]


def generate_fingerprint_config(
    account_id: int,
    account_email: str,
    proxy: str = "",
    proxy_node: str = "",
    node_locked: bool = False,
    salt: str = "",
) -> dict:
    seed_str = f"KeyVault-FP-{account_id}-{account_email.strip().lower()}-{salt}"
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()

    gpu_idx = int.from_bytes(digest[0:2], "big") % len(GPU_PROFILES)
    cpu_idx = digest[2] % len(CPU_OPTIONS)
    mem_idx = digest[3] % len(MEMORY_OPTIONS)
    scr_idx = digest[4] % len(SCREEN_OPTIONS)
    ver_idx = digest[5] % len(CHROME_VERSIONS)

    vendor, renderer, gpu_short = GPU_PROFILES[gpu_idx]
    cpu_cores = CPU_OPTIONS[cpu_idx]
    memory_gb = MEMORY_OPTIONS[mem_idx]
    scr_w, scr_h = SCREEN_OPTIONS[scr_idx]
    chrome_ver = CHROME_VERSIONS[ver_idx]

    canvas_seed = (int.from_bytes(digest[8:12], "big") % 900000) + 100001
    audio_seed = (int.from_bytes(digest[12:16], "big") % 900000) + 100001

    ua = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver} Safari/537.36"
    )

    return {
        "profile_code": f"FP-{int(account_id):03d}",
        "webgl_vendor": vendor,
        "webgl_renderer": renderer,
        "gpu_short": gpu_short,
        "cpu_cores": cpu_cores,
        "memory_gb": memory_gb,
        "screen_width": scr_w,
        "screen_height": scr_h,
        "screen": f"{scr_w}x{scr_h}",
        "chrome_version": chrome_ver,
        "user_agent": ua,
        "canvas_seed": canvas_seed,
        "audio_seed": audio_seed,
        "proxy": (proxy or "").strip(),
        "proxy_node": (proxy_node or "").strip(),
        "node_locked": bool(node_locked),
    }


def _build_autologin_js(fp: dict, account: dict) -> str:
    auth_payload = json.dumps(
        {
            "accountType": (account.get("account_type") or "ChatGPT").strip(),
            "account": (account.get("account") or "").strip(),
            "maskedAccount": (account.get("masked_account") or account.get("account") or "").strip(),
            "password": (account.get("password") or "").strip(),
            "recoveryEmail": (account.get("recovery_email") or "").strip(),
            "secretKey": (account.get("secret_key") or "").strip(),
            "initialSecretKey": (account.get("initial_secret_key") or "").strip(),
            "twofaModified": bool(account.get("twofa_modified")),
            "profileCode": fp.get("profile_code", "FP-000"),
            "proxyNode": (fp.get("proxy_node") or "").strip(),
        },
        ensure_ascii=False,
    )

    return f"""(() => {{
  const AUTH = {auth_payload};

  // --- Pure synchronous RFC 6238 TOTP (SHA-1 HMAC + Base32) ---
  function base32ToBytes(b32) {{
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    const cleaned = String(b32 || '').toUpperCase().replace(/[^A-Z2-7]/g, '');
    if (!cleaned) return new Uint8Array(0);
    let bits = 0, value = 0;
    const out = [];
    for (let i = 0; i < cleaned.length; i++) {{
      const idx = alphabet.indexOf(cleaned[i]);
      if (idx === -1) continue;
      value = (value << 5) | idx;
      bits += 5;
      if (bits >= 8) {{
        out.push((value >>> (bits - 8)) & 0xff);
        bits -= 8;
      }}
    }}
    return new Uint8Array(out);
  }}

  function sha1Bytes(msgBytes) {{
    function rotl(n, s) {{ return ((n << s) | (n >>> (32 - s))) >>> 0; }}
    const ml = msgBytes.length;
    const bitLenHi = Math.floor((ml * 8) / 0x100000000);
    const bitLenLo = (ml * 8) >>> 0;
    const padLen = ((ml + 8) >> 6 << 6) + 64;
    const buf = new Uint8Array(padLen);
    buf.set(msgBytes);
    buf[ml] = 0x80;
    const dv = new DataView(buf.buffer);
    dv.setUint32(padLen - 8, bitLenHi, false);
    dv.setUint32(padLen - 4, bitLenLo, false);

    let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0;
    const w = new Uint32Array(80);

    for (let off = 0; off < padLen; off += 64) {{
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(off + i * 4, false);
      for (let i = 16; i < 80; i++) w[i] = rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
      let a = h0, b = h1, c = h2, d = h3, e = h4;
      for (let i = 0; i < 80; i++) {{
        let f, k;
        if (i < 20) {{ f = (b & c) | (~b & d); k = 0x5a827999; }}
        else if (i < 40) {{ f = b ^ c ^ d; k = 0x6ed9eba1; }}
        else if (i < 60) {{ f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }}
        else {{ f = b ^ c ^ d; k = 0xca62c1d6; }}
        const temp = (rotl(a, 5) + f + e + k + w[i]) >>> 0;
        e = d; d = c; c = rotl(b, 30); b = a; a = temp;
      }}
      h0 = (h0 + a) >>> 0;
      h1 = (h1 + b) >>> 0;
      h2 = (h2 + c) >>> 0;
      h3 = (h3 + d) >>> 0;
      h4 = (h4 + e) >>> 0;
    }}
    const out = new Uint8Array(20);
    const outDv = new DataView(out.buffer);
    outDv.setUint32(0, h0, false);
    outDv.setUint32(4, h1, false);
    outDv.setUint32(8, h2, false);
    outDv.setUint32(12, h3, false);
    outDv.setUint32(16, h4, false);
    return out;
  }}

  function hmacSha1(keyBytes, msgBytes) {{
    let key = keyBytes;
    if (key.length > 64) key = sha1Bytes(key);
    const ipad = new Uint8Array(64);
    const opad = new Uint8Array(64);
    for (let i = 0; i < 64; i++) {{
      const b = i < key.length ? key[i] : 0;
      ipad[i] = b ^ 0x36;
      opad[i] = b ^ 0x5c;
    }}
    const innerInput = new Uint8Array(64 + msgBytes.length);
    innerInput.set(ipad, 0);
    innerInput.set(msgBytes, 64);
    const innerHash = sha1Bytes(innerInput);

    const outerInput = new Uint8Array(64 + 20);
    outerInput.set(opad, 0);
    outerInput.set(innerHash, 64);
    return sha1Bytes(outerInput);
  }}

  function computeTotp(secret, nowMs) {{
    const key = base32ToBytes(secret);
    if (!key.length) return '';
    const epochSec = Math.floor((nowMs || Date.now()) / 1000);
    const counter = Math.floor(epochSec / 30);
    const msg = new Uint8Array(8);
    const dv = new DataView(msg.buffer);
    dv.setUint32(0, Math.floor(counter / 0x100000000), false);
    dv.setUint32(4, counter >>> 0, false);
    const digest = hmacSha1(key, msg);
    const offset = digest[19] & 0x0f;
    const binCode =
      ((digest[offset] & 0x7f) << 24) |
      ((digest[offset + 1] & 0xff) << 16) |
      ((digest[offset + 2] & 0xff) << 8) |
      (digest[offset + 3] & 0xff);
    return String(binCode % 1000000).padStart(6, '0');
  }}

  if (typeof globalThis !== 'undefined') {{
    globalThis.__kvComputeTotp = computeTotp;
  }}
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  try {{
    if (window !== window.top) return;
  }} catch (_) {{
    return;
  }}
  if (!/^https?:$/i.test(location.protocol || '')) return;
  if (window.__kv_autologin_active) {{
    if (typeof window.__kv_ensure_mounted === 'function') {{
      try {{ window.__kv_ensure_mounted(); }} catch (_) {{}}
    }}
    return;
  }}
  window.__kv_autologin_active = true;

  function safeGetSession(k) {{
    try {{ return sessionStorage.getItem(k); }} catch (_) {{ return null; }}
  }}
  function safeSetSession(k, v) {{
    try {{ sessionStorage.setItem(k, v); }} catch (_) {{}}
  }}
  function safeResetStepCooldowns() {{
    try {{
      const keys = [];
      for (let i = 0; i < sessionStorage.length; i++) {{
        const k = sessionStorage.key(i);
        if (k && k.startsWith('kv_step_')) keys.push(k);
      }}
      keys.forEach((k) => sessionStorage.removeItem(k));
    }} catch (_) {{}}
  }}

  // --- DOM Helpers for React / Google Wiz ---
  let autoEnabled = safeGetSession('kv_autologin_enabled') !== '0';
  let statusText = '⚡ 正在检测登录表单...';
  let statusUiUpdater = null;
  let lastFocusedInput = null;

  document.addEventListener('focusin', (e) => {{
    if (e.target && e.target.tagName === 'INPUT') {{
      lastFocusedInput = e.target;
    }}
  }}, true);

  function setStatus(msg) {{
    statusText = msg;
    if (statusUiUpdater) statusUiUpdater();
  }}

  function isVisible(el) {{
    if (!el || !el.isConnected) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 8 && rect.height > 8;
  }}

  function findFirstVisible(selectors) {{
    for (const sel of selectors) {{
      const list = document.querySelectorAll(sel);
      for (const el of list) {{
        if (isVisible(el) && !el.disabled && !el.readOnly) return el;
      }}
    }}
    return null;
  }}

  function setNativeInputValue(input, val) {{
    if (!input || val === undefined || val === null) return false;
    input.focus();
    const proto = window.HTMLInputElement ? window.HTMLInputElement.prototype : null;
    const desc = proto ? Object.getOwnPropertyDescriptor(proto, 'value') : null;
    if (desc && desc.set) {{
      desc.set.call(input, String(val));
    }} else {{
      input.value = String(val);
    }}
    input.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true, key: 'a' }}));
    try {{
      input.dispatchEvent(new InputEvent('input', {{ bubbles: true, cancelable: true, inputType: 'insertText', data: String(val) }}));
    }} catch (_) {{
      input.dispatchEvent(new Event('input', {{ bubbles: true }}));
    }}
    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
    input.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true, key: 'a' }}));
    return true;
  }}

  function clickButton(btn) {{
    if (!btn) return false;
    try {{
      btn.focus();
      btn.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
      btn.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
      btn.click();
      return true;
    }} catch (_) {{
      return false;
    }}
  }}

  function canRunStep(stepKey, cooldownMs = 4200) {{
    const key = 'kv_step_' + stepKey;
    const last = parseInt(safeGetSession(key) || '0', 10);
    const now = Date.now();
    if (now - last < cooldownMs) return false;
    safeSetSession(key, String(now));
    return true;
  }}

  function resetStepCooldowns() {{
    safeResetStepCooldowns();
  }}

  function findOpenAISubmitButton(contextInput) {{
    const blockedWords = /google|microsoft|apple|phone|手机|电话|passkey|通行密钥|forgot|忘记|reset|sign up|注册|免费注册|back|返回|resend|重新发送|try another|其他方式|条款|隐私/i;
    const continueWords = /^(continue|继续|next|下一步|verify|验证|submit|提交|log in|登录)$/i;

    // 1. Always prioritize submit button inside the input's own <form>
    const form = contextInput && contextInput.closest ? contextInput.closest('form') : null;
    if (form) {{
      const formBtns = Array.from(form.querySelectorAll('button[type="submit"], button[name="intent"], button[name="action"], button'));
      for (const btn of formBtns) {{
        if (!isVisible(btn) || btn.disabled) continue;
        const txt = (btn.innerText || btn.textContent || '').trim();
        if (blockedWords.test(txt)) continue;
        if (btn.type === 'submit' && txt.length > 0) return btn;
        if (continueWords.test(txt)) return btn;
      }}
      for (const btn of formBtns) {{
        if (!isVisible(btn) || btn.disabled) continue;
        const txt = (btn.innerText || btn.textContent || '').trim();
        if (!blockedWords.test(txt) && btn.type === 'submit') return btn;
      }}
    }}

    // 2. Next prioritize explicit submit buttons across the page with "Continue / 继续"
    const submitBtns = Array.from(document.querySelectorAll('button[type="submit"], button[name="intent"], button[name="action"], button[data-dd-action-name="Continue"]'));
    for (const btn of submitBtns) {{
      if (!isVisible(btn) || btn.disabled) continue;
      const txt = (btn.innerText || btn.textContent || '').trim();
      if (blockedWords.test(txt)) continue;
      if (continueWords.test(txt)) return btn;
    }}

    // 3. Fallback to any visible button with "Continue / 继续 / 下一步" (excluding top header "登录" button if type="button")
    const allBtns = Array.from(document.querySelectorAll('button'));
    for (const btn of allBtns) {{
      if (!isVisible(btn) || btn.disabled) continue;
      const txt = (btn.innerText || btn.textContent || '').trim();
      if (blockedWords.test(txt)) continue;
      if (/^(continue|继续|next|下一步|verify|验证|submit|提交)$/i.test(txt)) return btn;
    }}
    return null;
  }}

  function fillOtpCodeOnPage(code) {{
    if (!code) return false;
    // Check if there are 6 individual 1-digit inputs
    const singleDigitBoxes = Array.from(document.querySelectorAll('input[maxlength="1"], input[data-index]')).filter(
      (el) => isVisible(el) && !el.disabled && !el.readOnly && el.type !== 'password' && el.type !== 'email'
    );
    if (singleDigitBoxes.length >= 6) {{
      for (let i = 0; i < 6; i++) {{
        setNativeInputValue(singleDigitBoxes[i], code[i]);
      }}
      return true;
    }}

    const otpInput = findFirstVisible([
      'input#totpPin',
      'input[name="totpPin"]',
      'input[autocomplete="one-time-code"]',
      'input[name="code"]',
      'input[name="otp"]',
      'input[id*="code"]',
      'input[id*="totp"]',
      'input[inputmode="numeric"]',
      'input[type="tel"]',
    ]);
    if (otpInput) {{
      return setNativeInputValue(otpInput, code);
    }}
    return false;
  }}

  function getActiveTotpSecret() {{
    return AUTH.secretKey || AUTH.initialSecretKey || '';
  }}

  function scheduleTotpFillAndSubmit(submitFinder) {{
    const secret = getActiveTotpSecret();
    if (!secret) {{
      setStatus('⚠️ 此账号未配置 2FA 密钥');
      return;
    }}
    const nowSec = Math.floor(Date.now() / 1000);
    const rem = 30 - (nowSec % 30);
    const delayMs = rem <= 2 ? (rem + 0.5) * 1000 : 250;
    if (rem <= 2) {{
      setStatus('⏳ 当前 2FA 即将刷新，等待新验证码...');
    }}
    setTimeout(() => {{
      const freshCode = computeTotp(secret, Date.now());
      if (fillOtpCodeOnPage(freshCode)) {{
        setStatus('⚡ 已填入 2FA 验证码 (' + freshCode + ')，正在提交...');
        setTimeout(() => {{
          const btn = submitFinder();
          if (btn) clickButton(btn);
        }}, 420);
      }}
    }}, delayMs);
  }}

  // --- Platform Specific Auto-Login Flows ---
  function runChatGPTFlow(force = false) {{
    const host = location.hostname.toLowerCase();

    // 1. Check for OpenAI 2FA / OTP step first
    const otpInput = findFirstVisible([
      'input[autocomplete="one-time-code"]',
      'input[name="code"]',
      'input[name="otp"]',
      'input[id*="code"]',
    ]);
    if (otpInput && otpInput.type !== 'email' && otpInput.type !== 'password') {{
      const pageText = (document.body ? document.body.innerText : '') || '';
      const isEmailInboxCode = /check your inbox|查看您的收件箱|sent a code to your email|已向您的电子邮件发送/i.test(pageText)
        && !/authenticator|身份验证器|one-time|一次性|two-step|两步验证/i.test(pageText);
      if (isEmailInboxCode && !force) {{
        setStatus('📧 检测到邮箱验证码步骤，请查收邮箱或手动点击[填2FA]');
        return;
      }}
      if (getActiveTotpSecret() && (force || canRunStep('openai_totp', 4200))) {{
        scheduleTotpFillAndSubmit(() => findOpenAISubmitButton(otpInput));
        return;
      }}
    }}

    // 2. Check for OpenAI Password step
    const pwdInput = findFirstVisible([
      'input[type="password"][name="current-password"]',
      'input[type="password"][name="password"]',
      'input[type="password"]#password',
      'input[type="password"][autocomplete*="current-password"]',
      'input[type="password"]',
    ]);
    const emailInput = findFirstVisible([
      'input#mobile-auth-email',
      'input[name="login_hint"][type="email"]',
      'input[name="email"]:not([type="hidden"])',
      'input#email-input',
      'input[name="username"]:not([type="hidden"])',
      'input[type="email"]',
      'input[autocomplete="email"]',
      'input[autocomplete="username"]',
    ]);

    if (pwdInput && AUTH.password) {{
      if (force || canRunStep('openai_pwd', 4000)) {{
        if (emailInput && !emailInput.value && AUTH.account) {{
          setNativeInputValue(emailInput, AUTH.account);
        }}
        setNativeInputValue(pwdInput, AUTH.password);
        setStatus('⚡ 已自动填入密码，正在登录...');
        setTimeout(() => {{
          const btn = findOpenAISubmitButton(pwdInput);
          if (btn) clickButton(btn);
        }}, 400);
      }}
      return;
    }}

    // 3. Check for OpenAI / ChatGPT Email step (works both on auth.openai.com and inline modal on chatgpt.com)
    if (emailInput && AUTH.account) {{
      if (force || canRunStep('openai_email', 4000)) {{
        setNativeInputValue(emailInput, AUTH.account);
        setStatus('⚡ 已自动填入账号邮箱，正在点击继续...');
        setTimeout(() => {{
          const btn = findOpenAISubmitButton(emailInput);
          if (btn) clickButton(btn);
        }}, 400);
      }}
      return;
    }}

    // 4. On chatgpt.com when no email/password/OTP input is visible yet
    if (host.includes('chatgpt.com')) {{
      const loginBtn = findFirstVisible([
        'button[data-testid="login-button"]',
        'a[data-testid="login-button"]',
        'button[data-testid="welcome-login-button"]',
      ]) || Array.from(document.querySelectorAll('button, a')).find((el) => {{
        if (!isVisible(el)) return false;
        const t = (el.innerText || el.textContent || '').trim();
        return /^(log in|登录)$/i.test(t);
      }});

      if (!loginBtn) {{
        setStatus('✅ 已成功登录 ChatGPT 主页');
        autoMinimizeCapsule();
        return;
      }}

      if (force || canRunStep('chatgpt_landing_login', 4500)) {{
        setStatus('⚡ 检测到未登录，正在点击「登录」按钮...');
        setTimeout(() => clickButton(loginBtn), 450);
        return;
      }}
    }}
  }}

  function findGoogleNextButton(primarySelector) {{
    if (primarySelector) {{
      const el = document.querySelector(primarySelector + ' button') || document.querySelector(primarySelector);
      if (el && isVisible(el)) return el;
    }}
    const candidates = Array.from(document.querySelectorAll('button[jsname="LgbsSe"], #identifierNext button, #passwordNext button, #totpNext button, button[type="submit"], button'));
    for (const btn of candidates) {{
      if (!isVisible(btn) || btn.disabled) continue;
      const txt = (btn.innerText || btn.textContent || '').trim();
      if (/^(next|下一步|继续|continue|verify|验证|确认|confirm)$/i.test(txt)) return btn;
    }}
    return null;
  }}

  function runGoogleFlow(force = false) {{
    const host = location.hostname.toLowerCase();
    const path = location.pathname.toLowerCase();

    if (host.includes('myaccount.google.com') && !path.includes('signin')) {{
      setStatus('✅ 已成功登录 Google 账号主页');
      autoMinimizeCapsule();
      return;
    }}

    // 0. Account Chooser screen (if present)
    if (AUTH.account) {{
      const chooserRow = document.querySelector(`div[data-identifier="${{CSS.escape(AUTH.account)}}"]`);
      if (chooserRow && isVisible(chooserRow) && (force || canRunStep('google_chooser', 4200))) {{
        setStatus('⚡ 已在列表中选择当前 Google 账号...');
        setTimeout(() => clickButton(chooserRow), 350);
        return;
      }}
    }}

    // 1. Google 2FA TOTP step
    const totpInput = findFirstVisible([
      'input#totpPin',
      'input[name="totpPin"]',
      'input[type="tel"][id*="totp"]',
      'input[autocomplete="one-time-code"]',
    ]);
    if (totpInput && getActiveTotpSecret()) {{
      if (force || canRunStep('google_totp', 4800)) {{
        scheduleTotpFillAndSubmit(() => findGoogleNextButton('#totpNext'));
      }}
      return;
    }}

    // 2. Google Recovery Email Verification step
    const recInput = findFirstVisible([
      'input#knowledge-preregistered-email-response',
      'input[name="knowledgePreregisteredEmailResponse"]',
    ]);
    if (recInput && AUTH.recoveryEmail) {{
      if (force || canRunStep('google_recovery_email', 4500)) {{
        setNativeInputValue(recInput, AUTH.recoveryEmail);
        setStatus('⚡ 已自动填入辅助邮箱，正在验证...');
        setTimeout(() => {{
          const btn = findGoogleNextButton(null);
          if (btn) clickButton(btn);
        }}, 450);
      }}
      return;
    }}

    // Also check if Google is showing the "Choose verification method" list with "Confirm your recovery email" (data-challengetype="12") or Authenticator (data-challengetype="6")
    const totpChallengeOption = document.querySelector('div[data-challengetype="6"], li div[data-challengetype="6"]');
    if (totpChallengeOption && isVisible(totpChallengeOption) && getActiveTotpSecret() && (force || canRunStep('google_pick_totp', 4200))) {{
      setStatus('⚡ 自动选择 Google 身份验证器 2FA 验证...');
      setTimeout(() => clickButton(totpChallengeOption), 400);
      return;
    }}
    const recChallengeOption = document.querySelector('div[data-challengetype="12"], li div[data-challengetype="12"]');
    if (recChallengeOption && isVisible(recChallengeOption) && AUTH.recoveryEmail && (force || canRunStep('google_pick_rec', 4200))) {{
      setStatus('⚡ 自动选择确认辅助邮箱验证...');
      setTimeout(() => clickButton(recChallengeOption), 400);
      return;
    }}

    // 3. Google Password step
    const pwdInput = findFirstVisible([
      'input[type="password"][name="Passwd"]',
      'input[type="password"][name="password"]',
      '#password input[type="password"]',
    ]);
    if (pwdInput && AUTH.password) {{
      if (force || canRunStep('google_pwd', 4500)) {{
        setNativeInputValue(pwdInput, AUTH.password);
        setStatus('⚡ 已自动填入 Google 密码，正在下一步...');
        setTimeout(() => {{
          const btn = findGoogleNextButton('#passwordNext');
          if (btn) clickButton(btn);
        }}, 450);
      }}
      return;
    }}

    // 4. Google Identifier (Email) step
    const emailInput = findFirstVisible([
      'input#identifierId',
      'input[type="email"][name="identifier"]',
    ]);
    if (emailInput && AUTH.account) {{
      if (force || canRunStep('google_email', 4500)) {{
        setNativeInputValue(emailInput, AUTH.account);
        setStatus('⚡ 已自动填入 Google 邮箱，正在下一步...');
        setTimeout(() => {{
          const btn = findGoogleNextButton('#identifierNext');
          if (btn) clickButton(btn);
        }}, 450);
      }}
      return;
    }}
  }}

  function runAutoLoginTick(force = false) {{
    if (!autoEnabled && !force) return;
    if (force) resetStepCooldowns();
    const host = location.hostname.toLowerCase();
    if (host.includes('google.com')) {{
      runGoogleFlow(force);
    }} else if (host.includes('chatgpt.com') || host.includes('openai.com')) {{
      runChatGPTFlow(force);
    }}
  }}

  // --- Closed Shadow DOM Floating Auto-Login Capsule ---
  let minimized = false;
  let minimizeTimer = null;

  function autoMinimizeCapsule() {{
    if (minimizeTimer) return;
    minimizeTimer = setTimeout(() => {{
      minimized = true;
      if (statusUiUpdater) statusUiUpdater();
    }}, 2200);
  }}

  function mountCapsule() {{
    const rootTarget = document.documentElement || document.body;
    if (!rootTarget || document.getElementById('__kv_autologin_host')) return;
    const hostEl = document.createElement('div');
    hostEl.id = '__kv_autologin_host';
    hostEl.style.cssText = 'all: initial; position: fixed; top: 14px; right: 14px; z-index: 2147483647; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;';
    const shadow = hostEl.attachShadow({{ mode: 'closed' }});

    const style = document.createElement('style');
    style.textContent = `
      .kv-box {{
        background: rgba(15, 23, 42, 0.94);
        backdrop-filter: blur(10px);
        color: #f8fafc;
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 12px;
        padding: 10px 12px;
        width: 270px;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.45);
        font-size: 12px;
        line-height: 1.4;
        user-select: none;
      }}
      .kv-box.minimized {{
        width: auto;
        padding: 6px 11px;
        border-radius: 999px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 6px;
      }}
      .kv-head {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 6px;
        padding-bottom: 5px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.18);
      }}
      .kv-title {{
        font-weight: 700;
        color: #38bdf8;
        font-size: 12px;
        display: flex;
        align-items: center;
        gap: 5px;
      }}
      .kv-actions-top {{
        display: flex;
        align-items: center;
        gap: 5px;
      }}
      .kv-mini-btn {{
        background: rgba(255,255,255,0.08);
        color: #cbd5e1;
        border: 1px solid rgba(255,255,255,0.14);
        border-radius: 5px;
        padding: 2px 6px;
        font-size: 11px;
        cursor: pointer;
      }}
      .kv-mini-btn.active {{
        background: rgba(16, 185, 129, 0.22);
        color: #34d399;
        border-color: rgba(16, 185, 129, 0.45);
      }}
      .kv-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 5px;
        color: #cbd5e1;
        font-size: 11.5px;
      }}
      .kv-totp {{
        font-family: ui-monospace, Consolas, monospace;
        font-weight: 700;
        color: #34d399;
        background: rgba(16, 185, 129, 0.14);
        padding: 1px 6px;
        border-radius: 5px;
        cursor: pointer;
      }}
      .kv-status {{
        background: rgba(30, 41, 59, 0.9);
        color: #e2e8f0;
        padding: 5px 8px;
        border-radius: 6px;
        font-size: 11px;
        margin: 6px 0;
        border-left: 3px solid #38bdf8;
      }}
      .kv-btns {{
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
        margin-top: 6px;
      }}
      .kv-btn {{
        flex: 1 1 auto;
        background: rgba(56, 189, 248, 0.15);
        color: #bae6fd;
        border: 1px solid rgba(56, 189, 248, 0.32);
        border-radius: 6px;
        padding: 4px 7px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        text-align: center;
      }}
      .kv-btn:hover {{
        background: rgba(56, 189, 248, 0.28);
        color: #fff;
      }}
      .kv-btn.primary {{
        background: #0284c7;
        color: #fff;
        border-color: #38bdf8;
      }}
    `;

    const container = document.createElement('div');
    container.className = 'kv-box';
    shadow.appendChild(style);
    shadow.appendChild(container);
    rootTarget.appendChild(hostEl);

    function fillIntoFocusedOrTarget(val, label, fallbackSelectors) {{
      if (!val) {{
        setStatus('⚠️ 此账号无' + label + '数据');
        return;
      }}
      let target = (lastFocusedInput && isVisible(lastFocusedInput)) ? lastFocusedInput : null;
      if (!target && fallbackSelectors) target = findFirstVisible(fallbackSelectors);
      if (target) {{
        setNativeInputValue(target, val);
        setStatus('✅ 已填入' + label);
      }} else {{
        navigator.clipboard?.writeText(val).catch(() => {{}});
        setStatus('📋 未找到输入框，已复制' + label + '到剪贴板');
      }}
    }}

    function mkEl(tag, className, text) {{
      const el = document.createElement(tag);
      if (className) el.className = className;
      if (text !== undefined && text !== null) el.textContent = String(text);
      return el;
    }}

    function render() {{
      try {{
        const secret = getActiveTotpSecret();
        const nowSec = Math.floor(Date.now() / 1000);
        const rem = 30 - (nowSec % 30);
        const code = secret ? computeTotp(secret, Date.now()) : '';
        const fmtCode = code ? code.slice(0, 3) + ' ' + code.slice(3) : '无 2FA';

        if (minimized) {{
          container.className = 'kv-box minimized';
          const s1 = mkEl('span', '', '🔐 ' + AUTH.profileCode);
          s1.style.cssText = 'color:#38bdf8;font-weight:700;';
          const s2 = mkEl('span', '', fmtCode);
          s2.style.cssText = 'color:#34d399;font-family:monospace;';
          container.replaceChildren(s1, s2);
          container.onclick = () => {{
            minimized = false;
            render();
          }};
          return;
        }}

        container.onclick = null;
        container.className = 'kv-box';

        // Header
        const head = mkEl('div', 'kv-head');
        const title = mkEl('span', 'kv-title', '🔐 KeyVault · ' + AUTH.profileCode);
        const actionsTop = mkEl('div', 'kv-actions-top');
        const toggleBtn = mkEl('button', 'kv-mini-btn' + (autoEnabled ? ' active' : ''), autoEnabled ? '自动: 开' : '自动: 关');
        toggleBtn.onclick = (e) => {{
          e.stopPropagation();
          autoEnabled = !autoEnabled;
          safeSetSession('kv_autologin_enabled', autoEnabled ? '1' : '0');
          setStatus(autoEnabled ? '⚡ 已开启自动登录检测' : '⏸ 已暂停自动提交，可点击下方按钮手动填入');
          if (autoEnabled) runAutoLoginTick(true);
        }};
        const minBtn = mkEl('button', 'kv-mini-btn', '—');
        minBtn.title = '收起';
        minBtn.onclick = (e) => {{
          e.stopPropagation();
          minimized = true;
          render();
        }};
        actionsTop.append(toggleBtn, minBtn);
        head.append(title, actionsTop);

        // Account & TOTP row
        const row = mkEl('div', 'kv-row');
        const accSpan = mkEl('span', '', AUTH.maskedAccount || AUTH.account);
        accSpan.title = AUTH.account;
        accSpan.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:145px;';
        const totpSpan = mkEl('span', 'kv-totp', fmtCode + ' (' + rem + 's)');
        totpSpan.title = '点击复制 2FA';
        totpSpan.onclick = (e) => {{
          e.stopPropagation();
          if (code) {{
            navigator.clipboard?.writeText(code).catch(() => {{}});
            setStatus('📋 已复制 2FA 验证码: ' + code);
          }}
        }};
        row.append(accSpan, totpSpan);

        // Status
        const statusEl = mkEl('div', 'kv-status', statusText);

        // Buttons
        const btns = mkEl('div', 'kv-btns');
        const runNowBtn = mkEl('button', 'kv-btn primary', '⚡ 自动登录');
        runNowBtn.onclick = (e) => {{
          e.stopPropagation();
          runAutoLoginTick(true);
        }};
        const fillUserBtn = mkEl('button', 'kv-btn', '填账号');
        fillUserBtn.onclick = (e) => {{
          e.stopPropagation();
          fillIntoFocusedOrTarget(AUTH.account, '账号', [
            'input#identifierId', 'input[name="identifier"]', 'input[name="email"]',
            'input#email-input', 'input[name="username"]', 'input[type="email"]'
          ]);
        }};
        const fillPwdBtn = mkEl('button', 'kv-btn', '填密码');
        fillPwdBtn.onclick = (e) => {{
          e.stopPropagation();
          fillIntoFocusedOrTarget(AUTH.password, '密码', [
            'input[type="password"][name="Passwd"]', 'input[type="password"][name="password"]', 'input[type="password"]'
          ]);
        }};
        const fill2faBtn = mkEl('button', 'kv-btn', '填2FA');
        fill2faBtn.onclick = (e) => {{
          e.stopPropagation();
          const c = computeTotp(secret, Date.now());
          if (!fillOtpCodeOnPage(c)) {{
            fillIntoFocusedOrTarget(c, '2FA 验证码', ['input[type="tel"]', 'input[type="text"]']);
          }} else {{
            setStatus('✅ 已填入 2FA 验证码: ' + c);
          }}
        }};
        btns.append(runNowBtn, fillUserBtn, fillPwdBtn, fill2faBtn);

        if (AUTH.initialSecretKey && AUTH.initialSecretKey !== AUTH.secretKey) {{
          const fillInit2faBtn = mkEl('button', 'kv-btn', '填原2FA');
          fillInit2faBtn.onclick = (e) => {{
            e.stopPropagation();
            const c = computeTotp(AUTH.initialSecretKey, Date.now());
            if (!fillOtpCodeOnPage(c)) {{
              fillIntoFocusedOrTarget(c, '初始 2FA 验证码', ['input[type="tel"]', 'input[type="text"]']);
            }} else {{
              setStatus('✅ 已填入初始 2FA 验证码: ' + c);
            }}
          }};
          btns.appendChild(fillInit2faBtn);
        }}

        if (AUTH.recoveryEmail) {{
          const fillRecBtn = mkEl('button', 'kv-btn', '填辅助邮箱');
          fillRecBtn.onclick = (e) => {{
            e.stopPropagation();
            fillIntoFocusedOrTarget(AUTH.recoveryEmail, '辅助邮箱', [
              'input#knowledge-preregistered-email-response', 'input[name="knowledgePreregisteredEmailResponse"]', 'input[type="email"]'
            ]);
          }};
          btns.appendChild(fillRecBtn);
        }}

        container.replaceChildren(head, row, statusEl, btns);
      }} catch (_) {{}}
    }}

    statusUiUpdater = render;
    render();
    setInterval(render, 1000);
  }}

  function init() {{
    window.__kv_ensure_mounted = () => {{
      try {{ mountCapsule(); }} catch (_) {{}}
      try {{ runAutoLoginTick(false); }} catch (_) {{}}
    }};
    window.__kv_ensure_mounted();
    setInterval(window.__kv_ensure_mounted, 900);
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', init);
  }} else {{
    init();
  }}
}})();
"""


def _build_extension_files(ext_dir: Path, fp: dict, account_or_label: dict | str) -> None:
    ext_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(account_or_label, dict):
        account_dict = account_or_label
        account_label = account_dict.get("masked_account") or account_dict.get("account", "")
    else:
        account_dict = {"account": str(account_or_label), "masked_account": str(account_or_label)}
        account_label = str(account_or_label)

    manifest = {
        "manifest_version": 3,
        "name": f"KeyVault Fingerprint & AutoLogin ({fp.get('profile_code', 'FP')})",
        "version": "1.1.0",
        "description": f"Isolated hardware fingerprint & auto-login paired to {account_label}",
        "content_scripts": [
            {
                "matches": ["<all_urls>"],
                "js": ["inject.js"],
                "run_at": "document_start",
                "world": "MAIN",
                "all_frames": True,
            },
            {
                "matches": [
                    "https://chatgpt.com/*",
                    "https://*.openai.com/*",
                    "https://accounts.google.com/*",
                    "https://myaccount.google.com/*",
                ],
                "js": ["autologin.js"],
                "run_at": "document_idle",
                "all_frames": False,
            },
        ],
    }
    (ext_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cfg_json = json.dumps(
        {
            "profileCode": fp.get("profile_code", "FP-000"),
            "vendor": fp.get("webgl_vendor", "Google Inc. (NVIDIA)"),
            "renderer": fp.get("webgl_renderer", "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            "cpu": int(fp.get("cpu_cores", 12)),
            "memory": int(fp.get("memory_gb", 16)),
            "screenW": int(fp.get("screen_width", 1920)),
            "screenH": int(fp.get("screen_height", 1080)),
            "canvasSeed": int(fp.get("canvas_seed", 123456)),
            "audioSeed": int(fp.get("audio_seed", 654321)),
        },
        ensure_ascii=False,
    )

    inject_js = f"""(() => {{
  const CFG = {cfg_json};
  try {{
    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => CFG.cpu, configurable: true }});
    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => CFG.memory, configurable: true }});
    Object.defineProperty(navigator, 'webdriver', {{ get: () => false, configurable: true }});

    if (window.screen) {{
      Object.defineProperty(window.screen, 'width', {{ get: () => CFG.screenW, configurable: true }});
      Object.defineProperty(window.screen, 'height', {{ get: () => CFG.screenH, configurable: true }});
      Object.defineProperty(window.screen, 'availWidth', {{ get: () => CFG.screenW, configurable: true }});
      Object.defineProperty(window.screen, 'availHeight', {{ get: () => CFG.screenH - 40, configurable: true }});
    }}

    const patchWebGL = (proto) => {{
      if (!proto || !proto.getParameter) return;
      const origGetParameter = proto.getParameter;
      proto.getParameter = function(param) {{
        if (param === 37445) return CFG.vendor;
        if (param === 37446) return CFG.renderer;
        return origGetParameter.apply(this, arguments);
      }};
    }};
    if (window.WebGLRenderingContext) patchWebGL(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) patchWebGL(WebGL2RenderingContext.prototype);

    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function(x, y, w, h) {{
      const imgData = origGetImageData.apply(this, arguments);
      if (imgData && imgData.data && imgData.data.length >= 16) {{
        const delta = (CFG.canvasSeed % 3) + 1;
        const idx = (CFG.canvasSeed % 12);
        imgData.data[idx] = (imgData.data[idx] + delta) & 255;
      }}
      return imgData;
    }};

    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function() {{
      try {{
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0) {{
          const px = origGetImageData.call(ctx, 0, 0, 1, 1);
          px.data[0] = (px.data[0] ^ (CFG.canvasSeed & 3)) & 255;
          ctx.putImageData(px, 0, 0);
        }}
      }} catch (_) {{}}
      return origToDataURL.apply(this, arguments);
    }};

    if (window.AudioBuffer && AudioBuffer.prototype.getChannelData) {{
      const origGetChannelData = AudioBuffer.prototype.getChannelData;
      AudioBuffer.prototype.getChannelData = function() {{
        const data = origGetChannelData.apply(this, arguments);
        if (data && data.length > 10) {{
          const offset = ((CFG.audioSeed % 97) + 1) * 1e-7;
          data[0] = data[0] + offset;
        }}
        return data;
      }};
    }}
  }} catch (_) {{}}
}})();
"""
    (ext_dir / "inject.js").write_text(inject_js, encoding="utf-8")
    (ext_dir / "autologin.js").write_text(_build_autologin_js(fp, account_dict), encoding="utf-8")


def prepare_profile_dir(data_dir: str | Path, account: dict) -> Path:
    base_data = Path(data_dir)
    acc_id = int(account["id"])
    profile_dir = base_data / "browsers" / f"acc_{acc_id}"
    ext_dir = profile_dir / "fp_ext"
    profile_dir.mkdir(parents=True, exist_ok=True)

    fp = account.get("fp_config") or generate_fingerprint_config(acc_id, account.get("account", ""))
    _build_extension_files(ext_dir, fp, account)
    return profile_dir


def find_chromium_executable() -> str | None:
    import shutil
    import sys

    env_override = os.environ.get("KEYVAULT_BROWSER_PATH", "").strip()
    if env_override and os.path.exists(env_override):
        return env_override

    candidates: list[str] = []
    if sys.platform == "win32":
        candidates.extend(
            [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chrome.exe"),
            ]
        )
    elif sys.platform == "darwin":
        candidates.extend(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )

    for path in candidates:
        if path and os.path.exists(path):
            return path

    for bin_name in (
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "msedge",
        "microsoft-edge",
        "brave-browser",
        "chromium",
        "chromium-browser",
    ):
        found = shutil.which(bin_name)
        if found:
            return found

    return None


def get_target_url(account_type: str) -> str:
    if (account_type or "").lower() == "google":
        return "https://accounts.google.com/"
    return "https://chatgpt.com/"


def get_debug_port(account_id: int) -> int:
    import socket

    base_port = 29000 + (int(account_id) % 5000)
    # Check if base_port is free or already our Chrome CDP port
    try:
        with socket.create_connection(("127.0.0.1", base_port), timeout=0.15):
            # Port is listening; check if it's already a Chromium DevTools endpoint
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{base_port}/json/version", timeout=0.3) as resp:
                    if resp.status == 200:
                        return base_port
            except Exception:
                pass
            # Occupied by a non-CDP process: find a free ephemeral port
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                return int(s.getsockname()[1])
    except OSError:
        return base_port


def build_browser_launch_args(account: dict, profile_dir: str | Path, exe_path: str | None = None) -> list[str]:
    exe = exe_path or find_chromium_executable() or "chrome.exe"
    p_dir = Path(profile_dir).resolve()
    ext_dir = (p_dir / "fp_ext").resolve()
    acc_id = int(account.get("id") or 1)
    debug_port = get_debug_port(acc_id)

    fp = account.get("fp_config") or generate_fingerprint_config(acc_id, account.get("account", ""))
    proxy = (fp.get("proxy") or "").strip()
    target_url = get_target_url(account.get("account_type", "ChatGPT"))

    args = [
        exe,
        f"--user-data-dir={p_dir}",
        f"--load-extension={ext_dir}",
        f"--remote-debugging-port={debug_port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-save-password-bubble",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-blink-features=AutomationControlled",
        "--disk-cache-size=52428800",
        "--media-cache-size=20971520",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-features=WebRtcHideLocalIpsWithMdns,OptimizationHints,Translate,DisableLoadExtensionCommandLineSwitch",
    ]
    if proxy:
        args.append(f"--proxy-server={proxy}")
    args.append(target_url)
    return args


async def _attach_cdp_page_target(ws_url: str, inject_js: str, autologin_js: str) -> None:
    try:
        async with websockets.connect(ws_url, max_size=None, open_timeout=5) as ws:
            msg_id = 1
            # Never call Runtime.enable so Cloudflare Turnstile & Google BotGuard cannot detect V8 inspector attachment
            for payload in (
                {"id": msg_id, "method": "Page.enable"},
                {"id": msg_id + 1, "method": "Page.addScriptToEvaluateOnNewDocument", "params": {"source": inject_js}},
                {"id": msg_id + 2, "method": "Page.addScriptToEvaluateOnNewDocument", "params": {"source": autologin_js}},
                {"id": msg_id + 3, "method": "Runtime.evaluate", "params": {"expression": inject_js}},
                {"id": msg_id + 4, "method": "Runtime.evaluate", "params": {"expression": autologin_js}},
            ):
                await ws.send(json.dumps(payload))
            msg_id += 10

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.2)
                    evt = json.loads(raw)
                    method = evt.get("method", "")
                    if method in (
                        "Page.domContentLoaded",
                        "Page.loadEventFired",
                        "Page.frameNavigated",
                    ):
                        msg_id += 1
                        await ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": inject_js}}))
                        msg_id += 1
                        await ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": autologin_js}}))
                except asyncio.TimeoutError:
                    msg_id += 1
                    await ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": autologin_js}}))
    except Exception:
        pass


async def _cdp_port_monitor(debug_port: int, inject_js: str, autologin_js: str, max_Wait_sec: float = 20.0) -> None:
    url = f"http://127.0.0.1:{debug_port}/json"
    attached_tasks: dict[str, asyncio.Task] = {}
    start_ts = time.time()
    connected_once = False
    consecutive_failures = 0

    while True:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                targets = json.loads(resp.read().decode("utf-8", errors="ignore"))
            connected_once = True
            consecutive_failures = 0

            for t in targets:
                if t.get("type") != "page":
                    continue
                t_url = t.get("url") or ""
                if t_url.startswith(("devtools://", "chrome-extension://", "chrome://", "edge://")):
                    continue
                tid = t.get("id")
                ws_url = t.get("webSocketDebuggerUrl")
                if tid and ws_url:
                    existing = attached_tasks.get(tid)
                    if existing is None or existing.done():
                        attached_tasks[tid] = asyncio.create_task(
                            _attach_cdp_page_target(ws_url, inject_js, autologin_js)
                        )
            await asyncio.sleep(0.8)
        except Exception:
            consecutive_failures += 1
            if not connected_once:
                if time.time() - start_ts > max_Wait_sec:
                    break
                await asyncio.sleep(0.25)
            else:
                if consecutive_failures >= 4:
                    break
                await asyncio.sleep(0.8)

    for task in attached_tasks.values():
        if not task.done():
            task.cancel()


def _start_cdp_injector(debug_port: int, profile_dir: Path) -> None:
    ext_dir = Path(profile_dir) / "fp_ext"
    inject_path = ext_dir / "inject.js"
    autologin_path = ext_dir / "autologin.js"
    if not inject_path.exists() or not autologin_path.exists():
        return
    inject_js = inject_path.read_text(encoding="utf-8")
    autologin_js = autologin_path.read_text(encoding="utf-8")

    def _runner():
        try:
            asyncio.run(_cdp_port_monitor(debug_port, inject_js, autologin_js))
        except Exception:
            pass

    t = threading.Thread(target=_runner, name=f"kv-cdp-{debug_port}", daemon=True)
    t.start()


def launch_isolated_browser(data_dir: str | Path, account: dict) -> dict:
    exe = find_chromium_executable()
    if not exe:
        return {"ok": False, "error": "未检测到 Chrome 或 Edge 浏览器"}

    fp = account.get("fp_config") or {}
    proxy_url = (fp.get("proxy") or "").strip()
    proxy_node = (fp.get("proxy_node") or "").strip()

    node_switch_res = {"ok": True, "switched": False}
    if proxy_node:
        node_switch_res = activate_proxy_node(
            account.get("account_type", "ChatGPT"),
            proxy_url,
            proxy_node,
        )

    profile_dir = prepare_profile_dir(data_dir, account)
    args = build_browser_launch_args(account, profile_dir, exe_path=exe)
    debug_port = get_debug_port(int(account.get("id") or 1))

    try:
        subprocess.Popen(
            args,
            cwd=str(profile_dir),
            close_fds=True,
        )
        _start_cdp_injector(debug_port, profile_dir)
        return {
            "ok": True,
            "profile_dir": str(profile_dir),
            "fp_config": fp,
            "node_switched": node_switch_res.get("switched", False),
            "engine": "Chrome" if "chrome" in exe.lower() else "Edge",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
