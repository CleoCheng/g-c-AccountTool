# KeyVault 全平台通用账号管理与动态属性绑定架构设计规范

**文档状态**: 设计评审中 (Reviewing)  
**创建日期**: 2026-11-04  
**目标系统**: KeyVault · 全平台账号与凭据管家 (`g-c-AccountTool`)

---

## 1. 背景与业务目标

### 1.1 现状与痛点
KeyVault 当前已从早期单一的 Google & ChatGPT 密钥工具，演进为支持多平台账号管理的应用。但在属性与字段层面，系统仍残留着平台强耦合的硬编码设计：
1. **属性与平台未解耦**：例如 `antigravity_tier`（Pro选项）和 `device_tag`（设备标记）在业务逻辑上只归属于 Google，但由于缺乏属性与平台的动态绑定机制，导致界面在所有平台下都显示这些字段或筛选器，不仅造成视觉干扰，也无法灵活适应新平台（如 WorkBuddy, Qcoder, Claude, GitHub 等）。
2. **缺乏自定义属性扩展能力**：用户无法根据新平台的特性自主新增属性（例如添加“所属团队”、“授权组织”、“API Key 额度”等），限制了应用成为真正通用的账号管理系统的能力。

### 1.2 升级目标
1. **属性定义与平台绑定模型**：
   - 建立统一的属性定义体系，支持设置属性的名称、标识键、字段类型（下拉单选、单行文本）以及所绑定的平台（支持「全部平台」或多选指定平台如「仅 Google」）。
   - 将现有 `health_status`（可用状态）、`device_tag`（设备标记）、`antigravity_tier`（Pro选项）统筹纳管为首批**系统内置属性**，默认配置其平台绑定关系，并允许用户在设置中自定义调整。
2. **三端动态联动渲染**：
   - **工具栏筛选联动**：选择「全部平台」时仅展示全局属性筛选；切换为具体平台（如 Google）时，自动动态展示该平台绑定的专属下拉筛选；切换为未绑定该属性的平台（如 ChatGPT）时，无关联下拉框自动隐藏。
   - **账号卡片联动**：卡片上仅渲染该账号所属平台关联的属性徽章与数据标签。
   - **新建/编辑弹窗联动**：切换账号归属平台时，表单动态根据所选平台所绑定的属性展示对应输入控件，未绑定的属性自动隐藏。
3. **设置中心统一维护扩展**：
   - 设置弹窗中提供统一的「属性与平台绑定」维护中心，支持属性的新增、修改绑定平台、删除（非系统项）以及下拉选项的字典维护。

---

## 2. 数据模型与存储设计

### 2.1 属性元数据表 (`account_attributes`)
在 SQLite 数据库中创建 `account_attributes` 表，集中管理所有属性的元数据定义：

