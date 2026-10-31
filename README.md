# 🔐 KeyVault · 账号管家 (Google & ChatGPT Account Manager)

一款轻量、100% 本地离线存储、专为 **Google** 与 **ChatGPT / OpenAI** 多账号管理打造的桌面端密钥库与防关联指纹浏览器工作台。

> [!WARNING]
> **使用前请阅读文末「⚠️ 免责声明」。** 本项目仅供学习研究及管理您本人合法拥有的账号。

---

## ✨ 核心特性

- 📦 **快递地址式智能识别导入**
  - 支持直接粘贴 `----` 或 `|` 分隔格式（如 `账号----密码----2FA秘钥` 或 `账号|密码|2FA`）、6 段式 Google 或带购买/停用日期与 `新2FA` 的多行块。
  - 自动修复跨行断行文本，支持单条实时拆解回填与多条一键批量导入。
- 🔑 **原生 TOTP (2FA) 动态验证码 & 自动清洗**
  - 内置离线 RFC 6238 TOTP 引擎，粘贴或输入 2FA 秘钥时**自动去除空格/连字符并转大写**。
  - 仅在 30 秒整点边界计算验证码，倒计时由前端时间戳驱动，后台静置几乎不占 CPU。
- 🛡️ **安全状态标记 & 生命周期统计**
  - 独立标记 **「密码已改 / 初始密码」** 与 **「2FA已改 / 初始2FA」**，支持一键切换及保留初始 2FA 秘钥备份。
  - 根据购买日期与停用日期自动计算账号状态（`使用中` / `已停用`）与累计使用天数。
- 🌐 **账号专属独立浏览器环境 (`FP-xxx`)**
  - 每个账号配对独立持久化的 Chromium 用户目录与硬件指纹参数（WebGL、Canvas、AudioContext、CPU 核心数、内存、屏幕分辨率、WebRTC 防泄漏策略）。
- ⚡ **自动登录助手 (Google & ChatGPT)**
  - 启动浏览器时注入登录助手，自动填入邮箱、密码、6 位 2FA 动态口令及辅助邮箱。
- 🔀 **代理客户端自适应探测 & 节点锁定**
  - **Clash / Mihomo 生态**：Clash Verge Rev、Clash Verge、Mihomo Party、Clash Nyanpasu、FlClash、Clash for Windows、Mihomo / Clash Meta（支持 Windows Named Pipe 与 HTTP `external-controller`，兼容 `proxy-providers` 远程订阅节点）。
  - **其他客户端**：v2rayN、Sing-box、NekoRay、Shadowsocks 等常见本地端口及系统代理自动探测；也可手动输入任意 `http://` / `socks5://` 代理地址。
  - 可为单个账号**锁定专属代理端口与节点**，未解锁前禁止变更。

---

## 💻 平台支持

| 平台 | 状态 |
|---|---|
| **Windows 10 / 11** | ✅ 主要开发与测试平台（含 `KeyVault.exe` 一键启动器） |
| macOS / Linux | ⚠️ 未充分测试。核心代码做了跨平台路径适配，但指纹 User-Agent 目前固定为 Windows，与真实系统不一致 |

---

## 🚀 快速开始

### 1. 环境要求
- **Python** `3.10+`
- **浏览器**：Google Chrome、Microsoft Edge、Brave 或 Chromium 任一
- **Node.js**（可选，仅运行测试需要：`tests/test_browser.py` 会用 Node 校验 JS 版 TOTP 实现）

### 2. 安装依赖
```bash
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 启动
- **命令行**：`python main.py`
- **Windows 无黑框启动**：双击根目录的 `KeyVault.exe`。它会按以下顺序寻找 Python：项目内 `.venv` / `venv` → `PATH` 中的 `pythonw.exe` → 常见安装目录。

### 4. 可选环境变量

| 变量 | 作用 |
|---|---|
| `KEYVAULT_BROWSER_PATH` | 指定浏览器可执行文件路径（自动探测失败时使用） |
| `KEYVAULT_CLASH_CONFIG` | 指定 Clash / Mihomo 配置文件路径（优先于自动探测） |

---

## 🔨 关于 `KeyVault.exe`

`KeyVault.exe` 只是一个极简启动器（约 80 行 C#），作用是用 `pythonw.exe` 无窗口运行 `main.py`，**不包含任何业务逻辑**。完整源码见 [`tools/launcher/KeyVaultLauncher.cs`](tools/launcher/KeyVaultLauncher.cs)。

如不信任仓库内的二进制文件，可以删除后自行编译（使用 Windows 自带的 .NET Framework 编译器，无需安装 Visual Studio）：

```powershell
powershell -ExecutionPolicy Bypass -File tools\launcher\build.ps1
```

> 未签名的小型启动器偶尔会被杀毒软件误报，自行编译或直接使用 `python main.py` 均可。

---

## 📂 目录结构

```text
.
├── data/                    # [本地私有 · 已被 .gitignore 排除] 首次运行自动创建
│   ├── accounts.db          # SQLite 数据库 (WAL 模式)
│   ├── settings.json        # 界面配置
│   ├── runtime/             # WebView2 运行缓存
│   └── browsers/            # 各账号独立的浏览器配置目录 (acc_1, acc_2 ...)
├── src/
│   ├── api.py               # pywebview 前后端桥接 API
│   ├── browser_service.py   # 指纹配置生成、CDP 注入与自动登录
│   ├── db_service.py        # SQLite CRUD、迁移与使用时长统计
│   ├── parser.py            # 智能粘贴解析器
│   ├── proxy_service.py     # 代理端口与节点探测/切换
│   └── totp_service.py      # 2FA 秘钥清洗、脱敏与 TOTP 计算
├── web/                     # 纯本地前端资源（无外部 CDN）
├── tools/launcher/          # KeyVault.exe 源码与编译脚本
├── tests/                   # Pytest 测试
├── main.py                  # 应用入口
└── requirements.txt
```

> **🔒 隐私**：所有账号数据、2FA 秘钥及浏览器 Cookie 仅保存在本地 `data/` 目录，应用不包含任何统计上报或云端上传逻辑。备份 / 迁移只需拷贝 `data/` 文件夹。**`data/` 中为明文存储，请自行保管好设备与备份。**

---

## 🧪 运行测试

```bash
python -m pytest -v
```

---

## ⚠️ 免责声明

- 本项目仅供**学习研究**以及**管理您本人合法拥有的账号**使用。
- Google、OpenAI 等平台的服务条款可能限制自动化登录、多账号操作或规避风控检测的行为。**使用者须自行了解并遵守相关平台条款及所在地法律法规**，因使用本项目导致的账号封禁、数据丢失或其他任何损失，由使用者自行承担。
- 严禁将本项目用于盗用他人账号、批量注册、账号倒卖、欺诈等任何违法违规用途。
- 本项目按「现状」提供，不提供任何明示或暗示的担保，详见 [LICENSE](LICENSE)。

---

## 📄 开源协议

本项目基于 [Apache License 2.0](LICENSE) 开源。
