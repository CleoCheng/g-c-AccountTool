# Device Tags, System Dictionaries & Dynamic Platforms Spec

**Date:** 2026-11-04  
**Author:** Cleo Cheng / Roger  
**Status:** Approved  

---

## 1. Background & Goals

KeyVault Account Manager currently has static platform buttons (`ChatGPT`, `Google`) and hardcoded values for health status and Antigravity tiers. As users manage more AI and developer services (e.g., `WorkBuddy`, `Qcoder`, Anthropic, etc.) across different client devices (`主机`, `iPhone`, `Pad`), the application needs:
1. **Device Tagging (`device_tag`)**: Classify accounts by device (主机, iPhone, Pad) with 1-click quick switching and filtering.
2. **System Dictionaries Subsystem (`system_dicts`)**: Manage `account_type`, `device_tag`, `health_status`, and `antigravity_tier` dynamically in SQLite.
3. **System Settings Modal**: A gear button in the topbar next to the theme toggle that opens a modal for common settings and dictionary table maintenance.
4. **Dynamic Navigation & Dropdowns**: Replace static platform buttons with a dynamic platform dropdown supporting user-added platforms (e.g. WorkBuddy, Qcoder), with real-time stats and filters.
5. **Theme & Layout Refinements**: Retain friendly light gray default backgrounds, simplified "Pro" labels (distinguished by color alone), and responsive 7-column table layout without horizontal scrollbars.

---

## 2. Architecture & Data Model

### 2.1 Database Schema (`src/db_service.py`)

#### `accounts` Table Extension
- Add column: `device_tag TEXT DEFAULT '主机'`
- Migration in `_init_db()` ensures all existing and future accounts have a valid `device_tag`.

#### `system_dicts` Table
```sql
CREATE TABLE IF NOT EXISTS system_dicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dict_type TEXT NOT NULL,       -- 'account_type' | 'device_tag' | 'health_status' | 'antigravity_tier'
    dict_key TEXT NOT NULL,        -- Internal identifier (e.g., 'WorkBuddy', '主机', '可用', '蓝色Pro')
    dict_label TEXT NOT NULL,      -- Display text (e.g., 'WorkBuddy', '主机', '可用', 'Pro')
    dict_value TEXT NOT NULL,      -- Persisted value
    color_class TEXT DEFAULT '',   -- UI theme styling tag
    icon TEXT DEFAULT '',          -- Icon or emoji
    sort_order INTEGER DEFAULT 0,  -- Display order
    is_default INTEGER DEFAULT 0,  -- Whether it is selected by default for new accounts
    is_system INTEGER DEFAULT 0,   -- Protected system items
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dict_type_key ON system_dicts(dict_type, dict_key);
```

#### Default Seed Data
- **`account_type`**: `ChatGPT` (default), `Google`, `WorkBuddy`, `Qcoder`
- **`device_tag`**: `主机` (default, 🖥️), `iPhone` (📱), `Pad` (📱)
- **`health_status`**: `可用` (default, 🟢), `不可用` (⚪), `封号` (🔴), `人机` (🟠), `短信` (🟣), `验证` (🔵)
- **`antigravity_tier`**: `无` (default, ⚪), `蓝色Pro` (💎), `金色Pro` (👑)

---

## 3. API Surface (`src/api.py`)

1. `get_system_dicts(dict_type=None)` -> List of dictionary records or grouped by type.
2. `save_dict_item(data)` -> Create or update a dictionary entry with uniqueness validation.
3. `delete_dict_item(item_id)` -> Safe deletion (verifies item is not protected or referenced by active accounts).
4. `get_system_settings()` / `save_system_settings(settings)` -> Persist general preferences.
5. `set_device_tag(account_id, device_tag)` -> 1-Click quick toggle.
6. `get_dashboard(...)` -> Extended with `device_tag` filter and dictionary-driven stats.

---

## 4. Frontend Architecture (`web/`)

### 4.1 Topbar
- Add `#btn-settings` icon button (gear) next to `#btn-theme`.
- Platform stats: Replaces static pills with a platform dropdown `<select id="topbar-platform-select">` or a neat pill showing `全部平台 (N) ▾`, showing real-time account counts.
- Retain core health stats: `可用 (N)` and `不可用 (N)`.

### 4.2 Toolbar
- Platform Filter: `<select id="platform-filter-select">` dynamically populated.
- Health Filter: `<select id="health-filter-select">` dynamically populated.
- Antigravity Filter: `<select id="ag-filter-select">` (⚪ 无 / 💎 Pro / 👑 Pro) with themed background feedback.
- Device Filter: `<select id="device-filter-select">` (全部设备 / 🖥️ 主机 / 📱 iPhone / 📱 Pad / ...).

### 4.3 System Settings Modal (`#settings-modal`)
- Tab 1: **常用设置 (General Settings)**: Default view mode, default platform, default device, TOTP interval, backup data.
- Tab 2: **字典表维护 (Dictionary Management)**: Sub-tabs for Account Types, Device Tags, Health Statuses, and Pro Tiers. Supports adding, editing, deleting, and default item setting.

### 4.4 Card & Table Layouts
- **Card**: Add `u-device-dropdown` on row 2 for 1-click device switching. Simplified "Pro" badges with blue and gold styles.
- **Table**: 7-column fixed layout without horizontal scrollbar. Device tag integrated into the account/device cell.
