# Universal Multi-Platform Attributes and Platform Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform KeyVault into a universal multi-platform account manager where attributes (e.g. Pro tier, device tag, health status, and user-defined custom attributes) can be defined as select dropdowns or single-line text, bound to specific platforms or all platforms, and dynamically adapted across the filter toolbar, account cards, and add/edit forms.

**Architecture:** Create an `account_attributes` table in SQLite to manage attribute definitions, types, and platform bindings (with initial seeds for `health_status` [All], `device_tag` [Google], `antigravity_tier` [Google]). Add `custom_fields_json` to `accounts` for lossless custom property persistence. Expose attribute CRUD and binding APIs in Python. Dynamically render filter selects, card tags, and modal inputs according to the active platform's bound attributes, with a dedicated Attribute Management tab in Settings.

**Tech Stack:** Python 3.10+, SQLite3 (WAL mode), pywebview, Vanilla JavaScript (ES6+), CSS3 Variables.

**Spec:** [docs/superpowers/specs/2026-11-04-universal-attributes-and-platform-binding-design.md](file:///d:/Documents/Servers/accountManger/docs/superpowers/specs/2026-11-04-universal-attributes-and-platform-binding-design.md)

## Global Constraints

- 100% backwards compatibility for existing 33 accounts and all legacy columns (`health_status`, `device_tag`, `antigravity_tier`, proxies, TOTP).
- Default bound platforms: `health_status` -> `All`; `device_tag` -> `["Google"]`; `antigravity_tier` -> `["Google"]`.
- System built-in attributes (`is_system == 1`) cannot have their `attr_key` renamed or be deleted, but their `bound_platforms` and labels can be edited.
- All new dropdowns must strictly use the unified `.c-select-container` dark glassmorphic custom dropdown component without OS native comboboxes.
- Encoding integrity: All files must be UTF-8 without BOM, CRLF line endings, and pass `text_guard.py scan`.
- Git commit author must strictly be `Cleo <30462934+CleoCheng@users.noreply.github.com>`.

## Review Focus

1. **Platform Filter Dynamic Switch**: Selecting "全部平台" in topbar or toolbar shows only global attributes (`health_status`). Switching to "Google" reveals "设备标记" and "Pro选项". Switching to "ChatGPT" cleanly hides "设备标记" and "Pro选项".
2. **Account Card Badge Isolation**: A ChatGPT account card must NEVER display a device tag or Pro badge if they are bound strictly to Google.
3. **Add/Edit Form Reactivity**: Changing the account type radio in the Add/Edit Account modal dynamically toggles the visible input fields according to that type's bound attributes.
4. **Attribute Schema Persistence**: Adding a custom attribute (e.g. `org_team`, type `text` or `select`, bound to `WorkBuddy`) in Settings persists to SQLite and immediately becomes available for accounts of that type.
5. **Lossless Custom Fields**: Saving an account with custom attributes stores values in `custom_fields_json` and reloads them accurately when editing.

---

### Task 1: Database Schema & Core Attributes Engine

**Files:**
- Modify: `src/db_service.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `list_attributes()` -> `list[dict]`
  - `get_attribute(attr_id: int)` -> `dict | None`
  - `save_attribute(data: dict)` -> `dict`
  - `delete_attribute(attr_id: int)` -> `dict`
  - `update_attribute_bindings(attr_id: int, bound_platforms: str | list)` -> `dict`
  - `accounts.custom_fields_json` column on `accounts` table

- [ ] **Step 1: Write unit tests in `tests/test_db.py` for `account_attributes` and `custom_fields_json`**
  - Test table initialization and default seeds (`health_status`, `device_tag`, `antigravity_tier`).
  - Test `save_attribute` inserting a new custom attribute (e.g. `org_team`, type `text`, bound to `["WorkBuddy"]`).
  - Test `update_attribute_bindings` changing `device_tag` bindings to `["Google", "WorkBuddy"]`.
  - Test `delete_attribute` blocking deletion of system attributes and allowing deletion of custom attributes.
  - Test saving an account with `custom_fields` dictionary storing to `custom_fields_json`.

- [ ] **Step 2: Run test to verify it fails**
  - Run: `pytest tests/test_db.py -k "test_attributes" -v`
  - Expected: FAIL (`list_attributes` or `account_attributes` not defined)

- [ ] **Step 3: Implement database migrations & CRUD methods in `src/db_service.py`**
  - Add `CREATE TABLE IF NOT EXISTS account_attributes (...)` in `_init_db()`.
  - Add `ALTER TABLE accounts ADD COLUMN custom_fields_json TEXT DEFAULT '{}'` migration in `_init_db()`.
  - Seed default rows for `health_status` (`All`), `device_tag` (`["Google"]`), `antigravity_tier` (`["Google"]`).
  - Implement `list_attributes()`, `get_attribute()`, `save_attribute()`, `delete_attribute()`, and `update_attribute_bindings()`.
  - Update `create_account()` and `update_account()` to accept and persist `custom_fields_json`.
  - Update `list_accounts()` row mapping to deserialize `custom_fields_json` into `item["custom_fields"]`.

- [ ] **Step 4: Run test to verify it passes**
  - Run: `pytest tests/test_db.py -k "test_attributes" -v`
  - Expected: PASS

- [ ] **Step 5: Commit**
  - `git add src/db_service.py tests/test_db.py`
  - `git commit --author="Cleo <30462934+CleoCheng@users.noreply.github.com>" -m "feat(db): implement account_attributes schema, seeds, and custom_fields_json storage"`

---

### Task 2: API Service & Dashboard Payload Integration

**Files:**
- Modify: `src/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces:
  - `AccountApi.get_attributes()` -> `dict(ok=True, data=list[dict])`
  - `AccountApi.save_attribute(data: dict)` -> `dict`
  - `AccountApi.delete_attribute(attr_id: int)` -> `dict`
  - `AccountApi.update_attribute_bindings(attr_id: int, bound_platforms)` -> `dict`
  - `AccountApi.get_dashboard(...)` includes `"attributes"` in response payload

- [ ] **Step 1: Write API tests in `tests/test_api.py`**
  - Test `get_attributes()` returns list containing the 3 seeded system attributes.
  - Test `save_attribute()` validates inputs and prevents renaming system `attr_key`.
  - Test `delete_attribute()` returns error when trying to delete system attributes.
  - Test `get_dashboard()` returns `"attributes"` key matching database records.

- [ ] **Step 2: Run test to verify it fails**
  - Run: `pytest tests/test_api.py -k "test_attribute_api" -v`
  - Expected: FAIL

- [ ] **Step 3: Implement API endpoints in `src/api.py`**
  - Expose `get_attributes()`, `save_attribute()`, `delete_attribute()`, `update_attribute_bindings()`.
  - In `get_dashboard()`, fetch `self.db.list_attributes()` and include in return payload.
  - In `save_account()`, accept `custom_fields` and pass to DB layer.

- [ ] **Step 4: Run test to verify it passes**
  - Run: `pytest tests/test_api.py -k "test_attribute_api" -v`
  - Expected: PASS

- [ ] **Step 5: Run full pytest suite to ensure zero regressions**
  - Run: `pytest`
  - Expected: All 31+ tests PASS

- [ ] **Step 6: Commit**
  - `git add src/api.py tests/test_api.py`
  - `git commit --author="Cleo <30462934+CleoCheng@users.noreply.github.com>" -m "feat(api): expose attribute management APIs and enrich dashboard payload with attributes"`

---

### Task 3: Settings Modal Attribute Manager & Binding UI

**Files:**
- Modify: `web/index.html`
- Modify: `web/style.css`
- Modify: `web/app.js`

- [ ] **Step 1: Update `web/index.html` settings navigation and panes**
  - In `#settings-modal .settings-tabs-nav`, add tab button:
    `<button class="settings-tab-btn" data-tab="attrs" onclick="switchSettingsTab('attrs')"><span class="tab-emoji">🧩</span><span>属性与平台绑定</span></button>`.
  - Add pane `#pane-attrs` with:
    - Header: title "🧩 属性定义与平台绑定", subtitle "配置字段类型及关联的账号平台", and "+ 新建属性" button.
    - Card container `#attrs-table-card` with table columns: 属性名称、标识键、字段类型、绑定平台、排序、操作.
  - Add sub-modal `#attr-edit-modal`:
    - Form `#attr-edit-form` with: 属性名称 (`attr_label`), 标识键 (`attr_key`), 字段类型下拉 (`attr_type`: select/text), 关联字典类型 (`dict_type`), 显示排序 (`sort_order`).
    - Platform bindings checkboxes container `#attr-platform-checkboxes` (dynamically listing "全部平台" + active account types from `state.dicts`).

- [ ] **Step 2: Add styles in `web/style.css` for Attribute Manager**
  - Add styles for `.attr-badge-pill`, `.attr-platform-tag`, `.platform-check-grid`, `.attr-type-badge`.
  - Style the platform checkboxes in a responsive flex-wrap pill grid.

- [ ] **Step 3: Implement Attribute UI controllers in `web/app.js`**
  - Store `state.attributes = data.attributes || []` in `loadDashboard()`.
  - Implement `renderAttributesPane()`: populates `#attrs-table-card` rows with name, key, type badge, bound platform badges, and Edit/Dict/Delete buttons.
  - Implement `openAddAttrModal()` and `openEditAttrModal(attrId)`.
  - Implement `renderAttrPlatformCheckboxes(selectedPlatforms)`.
  - Implement `submitAttrForm(event)`: validates and calls `callApi("save_attribute", payload)`, reloads dashboard, and refreshes UI.
  - Implement `confirmDeleteAttr(attrId)`: deletes attribute with confirmation.
  - Hook into `switchSettingsTab(tabName)`: when tab is `'attrs'`, call `renderAttributesPane()`.

- [ ] **Step 4: Manual verification in browser/pywebview**
  - Open Settings -> Click "🧩 属性与平台绑定".
  - Verify `health_status`, `device_tag`, and `antigravity_tier` are listed with correct bound platforms.
  - Click "编辑" on `device_tag`, toggle platforms, save, and confirm persistence.
  - Click "+ 新建属性", create `org_team` (text type, bound to WorkBuddy), and confirm it appears in the table.

- [ ] **Step 5: Commit**
  - `git add web/index.html web/style.css web/app.js`
  - `git commit --author="Cleo <30462934+CleoCheng@users.noreply.github.com>" -m "feat(ui): add attribute and platform binding management tab in settings modal"`

---

### Task 4: Dynamic Filter Toolbar Adaptation & Custom Select Integration

**Files:**
- Modify: `web/index.html`
- Modify: `web/style.css`
- Modify: `web/app.js`

- [ ] **Step 1: Refactor filter toolbar in `web/index.html`**
  - Inside `.toolbar .filter-group`, replace static `health-select-wrap` containers with:
    `<div id="dynamic-filter-attributes-container" class="dynamic-filters-wrap"></div>`.
  - Keep the platform select and search input intact.

- [ ] **Step 2: Implement dynamic attribute filtering in `web/app.js`**
  - Implement helper `isAttributeApplicable(attr, platform)`:
    - If `platform === "All"`, returns `attr.bound_platforms === "All"`.
    - If `platform !== "All"`, returns `attr.bound_platforms === "All" || platforms.includes(platform)`.
  - Update `renderFilterDropdowns()`:
    - Finds all applicable attributes where `is_filter == 1 && attr_type == 'select'`.
    - Dynamically generates `<select id="filter-${attr.attr_key}" class="health-filter-select">` with options from linked dictionary.
    - Enhances all generated selects with `enhanceSelectToCustom(sel)` so they use the `.c-select-container` dark glassmorphism component.
    - Binds `onchange` to trigger `setDynamicAttributeFilter(attrKey, value)`.
  - In `loadDashboard()`, pass dynamic attribute filters to API.

- [ ] **Step 3: Style dynamic filter container in `web/style.css`**
  - Ensure `.dynamic-filters-wrap` aligns seamlessly with search input and platform select with zero layout shift.

- [ ] **Step 4: Verify dynamic filter behavior**
  - When filtering by "All": only "可用状态" filter is visible.
  - When switching platform to "Google": "设备标记" and "Pro选项" filter dropdowns appear automatically.
  - When switching platform to "ChatGPT": "设备标记" and "Pro选项" are hidden.

- [ ] **Step 5: Commit**
  - `git add web/index.html web/style.css web/app.js`
  - `git commit --author="Cleo <30462934+CleoCheng@users.noreply.github.com>" -m "feat(ui): dynamically render filter toolbar dropdowns based on platform bindings"`

---

### Task 5: Dynamic Add/Edit Account Modal & Account Card Adaptation

**Files:**
- Modify: `web/index.html`
- Modify: `web/style.css`
- Modify: `web/app.js`

- [ ] **Step 1: Update Add/Edit Account form in `web/index.html`**
  - In `#account-modal #account-form`, add a dedicated dynamic attributes container:
    `<div id="form-dynamic-attributes-container" class="dynamic-form-section"></div>`.

- [ ] **Step 2: Implement dynamic form rendering in `web/app.js`**
  - Implement `renderAccountModalDynamicFields(accountType, currentValues)`:
    - Filters attributes applicable to `accountType`.
    - For `select` attributes: renders radio-pills or `.settings-select` dropdown with dictionary options.
    - For `text` attributes: renders `.form-group` with `<label>` and `<input type="text" class="settings-input">`.
  - Hook into account type radio changes: changing Account Type immediately re-renders `#form-dynamic-attributes-container` and preserves entered values.
  - In `openEditModal(id)`: populates values from both built-in fields and `item.custom_fields`.
  - In `submitAccountForm(event)`: gathers dynamic field values into `custom_fields` dictionary and submits to API.

- [ ] **Step 3: Update Account Card rendering in `web/app.js`**
  - In `renderCardItem(item)`:
    - Only render Device Tag badge if `device_tag` attribute is applicable to `item.account_type`.
    - Only render Pro badge if `antigravity_tier` attribute is applicable to `item.account_type`.
    - For custom attributes, render custom badges or detail drawer rows for applicable attributes.

- [ ] **Step 4: Manual verification**
  - Click "添加账号" -> select "ChatGPT" -> verify Google-specific fields (device, Pro) are hidden.
  - Select "Google" -> verify device and Pro fields appear.
  - Fill fields, save, and verify cards display only applicable badges.

- [ ] **Step 5: Commit**
  - `git add web/index.html web/style.css web/app.js`
  - `git commit --author="Cleo <30462934+CleoCheng@users.noreply.github.com>" -m "feat(ui): dynamic account form fields and card badges based on platform attribute bindings"`

---

### Task 6: End-to-End Verification, Test Suite & Encoding Scan

**Files:**
- Test: `tests/test_db.py`, `tests/test_api.py`
- Verify: `main.py`
- Scan: All modified files

- [ ] **Step 1: Run full pytest suite**
  - Run: `python -m pytest`
  - Verify all unit and integration tests pass without errors.

- [ ] **Step 2: Verify database integrity and account total**
  - Run: `python main.py --verify-init`
  - Verify output shows `total_accounts=33`.

- [ ] **Step 3: Run safe text editing scan**
  - Run: `python C:\Users\Roger\.gemini\config\skills\safe-text-editing\scripts\text_guard.py scan --root d:\Documents\Servers\accountManger --files src/db_service.py src/api.py web/index.html web/style.css web/app.js`
  - Verify 0 findings, UTF-8 encoding, CRLF newlines, and no replacement characters.

- [ ] **Step 4: Push to origin**
  - Run: `git push origin main`
