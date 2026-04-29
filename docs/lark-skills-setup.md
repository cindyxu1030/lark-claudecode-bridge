# Lark Skills Setup

Bridge runs `claude --print` and Claude loads skills from `~/.claude/skills/`. To give the bot Lark capabilities (calendar, mail, docs, etc.), three layers must be set up. None of this lives in the repo — it's all environment / global state on the host.

## Layers

| Layer | Lives in | Purpose |
|-------|----------|---------|
| `lark-cli` binary | `/opt/homebrew/bin/lark-cli` (npm global) | Executes Lark API calls |
| App credentials + tokens | `~/.lark-cli/config.json` | App ID/Secret, OAuth tokens per domain |
| Skill files | `~/.agents/skills/lark-*` (symlinked to `~/.claude/skills/`) | Teaches Claude how to call lark-cli |

## One-time install (per machine)

### 1. Install lark-cli

```bash
npm install -g @larksuite/cli
lark-cli --version  # confirm
```

### 2. Register the app

```bash
APP_ID=$(grep "^FEISHU_APP_ID=" .env | cut -d= -f2)
grep "^FEISHU_APP_SECRET=" .env | cut -d= -f2 | \
  lark-cli config init \
    --app-id "$APP_ID" \
    --app-secret-stdin \
    --brand lark \
    --lang en
```

`--brand lark` for Lark international (larksuite.com); use `--brand feishu` for Feishu (feishu.cn).

### 3. Authorize per domain

Each domain needs its own OAuth login. Browser device flow.

```bash
# Calendar (read/write events, check free/busy)
lark-cli auth login --domain calendar

# Email
lark-cli auth login --domain mail

# Docs
lark-cli auth login --domain docs

# Tasks
lark-cli auth login --domain task

# Or all at once
lark-cli auth login --domain all
```

Each prints a URL + verification code → open URL → grant scopes → terminal auto-detects.

Verify:

```bash
lark-cli auth status
```

Should list granted scopes (e.g. `calendar:calendar.event:read`, `calendar:calendar.event:create`, etc.).

### 4. Install skills

Single domain:

```bash
npx skills add larksuite/cli -s lark-calendar -y -g
```

All domains (recommended — 23 skills):

```bash
npx skills add larksuite/cli -y -g
```

Installs to `~/.agents/skills/lark-*`, symlinks into `~/.claude/skills/`.

### 5. Restart bridge

Skills load at Claude session start. Restart bridge so new sessions pick them up:

```bash
launchctl kickstart -k gui/$(id -u)/com.cindy.lark-claude
```

## App-side requirements (Open Platform)

For each domain you want, the **app** must also have matching scopes enabled:

1. https://open.larksuite.com/app → app → **Permissions & Scopes** (权限管理)
2. Search and enable scopes (e.g. `calendar:calendar`, `calendar:event`, `mail:user_mailbox.message:read`)
3. **Version Management & Release** → create new version → release
4. Wait for admin approval (or auto-approve for test scope)

Without app-side scopes, OAuth in step 3 will fail with "scope not granted" errors.

## Testing

Direct CLI test (bypasses bridge):

```bash
lark-cli calendar +agenda          # today's events
lark-cli mail +inbox               # recent emails
lark-cli task +list                # tasks
```

Bridge end-to-end test — message bot in Lark:

- `Run: lark-cli calendar +agenda`
- `What's on my calendar today?` (auto-trigger via skill description)

If auto-trigger fails (Claude says "no MCP connector"), use explicit prompts:
- `Use the lark-calendar skill to show today's events`
- `Run: lark-cli calendar +agenda`

## Troubleshooting

**"missing required scope"** — App-side scope not enabled, or user OAuth didn't include it. Run `lark-cli auth status` to see granted user scopes; visit Open Platform → Permissions to see app scopes. After app-side change, must release new version.

**Skill not auto-triggering** — Claude in `--print` headless mode sometimes misses skill description matching. Be explicit: name the skill or the command.

**OAuth token expired** — Tokens expire (`expiresAt` in `lark-cli auth status`). Re-run `lark-cli auth login --domain <name>`.

**Brand mismatch** — `--brand feishu` vs `--brand lark` chooses different API domains. Wrong brand = all calls 404. Re-init with correct brand.
