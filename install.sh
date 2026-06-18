#!/usr/bin/env bash
# One-command installer for aios-kit friend deployments.
# Safe default: create a unified ~/aios instance, install/update only the
# selected skills in the real agent skills directory, and create an OPS vault
# from the public aiops-vault-template.
set -euo pipefail

AIOS_KIT_REPO_URL="${AIOS_KIT_REPO_URL:-https://github.com/LinLin00000000/aios-kit.git}"
AIOPS_TEMPLATE_REPO_URL="${AIOPS_TEMPLATE_REPO_URL:-https://github.com/LinLin00000000/aiops-vault-template.git}"
LLL_REPO_URL="${LLL_REPO_URL:-https://github.com/LinLin00000000/lins-living-loop.git}"
AIOS_ROOT="${AIOS_ROOT:-$HOME/aios}"
KIT_DIR="${AIOS_KIT_DIR:-}"
TEMPLATE_DIR="${AIOPS_TEMPLATE_DIR:-}"
LLL_DIR="${LLL_DIR:-${AIOS_LLL_DIR:-}}"
VAULT_PATH="${AIOPS_ROOT:-}"
SKILLS_DIR="${AIOS_AGENT_SKILLS_DIR:-${AIOS_SKILLS_DIR:-}}"
KIT_DIR_EXPLICIT=$([ -n "${AIOS_KIT_DIR:-}" ] && echo 1 || echo 0)
TEMPLATE_DIR_EXPLICIT=$([ -n "${AIOPS_TEMPLATE_DIR:-}" ] && echo 1 || echo 0)
LLL_DIR_EXPLICIT=$([ -n "${LLL_DIR:-}" ] && echo 1 || echo 0)
VAULT_PATH_EXPLICIT=$([ -n "${AIOPS_ROOT:-}" ] && echo 1 || echo 0)
SKILLS_DIR_EXPLICIT=$([ -n "${AIOS_AGENT_SKILLS_DIR:-${AIOS_SKILLS_DIR:-}}" ] && echo 1 || echo 0)
WITH_AIOPS=1
DRY_RUN=0
TARGET="universal"
MODE="copy"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Installs a portable AIOS instance rooted at ~/aios by default:
- selected agent skills installed one-by-one under ~/.agents/skills;
- OPS vault under ~/aios/vault/ops;
- LLL work root under ~/aios/work;
- reusable module checkouts under ~/aios/modules.

Options:
  --root PATH          AIOS instance root (default: $AIOS_ROOT or ~/aios)
  --kit-dir PATH       Where to clone/update aios-kit (default: $AIOS_ROOT/modules/aios-kit)
  --lll-dir PATH       Where to clone/update lins-living-loop (default: $AIOS_ROOT/modules/lins-living-loop)
  --vault PATH         Where to create/update the OPS vault (default: $AIOPS_ROOT or $AIOS_ROOT/vault/ops)
  --skills-dir PATH    Agent runtime skills dir (default: ~/.agents/skills)
  --target TARGET      Skill target for aios skillpack sync: universal|hermes|both (default: universal)
  --mode MODE          Skill install mode: copy|symlink (default: copy; use copy for friends)
  --with-aiops         Install/update the OPS vault template too (default)
  --no-aiops           Only install the instance + skillpack, do not create the OPS vault
  --dry-run            Print actions without changing files
  -h, --help           Show this help

Friend install:
  bash install.sh

Remote one-liner after this file is pushed:
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
EOF
}

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
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
    --root) AIOS_ROOT="$2"; shift 2 ;;
    --kit-dir) KIT_DIR="$2"; KIT_DIR_EXPLICIT=1; shift 2 ;;
    --lll-dir) LLL_DIR="$2"; LLL_DIR_EXPLICIT=1; shift 2 ;;
    --vault) VAULT_PATH="$2"; VAULT_PATH_EXPLICIT=1; shift 2 ;;
    --skills-dir) SKILLS_DIR="$2"; SKILLS_DIR_EXPLICIT=1; shift 2 ;;
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

