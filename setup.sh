#!/usr/bin/env bash
set -euo pipefail

# ── Colors & helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

spinner() {
    local chars="/-\|"
    local i=0
    while :; do
        echo -ne "\b${chars:i:1}"
        i=$(( (i + 1) % 4 ))
        sleep 0.3
    done
}
info()  { echo -e "${CYAN}[setup]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENT_FILE="$PROJECT_ROOT/agents/QA_Analyst.md"
COMMAND_FILE="$PROJECT_ROOT/agents/runqa.md"
SECURITY_AGENT_FILE="$PROJECT_ROOT/agents/SecurityAnalyst.md"
SECURITY_COMMAND_FILE="$PROJECT_ROOT/agents/runsecurity.md"
BLACKBOX_AGENT_FILE="$PROJECT_ROOT/agents/BlackBoxAnalyst.md"
BLACKBOX_COMMAND_FILE="$PROJECT_ROOT/agents/runblackbox.md"
CONFIG_DIR="$HOME/.config/opencode"
CONFIG_FILE="$CONFIG_DIR/opencode.json"
API_BASE="http://localhost:8234"

# ── 1. Build & run AutoQA ────────────────────────────────────────────────────
info "Checking if AutoQA is already running..."

if curl -sf "$API_BASE/api/chrome-connection/" >/dev/null 2>&1; then
    ok "AutoQA is already running at $API_BASE"
else
    info "Starting AutoQA with docker compose..."
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" up --build -d || fail "docker compose failed"

    info "Waiting for services to be ready..."
    SPIN_PID=""
    for i in $(seq 1 60); do
        if curl -sf "$API_BASE/api/chrome-connection/" >/dev/null 2>&1; then
            kill "$SPIN_PID" 2>/dev/null || true
            wait "$SPIN_PID" 2>/dev/null || true
            ok "AutoQA is ready (took ${i}s)"
            break
        fi
        if [ -z "$SPIN_PID" ]; then spinner & SPIN_PID=$!; fi
        sleep 1
    done

    if curl -sf "$API_BASE/api/chrome-connection/" >/dev/null 2>&1; then
        : # success handled above
    else
        kill "$SPIN_PID" 2>/dev/null || true
        fail "AutoQA failed to start within 60 seconds. Check: docker compose logs"
    fi
fi

# ── Helper: run a Python snippet inside the Django container ─────────────────
run_django_py() {
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" \
        exec -T web python manage.py shell -c "$1"
}

# ── 2. Ensure at least one user exists ────────────────────────────────────────
USER_COUNT=$(run_django_py "from django.contrib.auth.models import User; print(User.objects.count())")

if [ "$USER_COUNT" -eq 0 ]; then
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  No users found. Let's create your AutoQA account.${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    read -rp "Username: " USERNAME
    [ -z "$USERNAME" ] && fail "Username cannot be empty."

    # Check username availability
    EXISTS=$(run_django_py "from django.contrib.auth.models import User; print(User.objects.filter(username='$USERNAME').exists())")
    [ "$EXISTS" = "True" ] && fail "Username '$USERNAME' already exists."

    echo ""
    read -rsp "Password: " PASSWORD
    echo ""
    read -rsp "Confirm:  " PASSWORD_CONFIRM
    echo ""

    [ -z "$PASSWORD" ] && fail "Password cannot be empty."
    [ "$PASSWORD" != "$PASSWORD_CONFIRM" ] && fail "Passwords do not match."

    info "Creating superuser '$USERNAME'..."

    run_django_py "
from django.contrib.auth.models import User
User.objects.create_superuser('$USERNAME', password='$PASSWORD')
" || fail "Failed to create user."

    ok "User '$USERNAME' created successfully."
else
    ok "Platform already has $USER_COUNT user(s). Skipping user creation."
fi

# ── 3. Create an API key ──────────────────────────────────────────────────────
info "Creating API key for the QA agent..."

API_KEY_OUTPUT=$(run_django_py "
from rest_framework_api_key.models import APIKey
import uuid
prefix = 'autoqa-' + uuid.uuid4().hex[:8]
instance, raw = APIKey.objects.create_key(name='autoqa-agent', prefix=prefix)
print(raw)
")

API_KEY=$(echo "$API_KEY_OUTPUT" | head -1 | tr -d '[:space:]')
[ -z "$API_KEY" ] && fail "Failed to extract API key from output."

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  API KEY (save this — it's shown only once):${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}${BOLD}${API_KEY}${NC}"
echo ""

# ── 4. Copy agent file to OpenCode config ─────────────────────────────────────
if [ ! -f "$AGENT_FILE" ]; then
    fail "Agent file not found at $AGENT_FILE"
fi

mkdir -p "$CONFIG_DIR/agents"
cp "$AGENT_FILE" "$CONFIG_DIR/agents/QA_Analyst.md"
ok "Agent file copied to $CONFIG_DIR/agents/QA_Analyst.md"

# ── 4b. Copy command file to OpenCode config ──────────────────────────────────
if [ ! -f "$COMMAND_FILE" ]; then
    warn "Command file not found at $COMMAND_FILE — skipping"
else
    mkdir -p "$CONFIG_DIR/commands"
    cp "$COMMAND_FILE" "$CONFIG_DIR/commands/runqa.md"
    ok "Command file copied to $CONFIG_DIR/commands/runqa.md"
fi

# ── 4c. Copy security agent file to OpenCode config ───────────────────────────
if [ ! -f "$SECURITY_AGENT_FILE" ]; then
    warn "Security agent file not found at $SECURITY_AGENT_FILE — skipping"
else
    mkdir -p "$CONFIG_DIR/agents"
    cp "$SECURITY_AGENT_FILE" "$CONFIG_DIR/agents/SecurityAnalyst.md"
    ok "Security agent copied to $CONFIG_DIR/agents/SecurityAnalyst.md"
fi

# ── 4e. Copy security command file to OpenCode config ─────────────────────────
if [ ! -f "$SECURITY_COMMAND_FILE" ]; then
    warn "Security command file not found at $SECURITY_COMMAND_FILE — skipping"
else
    mkdir -p "$CONFIG_DIR/commands"
    cp "$SECURITY_COMMAND_FILE" "$CONFIG_DIR/commands/runsecurity.md"
    ok "Security command copied to $CONFIG_DIR/commands/runsecurity.md"
fi

# ── 4f. Copy black-box agent file to OpenCode config ──────────────────────────
if [ ! -f "$BLACKBOX_AGENT_FILE" ]; then
    warn "Black-box agent file not found at $BLACKBOX_AGENT_FILE — skipping"
else
    mkdir -p "$CONFIG_DIR/agents"
    cp "$BLACKBOX_AGENT_FILE" "$CONFIG_DIR/agents/BlackBoxAnalyst.md"
    ok "Black-box agent copied to $CONFIG_DIR/agents/BlackBoxAnalyst.md"
fi

# ── 4g. Copy black-box command file to OpenCode config ────────────────────────
if [ ! -f "$BLACKBOX_COMMAND_FILE" ]; then
    warn "Black-box command file not found at $BLACKBOX_COMMAND_FILE — skipping"
else
    mkdir -p "$CONFIG_DIR/commands"
    cp "$BLACKBOX_COMMAND_FILE" "$CONFIG_DIR/commands/runblackbox.md"
    ok "Black-box command copied to $CONFIG_DIR/commands/runblackbox.md"
fi

# ── 5. Register MCP servers in OpenCode config ────────────────────────────────
info "Updating OpenCode config at $CONFIG_FILE..."

python3 - "$CONFIG_FILE" "$API_KEY" <<'PYEOF'
import json, sys, os
from datetime import datetime

config_path = sys.argv[1]
qa_api_key = sys.argv[2]

class Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

# Load existing config or start fresh
if os.path.exists(config_path):
    with open(config_path, 'r') as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError:
            config = {}
else:
    config = {}

# Ensure required keys exist
if '$schema' not in config:
    config['$schema'] = 'https://opencode.ai/config.json'

if 'mcp' not in config:
    config['mcp'] = {}

# Add/overwrite the QA entry
config['mcp']['autoqa'] = {
    'type': 'remote',
    'url': 'http://localhost:3157/mcp',
    'enabled': True,
    'headers': {
        'X-API-Key': qa_api_key
    }
}

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2, cls=Encoder)
    f.write('\n')
PYEOF

ok "MCP server registered in $CONFIG_FILE"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  AutoQA is ready!${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${CYAN}Platform:${NC}   $API_BASE"
echo -e "  ${CYAN}MCP Server:${NC} http://localhost:3157"
echo -e "  ${CYAN}Chrome CDP:${NC} http://localhost:9222"
echo ""
echo -e "  Start a session with:"
echo -e "  ${BOLD}opencode${NC}"
echo -e "  Then run a command:"
echo -e "  ${BOLD}/runqa${NC}          — QA analysis"
echo -e "  ${BOLD}/runsecurity${NC}    — Security assessment (codebase-based)"
echo -e "  ${BOLD}/runblackbox${NC}   — Black-box security (browser-based)"
echo ""
