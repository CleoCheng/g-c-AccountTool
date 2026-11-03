# Device Tags and System Dictionaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust system dictionary subsystem, support device tagging (主机/iPhone/Pad), provide a System Settings modal for common configs and dictionary maintenance, and transform topbar/toolbar platform selections into dynamic dropdowns supporting custom account types (e.g., WorkBuddy, Qcoder).

**Architecture:** Extend SQLite database with `device_tag` column on `accounts` and a `system_dicts` table pre-seeded with 4 categories (`account_type`, `device_tag`, `health_status`, `antigravity_tier`). Expose CRUD API via `AccountApi` to `pywebview`. Redesign topbar and toolbar navigation with dynamic selects, add a Settings modal with tabbed dictionary management, and support 1-click device switching on cards and tables.

**Tech Stack:** Python 3.10+, SQLite3 (WAL mode), pywebview, Vanilla JavaScript (ES6+), CSS3 Variables.

**Spec:** [docs/superpowers/specs/2026-11-04-device-tags-and-system-dicts-design.md](file:///d:/Documents/Servers/accountManger/docs/superpowers/specs/2026-11-04-device-tags-and-system-dicts-design.md)

## Global Constraints

- Preserve backwards compatibility for all existing account fields, proxies, TOTP secret generation, and isolated browser launches.
- Default device tag is `主机`; default Antigravity tier is `无`; default health status is `可用`.
- Prevent accidental deletion of protected/system dictionary items or items currently in use by active accounts.
- Maintain responsive 7-column table layout with `overflow: hidden; table-layout: fixed;` to eliminate horizontal scrollbars.
- Git commit author must strictly be `Cleo <30462934+CleoCheng@users.noreply.github.com>`.

## Review Focus

1. **Custom Account Type Integration**: Newly added account types (e.g. WorkBuddy, Qcoder) must immediately appear in topbar dropdown, toolbar filter, Add/Edit modal, and filter accounts correctly.
2. **Device Tag Persistence & Filtering**: Modifying device tag (主机/iPhone/Pad) must persist immediately in SQLite and filter accounts without page reload.
3. **1-Click Device & Health & Pro Switching**: Quick popovers on cards and tables must update account state in place and sync stats.
4. **Dictionary Deletion Guard**: Attempting to delete a dictionary entry that is referenced by existing accounts must be rejected with a user-friendly error message.
5. **No Layout Overflow**: On window resize down to 860px width, neither the toolbar dropdowns nor the accounts table should produce a horizontal scrollbar.

---

### Task 1: Database Schema Extension & System Dictionaries Subsystem

**Files:**
- Modify: `src/db_service.py`

- [ ] Add `device_tag` column migration to `accounts` table in `_init_db()` (`DEFAULT '主机'`).
- [ ] Create `system_dicts` table in `_init_db()` with unique index on `(dict_type, dict_key)` and seed initial items for `account_type` (`ChatGPT`, `Google`, `WorkBuddy`, `Qcoder`), `device_tag` (`主机`, `iPhone`, `Pad`), `health_status` (`可用`, `不可用`, `封号`, `人机`, `短信`, `验证`), and `antigravity_tier` (`无`, `蓝色Pro`, `金色Pro`).
- [ ] Implement `list_system_dicts(dict_type=None)` returning sorted dictionary records.
- [ ] Implement `save_system_dict(data)` supporting insert/update with uniqueness and name checks.
- [ ] Implement `delete_system_dict(dict_id)` with validation against built-in protection and active account references.
- [ ] Update `list_accounts()` to support `device_tag` filtering and arbitrary `account_type`.
- [ ] Implement `set_device_tag(account_id, device_tag)` method.
- [ ] Update `get_stats()` to dynamically calculate statistics across all active account types, device tags, health statuses, and Antigravity tiers.

---

### Task 2: API Service Extension

**Files:**
- Modify: `src/api.py`

- [ ] Expose `get_system_dicts(dict_type=None)` via `AccountApi`.
- [ ] Expose `save_system_dict(data)` via `AccountApi`.
- [ ] Expose `delete_system_dict(dict_id)` via `AccountApi`.
- [ ] Expose `set_device_tag(account_id, device_tag)` via `AccountApi`.
- [ ] Update `get_dashboard()` to accept `device_tag="All"` parameter and return `dicts` alongside `accounts`, `stats`, and `settings`.
- [ ] Update `save_account()` to accept and persist `device_tag`.

---

### Task 3: Unit Tests for Database & API

**Files:**
- Modify: `tests/test_db.py`
- Modify: `tests/test_api.py`

- [ ] Add tests in `tests/test_db.py` for `system_dicts` initialization, listing, saving new item (`WorkBuddy`), updating, and deletion guard.
- [ ] Add tests in `tests/test_db.py` for `device_tag` assignment and filtering (`主机`, `iPhone`, `Pad`).
- [ ] Add tests in `tests/test_api.py` for `get_system_dicts`, `save_system_dict`, `set_device_tag`, and dashboard filtering with `device_tag` and dynamic platform.
- [ ] Run `python -m pytest` and ensure all tests pass.

---

### Task 4: UI HTML Structure & Modals

**Files:**
- Modify: `web/index.html`

- [ ] Add `#btn-settings` icon button (gear) next to `#btn-theme` in the topbar.
- [ ] Refactor topbar stats platform representation to a dynamic dropdown or aggregate pill `[全部平台 ▾]`.
- [ ] Refactor toolbar platform selection into a dynamic `<select id="platform-filter-select">`.
- [ ] Add device filter `<select id="device-filter-select">` to the toolbar.
- [ ] Add `#settings-modal` containing:
  - Tab 1: 常用设置 (General Settings)
  - Tab 2: 字典表维护 (Dictionary Table Maintenance) with sub-tabs for `账号类型`, `设备标记`, `可用状态`, `Pro选项`, an items table, and an Add/Edit Item sub-modal.
- [ ] In Add / Edit Account modal (`#account-modal`), add `device_tag` selector and replace static platform radio buttons with a dynamic platform dropdown or pill group.

---

### Task 5: CSS Styles for Settings Modal, Device Badges & Responsive Layout

**Files:**
- Modify: `web/style.css`

- [ ] Add styles for `#btn-settings` icon button.
- [ ] Add styles for `#settings-modal`, tabs, dictionary list table, badge color previews, and item action buttons.
- [ ] Add styles for device badges (`.u-device-tag`, `.u-device-dropdown`, `.opt-device-*`).
- [ ] Add styles for dynamic platform filter dropdown and device filter dropdown.
- [ ] Integrate 浅灰色 default card theme and simplified "Pro" badges (blue & gold).
- [ ] Ensure `.accounts-table-wrapper` has `overflow: hidden; width: 100%;` and `.u-table` has `table-layout: fixed;` to guarantee no horizontal scrollbar.

---

### Task 6: Frontend Controller & Dictionary Interaction Logic

**Files:**
- Modify: `web/app.js`

- [ ] Store `state.dicts` and `state.deviceFilter` in global state.
- [ ] Dynamically populate platform filter, health filter, Pro filter, and device filter from `state.dicts`.
- [ ] Render device tag badge with 1-click quick-select popover on cards and table rows.
- [ ] Implement `openSettingsModal()`, tab switching, dictionary CRUD rendering, and saving handlers.
- [ ] Implement `onQuickSelectDevice(accId, deviceTag)` for instant updates.
- [ ] Update `renderTableView()` to show device tag clearly in the 7-column layout without horizontal overflow.
- [ ] Update `populateEditForm()` and `collectFormData()` to load and save `device_tag`.

---

### Task 7: Full Verification & Automated Scans

- [ ] Run `python -m pytest` across all test files.
- [ ] Run `python main.py --verify-init` to ensure database initializes cleanly with 33 accounts and default dictionaries.
- [ ] Run `text_guard.py` scan on modified files.
- [ ] Inspect `git status` and `git diff` for cleanliness.

---

### Task 8: Git Commit & Push

- [ ] Stage all modified files (`src/db_service.py`, `src/api.py`, `web/index.html`, `web/app.js`, `web/style.css`, `tests/test_db.py`, `tests/test_api.py`, and `docs/`).
- [ ] Commit with author `Cleo <30462934+CleoCheng@users.noreply.github.com>`.
- [ ] Push to `origin main`.
