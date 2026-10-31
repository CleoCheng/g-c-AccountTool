# 账号管家桌面应用设计规范 (Account Manager Desktop Design - 优化版)

**日期**：2026-10-30  
**状态**：已评审并完成深度优化 (Optimized & Approved)  
**目标**：构建一个极致轻量（~35MB RAM，空闲 0% CPU）、现代高颜值、100% 离线零外部依赖、聚焦 Google 和 ChatGPT 账号管理的 Windows 桌面应用。具备快递地址式智能容错识别（支持跨行拼接与批量导入）、可辨识脱敏展示、全字段一键复制及原生 TOTP 动态口令生成等核心功能。

---

## 1. 方案合理性审查与六大核心优化点

经过对初版方案的深度复盘，针对实际使用痛点与性能瓶颈进行了以下 **6 项关键优化**：

1. **跨行断行自动拼接与智能特征识别（解决真实粘贴痛点）**
   - **痛点**：从聊天软件或文本复制长账号（如您提供的谷歌格式示例）时，`----` 前后经常带有意外换行（`\n----`），普通按行分割会将其错误拆成两行废数据。
   - **优化**：解析器先执行跨行断行缝合（将 `\n----` 或 `----\n` 自动合并为同一条记录）；同时除按位置解析外，引入**特征启发式识别**（自动识别含 `@` 的辅助邮箱、Base32 特征的 2FA 秘钥、4 位数字年份、国家地区及去空格清洗），即使字段顺序微调或缺失某项也能精准入座。
2. **单条实时回填 + 多条一键批量导入双模式**
   - **优化**：在智能粘贴框中，粘贴 **1 条**时自动回填下方表单供核对微调；若一次性粘贴 **多条账号**，自动识别并开启“一键批量导入 N 条账号”模式，兼顾单条精细编辑与大批量入库。
3. **TOTP 零轮询计算优化（空闲 CPU 占用降至 0%）**
   - **痛点**：若前端每秒通过 IPC 调用 Python 计算所有账号的 2FA 验证码，会导致不必要的进程通信开销。
   - **优化**：由于 TOTP 每 30 秒才变化一次，仅在 **跨越 30 秒整点边界** 或列表变更时批量计算一次 6 位验证码；中间 1~29 秒的环形倒计时完全由前端轻量级时间戳差值驱动，应用静置时 **CPU 占用为 0.0%**。
4. **首尾保留的可辨识邮箱脱敏**
   - **痛点**：若多个邮箱前缀相同（如 `alice_demo.15+nxuw@...` 与 `alice_demo.15+abcd@...`），仅保留前几位脱敏会导致列表里长相完全一样，无法区分。
   - **优化**：采用**首 3 位 + `***` + `@` 前末 2 位 + `@域名`** 的可辨识脱敏算法（例如 `ali***uw@example.com`、`bob***99@gmail.com`），既保护隐私防窥屏，又能一眼区分不同账号。
5. **100% 本地内嵌资源与防白屏启动**
   - **优化**：不依赖任何外部 CDN 字体、图标或样式库，所有 SVG 图标与现代样式 100% 本地内联，断网秒开；`pywebview` 窗口初始化即注入深色背景色 `#0f172a`，彻底消除启动瞬间的白屏闪烁。
6. **彻底的单文件夹数据收敛（含 WebView 运行时缓存）**
   - **优化**：不仅 `accounts.db`（开启 WAL 高性能模式）和 `settings.json` 存放在 `data/` 目录，连同 `pywebview` 的底层 WebView2 运行时缓存目录也强制重定向至 `data/runtime/` 下，确保不在项目根目录或系统目录散落杂乱文件。

---

## 2. 目录组织规范（纯粹整洁）