if [ "$KIT_DIR_EXPLICIT" -eq 0 ]; then KIT_DIR="$AIOS_ROOT/modules/aios-kit"; fi
if [ "$TEMPLATE_DIR_EXPLICIT" -eq 0 ]; then TEMPLATE_DIR="$AIOS_ROOT/modules/aiops-vault-template"; fi
if [ "$LLL_DIR_EXPLICIT" -eq 0 ]; then LLL_DIR="$AIOS_ROOT/modules/lins-living-loop"; fi
if [ "$VAULT_PATH_EXPLICIT" -eq 0 ]; then VAULT_PATH="$AIOS_ROOT/vault/ops"; fi
if [ "$SKILLS_DIR_EXPLICIT" -eq 0 ]; then SKILLS_DIR="$HOME/.agents/skills"; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P || true)"
if [ -n "$SCRIPT_DIR" ] && [ -x "$SCRIPT_DIR/aios" ] && [ -f "$SCRIPT_DIR/skillpack.yaml" ] && [ "$KIT_DIR_EXPLICIT" -eq 0 ]; then
  KIT_DIR="$SCRIPT_DIR"
fi

log "Checking prerequisites"
need_cmd git
need_cmd python3
need_cmd node
need_cmd npx

log "Preparing AIOS instance root at $AIOS_ROOT"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "+ mkdir -p $AIOS_ROOT/modules"
else
  mkdir -p "$AIOS_ROOT/modules"
fi

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

log "Initializing AIOS instance layout"
if [ "$DRY_RUN" -eq 1 ]; then
  run_visible "$KIT_DIR/aios" --home "$HOME" init --root "$AIOS_ROOT" --ops "$VAULT_PATH" --skills-dir "$SKILLS_DIR" --dry-run
else
  "$KIT_DIR/aios" --home "$HOME" init --root "$AIOS_ROOT" --ops "$VAULT_PATH" --skills-dir "$SKILLS_DIR"
fi

log "Preparing lins-living-loop module at $LLL_DIR"
if [ ! -f "$LLL_DIR/SKILL.md" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ git clone $LLL_REPO_URL $LLL_DIR"
  else
    mkdir -p "$(dirname "$LLL_DIR")"
    git clone "$LLL_REPO_URL" "$LLL_DIR"
  fi
else
  if [ -d "$LLL_DIR/.git" ]; then
    run_visible git -C "$LLL_DIR" pull --ff-only
  else
    echo "using existing non-git LLL dir: $LLL_DIR"
  fi
fi

log "Installing skillpack"
AIOS_ROOT="$AIOS_ROOT" AIOS_AGENT_SKILLS_DIR="$SKILLS_DIR" run_visible "$KIT_DIR/aios" --home "$HOME" skillpack sync --apply --mode "$MODE" --target "$TARGET"
AIOS_ROOT="$AIOS_ROOT" AIOS_AGENT_SKILLS_DIR="$SKILLS_DIR" run_visible "$KIT_DIR/aios" --home "$HOME" skillpack doctor --target "$TARGET"

if [ "$WITH_AIOPS" -eq 1 ]; then
  log "Preparing OPS vault template at $TEMPLATE_DIR"
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

  log "Installing OPS vault at $VAULT_PATH"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ python3 $TEMPLATE_DIR/scripts/install.py --vault $VAULT_PATH --agent auto --skills-dir $SKILLS_DIR"
    echo "+ AIOPS_ROOT=$VAULT_PATH python3 $VAULT_PATH/scripts/aiops.py check"
  else
    python3 "$TEMPLATE_DIR/scripts/install.py" --vault "$VAULT_PATH" --agent auto --skills-dir "$SKILLS_DIR"
    AIOPS_ROOT="$VAULT_PATH" python3 "$VAULT_PATH/scripts/aiops.py" check
  fi
else
  log "Skipping OPS vault install (--no-aiops)"
fi

log "Done"
echo "AIOS root: $AIOS_ROOT"
echo "aios-kit: $KIT_DIR"
echo "lins-living-loop: $LLL_DIR"
echo "agent runtime skills: $SKILLS_DIR"
if [ "$WITH_AIOPS" -eq 1 ]; then
  echo "OPS vault: $VAULT_PATH"
fi
