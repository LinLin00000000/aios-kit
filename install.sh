#!/usr/bin/env bash
# One-command installer for aios-kit friend deployments.
# Safe default: install the portable skillpack and create an AIOps vault from the public template.
set -euo pipefail

AIOS_KIT_REPO_URL="${AIOS_KIT_REPO_URL:-https://github.com/LinLin00000000/aios-kit.git}"
AIOPS_TEMPLATE_REPO_URL="${AIOPS_TEMPLATE_REPO_URL:-https://github.com/LinLin00000000/aiops-vault-template.git}"
KIT_DIR="${AIOS_KIT_DIR:-$HOME/.agents/skillpacks/aios-kit}"
TEMPLATE_DIR="${AIOPS_TEMPLATE_DIR:-$HOME/.agents/templates/aiops-vault-template}"
VAULT_PATH="${AIOPS_ROOT:-$HOME/ai-ops}"
WITH_AIOPS=1
DRY_RUN=0
TARGET="universal"
MODE="copy"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Installs the portable aios-kit skillpack and, by default, an AIOps vault
created from the public aiops-vault-template.

Options:
  --kit-dir PATH       Where to clone/update aios-kit (default: ~/.agents/skillpacks/aios-kit)
  --vault PATH         Where to create/update the AIOps vault (default: $AIOPS_ROOT or ~/ai-ops)
  --target TARGET      Skill target for aios skillpack sync: universal|hermes|both (default: universal)
  --mode MODE          Skill install mode: copy|symlink (default: copy; use copy for friends)
  --with-aiops         Install/update the AIOps vault template too (default)
  --no-aiops           Only install the skillpack, do not create ~/ai-ops
  --dry-run            Print actions without changing files
  -h, --help           Show this help

Friend install:
  bash install.sh

Remote one-liner after this file is pushed:
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
EOF
}

log() { printf '\n==> %s\n' "$*"; }
print_cmd() {
  printf '+'
  for arg in "$@"; do printf ' %q' "$arg"; done
  printf '\n'
}
run_visible() {
  print_cmd "$@"
  if [ "$DRY_RUN" -eq 0 ]; then
    command "$@"
  fi
}
need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --kit-dir) KIT_DIR="$2"; shift 2 ;;
    --vault) VAULT_PATH="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --with-aiops) WITH_AIOPS=1; shift ;;
    --no-aiops) WITH_AIOPS=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

case "$TARGET" in universal|hermes|both) ;; *) echo "invalid --target: $TARGET" >&2; exit 2 ;; esac
case "$MODE" in copy|symlink) ;; *) echo "invalid --mode: $MODE" >&2; exit 2 ;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P || true)"
if [ -n "$SCRIPT_DIR" ] && [ -x "$SCRIPT_DIR/aios" ] && [ -f "$SCRIPT_DIR/skillpack.yaml" ]; then
  KIT_DIR="$SCRIPT_DIR"
fi

log "Checking prerequisites"
need_cmd git
need_cmd python3
need_cmd node
need_cmd npx

log "Preparing aios-kit at $KIT_DIR"
if [ ! -f "$KIT_DIR/aios" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ git clone $AIOS_KIT_REPO_URL $KIT_DIR"
  else
    mkdir -p "$(dirname "$KIT_DIR")"
    git clone "$AIOS_KIT_REPO_URL" "$KIT_DIR"
  fi
else
  if [ -d "$KIT_DIR/.git" ]; then
    run_visible git -C "$KIT_DIR" pull --ff-only
  else
    echo "using existing non-git kit dir: $KIT_DIR"
  fi
fi

log "Installing skillpack"
run_visible "$KIT_DIR/aios" skillpack sync --apply --mode "$MODE" --target "$TARGET"
run_visible "$KIT_DIR/aios" skillpack doctor --target "$TARGET"

if [ "$WITH_AIOPS" -eq 1 ]; then
  log "Preparing AIOps vault template at $TEMPLATE_DIR"
  if [ ! -f "$TEMPLATE_DIR/scripts/install.py" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "+ git clone $AIOPS_TEMPLATE_REPO_URL $TEMPLATE_DIR"
    else
      mkdir -p "$(dirname "$TEMPLATE_DIR")"
      git clone "$AIOPS_TEMPLATE_REPO_URL" "$TEMPLATE_DIR"
    fi
  else
    if [ -d "$TEMPLATE_DIR/.git" ]; then
      run_visible git -C "$TEMPLATE_DIR" pull --ff-only
    else
      echo "using existing non-git template dir: $TEMPLATE_DIR"
    fi
  fi

  log "Installing AIOps vault at $VAULT_PATH"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ python3 $TEMPLATE_DIR/scripts/install.py --vault $VAULT_PATH --agent auto --skills-dir $HOME/.agents/skills"
    echo "+ python3 $VAULT_PATH/scripts/aiops.py check"
  else
    python3 "$TEMPLATE_DIR/scripts/install.py" --vault "$VAULT_PATH" --agent auto --skills-dir "$HOME/.agents/skills"
    python3 "$VAULT_PATH/scripts/aiops.py" check
  fi
else
  log "Skipping AIOps vault install (--no-aiops)"
fi

log "Done"
echo "aios-kit: $KIT_DIR"
echo "skills: $HOME/.agents/skills"
if [ "$WITH_AIOPS" -eq 1 ]; then
  echo "ai-ops vault: $VAULT_PATH"
fi