```text
accountManger/
├── data/                    # [唯一数据与运行状态目录] 备份或迁移仅需拷贝此文件夹
│   ├── accounts.db          # SQLite 本地账号数据库文件 (WAL 模式)
│   ├── settings.json        # 界面配置（主题模式、默认视图等）
│   └── runtime/             # WebView2 本地运行缓存（自动收纳，不污染外部）
├── src/                     # Python 业务核心包
│   ├── __init__.py
│   ├── parser.py            # 智能快递式粘贴解析器（跨行合并、特征识别、批量解析）
│   ├── totp_service.py      # 2FA 动态口令生成、秘钥清洗与脱敏工具函数
│   ├── db_service.py        # SQLite 数据库 CRUD 与统计导出服务
│   └── api.py               # pywebview 前后端桥接 API 类
├── web/                     # 100% 本地化现代 UI 资源（零外部 CDN 依赖）
│   ├── index.html           # 界面主视图与弹窗结构
│   ├── style.css            # 现代化精致样式表（支持暗黑/明亮双主题）
│   └── app.js               # 前端状态管理、30s 边界同步器、一键复制与交互逻辑
├── tests/                   # 自动化单元测试
│   ├── test_parser.py       # 解析器多格式、跨行、乱序容错测试
│   ├── test_totp.py         # TOTP 生成与脱敏函数测试
│   └── test_db.py           # 数据库 CRUD 与搜索过滤测试
├── main.py                  # 桌面应用主入口
├── requirements.txt         # 极简依赖清单 (pywebview, pyotp)
└── run.bat                  # Windows 一键无黑框/快捷启动脚本
```

---

## 3. 数据结构设计 (Data Model)

SQLite 数据库文件存储在 `data/accounts.db`：

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_type TEXT NOT NULL DEFAULT 'ChatGPT', -- 'Google' | 'ChatGPT' | 'Other'
    account TEXT NOT NULL,                        -- 主账号 / 登录邮箱
    password TEXT NOT NULL,                       -- 登录密码
    recovery_email TEXT DEFAULT '',               -- 辅助邮箱 (常见于 Google 账号)
    secret_key TEXT DEFAULT '',                   -- 2FA 秘钥 (清洗后的大写 Base32)
    reg_year TEXT DEFAULT '',                     -- 注册年份 (如 2024)
    reg_region TEXT DEFAULT '',                   -- 注册国家/地区 (如 China)
    note TEXT DEFAULT '',                         -- 自定义备注
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. 核心算法与模块细节

### 4.1 智能粘贴解析器 (`src/parser.py`)
1. **跨行预处理**：
   - 将文本中的 `\r\n` 统一为 `\n`。
   - 正则匹配 `\n\s*----` 或 `----\s*\n`，将其无缝拼接为 `----`，解决长文本复制折行问题。
2. **单行分段提取**：
   - 支持分隔符：`----`、`---`、`----`（带空格）、`|` 或 `\t`。
   - **3 段式标准规则**：`[账号, 密码, 2FA秘钥]` -> 默认归类为 `ChatGPT`（若邮箱后缀为 `@gmail.com` 且用户未指定，可根据上下文智能提示，默认遵循 3 段式为 ChatGPT / 通用，6 段式为 Google，且支持手动一键切换）。
   - **6 段式标准规则**：`[账号, 密码, 辅助邮箱, 2FA秘钥, 注册年份, 注册地区]` -> 自动归类为 `Google`。
   - **4~5 段变体启发式兼容**：遍历第 3 段及之后的字段：
     - 含 `@` 符号 -> 识别为 `recovery_email`（辅助邮箱）
     - 去除空格后为 16~64 位字母数字 Base32 格式 -> 识别为 `secret_key`（2FA 秘钥）
     - 4 位数字（1995-2035） -> 识别为 `reg_year`（注册年份）
     - 其余短文本 -> 识别为 `reg_region`（注册地区）

### 4.2 脱敏与 2FA 服务 (`src/totp_service.py`)
1. **邮箱脱敏 (`mask_email`)**：
   - 若包含 `@`：切分出 `local` 与 `domain`。
   - `local` 长度 > 5：展示 `local[:3] + "***" + local[-2:] + "@" + domain`。
   - `local` 长度 2~5：展示 `local[0] + "***" + local[-1] + "@" + domain`。
   - `local` 长度 <= 1：展示 `local + "***@" + domain`。
2. **密码脱敏 (`mask_password`)**：
   - 固定返回 `"••••••••"`（不暴露真实密码长度）。
3. **2FA 秘钥脱敏 (`mask_secret`)**：
   - 清洗空格并转大写后，若长度 > 8：返回 `secret[:4] + "****" + secret[-4:]`；否则返回 `"****"`。
4. **TOTP 计算 (`generate_totp`)**：
   - 自动剔除秘钥中的空格、横杠并补齐必要的 Base32 `=` 填充。
   - 生成 6 位数字验证码及当前周期剩余秒数 `30 - (int(time.time()) % 30)`。
   - 若秘钥非法，优雅返回 `{"code": "", "valid": False}`，绝不抛出未捕获异常阻断列表加载。

### 4.3 原格式导出与备份
- 支持将选中或全部账号一键复制/导出为标准 `----` 分隔文本格式，方便随时迁移或导出使用。
