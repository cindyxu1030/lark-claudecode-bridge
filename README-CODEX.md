# Lark Codex Bridge

This is the Codex version of the Lark Claude Code bridge. The Lark event, group chat, card streaming, session, `/ws`, `/cd`, `/resume`, and `/stop` plumbing stays the same; the local agent runner now calls `codex exec --json`.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

Fill `.env` with the same Lark/Feishu app credentials you used for the Claude bridge:

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
LARKSUITE_CLI_BRAND=lark
DEFAULT_MODEL=gpt-5.4
DEFAULT_CWD=/path/to/your/project
PERMISSION_MODE=bypassPermissions
CODEX_HOME=~/.codex
```

Use `LARKSUITE_CLI_BRAND=feishu` for Feishu China.

If one clone runs both Claude and Codex with separate Lark apps, keep separate env files:

```bash
LARK_BRIDGE_ENV_FILE=.env.codex python main_codex.py
```

If Codex is running from a sandboxed context that cannot write to `~/.codex`, create a local writable Codex home and copy only your existing Codex auth/config:

```bash
mkdir -p .codex-home
cp ~/.codex/auth.json .codex-home/auth.json
cp ~/.codex/config.toml .codex-home/config.toml
echo "CODEX_HOME=$(pwd)/.codex-home" >> .env
```

Then start the bridge:

```bash
python main_codex.py
```

Or use the helper script:

```bash
scripts/start-codex-bridge.sh
```

## Lark App Requirements

Enable the same bot setup as the Claude bridge:

- Bot feature enabled
- Long connection event delivery enabled
- Event subscribed: `im.message.receive_v1`
- Published app version approved in the Lark/Feishu admin console

Minimum scopes for group chat:

- `im:message`
- `im:message:send_as_bot`
- `im:message.reactions:write_only`
- `im:resource`

Useful extras:

- `im:chat:read`
- `im:chat.members:read`
- `im:message.reactions:read`

Events:

- `im.message.receive_v1`
- `card.action.trigger`
- Optional for document comments: `drive.notice.comment_add_v1`

## Codex Modes

- `/mode bypass` uses Codex approval `never` with workspace-write sandboxing.
- `/mode default` uses Codex approval-on-request with workspace-write sandboxing.
- `/mode plan` uses a read-only sandbox and prepends a plan-only instruction.
- Set `CODEX_DANGEROUS_BYPASS=true` only if you explicitly want Codex to run with `--dangerously-bypass-approvals-and-sandbox`.

## Agent Hub

Agent Hub stores shared project memory under `~/projects` by default so Codex, Claude Code, Claude Desktop, and Lark group chats can work from the same source of truth.

Recommended pattern:

```text
One project = one folder = one Lark group chat = one memory set
```

Commands:

- `/project` — show current project binding and known projects
- `/project new NAME` — create `~/projects/NAME`, add shared memory files, and bind the current Lark chat
- `/project use NAME_OR_PATH` — bind the current Lark chat to an existing/new project
- `/brief` — show the current project brief from shared memory files
- `/handoff TEXT` — append a handoff note to `HANDOFF.md`
- `/task TEXT` — append a task to `TASKS.md`
- `/sync` — write `PROJECT_BRIEF.md` and a copy in `~/projects/_agent-hub/latest-briefs`
- `/discuss TOPIC` — run a bounded Claude/Codex discussion, post a summary, and save the transcript to `DISCUSSIONS.md`

Group chat routing:

- No bot mention: both Claude and Codex respond
- `@Codex`: only Codex responds
- `@Claude` / `@Claude Code`: only Claude responds

Project memory files:

```text
AGENTS.md
CLAUDE.md
PROJECT_CONTEXT.md
TASKS.md
DECISIONS.md
DISCUSSIONS.md
HANDOFF.md
```
