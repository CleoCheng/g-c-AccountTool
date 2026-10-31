// State Management
const state = {
  accounts: [],
  stats: { total: 0, google: 0, chatgpt: 0, other: 0, active: 0, deactivated: 0, health: {} },
  filterType: "All",
  statusFilter: "All",
  healthFilter: "All",
  searchQuery: "",
  theme: "dark",
  viewMode: "compact", // 'compact' | 'full' | 'table'
  expandedCards: {}, // id -> boolean
  revealedFields: {}, // `${id}_${field}` -> boolean
  lastTotpSlot: Math.floor(Date.now() / 30000),
  parsedBatchRecords: [],
  // Proxy Node Selector & Lock State
  proxyEnv: null,
  nodeModalAccountId: null,
  selectedRegion: "全部",
  selectedProxyUrl: "http://127.0.0.1:17898",
  selectedNodeName: "",
};

async function callApi(method, ...args) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api[method]) {
    return await window.pywebview.api[method](...args);
  }
  throw new Error("pywebview API not ready");
}

function initApp() {
  loadDashboard();
  startZeroOverheadTotpTicker();
}

window.addEventListener("pywebviewready", () => {
  initApp();
});

document.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    if (window.pywebview && window.pywebview.api) {
      initApp();
    }
  }, 120);
});

async function loadDashboard() {
  try {
    const data = await callApi("get_dashboard", state.filterType, state.searchQuery, state.statusFilter, state.healthFilter);
    state.accounts = data.accounts || [];
    state.stats = data.stats || { total: 0, google: 0, chatgpt: 0, other: 0, active: 0, deactivated: 0, available: 0, unavailable: 0, health: {} };
    if (data.settings) {
      applyTheme(data.settings.theme || "dark", false);
      const savedMode = data.settings.view_mode === "grid" ? "compact" : data.settings.view_mode || "compact";
      applyViewMode(savedMode, false);
    }
    renderStats();
    syncTopBarPills();
    renderAccounts();
  } catch (err) {
    console.error("Load dashboard failed:", err);
  }
}

function renderStats() {
  const setEl = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val !== undefined && val !== null ? val : 0;
  };
  setEl("stat-total", state.stats.total);
  setEl("stat-google", state.stats.google);
  setEl("stat-chatgpt", state.stats.chatgpt);
  const h = state.stats.health || {};
  const avail = state.stats.available !== undefined ? state.stats.available : (h["可用"] || 0);
  const unavail = state.stats.unavailable !== undefined ? state.stats.unavailable : (h["不可用"] || 0);
  setEl("stat-health-available", avail);
  setEl("stat-health-unavailable", unavail);
}

function syncTopBarPills() {
  const isTotal = (state.filterType === "All" || !state.filterType) && (state.healthFilter === "All" || !state.healthFilter);
  const pillTotal = document.getElementById("stat-pill-total");
  const pillGpt = document.getElementById("stat-pill-chatgpt");
  const pillGgl = document.getElementById("stat-pill-google");
  const pillAvail = document.getElementById("stat-pill-available");
  const pillUnavail = document.getElementById("stat-pill-unavailable");

  if (pillTotal) pillTotal.classList.toggle("active", isTotal);
  if (pillGpt) pillGpt.classList.toggle("active", state.filterType === "ChatGPT");
  if (pillGgl) pillGgl.classList.toggle("active", state.filterType === "Google");
  if (pillAvail) pillAvail.classList.toggle("active", state.healthFilter === "可用");
  if (pillUnavail) pillUnavail.classList.toggle("active", state.healthFilter === "不可用");
}

function onHealthSelectChange(val) {
  setHealthFilter(val);
}

function setHealthFilter(health) {
  state.healthFilter = health || "All";
  const sel = document.getElementById("health-filter-select");
  if (sel && sel.value !== state.healthFilter) {
    sel.value = state.healthFilter;
  }
  syncTopBarPills();
  loadDashboard();
}

function getHealthMeta(status) {
  switch (status) {
    case "封号":
      return { key: "banned", label: "封号", dotClass: "dot-banned" };
    case "人机":
      return { key: "captcha", label: "人机", dotClass: "dot-captcha" };
    case "短信":
      return { key: "sms", label: "短信", dotClass: "dot-sms" };
    case "验证":
      return { key: "verify", label: "验证", dotClass: "dot-verify" };
    case "不可用":
      return { key: "unavailable", label: "不可用", dotClass: "dot-unavailable" };
    case "可用":
    default:
      return { key: "available", label: "可用", dotClass: "dot-available" };
  }
}

function toggleHealthMenu(event, accountId) {
  event.stopPropagation();
  const menuEl = document.getElementById(`health-menu-${accountId}`);
  if (!menuEl) return;
  const isShown = menuEl.style.display === "block";
  closeAllHealthPopovers();
  if (!isShown) {
    menuEl.style.display = "block";
  }
}

function closeAllHealthPopovers() {
  document.querySelectorAll(".u-health-popover").forEach((el) => {
    el.style.display = "none";
  });
}

document.addEventListener("click", () => {
  closeAllHealthPopovers();
});