```sql
CREATE TABLE IF NOT EXISTS account_attributes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attr_key TEXT UNIQUE NOT NULL,               -- 属性唯一标识键，如 'health_status', 'device_tag', 'antigravity_tier', 'org_team'
    attr_label TEXT NOT NULL,                    -- 显示名称，如 '可用状态', '设备标记', 'Pro选项', '所属团队'
    attr_type TEXT NOT NULL DEFAULT 'select',    -- 字段类型：'select' (下拉单选) | 'text' (单行文本)
    bound_platforms TEXT NOT NULL DEFAULT 'All', -- 绑定平台：'All' 或 JSON 数组字符串如 '["Google"]', '["Google","WorkBuddy"]'
    dict_type TEXT DEFAULT '',                   -- 若为 select 类型，关联的 system_dicts.dict_type
    sort_order INTEGER DEFAULT 0,                -- 排序权重，升序排布
    is_system INTEGER DEFAULT 0,                 -- 1: 系统内置保护项 (禁止删除键名); 0: 用户自定义新增
    is_required INTEGER DEFAULT 0,               -- 0: 选填; 1: 必填
    is_filter INTEGER DEFAULT 1,                 -- 是否作为列表筛选器展示 (1: 参与筛选; 0: 仅详情/编辑可见)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 账号表扩展 (`accounts.custom_fields_json`)
为保证现有 33 个账号及已有功能的 100% 绝对稳定与无缝兼容：
1. 保持 `accounts` 表现有物理列（`health_status`, `device_tag`, `antigravity_tier`）不变，系统内置属性直接读写原有字段；
2. 为 `accounts` 表追加 `custom_fields_json TEXT DEFAULT '{}'` 列，用于存储用户后续新增的自定义扩展属性（以 JSON 键值对存储，如 `{"org_team": "AI Lab", "vip_level": "Tier-3"}`）。

### 2.3 系统内置属性初始化数据 (Initial Seed Data)
系统启动或迁移时自动写入内置属性：
| `attr_key` | `attr_label` | `attr_type` | `bound_platforms` | `dict_type` | `is_system` | `sort_order` |
|---|---|---|---|---|---|---|
| `health_status` | 可用状态 | `select` | `All` | `health_status` | 1 | 10 |
| `device_tag` | 设备标记 | `select` | `["Google"]` | `device_tag` | 1 | 20 |
| `antigravity_tier` | Pro选项 | `select` | `["Google"]` | `antigravity_tier` | 1 | 30 |

用户可在设置中自由修改 `device_tag` 或 `antigravity_tier` 的绑定平台（如追加 `WorkBuddy`）。

---

## 3. 后端 API 与接口设计 (`src/api.py` & `src/db_service.py`)

### 3.1 属性元数据管理接口
1. `get_attributes()`:
   - 返回按 `sort_order ASC, id ASC` 排序的所有属性定义列表。
2. `save_attribute(attr_data: dict)`:
   - 新增或更新属性定义。
   - 包含校验：`attr_key` 命名合法性、系统内置项禁止篡改 `attr_key` 与 `is_system`、当 `attr_type == 'select'` 且未指定 `dict_type` 时自动以 `attr_key` 初始化字典类型。
3. `delete_attribute(attr_id: int)`:
   - 删除自定义属性（系统内置项 `is_system == 1` 拒绝删除并返回错误提示）。
4. `update_attribute_bindings(attr_id: int, bound_platforms: str | list)`:
   - 快捷修改指定属性绑定的平台列表。

### 3.2 仪表盘聚合数据增强 (`get_dashboard`)
在 `get_dashboard()` 返回的数据结构中增加 `attributes` 数组：
```json
{
  "accounts": [...],
  "stats": {...},
  "dicts": [...],
  "attributes": [
    {
      "id": 1,
      "attr_key": "health_status",
      "attr_label": "可用状态",
      "attr_type": "select",
      "bound_platforms": "All",
      "dict_type": "health_status",
      "sort_order": 10,
      "is_system": 1,
      "is_filter": 1
    },
    ...
  ],
  "settings": {...}
}
```

### 3.3 账号保存与查询过滤扩展
- `create_account` / `update_account`: 支持接收 `custom_fields: dict`，落盘存入 `custom_fields_json`。
- `get_dashboard`: 过滤 SQL 支持通用自定义属性匹配（利用 SQLite 内置函数 `json_extract(custom_fields_json, '$.' || :attr_key)`）。

---

## 4. 前端交互与动态渲染引擎设计 (`web/`)

### 4.1 属性适用性判定规则 (Utility Rule)
前端提供统一判定工具函数：
```javascript
function isAttributeApplicable(attr, platform) {
  if (!attr) return false;
  if (attr.bound_platforms === "All" || !attr.bound_platforms) return true;
  let platforms = [];
  try {
    platforms = typeof attr.bound_platforms === "string" 
      ? JSON.parse(attr.bound_platforms) 
      : attr.bound_platforms;
  } catch (e) {
    platforms = [attr.bound_platforms];
  }
  if (!platform || platform === "All") {
    // 当筛选全部平台时，仅显示标记为 All 的全局通用属性
    return attr.bound_platforms === "All";
  }
  return platforms.includes(platform);
}
```

### 4.2 工具栏动态筛选框渲染 (`renderFilterDropdowns`)
- 依据当前选中的平台 `state.filterType`，动态计算应展示的属性筛选器；
- 容器根据适用属性列表动态渲染自定义下拉框（复用已建成的 `.c-select-container` 磨砂玻璃组件）；
- 不适用的属性下拉框不出现在 DOM 中或平滑隐藏，确保工具栏精简不冗余。

### 4.3 账号卡片动态徽章展示 (`renderCardItem`)
- 渲染账号卡片时，获取该账号所属平台 `item.account_type` 关联的所有属性；
- 对于 `device_tag`、`antigravity_tier` 等，仅在与该平台关联时才渲染其胶囊徽章与快捷修改弹窗；
- 对于用户新增的自定义属性：
  - 下拉型：渲染为对应配色与图标的徽章；
  - 文本型：在展开详情抽屉中以键值对（`所属团队: AI Lab`）优雅呈现。

### 4.4 新建 / 编辑账号弹窗动态表单
- 在账号表单中开辟「平台专属扩展属性」区域；
- 当用户切换账号归属平台（如从 ChatGPT 点击切换到 Google）时，表单区域即时响应重新计算，仅渲染该平台绑定的输入控件；
- 文本型属性渲染为 `.settings-input` 输入框，下拉型属性渲染为单选胶囊或自定义下拉框。

### 4.5 设置弹窗内「属性与平台绑定」管理面板
在系统设置弹窗（`#settings-modal`）的导航药丸栏中新增「🧩 属性与平台绑定」标签页：
1. **属性列表卡片**：
   - 清楚标明：属性名称、标识键、字段类型（下拉 / 单行文本）、系统内置 / 自定义标识；
   - 绑定平台展示为蓝色微光胶囊（如 `全部平台`、`Google`、`WorkBuddy`）；
   - 操作按钮：【修改绑定平台】、【维护选项字典】（下拉型）、【删除】（自定义项）。
2. **新增 / 编辑属性模态子弹窗**：
   - 输入属性名称、标识键；
   - 选择字段类型（下拉选择 / 单行文本）；
   - 平台绑定勾选区：提供「全部平台」勾选框，以及根据 `account_type` 字典动态生成的平台复选框列表（如 Google, ChatGPT, WorkBuddy, Qcoder 等）。

---

## 5. 质量保障与验证方案

1. **后端自动化测试套件 (`pytest`)**：
   - `test_db.py`：测试 `account_attributes` 表创建、默认种子初始化、增删改查、平台绑定 JSON 序列化存储；测试带 `custom_fields_json` 的账号存取；
   - `test_api.py`：测试属性 CRUD API 鉴权与业务规则、测试系统项防删除保护、测试过滤联动。
2. **前端与 UI 测试**：
   - 验证「全部平台」状态下工具栏筛选器仅显示通用属性；
   - 验证切换为「Google」时工具栏自动平滑展开「设备标记」与「Pro选项」下拉框；
   - 验证切换为「ChatGPT」时自动隐藏无关联下拉框；
   - 验证编辑账号弹窗在切换平台时动态切换表单项；
   - 验证设置中心中自定义添加属性及调整绑定平台功能。
3. **编码安全检查**：
   - 使用 `text_guard.py` 扫描所有修改的文件，确保 UTF-8 编码、无 BOM、CRLF 规范且无乱码字符。
