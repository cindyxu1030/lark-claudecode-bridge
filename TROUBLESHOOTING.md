# 故障排查

## 机器人"连着但不回消息"

### 症状

- 飞书里给机器人发消息，完全没反应
- 日志里明明有 `✅ 事件订阅已连接`，看起来连上了
- 但永远没有 `[收到消息]` 这一行事件到达
- Watchdog 每 10 分钟重启一次连接，重启后还是同样症状

### 根因：配置被别的 skill 悄悄覆盖了

Bridge 的架构有两条路径：

- **发消息 / 表情 / 图片下载**走 Python SDK 或直接 OpenAPI，读的是项目里的 `.env`
- **收消息**走 `lark-cli` 子进程，启动时会把 `.env` 里的 App ID/Secret/brand 传给子进程

旧版本曾经强依赖全局 `~/.lark-cli/config.json`。如果你同时使用很多 lark-\* skill，仍然建议让全局配置和 bridge 的 `.env` 指向同一个 App，避免手动调试 `lark-cli` 时看错 App。

**打个比方：** 你家装了两部电话，一部（Python SDK）专门拨出去，一部（lark-cli）专门接听。室友（别的 skill）把接听这部电话的号码改了，别人再打你家旧号码进来，那边永远没人接。你自己拨出去还正常，因为那部电话号码没被动。

### 已做的修复

1. `lark-cli event +subscribe` 会收到 bridge `.env` 里的 App ID/Secret/brand
2. `main.py` 的 `lark-cli event +subscribe` 加了 `--force` 参数，启动时强制接管飞书后端的 WebSocket 槽位，避免崩溃残留的幽灵连接吃掉事件
3. 表情 reaction 不再依赖 `lark-cli` token 状态，改为使用 `.env` 里的 App ID/Secret 直接调用 OpenAPI

> 注意：如果你在同一个 clone 里同时跑 Claude 和 Codex，请用 `LARK_BRIDGE_ENV_FILE=.env.claude` / `.env.codex` 分开加载不同 App 凭证。

### 下次自己怎么诊断

症状一样（连着但收不到），按顺序跑这两步：

```bash
# 1. 全局配置现在配的 App ID 是哪个？
lark-cli config show | grep appId

# 2. 和 .env 里的 FEISHU_APP_ID 比对，必须完全一致
grep FEISHU_APP_ID "/ABSOLUTE/PATH/TO/lark-agents-bridge/.env"
```

App ID 对不上，先重新初始化 CLI 配置：

```bash
APP_ID=$(grep "^FEISHU_APP_ID=" .env | cut -d= -f2)
grep "^FEISHU_APP_SECRET=" .env | cut -d= -f2 | \
  lark-cli config init --app-id "$APP_ID" --app-secret-stdin --brand lark
```

飞书国内版把 `--brand lark` 改成 `--brand feishu`，并确认 `.env` 里也有对应的 `LARKSUITE_CLI_BRAND`。

如果 App ID 都对得上但还是收不到，可能的下一层问题：

- 飞书开放平台那边 `im.message.receive_v1` 事件订阅被取消了
- 机器人被管理员禁用或权限被撤销
- App Secret 过期或被刷新（需要重新从开放平台获取并更新两份配置）

### 重启命令速查

```bash
# 完全重启（改了 plist 之后必须这样，kickstart 不会重载环境变量）
launchctl unload ~/Library/LaunchAgents/com.example.lark-claude.plist
launchctl load ~/Library/LaunchAgents/com.example.lark-claude.plist

# 快速踢一脚（没改配置、只是进程卡住了）
launchctl kickstart -k gui/$(id -u)/com.example.lark-claude

# 看日志
tail -f "/ABSOLUTE/PATH/TO/lark-agents-bridge/stdout.log"
```