async function onQuickSelectHealth(accountId, nextStatus) {
  closeAllHealthPopovers();
  try {
    const res = await callApi("set_health_status", accountId, nextStatus);
    if (res && res.ok) {
      showToast(`✓ 已标记账号状态为「${nextStatus}」`);
      await loadDashboard();
    } else {
      showToast(res.error || "状态更新失败");
    }
  } catch (err) {
    showToast("状态更新异常: " + err.message);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatTotpCode(code) {
  if (!code || code.length !== 6) return "--- ---";
  return `${code.slice(0, 3)} ${code.slice(3)}`;
}

function isRevealed(id, field) {
  return !!state.revealedFields[`${id}_${field}`];
}

function toggleReveal(id, field) {
  const key = `${id}_${field}`;
  state.revealedFields[key] = !state.revealedFields[key];
  renderAccounts();
}

function toggleCardExpand(id) {
  state.expandedCards[id] = !state.expandedCards[id];
  renderAccounts();
}

function getUnifiedMetaSummary(item) {
  const parts = [];
  if (item.purchase_date) {
    if (item.deactivated_date) {
      parts.push(`${item.purchase_date} ~ ${item.deactivated_date}`);
    } else {
      parts.push(`购入 ${item.purchase_date}`);
    }
  }
  if (item.reg_year || item.reg_region) {
    const yr = [item.reg_year, item.reg_region].filter(Boolean).join(" · ");
    parts.push(yr);
  }
  return parts.length ? parts.join(" | ") : "标准账号";
}

function getFpSummary(item) {
  const fp = item.fp_config || {};
  const code = fp.profile_code || `FP-${String(item.id).padStart(3, "0")}`;
  const gpu = fp.gpu_short || "RTX 4070";
  const cpu = fp.cpu_cores || 12;
  const mem = fp.memory_gb || 16;
  const scr = fp.screen || "1920x1080";
  const proxyNode = fp.proxy_node || "";
  const locked = !!fp.node_locked;
  const proxyPort = fp.proxy ? fp.proxy.replace("http://127.0.0.1:", ":") : "";
  return {
    code,
    proxyNode,
    locked,
    proxyPort,
    shortDesc: `${gpu} · ${cpu}核/${mem}G · ${scr}`,
    tooltip: `专属配对指纹环境 [${code}]\nGPU: ${gpu}\nCPU/内存: ${cpu}核 / ${mem}GB\n分辨率: ${scr}\n绑定节点: ${proxyNode || "未绑定"} (${locked ? "已锁定" : "未锁定"})\n端口: ${fp.proxy || "默认"}\n数据隔离目录: data/browsers/acc_${item.id}`,
  };
}

function renderAccounts() {
  const container = document.getElementById("accounts-container");
  const emptyState = document.getElementById("empty-state");

  if (!state.accounts || state.accounts.length === 0) {
    container.innerHTML = "";
    emptyState.style.display = "block";
    return;
  }

  emptyState.style.display = "none";
  const remaining = 30 - (Math.floor(Date.now() / 1000) % 30);

  if (state.viewMode === "table") {
    container.className = "accounts-table-wrapper";
    container.innerHTML = renderTableView(remaining);
    return;
  }

  container.className = "accounts-grid";
  container.innerHTML = state.accounts
    .map((item) => renderCardItem(item, remaining))
    .join("");
}

function renderCardItem(item, remaining) {
  const showAcc = isRevealed(item.id, "account");
  const displayAcc = showAcc ? item.account : item.masked_account;

  const hasTotp = item.secret_key && item.totp && item.totp.valid;
  const totpFormatted = hasTotp ? formatTotpCode(item.totp.code) : "无 2FA";

  const usage = item.usage || { status: "active", status_label: "使用中", duration_text: "使用中" };
  const isDeactivated = usage.status === "deactivated";
  const statusText =
    usage.duration_text && usage.duration_text !== usage.status_label
      ? usage.duration_text
      : usage.status_label;

  const hMeta = getHealthMeta(item.health_status || "可用");

  const isPwdModified = !!item.password_modified;
  const pwdFlagHtml = `<button class="u-2fa-flag ${isPwdModified ? "modified" : "unmodified"}" onclick="toggleCardPasswordModified(${item.id}, ${isPwdModified ? 0 : 1})" title="点击切换密码是否已修改标记">
      ${isPwdModified ? "🔑 密码已改 ✓" : "🔑 初始密码"}
    </button>`;

  const is2faModified = !!item.twofa_modified;
  const twofaFlagHtml = item.secret_key
    ? `<button class="u-2fa-flag ${is2faModified ? "modified" : "unmodified"}" onclick="toggleCardTwofaModified(${item.id}, ${is2faModified ? 0 : 1})" title="点击切换 2FA 是否已修改标记">
        ${is2faModified ? "🛡️ 2FA已改 ✓" : "🛡️ 初始2FA"}
      </button>`
    : `<span class="u-2fa-flag none" title="未配置 2FA 动态秘钥">🛡️ 无2FA</span>`;

  const fpInfo = getFpSummary(item);
  const nodePillText = fpInfo.proxyNode
    ? `${fpInfo.locked ? "🔒" : "🔓"} ${fpInfo.proxyNode}${fpInfo.proxyPort ? ` (${fpInfo.proxyPort})` : ""}`
    : "🔓 绑定节点";

  const metaLeft = getUnifiedMetaSummary(item);
  const showDrawer = state.viewMode === "full" || !!state.expandedCards[item.id];

  // 1-Click Quick Health Status Dropdown
  const healthBadgeHtml = `
    <div class="u-health-dropdown" data-acc-id="${item.id}">
      <button class="u-health-btn health-${hMeta.key}" onclick="toggleHealthMenu(event, ${item.id})" title="点击快捷维护账号可用状态">
        <span class="badge-dot ${hMeta.dotClass}"></span>
        <span class="health-btn-label">${escapeHtml(hMeta.label)}</span>
        <span class="health-arrow">▾</span>
      </button>
      <div class="u-health-popover" id="health-menu-${item.id}" style="display: none;">
        <div class="popover-title">维护账号可用状态</div>
        <button class="health-opt ${hMeta.key === 'available' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '可用')">
          <span class="badge-dot dot-available"></span><span>可用 (正常使用)</span>
        </button>
        <button class="health-opt ${hMeta.key === 'banned' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '封号')">
          <span class="badge-dot dot-banned"></span><span>封号 (官方封禁)</span>
        </button>
        <button class="health-opt ${hMeta.key === 'captcha' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '人机')">
          <span class="badge-dot dot-captcha"></span><span>人机 (盾 / 验证码)</span>
        </button>
        <button class="health-opt ${hMeta.key === 'sms' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '短信')">
          <span class="badge-dot dot-sms"></span><span>短信 (手机验证)</span>
        </button>
        <button class="health-opt ${hMeta.key === 'verify' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '验证')">
          <span class="badge-dot dot-verify"></span><span>验证 (邮箱/密码)</span>
        </button>
        <button class="health-opt ${hMeta.key === 'unavailable' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '不可用')">
          <span class="badge-dot dot-unavailable"></span><span>不可用 (闲置停用)</span>
        </button>
      </div>
    </div>
  `;

  // Detail Drawer Content
  let drawerHtml = "";
  if (showDrawer) {
    const showPwd = isRevealed(item.id, "password");
    const showSec = isRevealed(item.id, "secret");
    const showInitSec = isRevealed(item.id, "init_secret");
    const showRec = isRevealed(item.id, "recovery");

    drawerHtml = `
      <div class="u-detail-drawer">
        <div class="detail-row">
          <span class="detail-key">可用状态</span>
          <span class="detail-val" style="display:inline-flex;align-items:center;gap:6px;">
            <span class="badge-dot ${hMeta.dotClass}"></span>
            <strong>${escapeHtml(hMeta.label)}</strong>
          </span>
          <div class="detail-ops">
            <button class="u-peek-btn" onclick="openEditModal(${item.id})">在表单维护</button>
          </div>
        </div>
        <div class="detail-row">
          <span class="detail-key">指纹环境</span>
          <span class="detail-val">[${escapeHtml(fpInfo.code)}] ${escapeHtml(fpInfo.shortDesc)}</span>
          <div class="detail-ops">
            <button class="u-peek-btn" onclick="openNodeModal(${item.id})">${fpInfo.locked ? "🔒 节点已锁" : "配置节点"}</button>
            <button class="u-peek-btn" onclick="regenerateAccountFp(${item.id})" title="重新生成该账号绑定的硬件指纹参数">换新指纹</button>
          </div>
        </div>
        <div class="detail-row">
          <span class="detail-key">完整账号</span>
          <span class="detail-val">${escapeHtml(item.account)}</span>
          <div class="detail-ops">
            <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'account', '账号邮箱')">复制</button>
          </div>
        </div>
        <div class="detail-row">
          <span class="detail-key">登录密码</span>
          <span class="detail-val">${escapeHtml(showPwd ? item.password : item.masked_password)}</span>
          <div class="detail-ops">
            <button class="u-peek-btn" onclick="toggleReveal(${item.id}, 'password')">${showPwd ? "隐藏" : "明文"}</button>
            <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'password', '登录密码')">复制</button>
          </div>
        </div>
        ${
          item.secret_key
            ? `
        <div class="detail-row">
          <span class="detail-key">${is2faModified ? "新2FA秘钥" : "2FA秘钥"}</span>
          <span class="detail-val">${escapeHtml(showSec ? item.secret_key : item.masked_secret)}</span>
          <div class="detail-ops">
            <button class="u-peek-btn" onclick="toggleReveal(${item.id}, 'secret')">${showSec ? "隐藏" : "明文"}</button>
            <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'secret_key', '2FA秘钥')">复制</button>
          </div>
        </div>`
            : ""
        }
        ${
          item.initial_secret_key
            ? `
        <div class="detail-row">
          <span class="detail-key">初始2FA</span>
          <span class="detail-val">${escapeHtml(showInitSec ? item.initial_secret_key : item.masked_initial_secret)}</span>
          <div class="detail-ops">
            <button class="u-peek-btn" onclick="toggleReveal(${item.id}, 'init_secret')">${showInitSec ? "隐藏" : "明文"}</button>
            <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'initial_secret_key', '初始2FA秘钥')">复制</button>
          </div>
        </div>`
            : ""
        }
        ${
          item.recovery_email
            ? `
        <div class="detail-row">
          <span class="detail-key">辅助邮箱</span>
          <span class="detail-val">${escapeHtml(showRec ? item.recovery_email : item.masked_recovery_email)}</span>
          <div class="detail-ops">
            <button class="u-peek-btn" onclick="toggleReveal(${item.id}, 'recovery')">${showRec ? "隐藏" : "明文"}</button>
            <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'recovery_email', '辅助邮箱')">复制</button>
          </div>
        </div>`
            : ""
        }
      </div>
    `;
  }

  // Device Chip (Prominent, dedicated flex chip that never gets crushed)
  const deviceChipHtml = item.note
    ? `<span class="u-device-chip" title="所在设备/备注: ${escapeHtml(item.note)}">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
          <line x1="8" y1="21" x2="16" y2="21"></line>
          <line x1="12" y1="17" x2="12" y2="21"></line>
        </svg>
        <span class="device-text">${escapeHtml(item.note)}</span>
      </span>`
    : "";

  return `
    <article class="u-card health-border-${hMeta.key} ${isDeactivated ? "is-deactivated" : ""}" data-id="${item.id}">
      <!-- Line 1: Header (Account Identity & 1-Click Health Status Badge) -->
      <div class="u-row-top">
        <div class="u-identity">
          <span class="u-platform ${escapeHtml(item.account_type)}">${escapeHtml(item.account_type)}</span>
          <span class="u-fp-badge" title="${escapeHtml(fpInfo.tooltip)}">${escapeHtml(fpInfo.code)}</span>
          <span class="u-email" onclick="copyFieldValue(null, ${item.id}, 'account', '账号邮箱')" title="点击直接复制账号: ${escapeHtml(displayAcc)}">
            ${escapeHtml(displayAcc)}
          </span>
          <button class="u-peek-btn" onclick="toggleReveal(${item.id}, 'account')" title="切换显示完整邮箱">
            ${showAcc ? "隐" : "明"}
          </button>
        </div>

        <div class="u-top-right">
          ${healthBadgeHtml}
        </div>
      </div>

      <!-- Line 2: Security Flags Row (初始密码是否改、2FA是否改独立换行展示) -->
      <div class="u-sec-row">
        <div class="u-sec-left">
          <span class="u-sec-label">安全状态:</span>
          ${pwdFlagHtml}
          ${twofaFlagHtml}
        </div>
        <div class="u-sec-right">
          <span class="u-sec-hint" title="可点击对应徽章快速切换已改/初始标记">点击徽章可标记</span>
        </div>
      </div>

      <!-- Line 3: Usage Timeline & Proxy Node Row (时长与绑定节点独立行) -->
      <div class="u-status-row">
        <div class="u-status-left">
          <span class="u-usage-badge ${usage.status}">
            <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            ${escapeHtml(statusText)}
          </span>
        </div>
        <div class="u-status-right">
          <button class="u-node-pill ${fpInfo.locked ? "locked" : ""}" onclick="openNodeModal(${item.id})" title="专属代理节点">
            ${escapeHtml(nodePillText)}
          </button>
        </div>
      </div>

      <!-- Line 3: Unified TOTP + 1-Click Copy + Fingerprint Browser Launch Strip -->
      <div class="u-action-bar">
        <div class="u-totp-box" onclick="copyTotpCode(null, ${item.id})" title="点击复制 6 位 2FA 动态验证码">
          <span class="u-totp-label">2FA码</span>
          <span class="u-totp-code" id="totp-code-${item.id}">${totpFormatted}</span>
          ${hasTotp ? `<span class="u-totp-sec">(<span class="card-rem-sec">${remaining}</span>s)</span>` : ""}
        </div>

        <div class="u-copy-group">
          <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'account', '账号')">账号</button>
          <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'password', '密码')">密码</button>
          ${
            item.secret_key
              ? `<button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'secret_key', '2FA秘钥')">2FA</button>`
              : ""
          }
          <button class="btn-browser" onclick="onClickLaunchBrowser(${item.id}, this)" title="${escapeHtml(fpInfo.tooltip)}">
            🌐 启动浏览器
          </button>
        </div>
      </div>

      ${drawerHtml}

      <!-- Line 4: Dedicated Footer (Device Code / Note & Meta Info + Tools) -->
      <div class="u-footer">
        <div class="u-meta-left">
          ${deviceChipHtml}
          ${metaLeft ? `<span class="u-meta-item">${escapeHtml(metaLeft)}</span>` : ""}
        </div>

        <div class="u-card-tools">
          ${
            state.viewMode === "compact"
              ? `<button class="tool-link" onclick="toggleCardExpand(${item.id})">${showDrawer ? "收起 ▴" : "详情 ▾"}</button>`
              : ""
          }
          <button class="tool-link" onclick="copyFullFormattedLine(${item.id})" title="按 ---- 格式复制整行">整串</button>
          <button class="tool-link" onclick="openEditModal(${item.id})">编辑</button>
          <button class="tool-link danger" onclick="confirmDeleteAccount(${item.id})">删除</button>
        </div>
      </div>
    </article>
  `;
}

function renderTableView(remaining) {
  const rows = state.accounts
    .map((item, idx) => {
      const showAcc = isRevealed(item.id, "account");
      const displayAcc = showAcc ? item.account : item.masked_account;
      const hasTotp = item.secret_key && item.totp && item.totp.valid;
      const totpFormatted = hasTotp ? formatTotpCode(item.totp.code) : "-";
      const usage = item.usage || { status: "active", status_label: "使用中", duration_text: "使用中" };
      const hMeta = getHealthMeta(item.health_status || "可用");
      const isPwdModified = !!item.password_modified;
      const is2faModified = !!item.twofa_modified;
      const metaLeft = getUnifiedMetaSummary(item);
      const fpInfo = getFpSummary(item);
      const nodePillText = fpInfo.proxyNode
        ? `${fpInfo.locked ? "🔒" : "🔓"} ${fpInfo.proxyNode}`
        : "🔓 绑定节点";

      const healthBadgeHtml = `
        <div class="u-health-dropdown" data-acc-id="${item.id}">
          <button class="u-health-btn health-${hMeta.key}" onclick="toggleHealthMenu(event, ${item.id})" title="点击快捷维护账号可用状态">
            <span class="badge-dot ${hMeta.dotClass}"></span>
            <span class="health-btn-label">${escapeHtml(hMeta.label)}</span>
            <span class="health-arrow">▾</span>
          </button>
          <div class="u-health-popover" id="health-menu-${item.id}" style="display: none;">
            <div class="popover-title">维护可用状态</div>
            <button class="health-opt ${hMeta.key === 'available' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '可用')">
              <span class="badge-dot dot-available"></span><span>可用</span>
            </button>
            <button class="health-opt ${hMeta.key === 'banned' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '封号')">
              <span class="badge-dot dot-banned"></span><span>封号</span>
            </button>
            <button class="health-opt ${hMeta.key === 'captcha' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '人机')">
              <span class="badge-dot dot-captcha"></span><span>人机</span>
            </button>
            <button class="health-opt ${hMeta.key === 'sms' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '短信')">
              <span class="badge-dot dot-sms"></span><span>短信</span>
            </button>
            <button class="health-opt ${hMeta.key === 'verify' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '验证')">
              <span class="badge-dot dot-verify"></span><span>验证</span>
            </button>
            <button class="health-opt ${hMeta.key === 'unavailable' ? 'active' : ''}" onclick="onQuickSelectHealth(${item.id}, '不可用')">
              <span class="badge-dot dot-unavailable"></span><span>不可用</span>
            </button>
          </div>
        </div>
      `;

      const deviceChipHtml = item.note
        ? `<span class="u-device-chip" title="所在设备/备注: ${escapeHtml(item.note)}">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
              <line x1="8" y1="21" x2="16" y2="21"></line>
              <line x1="12" y1="17" x2="12" y2="21"></line>
            </svg>
            <span class="device-text">${escapeHtml(item.note)}</span>
          </span>`
        : `<span style="color:var(--text-muted);">-</span>`;

      return `
        <tr>
          <td style="color: var(--text-muted);">${idx + 1}</td>
          <td><span class="u-platform ${escapeHtml(item.account_type)}">${escapeHtml(item.account_type)}</span></td>
          <td>
            <span class="u-fp-badge" title="${escapeHtml(fpInfo.tooltip)}">${escapeHtml(fpInfo.code)}</span>
            <button class="u-node-pill ${fpInfo.locked ? "locked" : ""}" onclick="openNodeModal(${item.id})" style="margin-left:4px;">
              ${escapeHtml(nodePillText)}
            </button>
          </td>
          <td>
            <span class="u-email" onclick="copyFieldValue(null, ${item.id}, 'account', '账号')">${escapeHtml(displayAcc)}</span>
            <button class="u-peek-btn" onclick="toggleReveal(${item.id}, 'account')">${showAcc ? "隐" : "明"}</button>
          </td>
          <td>
            ${healthBadgeHtml}
          </td>
          <td>
            <div style="display:flex;flex-direction:column;gap:3px;align-items:flex-start;">
              <button class="u-2fa-flag ${isPwdModified ? "modified" : "unmodified"}" onclick="toggleCardPasswordModified(${item.id}, ${isPwdModified ? 0 : 1})" title="点击切换密码是否已修改标记">
                ${isPwdModified ? "🔑 密码已改 ✓" : "🔑 初始密码"}
              </button>
              ${
                item.secret_key
                  ? `<button class="u-2fa-flag ${is2faModified ? "modified" : "unmodified"}" onclick="toggleCardTwofaModified(${item.id}, ${is2faModified ? 0 : 1})" title="点击切换 2FA 是否已修改标记">
                      ${is2faModified ? "🛡️ 2FA已改 ✓" : "🛡️ 初始2FA"}
                    </button>`
                  : `<span class="u-2fa-flag none">🛡️ 无2FA</span>`
              }
            </div>
          </td>
          <td>
            <span class="u-usage-badge ${usage.status}">${escapeHtml(usage.duration_text)}</span>
          </td>
          <td>
            <span class="u-totp-code" id="totp-code-${item.id}" style="font-size:14px;cursor:pointer;" onclick="copyTotpCode(null, ${item.id})">${totpFormatted}</span>
            ${hasTotp ? `<span class="u-totp-sec">(<span class="card-rem-sec">${remaining}</span>s)</span>` : ""}
          </td>
          <td>${deviceChipHtml}</td>
          <td>
            <div class="u-copy-group">
              <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'account', '账号')">账号</button>
              <button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'password', '密码')">密码</button>
              ${item.secret_key ? `<button class="copy-btn" onclick="copyFieldValue(this, ${item.id}, 'secret_key', '2FA秘钥')">2FA</button>` : ""}
              <button class="btn-browser" onclick="onClickLaunchBrowser(${item.id}, this)">🌐 启动浏览器</button>
            </div>
          </td>
          <td>
            <div class="u-card-tools">
              <button class="tool-link" onclick="openEditModal(${item.id})">编辑</button>
              <button class="tool-link danger" onclick="confirmDeleteAccount(${item.id})">删除</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  return `
    <table class="u-table">
      <thead>
        <tr>
          <th>#</th>
          <th>平台</th>
          <th>指纹与锁定节点</th>
          <th>账号邮箱</th>
          <th>可用状态</th>
          <th>安全修改状态</th>
          <th>使用时长</th>
          <th>动态验证码</th>
          <th>所在设备 / 备注</th>
          <th>快捷操作与防关联浏览器</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ============================================================
// PROXY NODE SELECTOR & NODE LOCK MODAL
// ============================================================
async function onClickLaunchBrowser(accountId, btnEl = null) {
  const item = state.accounts.find((a) => a.id === accountId);
  if (!item) return;
  const fp = item.fp_config || {};
  // If account hasn't locked/bound a node yet, open the Node Selector & Lock modal first!
  if (!fp.proxy_node && !fp.node_locked) {
    await openNodeModal(accountId);
    return;
  }
  await executeLaunchBrowser(accountId, btnEl);
}

async function executeLaunchBrowser(accountId, btnEl = null) {
  const origHtml = btnEl ? btnEl.innerHTML : "";
  if (btnEl) {
    btnEl.classList.add("loading");
    btnEl.disabled = true;
    btnEl.innerHTML = "<span>🚀 正在启动...</span>";
  }
  showToast("🚀 正在配置独立指纹环境并启动浏览器...", 2800);

  try {
    const res = await callApi("launch_browser", accountId);
    if (res && res.ok) {
      const fp = res.fp_config || {};
      const nodeStr = fp.proxy_node ? ` · 节点:${fp.proxy_node}` : "";
      showToast(`🌐 已启动 [${fp.profile_code || "FP"}] (${fp.gpu_short || "GPU"}${nodeStr}) · 自动登录助手已就绪`);
    } else {
      showToast(res.error || "启动指纹浏览器失败");
    }
  } catch (err) {
    showToast("启动浏览器异常: " + err.message);
  } finally {
    if (btnEl) {
      btnEl.classList.remove("loading");
      btnEl.disabled = false;
      btnEl.innerHTML = origHtml;
    }
  }
}

async function openNodeModal(accountId) {
  const item = state.accounts.find((a) => a.id === accountId);
  if (!item) return;
  state.nodeModalAccountId = accountId;

  const fp = item.fp_config || {};
  document.getElementById("node-modal-title").textContent = `节点锁定配置 · [${fp.profile_code || "FP"}] ${item.masked_account}`;
  document.getElementById("node-modal").style.display = "flex";

  // Loading state
  const loadingEl = document.getElementById("node-modal-loading");
  const contentEl = document.getElementById("node-modal-main-content");
  const subEl = document.getElementById("node-modal-sub");
  const btnSaveOnly = document.getElementById("btn-save-node-only");
  const btnSaveLaunch = document.getElementById("btn-save-and-launch");

  if (loadingEl) loadingEl.style.display = "flex";
  if (contentEl) contentEl.style.display = "none";
  if (btnSaveOnly) btnSaveOnly.disabled = true;
  if (btnSaveLaunch) btnSaveLaunch.disabled = true;
  subEl.textContent = "正在实时探测本机代理端口与节点列表，请稍候...";

  try {
    state.proxyEnv = await callApi("get_proxy_nodes", item.account_type);
  } catch (e) {
    state.proxyEnv = { client_name: "未检测到代理", controller_online: false, ports: [], nodes: [] };
  }

  if (loadingEl) loadingEl.style.display = "none";
  if (contentEl) contentEl.style.display = "block";
  if (btnSaveOnly) btnSaveOnly.disabled = false;
  if (btnSaveLaunch) btnSaveLaunch.disabled = false;

  const env = state.proxyEnv;
  const activeHint = env.active_node ? ` · 本机当前在用:【${env.active_node}】` : "";
  subEl.textContent = `已探测本机代理环境：${env.client_name} (${env.controller_online ? "🟢 控制接口在线" : "⚪ 端口/配置模式"}) · 共发现 ${(env.nodes || []).length} 个可用节点${activeHint}`;

  // Populate Ports Dropdown
  const portSelect = document.getElementById("node-port-select");
  const customInput = document.getElementById("node-custom-proxy");
  const ports = env.ports && env.ports.length
    ? env.ports
    : [{ url: "http://127.0.0.1:7890", label: "127.0.0.1:7890 (通用默认代理端口)" }];

  state.selectedProxyUrl = fp.proxy ? fp.proxy : ports[0].url;

  // Auto select active node by default if not locked
  if (fp.node_locked && fp.proxy_node) {
    state.selectedNodeName = fp.proxy_node;
  } else if (fp.proxy_node) {
    state.selectedNodeName = fp.proxy_node;
  } else if (env.active_node) {
    state.selectedNodeName = env.active_node;
  } else {
    state.selectedNodeName = "";
  }

  // Auto switch tab to the active node's region if present
  if (state.selectedNodeName) {
    const matchedNode = (env.nodes || []).find((n) => n.name === state.selectedNodeName);
    if (matchedNode && matchedNode.region) {
      state.selectedRegion = matchedNode.region;
    } else {
      state.selectedRegion = "全部";
    }
  } else {
    state.selectedRegion = "全部";
  }

  const portOptionsHtml = ports
    .map(
      (p) =>
        `<option value="${escapeHtml(p.url)}" ${p.url === state.selectedProxyUrl ? "selected" : ""}>${escapeHtml(p.label)}</option>`
    )
    .join("");
  portSelect.innerHTML = portOptionsHtml + `<option value="__custom__" ${!ports.some((p) => p.url === state.selectedProxyUrl) ? "selected" : ""}>自定义代理地址 / 直连...</option>`;
  if (customInput) {
    customInput.value = state.selectedProxyUrl;
  }

  portSelect.onchange = (e) => {
    if (e.target.value !== "__custom__") {
      state.selectedProxyUrl = e.target.value;
      if (customInput) customInput.value = state.selectedProxyUrl;
    } else if (customInput) {
      customInput.focus();
    }
  };

  renderNodeModalLockState(item);
  renderNodeRegionTabs();
  renderNodeGrid(!!fp.node_locked);

  setTimeout(() => {
    const selEl = document.querySelector(".node-item.selected");
    if (selEl) {
      selEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, 100);
}

function onCustomProxyUrlInput(val) {
  state.selectedProxyUrl = (val || "").trim();
}

function renderNodeModalLockState(item) {
  const fp = item.fp_config || {};
  const isLocked = !!fp.node_locked;
  const banner = document.getElementById("node-locked-banner");
  const portSelect = document.getElementById("node-port-select");
  const customInput = document.getElementById("node-custom-proxy");
  const btnSaveOnly = document.getElementById("btn-save-node-only");
  const btnSaveLaunch = document.getElementById("btn-save-and-launch");

  if (isLocked) {
    banner.style.display = "flex";
    document.getElementById("locked-node-title").textContent = `当前账号已锁定：${fp.proxy_node || "仅固定代理端口"} (${fp.proxy || "直连"})`;
    portSelect.disabled = true;
    if (customInput) customInput.disabled = true;
    btnSaveOnly.style.display = "none";
    btnSaveLaunch.textContent = "🚀 以当前锁定环境直接启动浏览器";
  } else {
    banner.style.display = "none";
    portSelect.disabled = false;
    if (customInput) customInput.disabled = false;
    btnSaveOnly.style.display = "inline-flex";
    btnSaveLaunch.textContent = "🚀 锁定此配置并启动指纹浏览器";
  }
}

function renderNodeRegionTabs() {
  const nodes = (state.proxyEnv && state.proxyEnv.nodes) || [];
  const regions = ["全部"];
  nodes.forEach((n) => {
    if (n.region && !regions.includes(n.region)) regions.push(n.region);
  });

  const tabsEl = document.getElementById("node-region-tabs");
  tabsEl.innerHTML = regions
    .map(
      (r) =>
        `<button type="button" class="region-tab ${state.selectedRegion === r ? "active" : ""}" onclick="selectNodeRegion('${escapeHtml(r)}')">${escapeHtml(r)}</button>`
    )
    .join("");
}

function selectNodeRegion(region) {
  state.selectedRegion = region;
  const item = state.accounts.find((a) => a.id === state.nodeModalAccountId);
  const isLocked = !!(item && item.fp_config && item.fp_config.node_locked);
  renderNodeRegionTabs();
  renderNodeGrid(isLocked);
}

function renderNodeGrid(isLocked) {
  const nodes = (state.proxyEnv && state.proxyEnv.nodes) || [];
  const activeNodeName = (state.proxyEnv && state.proxyEnv.active_node) || "";
  const filtered = state.selectedRegion === "全部" ? nodes : nodes.filter((n) => n.region === state.selectedRegion);
  const gridEl = document.getElementById("node-grid-container");

  const portOnlySelected = state.selectedNodeName === "";
  const portOnlyCard = `
    <div class="node-item ${portOnlySelected ? "selected" : ""} ${isLocked ? "disabled" : ""}" onclick="onSelectNodeItem('', ${isLocked})">
      <span>🌐 仅绑定代理端口 (不切换特定节点 / 兼容 v2rayN·Sing-box)</span>
    </div>
  `;

  if (!filtered.length) {
    gridEl.innerHTML =
      portOnlyCard +
      `<div style="color:var(--text-secondary);font-size:12px;padding:12px;">未探测到该分区下的节点，可直接锁定上方代理端口使用</div>`;
    return;
  }

  gridEl.innerHTML =
    (state.selectedRegion === "全部" ? portOnlyCard : "") +
    filtered
      .map((n) => {
        const isSel = n.name === state.selectedNodeName;
        const isLiveActive = n.name === activeNodeName;
        const delayHtml = n.delay ? `<span class="node-delay">${n.delay}ms</span>` : "";
        const activeBadge = isLiveActive ? `<span class="node-item-badge" title="本机当前正在生效的代理节点">🟢 当前在用</span>` : "";
        return `
          <div class="node-item ${isSel ? "selected" : ""} ${isLiveActive ? "is-active-now" : ""} ${isLocked ? "disabled" : ""}" onclick="onSelectNodeItem('${escapeHtml(n.name)}', ${isLocked})">
            <span style="display:flex;align-items:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
              ${escapeHtml(n.name)}
              ${activeBadge}
            </span>
            ${delayHtml}
          </div>
        `;
      })
      .join("");
}

function onSelectNodeItem(nodeName, isLocked) {
  if (isLocked) {
    showToast("🔒 该账号节点已锁定，请先点击上方「解锁节点」后再变更！");
    return;
  }
  state.selectedNodeName = nodeName;
  renderNodeGrid(false);
}

async function unlockCurrentAccountNode() {
  if (!state.nodeModalAccountId) return;
  try {
    const res = await callApi("set_node_lock", state.nodeModalAccountId, false);
    if (res && res.ok) {
      showToast("🔓 已解锁该账号节点，现在可以重新选择新节点并锁定");
      await loadDashboard();
      const updatedItem = state.accounts.find((a) => a.id === state.nodeModalAccountId);
      if (updatedItem) {
        renderNodeModalLockState(updatedItem);
        renderNodeGrid(false);
      }
    }
  } catch (err) {
    showToast("解锁失败");
  }
}

async function saveAndLockNode(andLaunch = false) {
  const accId = state.nodeModalAccountId;
  if (!accId) return;
  const item = state.accounts.find((a) => a.id === accId);
  if (!item) return;

  const btn = andLaunch ? document.getElementById("btn-save-and-launch") : document.getElementById("btn-save-node-only");
  if (btn) {
    btn.classList.add("loading");
    btn.disabled = true;
  }

  // If already locked and user clicked "Launch with locked node"
  if (item.fp_config && item.fp_config.node_locked) {
    closeNodeModal();
    if (andLaunch) {
      await executeLaunchBrowser(accId);
    }
    return;
  }

  if (!state.selectedNodeName && !state.selectedProxyUrl) {
    if (btn) {
      btn.classList.remove("loading");
      btn.disabled = false;
    }
    showToast("请至少选择一个代理端口或节点");
    return;
  }

  try {
    const res = await callApi(
      "bind_proxy_node",
      accId,
      state.selectedProxyUrl,
      state.selectedNodeName || "",
      true
    );
    if (res && res.ok) {
      showToast(`🔒 已为该账号锁定代理环境: ${state.selectedNodeName || state.selectedProxyUrl || "直连"}`);
      closeNodeModal();
      await loadDashboard();
      if (andLaunch) {
        await executeLaunchBrowser(accId);
      }
    } else {
      showToast(res.error || "锁定节点失败");
    }
  } catch (err) {
    showToast("保存节点异常: " + err.message);
  } finally {
    if (btn) {
      btn.classList.remove("loading");
      btn.disabled = false;
    }
  }
}

function closeNodeModal() {
  document.getElementById("node-modal").style.display = "none";
}

async function regenerateAccountFp(accountId) {
  try {
    const res = await callApi("regenerate_fingerprint", accountId);
    if (res && res.ok) {
      const fp = res.account.fp_config || {};
      showToast(`✓ 已为 [${fp.profile_code}] 重新生成专属指纹 (${fp.gpu_short} · ${fp.screen})`);
      await loadDashboard();
    }
  } catch (err) {
    showToast("重置指纹失败");
  }
}

async function toggleCardTwofaModified(accountId, nextVal) {
  try {
    const res = await callApi("toggle_twofa_modified", accountId, nextVal);
    if (res && res.ok) {
      showToast(nextVal ? "✓ 已标记为「2FA已修改」" : "已切换为「初始2FA」");
      await loadDashboard();
    }
  } catch (err) {
    showToast("切换状态失败");
  }
}

async function toggleCardPasswordModified(accountId, nextVal) {
  try {
    const res = await callApi("toggle_password_modified", accountId, nextVal);
    if (res && res.ok) {
      showToast(nextVal ? "✓ 已标记为「密码已修改」" : "已切换为「初始密码」");
      await loadDashboard();
    }
  } catch (err) {
    showToast("切换状态失败");
  }
}

// Zero-Idle-CPU TOTP Countdown Timer
function startZeroOverheadTotpTicker() {
  const circumference = 2 * Math.PI * 9;
  const ringEl = document.getElementById("global-ring");
  const remEl = document.getElementById("global-remaining");

  setInterval(async () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const remaining = 30 - (nowSec % 30);
    const currentSlot = Math.floor(nowSec / 30);

    if (remEl) remEl.textContent = remaining;
    if (ringEl) {
      const offset = circumference * (1 - remaining / 30);
      ringEl.style.strokeDashoffset = offset.toFixed(2);
      ringEl.classList.toggle("urgent", remaining <= 5);
    }

    document.querySelectorAll(".card-rem-sec").forEach((el) => {
      el.textContent = remaining;
    });

    if (currentSlot !== state.lastTotpSlot) {
      state.lastTotpSlot = currentSlot;
      try {
        const res = await callApi("refresh_totp");
        if (res && res.codes) {
          state.accounts.forEach((acc) => {
            const updatedTotp = res.codes[String(acc.id)];
            if (updatedTotp) {
              acc.totp = updatedTotp;
              const codeEl = document.getElementById(`totp-code-${acc.id}`);
              if (codeEl && updatedTotp.valid) {
                codeEl.textContent = formatTotpCode(updatedTotp.code);
              }
            }
          });
        }
      } catch (e) {
        console.error("Refresh TOTP error:", e);
      }
    }
  }, 1000);
}

// Copy Helpers
async function writeClipboard(text) {
  if (!text) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  }
}

async function copyFieldValue(btnEl, accountId, fieldName, labelText) {
  const item = state.accounts.find((a) => a.id === accountId);
  if (!item) return;
  let rawValue = item[fieldName] || "";
  if (fieldName === "secret_key" || fieldName === "initial_secret_key") {
    rawValue = normalizeSecretString(rawValue);
  }
  await writeClipboard(rawValue);
  flashCopyButton(btnEl);
  showToast(`✓ 已复制 ${labelText}`);
}

async function copyTotpCode(btnEl, accountId) {
  const item = state.accounts.find((a) => a.id === accountId);
  if (!item || !item.totp || !item.totp.code) return;
  await writeClipboard(item.totp.code);
  flashCopyButton(btnEl);
  showToast(`✓ 已复制 6 位动态验证码: ${item.totp.code}`);
}

async function copyFullFormattedLine(accountId) {
  const item = state.accounts.find((a) => a.id === accountId);
  if (!item) return;
  let line = "";
  if (item.account_type === "Google" || item.recovery_email || item.reg_year || item.reg_region) {
    const parts = [
      item.account,
      item.password,
      item.recovery_email,
      item.secret_key,
      item.reg_year,
      item.reg_region,
    ];
    while (parts.length && !parts[parts.length - 1]) parts.pop();
    line = parts.join("----");
  } else {
    const parts = [item.account, item.password];
    if (item.secret_key) parts.push(item.secret_key);
    line = parts.join("----");
  }
  await writeClipboard(line);
  showToast("✓ 已按标准 ---- 格式复制整条账号");
}

function flashCopyButton(btnEl) {
  if (!btnEl || !btnEl.classList.contains("copy-btn")) return;
  const original = btnEl.textContent;
  btnEl.classList.add("copied");
  btnEl.textContent = "✓ 已复制";
  setTimeout(() => {
    btnEl.classList.remove("copied");
    btnEl.textContent = original;
  }, 1100);
}

// Filters & Search
function setFilterType(type) {
  state.filterType = type || "All";
  document.querySelectorAll("#filter-tabs .seg-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.type === state.filterType);
  });
  syncTopBarPills();
  loadDashboard();
}

function setStatusFilter(status) {
  state.statusFilter = status;
  document.querySelectorAll("#status-tabs .seg-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.status === status);
  });
  loadDashboard();
}

let searchDebounce = null;
function onSearchInput(val) {
  state.searchQuery = val;
  document.getElementById("btn-clear-search").style.display = val ? "block" : "none";
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    loadDashboard();
  }, 160);
}

function clearSearch() {
  const input = document.getElementById("search-input");
  input.value = "";
  onSearchInput("");
}

// Theme & View Mode
function applyTheme(theme, persist = true) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  if (persist) {
    callApi("save_settings", { theme }).catch(() => {});
  }
}

function toggleTheme() {
  const next = state.theme === "dark" ? "light" : "dark";
  applyTheme(next, true);
}

function applyViewMode(mode, persist = true) {
  state.viewMode = mode;
  document.getElementById("view-compact").classList.toggle("active", mode === "compact");
  document.getElementById("view-full").classList.toggle("active", mode === "full");
  document.getElementById("view-table").classList.toggle("active", mode === "table");
  renderAccounts();
  if (persist) {
    callApi("save_settings", { view_mode: mode }).catch(() => {});
  }
}

function setViewMode(mode) {
  applyViewMode(mode, true);
}

function fillTodayDeactivated() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  document.getElementById("field-deactivated-date").value = `${y}-${m}-${d}`;
}

// Modal: Add / Edit + Express Smart Paste
function openAddModal() {
  document.getElementById("modal-title").textContent = "添加账号 · 智能快递式识别";
  document.getElementById("smart-paste-section").style.display = "block";
  document.getElementById("batch-banner").style.display = "none";
  document.getElementById("smart-paste-input").value = "";
  resetFeedbackText();
  resetFormFields();
  setRadioHealth("可用");
  document.getElementById("account-modal").style.display = "flex";
  setTimeout(() => document.getElementById("smart-paste-input").focus(), 60);
}

function openEditModal(accountId) {
  const item = state.accounts.find((a) => a.id === accountId);
  if (!item) return;
  document.getElementById("modal-title").textContent = "编辑账号信息";
  document.getElementById("smart-paste-section").style.display = "block";
  document.getElementById("batch-banner").style.display = "none";
  document.getElementById("smart-paste-input").value = "";
  resetFeedbackText();

  document.getElementById("field-id").value = item.id;
  setRadioType(item.account_type || "ChatGPT");
  setRadioHealth(item.health_status || "可用");
  document.getElementById("field-password-modified").checked = !!item.password_modified;
  document.getElementById("field-twofa-modified").checked = !!item.twofa_modified;
  document.getElementById("field-account").value = item.account || "";
  const pwdEl = document.getElementById("field-password");
  pwdEl.value = item.password || "";
  pwdEl.oninput = () => {
    if (item.password && pwdEl.value.trim() && pwdEl.value.trim() !== item.password) {
      document.getElementById("field-password-modified").checked = true;
    }
  };
  document.getElementById("field-secret").value = normalizeSecretString(item.secret_key || "");
  document.getElementById("field-initial-secret").value = normalizeSecretString(item.initial_secret_key || "");
  document.getElementById("field-purchase-date").value = item.purchase_date || "";
  document.getElementById("field-deactivated-date").value = item.deactivated_date || "";
  document.getElementById("field-recovery").value = item.recovery_email || "";
  document.getElementById("field-year").value = item.reg_year || "";
  document.getElementById("field-region").value = item.reg_region || "";
  document.getElementById("field-note").value = item.note || "";
  const isLocked = !!(item.fp_config && item.fp_config.node_locked);
  const proxyInput = document.getElementById("field-proxy");
  proxyInput.value = (item.fp_config && item.fp_config.proxy) || "";
  proxyInput.disabled = isLocked;
  onSecretFieldInput(item.secret_key || "");

  document.getElementById("account-modal").style.display = "flex";
}

function closeAccountModal() {
  document.getElementById("account-modal").style.display = "none";
}

function setRadioHealth(status) {
  const targetVal = status || "可用";
  const radio = document.querySelector(`input[name="health_status"][value="${targetVal}"]`);
  if (radio) radio.checked = true;
}

function getRadioHealth() {
  const checked = document.querySelector('input[name="health_status"]:checked');
  return checked ? checked.value : "可用";
}

function resetFormFields() {
  document.getElementById("field-id").value = "";
  setRadioType("ChatGPT");
  setRadioHealth("可用");
  document.getElementById("field-password-modified").checked = false;
  document.getElementById("field-twofa-modified").checked = false;
  document.getElementById("field-account").value = "";
  const pwdEl = document.getElementById("field-password");
  pwdEl.value = "";
  pwdEl.oninput = null;
  document.getElementById("field-secret").value = "";
  document.getElementById("field-initial-secret").value = "";
  document.getElementById("field-purchase-date").value = "";
  document.getElementById("field-deactivated-date").value = "";
  document.getElementById("field-recovery").value = "";
  document.getElementById("field-year").value = "";
  document.getElementById("field-region").value = "";
  document.getElementById("field-note").value = "";
  const proxyInput = document.getElementById("field-proxy");
  proxyInput.value = "";
  proxyInput.disabled = false;
  document.getElementById("secret-live-preview").textContent = "填写后将自动计算 6 位动态验证码";
}

function setRadioType(type) {
  const radio = document.querySelector(`input[name="account_type"][value="${type}"]`);
  if (radio) radio.checked = true;
}

function getRadioType() {
  const checked = document.querySelector('input[name="account_type"]:checked');
  return checked ? checked.value : "ChatGPT";
}

function resetFeedbackText() {
  const fb = document.getElementById("smart-parse-feedback");
  fb.className = "smart-parse-feedback";
  fb.textContent = "粘贴后将自动识别：账号、密码、初始/新2FA秘钥、购买与停用日期、辅助邮箱、年份、地区与备注";
}

function clearSmartPaste() {
  document.getElementById("smart-paste-input").value = "";
  document.getElementById("batch-banner").style.display = "none";
  state.parsedBatchRecords = [];
  resetFeedbackText();
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      const ta = document.getElementById("smart-paste-input");
      ta.value = text;
      await onSmartPasteInput(text);
    }
  } catch (_) {
    showToast("请直接在识别框内按 Ctrl+V 粘贴");
  }
}

function normalizeSecretString(val) {
  return String(val || "").replace(/[\s\-]+/g, "").toUpperCase();
}

async function onSmartPasteInput(rawText) {
  const fb = document.getElementById("smart-parse-feedback");
  const batchBanner = document.getElementById("batch-banner");

  if (!rawText || !rawText.trim()) {
    batchBanner.style.display = "none";
    state.parsedBatchRecords = [];
    resetFeedbackText();
    return;
  }

  try {
    const res = await callApi("smart_parse", rawText);
    if (res && res.only_secret) {
      batchBanner.style.display = "none";
      const sObj = res.only_secret;
      const cleaned = normalizeSecretString(sObj.secret_key);
      const secretEl = document.getElementById("field-secret");
      const initEl = document.getElementById("field-initial-secret");
      if (secretEl.value && secretEl.value !== cleaned && !initEl.value) {
        initEl.value = normalizeSecretString(secretEl.value);
        document.getElementById("field-twofa-modified").checked = true;
      } else if (sObj.twofa_modified) {
        document.getElementById("field-twofa-modified").checked = true;
      }
      secretEl.value = cleaned;
      document.getElementById("smart-paste-input").value = cleaned;
      if (sObj.totp && sObj.totp.valid) {
        document.getElementById("secret-live-preview").textContent = `✓ 已去空格并转大写 (${sObj.masked_secret}) · 当前动态验证码: ${formatTotpCode(sObj.totp.code)}`;
      }
      fb.className = "smart-parse-feedback recognized";
      fb.textContent = "✓ 已识别为 2FA 秘钥，自动去除空格并转为大写填入下方 2FA 栏！";
      return;
    }

    const records = res.records || [];
    state.parsedBatchRecords = records;

    if (records.length === 0) {
      batchBanner.style.display = "none";
      fb.className = "smart-parse-feedback";
      fb.textContent = "未识别到标准分隔格式，请在下方手动填写或检查粘贴内容";
      return;
    }

    const first = records[0];
    setRadioType(first.account_type || "ChatGPT");
    setRadioHealth(first.health_status || "可用");
    if (first.password_modified) {
      document.getElementById("field-password-modified").checked = true;
    }
    document.getElementById("field-twofa-modified").checked = !!first.twofa_modified;
    document.getElementById("field-account").value = first.account || "";
    document.getElementById("field-password").value = first.password || "";
    document.getElementById("field-secret").value = normalizeSecretString(first.secret_key);
    document.getElementById("field-initial-secret").value = normalizeSecretString(first.initial_secret_key);
    document.getElementById("field-purchase-date").value = first.purchase_date || "";
    document.getElementById("field-deactivated-date").value = first.deactivated_date || "";
    document.getElementById("field-recovery").value = first.recovery_email || "";
    document.getElementById("field-year").value = first.reg_year || "";
    document.getElementById("field-region").value = first.reg_region || "";
    if (first.note) document.getElementById("field-note").value = first.note;

    if (first.totp && first.totp.valid) {
      document.getElementById("secret-live-preview").textContent = `✓ 2FA秘钥有效 (已去空格转大写) · 当前动态验证码: ${formatTotpCode(first.totp.code)}`;
    } else if (first.secret_key) {
      document.getElementById("secret-live-preview").textContent = "⚠ 2FA秘钥格式非标准Base32，仍可原样保存";
    } else {
      document.getElementById("secret-live-preview").textContent = "未包含2FA秘钥";
    }

    fb.className = "smart-parse-feedback recognized";
    if (records.length === 1) {
      batchBanner.style.display = "none";
      fb.textContent = `✓ 智能识别成功：已自动识别为 [${first.account_type}] 格式（2FA秘钥已自动去空格转大写）！`;
    } else {
      batchBanner.style.display = "flex";
      document.getElementById("batch-count").textContent = records.length;
      document.getElementById("batch-btn-count").textContent = `${records.length} 条`;
      fb.textContent = `✓ 已识别到 ${records.length} 条账号记录（下方预览第 1 条，可点击上方按钮一键全部导入）`;
    }
  } catch (err) {
    console.error("Smart parse error:", err);
  }
}

async function onSecretFieldInput(secretVal) {
  const secretInput = document.getElementById("field-secret");
  const cleaned = normalizeSecretString(secretVal);
  if (secretInput && secretInput.value !== cleaned) {
    secretInput.value = cleaned;
  }
  const hintEl = document.getElementById("secret-live-preview");
  if (!cleaned) {
    hintEl.textContent = "填写后将自动计算 6 位动态验证码";
    return;
  }
  try {
    const res = await callApi("preview_totp", cleaned);
    if (res.totp && res.totp.valid) {
      hintEl.textContent = `✓ 秘钥有效 (${res.masked_secret}) · 当前动态验证码: ${formatTotpCode(res.totp.code)}`;
    } else {
      hintEl.textContent = "⚠ 秘钥非标准 Base32 格式，无法生成动态验证码（仍可保存）";
    }
  } catch (_) {}
}

function onInitialSecretFieldInput(secretVal) {
  const initInput = document.getElementById("field-initial-secret");
  const cleaned = normalizeSecretString(secretVal);
  if (initInput && initInput.value !== cleaned) {
    initInput.value = cleaned;
  }
}

async function submitAccountForm(e) {
  e.preventDefault();
  const payload = {
    id: document.getElementById("field-id").value || null,
    account_type: getRadioType(),
    health_status: getRadioHealth(),
    password_modified: document.getElementById("field-password-modified").checked ? 1 : 0,
    twofa_modified: document.getElementById("field-twofa-modified").checked ? 1 : 0,
    account: document.getElementById("field-account").value.trim(),
    password: document.getElementById("field-password").value.trim(),
    secret_key: normalizeSecretString(document.getElementById("field-secret").value),
    initial_secret_key: normalizeSecretString(document.getElementById("field-initial-secret").value),
    purchase_date: document.getElementById("field-purchase-date").value.trim(),
    deactivated_date: document.getElementById("field-deactivated-date").value.trim(),
    recovery_email: document.getElementById("field-recovery").value.trim(),
    reg_year: document.getElementById("field-year").value.trim(),
    reg_region: document.getElementById("field-region").value.trim(),
    note: document.getElementById("field-note").value.trim(),
    proxy: document.getElementById("field-proxy").value.trim(),
  };

  try {
    const res = await callApi("save_account", payload);
    if (res.ok) {
      closeAccountModal();
      showToast(payload.id ? "✓ 账号更新成功" : "✓ 账号添加成功");
      await loadDashboard();
    } else {
      showToast(res.error || "保存失败");
    }
  } catch (err) {
    showToast("保存失败: " + err.message);
  }
}

async function confirmBatchImport() {
  const rawText = document.getElementById("smart-paste-input").value;
  if (!rawText.trim()) return;
  try {
    const res = await callApi("batch_import", rawText);
    if (res.ok) {
      closeAccountModal();
      showToast(`✓ 成功批量导入 ${res.imported} 条账号记录`);
      await loadDashboard();
    } else {
      showToast(res.error || "批量导入失败");
    }
  } catch (err) {
    showToast("批量导入异常: " + err.message);
  }
}

async function confirmDeleteAccount(accountId) {
  const item = state.accounts.find((a) => a.id === accountId);
  if (!item) return;
  try {
    const res = await callApi("delete_account", accountId);
    if (res.ok) {
      showToast(`已删除账号 ${item.masked_account}`);
      await loadDashboard();
    }
  } catch (err) {
    showToast("删除失败");
  }
}

// Export Modal
async function openExportModal() {
  try {
    const res = await callApi("export_text", state.filterType);
    document.getElementById("export-textarea").value = res.text || "";
    document.getElementById("export-modal").style.display = "flex";
  } catch (err) {
    showToast("导出失败");
  }
}

function closeExportModal() {
  document.getElementById("export-modal").style.display = "none";
}

async function copyExportText() {
  const text = document.getElementById("export-textarea").value;
  if (!text) {
    showToast("暂无可导出的账号数据");
    return;
  }
  await writeClipboard(text);
  showToast("✓ 已复制全部导出内容至剪贴板");
}

function showToast(msg) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 2200);
}
