import os
import shutil
from dotenv import load_dotenv

ENV_FILE = os.getenv("LARK_BRIDGE_ENV_FILE") or os.getenv("ENV_FILE") or ".env"
load_dotenv(ENV_FILE)

FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]

CLAUDE_CLI = os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude") or "claude"
CODEX_CLI = os.getenv("CODEX_CLI_PATH") or shutil.which("codex") or "codex"
CODEX_HOME = os.path.expanduser(os.getenv("CODEX_HOME", "~/.codex"))

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
DEFAULT_CWD = os.path.expanduser(os.getenv("DEFAULT_CWD", "~"))
PERMISSION_MODE = os.getenv("PERMISSION_MODE", "bypassPermissions")

SESSIONS_DIR = os.path.expanduser(os.getenv("SESSIONS_DIR", "~/.lark-claude"))
PROJECTS_ROOT = os.path.expanduser(os.getenv("PROJECTS_ROOT", "~/projects"))
AGENT_HUB_ROOT = os.path.expanduser(os.getenv("AGENT_HUB_ROOT", os.path.join(PROJECTS_ROOT, "_agent-hub")))

BOT_MENTION_OPEN_IDS = [v.strip() for v in os.getenv("BOT_MENTION_OPEN_IDS", "").split(",") if v.strip()]
OTHER_BOT_MENTION_OPEN_IDS = [v.strip() for v in os.getenv("OTHER_BOT_MENTION_OPEN_IDS", "").split(",") if v.strip()]

COLLAB_COORDINATOR_AGENT = os.getenv("COLLAB_COORDINATOR_AGENT", "codex").strip().lower()
COLLAB_CLAUDE_MODEL = os.getenv("COLLAB_CLAUDE_MODEL", "claude-sonnet-4-6")
COLLAB_CODEX_MODEL = os.getenv("COLLAB_CODEX_MODEL", "gpt-5.4")

# 卡片按钮回调 HTTP 端口（需 ngrok 暴露）
CALLBACK_PORT = int(os.getenv("CALLBACK_PORT", "9981"))

# 流式卡片更新：每积累多少字符推送一次
STREAM_CHUNK_SIZE = int(os.getenv("STREAM_CHUNK_SIZE", "20"))
