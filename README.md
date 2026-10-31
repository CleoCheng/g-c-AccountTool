# 🔐 KeyVault · 账号管家 (Google & ChatGPT Account Manager)

一款极致轻量（~35MB RAM，静置 0% CPU）、100% 本地离线存储、专为 **Google** 与 **ChatGPT / OpenAI** 多账号管理打造的桌面端密钥库与防关联指纹浏览器工作台。

---

## ✨ 核心特性

- 📦 **快递地址式智能识别导入**
  - 支持直接粘贴 `账号----密码----2FA秘钥`（3 段式 ChatGPT）、`账号----密码----辅助邮箱----2FA秘钥----年份----地区`（6 段式 Google）或带购买/停用日期与 `新2FA----` 的多行块。
  - 自动修复跨行断行文本，支持单条实时拆解回填与多条一键批量导入。
- 🔑 **原生 TOTP (2FA) 动态验证码 & 自动清洗**
  - 内置离线 RFC 6238 TOTP 引擎，粘贴或输入 2FA 秘钥时**自动去除空格/连字符并转大写**。
  - 采用 **30 秒整点边界计算 + 前端零轮询时间戳倒计时**，应用后台静置时 CPU 占用为 `0.0%`。
- 🛡️ **安全状态标记 & 生命周期统计**
  - 独立标记 **「密码已改 / 初始密码」** 与 **「2FA已改 / 初始2FA」**，支持卡片/列表一键切换及保留初始 2FA 秘钥备份。
  - 自动根据购买日期与停用日期计算账号在用状态（`使用中` / `已停用`）与累计使用天数。
- 🌐 **账号专属防关联指纹浏览器 (`FP-xxx`)**
  - 每个账号自动配对独立持久化的 Chromium 用户目录与硬件指纹（WebGL 显卡厂商/渲染器、Canvas 噪声种子、AudioContext 频谱微偏、CPU 核心数、内存容量、屏幕分辨率及 WebRTC 防泄漏策略）。
- ⚡ **全自动登录助手 (Google & ChatGPT)**
  - 启动指纹浏览器时通过无痕 CDP 注入专属登录胶囊助手，自动完成 **ChatGPT / OpenAI** 与 **Google** 的邮箱、密码、6 位 2FA 动态口令及辅助邮箱验证填入与提交。
- 🔀 **多代理客户端自适应探测 & 节点永久锁定**
  - 自动适配本机主流代理软件：
    - **Clash / Mihomo 生态**：Clash Verge Rev、Clash Verge、Mihomo Party、Clash Nyanpasu、FlClash、Clash for Windows (CFW)、Mihomo / Clash Meta（同时支持 Windows Named Pipe 与 HTTP `external-controller` 接口，兼容本地 `proxies` 与远程 `proxy-providers` 节点）。
    - **通用代理客户端**：v2rayN、Sing-box、NekoRay、Shadowsocks 及系统代理端口自动探测，并支持手动输入任意自定义 `http://` 或 `socks5://` 代理地址。
  - 支持为单个账号**永久锁定专属代理端口与节点**，未解锁前禁止变更，确保账号网络环境稳定。

---

## 🚀 快速开始

### 1. 环境要求
- **Python**: `3.10+`（推荐 Python 3.11 ~ 3.14）
- **浏览器**: 本机装有 Google Chrome、Microsoft Edge、Brave 或 Chromium 之一（用于驱动独立指纹浏览器）
- **操作系统**: Windows 10/11（原生支持 Edge WebView2 与一键启动器 `KeyVault.exe`），核心代码亦兼容 macOS / Linux

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 启动应用
- **方式一（命令行启动）**：
  ```bash
  python main.py
  ```
- **方式二（Windows 桌面无黑框启动）**：
  直接双击仓库根目录下的 `KeyVault.exe`（自动寻址本机 `.venv` 或系统环境变量中的 `pythonw.exe` 启动）。

---

## 📂 目录结构与隐私安全说明

```text
accountManger/
├── data/                    # [本地私有目录 · 已在 .gitignore 排除]
│   ├── accounts.db          # SQLite 本地数据库 (WAL 模式)
│   ├── settings.json        # 界面配置 (深浅主题、默认视图)
│   ├── runtime/             # WebView2 本地运行缓存
│   └── browsers/            # 各账号独立的指纹浏览器配置与缓存 (acc_1, acc_2...)
├── src/
│   ├── api.py               # pywebview 前后端桥接 API
│   ├── browser_service.py   # 独立指纹生成、无痕 CDP 注入与自动登录引擎
│   ├── db_service.py        # SQLite CRUD、迁移与使用时长统计
│   ├── parser.py            # 智能快递式粘贴解析器
│   ├── proxy_service.py     # 跨客户端代理端口与节点自适应探测/切换服务
│   └── totp_service.py      # 2FA 秘钥清洗、脱敏与 TOTP 计算
├── web/                     # 100% 本地零外部 CDN 依赖前端资源
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/                   # Pytest 自动化测试套件
├── main.py                  # 应用入口
└── requirements.txt         # Python 依赖清单
```

> **🔒 隐私承诺**：所有账号数据、2FA 秘钥及浏览器 Cookie 均 100% 存储在您本地的 `data/` 目录下，应用无任何外部联网统计或云端上传逻辑。备份或迁移时仅需拷贝 `data/` 文件夹即可。

---

## 🧪 运行测试

```bash
python -m pytest -v
```
