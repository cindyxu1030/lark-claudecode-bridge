# lark-agents-bridge

This repo contains Lark/Feishu bridges for local coding agents:

- Claude Code bridge: `main.py`
- Codex bridge: `main_codex.py` and [README-CODEX.md](README-CODEX.md)
- Shared Agent Hub project memory: `/project`, `/brief`, `/task`, `/handoff`, `/sync`

[English](#english) · [中文](#chinese)

Talk to your local Claude Code from inside **Lark** (international) or **Feishu** (国内版). WebSocket long connection, streaming card output, full session management — code review, debug, ask anything from your phone.

> Reuses your Claude Max/Pro subscription. No API key, no public IP, no cloud — runs entirely on your Mac.

This fork has been **tested end-to-end on Lark international** (larksuite.com). The original upstream was built and tested on Feishu (feishu.cn). Both work — the only difference is the `--brand` flag passed to `lark-cli`.

---

<a id="english"></a>

## English

### Features

**Core**

- **Streaming card output** — Claude streams as it thinks; tool-call progress updates live in the Lark card
- **Cross-device sessions** — start on phone, continue from desktop; CLI sessions resume in chat
- **Image recognition** — paste a screenshot, Claude analyzes it
- **Slash commands** — switch model, resume sessions, view usage, manage working directories
- **Skills passthrough** — `/commit`, `/review`, and any installed Claude Code skill works directly in chat

**Group chat (beta)**

- Add bot to a group, **@mention** to talk; un-mentioned messages are silently ignored
- Each group has its own session, model, and working directory — no interference with 1:1
- `/ws` command binds different groups to different project directories; concurrent groups don't block each other

**Deployment**

- **No public IP needed** — Lark/Feishu WebSocket long connection, runs on your own Mac
- **No extra cost** — calls local `claude` CLI, reuses your existing subscription
- **Self-healing** — auto-reconnects on laptop wake; launchd keeps the process alive

### Quick Start

#### Prerequisites

| Dependency | Min version | Verify |
|------------|-------------|--------|
| Python | 3.11+ | `python3 --version` |
| Claude Code CLI | latest | `claude --version` |
| Claude Max/Pro subscription | — | `claude "hi"` works |
| `lark-cli` | latest | `npm install -g @larksuite/cli` |

#### Install & run

```bash
git clone https://github.com/cindyxu1030/lark-agents-bridge.git
cd lark-agents-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env, fill in App ID and Secret (see "App Setup" below)

# Configure lark-cli with your app credentials
APP_ID=$(grep "^FEISHU_APP_ID=" .env | cut -d= -f2)
grep "^FEISHU_APP_SECRET=" .env | cut -d= -f2 | \
  lark-cli config init --app-id "$APP_ID" --app-secret-stdin --brand lark
# Use --brand feishu instead if you're on the Chinese version

# Authorize for messaging events
lark-cli auth login --domain im

python main.py
```

Expected output:

```
🚀 Bot starting...
   App ID      : cli_xxx...
   Event source: lark-cli WebSocket (single connection)
[lark-cli] ✅ Event subscription connected
```

> Upgrading from old versions: run `python migrate_sessions.py` to migrate session data (auto-backup).

### Commands

**Session management**

| Command | Description |
|---------|-------------|
| `/new` | Start a new session |
| `/resume` | List historical sessions |
| `/resume <n>` | Resume session by index |
| `/stop` | Stop the running task |
| `/status` | Show current session info |

**Model and mode**

| Command | Description |
|---------|-------------|
| `/model opus` | Switch model (opus / sonnet / haiku) |
| `/mode bypass` | Switch permission mode |

**Working directory**

| Command | Description |
|---------|-------------|
| `/cd ~/project` | Change working directory |
| `/ls` | List current working directory |
| `/ws save <name> <path>` | Save a named workspace |
| `/ws use <name>` | Bind current chat/group to a workspace |

**Info**

| Command | Description |
|---------|-------------|
| `/usage` | Claude Max usage (macOS) |
| `/skills` | List installed Claude Skills |
| `/mcp` | List MCP servers |
| `/help` | Help |

**Skills passthrough**

Any unregistered slash command (e.g. `/commit`) is forwarded directly to the Claude CLI.

### Architecture

```
┌────────────┐  WebSocket  ┌────────────────┐  subprocess  ┌────────────┐
│ Lark/Feishu│◄───────────►│ lark-claude    │─────────────►│ claude CLI │
│   App      │   long-conn │  (main.py)     │ stream-json  │  (local)   │
└────────────┘             └────────────────┘              └────────────┘
```

Lark/Feishu pushes messages over a WebSocket to the local process. The process invokes `claude` CLI in `--print --output-format stream-json` mode, then patches the Lark card message in real time as output streams.

### App Setup

1. **Create app**
   - Lark: https://open.larksuite.com/app
   - Feishu: https://open.feishu.cn/app
   - Click "Create Custom App"; pick a name (e.g. `Claude Code`) and icon

2. **Add bot capability**
   - App detail page → left sidebar → **Add App Features** (添加应用能力)
   - Add **Bot** (机器人)

3. **Enable permissions** — Permissions & Scopes (权限管理):

   | Scope | Purpose |
   |-------|---------|
   | `im:message` | Read and send 1:1 and group messages |
   | `im:message:send_as_bot` | Send messages as the app/bot |
   | `im:resource` | Download message resources (images, etc.) |

4. **Enable long connection mode**
   - Left sidebar → **Events and Callbacks** (事件与回调) → Event Configuration
   - Subscription mode: **Receive events through persistent connection** (not Webhook)
   - Add event: `im.message.receive_v1`

5. **Get credentials**
   - **Credentials & Basic Info** (凭证与基础信息) page
   - Copy **App ID** and **App Secret** into `.env`

6. **Release version**
   - **Version Management & Release** (版本管理与发布) → Create Version
   - Set availability (specific test members for personal use, or whole org)
   - Submit for review → admin approval → released

> **Important:** every time you change scopes or events, you must create a new version and release it for changes to take effect.

### Environment Variables

| Var | Required | Default | Description |
|-----|:--------:|---------|-------------|
| `FEISHU_APP_ID` | yes | — | App ID (works for both Lark and Feishu) |
| `FEISHU_APP_SECRET` | yes | — | App Secret |
| `DEFAULT_MODEL` | no | `claude-sonnet-4-6` | Default Claude model |
| `DEFAULT_CWD` | no | `~` | Default working directory for `claude` CLI |
| `PERMISSION_MODE` | no | `bypassPermissions` | Tool permission mode |
| `STREAM_CHUNK_SIZE` | no | `20` | Char threshold per streaming card update |
| `CLAUDE_CLI_PATH` | no | auto | Path to `claude` binary |

> The env vars are named `FEISHU_*` for upstream compatibility but apply equally to Lark.

### Persistent Deployment (macOS launchd)

Run as a background service that auto-starts at login and restarts on crash.

```bash
# 1. Edit deploy/lark-claude.plist — change all hardcoded paths to yours
#    (the file currently has /Users/cindy/projects/lark-claudecode-bridge)

# 2. Install and load
cp deploy/lark-claude.plist ~/Library/LaunchAgents/com.cindy.lark-claude.plist
launchctl load ~/Library/LaunchAgents/com.cindy.lark-claude.plist

# 3. Verify
launchctl list | grep lark-claude     # process should be listed
tail -f stdout.log                     # logs in repo dir
```

Operations:

```bash
launchctl kickstart -k gui/$(id -u)/com.cindy.lark-claude    # restart
launchctl unload ~/Library/LaunchAgents/com.cindy.lark-claude.plist   # stop
```

### Lark Skills (Calendar, Mail, Docs, etc.)

To let the bot read/write your calendar, send mail, etc. via Lark APIs, install the official `@larksuite/cli` AI Agent Skills. See [`docs/lark-skills-setup.md`](docs/lark-skills-setup.md) for full setup.

---

<a id="chinese"></a>

## 中文

在 **Lark**（国际版）或**飞书**（国内版）里直接和你本机的 Claude Code 对话。WebSocket 长连接，流式卡片输出，手机上随时 code review、debug、问问题。

> 复用 Claude Max/Pro 订阅，不需要 API Key，不需要公网 IP，全部跑在自己 Mac 上。

本 fork 已在 **Lark 国际版**（larksuite.com）端到端测试通过。原 upstream 仓库基于飞书（feishu.cn）开发测试。两者都能用，区别仅在 `lark-cli` 的 `--brand` 参数。

### 特性

**核心能力**

- **流式卡片输出** — Claude 边想边输出，工具调用进度实时可见
- **Session 跨设备** — 手机上开始的对话，回到电脑前接着聊；CLI 终端的会话也能在飞书 / Lark 恢复
- **图片识别** — 直接发截图给 Claude 分析
- **斜杠命令** — 切换模型、恢复会话、查看用量、管理工作目录
- **Skills 透传** — `/commit`、`/review` 等 Claude Code Skills 直接在 Lark/飞书里用

**群聊支持 (beta)**

- 拉机器人进群，**@机器人** 即可对话，不 @ 的消息静默忽略
- 每个群独立 session、模型、工作目录，和私聊互不干扰
- `/ws` 命令为不同群绑定不同项目目录，多群并发互不阻塞

**部署简单**

- **无需公网 IP** — Lark/飞书 WebSocket 长连接，跑在自己 Mac 上即可
- **零额外成本** — 直接调用本机 `claude` CLI，复用已有订阅
- **休眠自愈** — 笔记本从睡眠唤醒后自动重连，launchd 保活进程

### 快速开始

#### 前置条件

| 依赖 | 最低版本 | 验证 |
|------|---------|------|
| Python | 3.11+ | `python3 --version` |
| Claude Code CLI | 最新 | `claude --version` |
| Claude Max/Pro 订阅 | — | `claude "hi"` 能正常回复 |
| `lark-cli` | 最新 | `npm install -g @larksuite/cli` |

#### 安装与启动

```bash
git clone https://github.com/cindyxu1030/lark-claudecode-bridge.git
cd lark-claudecode-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入 App ID 和 App Secret（见下方「应用配置」）

# 用 App ID/Secret 配置 lark-cli
APP_ID=$(grep "^FEISHU_APP_ID=" .env | cut -d= -f2)
grep "^FEISHU_APP_SECRET=" .env | cut -d= -f2 | \
  lark-cli config init --app-id "$APP_ID" --app-secret-stdin --brand lark
# 飞书国内版改成 --brand feishu

# 授权消息事件接收
lark-cli auth login --domain im

python main.py
```

预期输出：

```
🚀 Bot 启动中...
   App ID      : cli_xxx...
[lark-cli] ✅ 事件订阅已连接
```

> 旧版升级：运行 `python migrate_sessions.py` 迁移 session 数据（自动备份）。

### 命令速查

**会话管理**

| 命令 | 说明 |
|------|------|
| `/new` | 开始新 session |
| `/resume` | 查看历史 sessions |
| `/resume 序号` | 恢复指定 session |
| `/stop` | 停止当前任务 |
| `/status` | 当前 session 信息 |

**模型与模式**

| 命令 | 说明 |
|------|------|
| `/model opus` | 切换模型（opus / sonnet / haiku） |
| `/mode bypass` | 切换权限模式 |

**工作目录**

| 命令 | 说明 |
|------|------|
| `/cd ~/project` | 切换工作目录 |
| `/ls` | 查看当前工作目录 |
| `/ws save 名称 路径` | 保存命名工作空间 |
| `/ws use 名称` | 绑定当前群组/私聊到工作空间 |

**信息查询**

| 命令 | 说明 |
|------|------|
| `/usage` | Claude Max 用量（macOS） |
| `/skills` | 列出 Claude Skills |
| `/mcp` | 列出 MCP Servers |
| `/help` | 帮助 |

**Skills 透传**：未注册的斜杠命令（如 `/commit`）直接转发给 Claude CLI。

### 应用配置

1. **创建应用**
   - Lark：https://open.larksuite.com/app
   - 飞书：https://open.feishu.cn/app
   - 点击「创建企业自建应用」，填名字（如 `Claude Code`）和图标

2. **添加机器人能力** —「添加应用能力」→ 机器人

3. **开启权限**（权限管理页面）：

   | 权限 scope | 说明 |
   |-----------|------|
   | `im:message` | 收发单聊和群聊消息 |
   | `im:message:send_as_bot` | 以应用身份发送消息 |
   | `im:resource` | 下载消息资源（图片等） |

4. **开启长连接模式**
   - 左侧菜单「事件与回调」→ 事件配置
   - 订阅方式选「使用长连接接收事件」（**不是** Webhook）
   - 添加事件 `im.message.receive_v1`

5. **获取凭证** —「凭证与基础信息」页面，复制 App ID 和 App Secret 到 `.env`

6. **发布应用** —「版本管理与发布」→ 创建版本 → 设置可用范围 → 提交审核 → 管理员通过

> **重要**：每次改了 scope 或事件，都必须创建新版本并发布，才会生效。

### 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|:---:|-------|------|
| `FEISHU_APP_ID` | 是 | — | App ID（Lark 和飞书共用） |
| `FEISHU_APP_SECRET` | 是 | — | App Secret |
| `DEFAULT_MODEL` | 否 | `claude-sonnet-4-6` | 默认 Claude 模型 |
| `DEFAULT_CWD` | 否 | `~` | `claude` CLI 默认工作目录 |
| `PERMISSION_MODE` | 否 | `bypassPermissions` | 工具权限模式 |
| `STREAM_CHUNK_SIZE` | 否 | `20` | 流式推送的字符阈值 |
| `CLAUDE_CLI_PATH` | 否 | 自动查找 | Claude CLI 路径 |

> 变量名沿用 `FEISHU_*` 前缀是为了兼容 upstream，对 Lark 同样适用。

### 持久化部署（macOS launchd）

后台常驻服务，开机自启，崩溃自动重启。

```bash
# 1. 编辑 deploy/lark-claude.plist，改成你自己的绝对路径

# 2. 安装并加载
cp deploy/lark-claude.plist ~/Library/LaunchAgents/com.cindy.lark-claude.plist
launchctl load ~/Library/LaunchAgents/com.cindy.lark-claude.plist

# 3. 验证
launchctl list | grep lark-claude
tail -f stdout.log
```

运维：

```bash
launchctl kickstart -k gui/$(id -u)/com.cindy.lark-claude   # 重启
launchctl unload ~/Library/LaunchAgents/com.cindy.lark-claude.plist  # 停服务
```

### Lark Skills（日历、邮件、文档等）

让机器人通过 Lark API 读写日历、收发邮件等，需要装官方 `@larksuite/cli` AI Agent Skills。完整步骤见 [`docs/lark-skills-setup.md`](docs/lark-skills-setup.md)。

---

## Credits

Forked from [joewongjc/feishu-claude-code](https://github.com/joewongjc/feishu-claude-code) by Jonathan. Maintained by Cindy Xu.

## License

[MIT](LICENSE)
