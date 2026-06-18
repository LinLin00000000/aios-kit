#!/usr/bin/env bash
# One-command installer for aios-kit deployments.
# Default path is interactive and conservative; all major choices also have
# flags for non-interactive automation.
set -euo pipefail

AIOS_GITHUB_MIRROR_PREFIX="${AIOS_GITHUB_MIRROR_PREFIX:-}"
AIOS_KIT_REPO_URL="${AIOS_KIT_REPO_URL:-https://github.com/LinLin00000000/aios-kit.git}"
AIOPS_TEMPLATE_REPO_URL="${AIOPS_TEMPLATE_REPO_URL:-https://github.com/LinLin00000000/aiops-vault-template.git}"
LLL_REPO_URL="${LLL_REPO_URL:-https://github.com/LinLin00000000/lins-living-loop.git}"
HERMES_INSTALL_URL="${HERMES_INSTALL_URL:-https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh}"
MIHOMO_DOWNLOAD_URL="${MIHOMO_DOWNLOAD_URL:-}"
MIHOMO_VERSION="${MIHOMO_VERSION:-v1.19.27}"
MIHOMO_RELEASE_BASE_URL="${MIHOMO_RELEASE_BASE_URL:-https://github.com/MetaCubeX/mihomo/releases/download}"
PROXY_SUBSCRIPTION_URL="${PROXY_SUBSCRIPTION_URL:-}"
PROXY_PROXIES_FILE="${PROXY_PROXIES_FILE:-}"
PROXY_AUTO_ENV="${PROXY_AUTO_ENV:-auto}"
MIHOMO_EXTERNAL_UI_URL="${MIHOMO_EXTERNAL_UI_URL:-https://github.com/MetaCubeX/metacubexd/archive/refs/heads/gh-pages.zip}"
MIHOMO_GEO_BASE_URL="${MIHOMO_GEO_BASE_URL:-https://github.com/DustinWin/ruleset_geodata/releases/download/mihomo-geodata}"

AIOS_ROOT="${AIOS_ROOT:-$HOME/aios}"
KIT_DIR="${AIOS_KIT_DIR:-}"
TEMPLATE_DIR="${AIOPS_TEMPLATE_DIR:-}"
LLL_DIR="${LLL_DIR:-${AIOS_LLL_DIR:-}}"
VAULT_PATH="${AIOPS_ROOT:-}"
SKILLS_DIR="${AIOS_AGENT_SKILLS_DIR:-${AIOS_SKILLS_DIR:-}}"
GLOBAL_BIN_DIR="${AIOS_GLOBAL_BIN_DIR:-}"
KIT_DIR_EXPLICIT=$([ -n "${AIOS_KIT_DIR:-}" ] && echo 1 || echo 0)
TEMPLATE_DIR_EXPLICIT=$([ -n "${AIOPS_TEMPLATE_DIR:-}" ] && echo 1 || echo 0)
LLL_DIR_EXPLICIT=$([ -n "${LLL_DIR:-}" ] && echo 1 || echo 0)
VAULT_PATH_EXPLICIT=$([ -n "${AIOPS_ROOT:-}" ] && echo 1 || echo 0)
SKILLS_DIR_EXPLICIT=$([ -n "${AIOS_AGENT_SKILLS_DIR:-${AIOS_SKILLS_DIR:-}}" ] && echo 1 || echo 0)
GLOBAL_BIN_EXPLICIT=$([ -n "${AIOS_GLOBAL_BIN_DIR:-}" ] && echo 1 || echo 0)

WITH_AIOPS=1
WITH_DEV_ENV=1
WITH_CORE=1
WITH_HERMES=1
WITH_PROXY="auto"
PROXY_TUN=1
RESET_SOURCES=1
ADD_TO_PATH="ask"
INTERACTIVE="auto"
ASSUME_YES=0
DRY_RUN=0
TARGET="universal"
MODE="copy"
FORCE=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Default: run an interactive AIOS bootstrap for a new server. The same flow can
be automated with flags for repeatable operations.

Core options:
  --root PATH              AIOS instance root (default: $AIOS_ROOT or ~/aios)
  --kit-dir PATH           aios-kit checkout (default: $AIOS_ROOT/modules/aios-kit)
  --lll-dir PATH           lins-living-loop checkout (default: $AIOS_ROOT/modules/lins-living-loop)
  --vault PATH             OPS vault path (default: $AIOS_ROOT/vault/ops)
  --skills-dir PATH        Agent runtime skills dir (default: ~/.agents/skills)
  --global-bin DIR         Link `aios` into DIR, e.g. ~/.local/bin; refuses conflicts
  --add-to-path yes|no|ask Add ~/aios/bin to shell PATH block (default: ask in interactive)
  --github-mirror PREFIX    Prefix GitHub/raw release URLs, e.g. https://gh-proxy.com/

Network/proxy:
  --proxy auto|yes|no      auto: test direct external network first (default)
  --proxy-tun              Enable TUN in the Mihomo config (default)
  --no-proxy-tun           Disable TUN; shell proxy env auto-start becomes useful
  --proxy-subscription-url URL  Provider subscription URL; rendered as proxy-providers
  --proxy-proxies-file PATH     Local YAML snippet with proxies: or a proxy list
  --proxy-auto-env auto|yes|no  Auto-run proxy_on in shell helpers (default: auto; yes when TUN is off)
  --mihomo-url URL         Optional Mihomo .gz binary URL; otherwise release asset URL is derived
  --mihomo-version VERSION  Mihomo version tag for derived URL (default: v1.19.27; use latest to query GitHub API)
  --reset-sources          Restore apt/npm/pip/Docker source config toward official defaults (default)
  --no-reset-sources       Do not touch source config

Install phases:
  --with-dev-env           Install/check Python+UV, NVM+Node 24 LTS, Docker, Caddy (default)
  --no-dev-env             Skip development/runtime packages
  --with-core              Install/check Hermes and skill dirs (default)
  --no-core                Skip Hermes/core component phase
  --with-aiops             Install/update OPS vault template too (default)
  --no-aiops               Skip OPS vault template

Skillpack:
  --target TARGET          universal|hermes|both (default: universal)
  --mode MODE              copy|symlink (default: copy)
  --force                  Overwrite locally modified managed skill copies

Automation:
  --non-interactive        Never prompt; use defaults/flags
  --interactive            Prompt even when stdin is not detected as TTY
  -y, --yes                Non-interactive yes for optional recommended steps
  --dry-run                Print actions without changing files
  -h, --help               Show this help

One-line install:
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"

Non-interactive example:
  bash install.sh --non-interactive -y --root ~/aios --proxy auto --add-to-path yes --target universal --mode copy
EOF
}

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
print_cmd() { printf '+'; for arg in "$@"; do printf ' %q' "$arg"; done; printf '\n'; }
run_visible() { print_cmd "$@"; if [ "$DRY_RUN" -eq 0 ]; then command "$@"; fi; }
have_cmd() { command -v "$1" >/dev/null 2>&1; }
need_cmd() { if ! have_cmd "$1"; then echo "missing required command: $1" >&2; exit 1; fi; }

mirror_url() {
  url="$1"
  prefix="$AIOS_GITHUB_MIRROR_PREFIX"
  [ -n "$prefix" ] || { printf '%s\n' "$url"; return 0; }
  case "$url" in
    https://github.com/*|https://raw.githubusercontent.com/*)
      case "$prefix" in */) printf '%s%s\n' "$prefix" "$url" ;; *) printf '%s/%s\n' "$prefix" "$url" ;; esac ;;
    *) printf '%s\n' "$url" ;;
  esac
}

is_interactive() {
  [ "$INTERACTIVE" = "yes" ] && return 0
  [ "$INTERACTIVE" = "no" ] && return 1
  [ -t 0 ] && [ -t 1 ]
}

ask_choice() {
  # ask_choice VAR prompt default allowed-values
  var="$1"; prompt="$2"; default="$3"; allowed="$4"
  current="$(eval "printf '%s' \"\${$var:-}\"")"
  if ! is_interactive; then
    [ -n "$current" ] || eval "$var=\"$default\""
    return 0
  fi
  while true; do
    printf "%s [%s]: " "$prompt" "$default"
    read -r ans || ans=""
    ans="${ans:-$default}"
    case " $allowed " in *" $ans "*) eval "$var=\"$ans\""; return 0 ;; esac
    printf 'Please enter one of: %s\n' "$allowed"
  done
}

ask_text() {
  var="$1"; prompt="$2"; default="$3"
  current="$(eval "printf '%s' \"\${$var:-}\"")"
  if ! is_interactive; then
    [ -n "$current" ] || eval "$var=\"$default\""
    return 0
  fi
  printf "%s [%s]: " "$prompt" "$default"
  read -r ans || ans=""
  ans="${ans:-$default}"
  eval "$var=\"$ans\""
}

ask_path() {
  var="$1"; prompt="$2"; default="$3"
  current="$(eval "printf '%s' \"\${$var:-}\"")"
  if ! is_interactive; then
    [ -n "$current" ] || eval "$var=\"$default\""
    return 0
  fi
  printf "%s [%s]: " "$prompt" "$default"
  read -r ans || ans=""
  ans="${ans:-$default}"
  eval "$var=\"$ans\""
}

expand_path() {
  case "$1" in
    ~) printf '%s\n' "$HOME" ;;
    ~/*) printf '%s/%s\n' "$HOME" "${1#~/}" ;;
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$(pwd)" "$1" ;;
  esac
}

validate_path() {
  label="$1"; raw="$2"; expanded="$(expand_path "$raw")"
  case "$expanded" in
    /|/bin|/boot|/dev|/etc|/lib|/lib64|/proc|/root|/run|/sbin|/sys|/usr|/var)
      echo "invalid $label path: $expanded" >&2; exit 2 ;;
  esac
  case "$expanded" in *$'\n'*|*'..'* ) echo "invalid $label path: $raw" >&2; exit 2 ;; esac
  printf '%s\n' "$expanded"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --root) AIOS_ROOT="$2"; shift 2 ;;
    --kit-dir) KIT_DIR="$2"; KIT_DIR_EXPLICIT=1; shift 2 ;;
    --lll-dir) LLL_DIR="$2"; LLL_DIR_EXPLICIT=1; shift 2 ;;
    --vault) VAULT_PATH="$2"; VAULT_PATH_EXPLICIT=1; shift 2 ;;
    --skills-dir) SKILLS_DIR="$2"; SKILLS_DIR_EXPLICIT=1; shift 2 ;;
    --global-bin) GLOBAL_BIN_DIR="$2"; GLOBAL_BIN_EXPLICIT=1; shift 2 ;;
    --add-to-path) ADD_TO_PATH="$2"; shift 2 ;;
    --github-mirror) AIOS_GITHUB_MIRROR_PREFIX="$2"; shift 2 ;;
    --proxy) WITH_PROXY="$2"; shift 2 ;;
    --proxy-tun) PROXY_TUN=1; shift ;;
    --no-proxy-tun) PROXY_TUN=0; shift ;;
    --proxy-subscription-url) PROXY_SUBSCRIPTION_URL="$2"; shift 2 ;;
    --proxy-proxies-file) PROXY_PROXIES_FILE="$2"; shift 2 ;;
    --proxy-auto-env) PROXY_AUTO_ENV="$2"; shift 2 ;;
    --mihomo-url) MIHOMO_DOWNLOAD_URL="$2"; shift 2 ;;
    --mihomo-version) MIHOMO_VERSION="$2"; shift 2 ;;
    --reset-sources) RESET_SOURCES=1; shift ;;
    --no-reset-sources) RESET_SOURCES=0; shift ;;
    --with-dev-env) WITH_DEV_ENV=1; shift ;;
    --no-dev-env) WITH_DEV_ENV=0; shift ;;
    --with-core) WITH_CORE=1; shift ;;
    --no-core) WITH_CORE=0; shift ;;
    --with-aiops) WITH_AIOPS=1; shift ;;
    --no-aiops) WITH_AIOPS=0; shift ;;
    --target) TARGET="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --non-interactive) INTERACTIVE="no"; shift ;;
    --interactive) INTERACTIVE="yes"; shift ;;
    -y|--yes) ASSUME_YES=1; INTERACTIVE="no"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

case "$TARGET" in universal|hermes|both) ;; *) echo "invalid --target: $TARGET" >&2; exit 2 ;; esac
case "$MODE" in copy|symlink) ;; *) echo "invalid --mode: $MODE" >&2; exit 2 ;; esac
case "$WITH_PROXY" in auto|yes|no) ;; *) echo "invalid --proxy: $WITH_PROXY" >&2; exit 2 ;; esac
case "$ADD_TO_PATH" in yes|no|ask) ;; *) echo "invalid --add-to-path: $ADD_TO_PATH" >&2; exit 2 ;; esac
case "$PROXY_AUTO_ENV" in auto|yes|no) ;; *) echo "invalid --proxy-auto-env: $PROXY_AUTO_ENV" >&2; exit 2 ;; esac

if is_interactive; then
  log "AIOS interactive bootstrap"
  ask_path AIOS_ROOT "AIOS install root" "$AIOS_ROOT"
  ask_choice WITH_PROXY "Proxy setup" "$WITH_PROXY" "auto yes no"
  ask_choice PROXY_TUN "Enable Mihomo TUN mode? (1=yes, 0=no)" "$PROXY_TUN" "0 1"
  ask_text PROXY_SUBSCRIPTION_URL "Proxy subscription URL, leave empty if using a proxies YAML file" "$PROXY_SUBSCRIPTION_URL"
  ask_text PROXY_PROXIES_FILE "Local proxies YAML snippet path, leave empty if using subscription" "$PROXY_PROXIES_FILE"
  ask_choice WITH_DEV_ENV "Install/check Python+UV, Node 24, Docker, Caddy? (1=yes, 0=no)" "$WITH_DEV_ENV" "0 1"
  ask_choice WITH_CORE "Install/check Hermes core components? (1=yes, 0=no)" "$WITH_CORE" "0 1"
  ask_choice WITH_AIOPS "Install/update OPS vault template? (1=yes, 0=no)" "$WITH_AIOPS" "0 1"
  ask_choice ADD_TO_PATH "Add AIOS bin to PATH?" "yes" "yes no"
fi

AIOS_ROOT="$(validate_path AIOS_ROOT "$AIOS_ROOT")"
if [ "$KIT_DIR_EXPLICIT" -eq 0 ]; then KIT_DIR="$AIOS_ROOT/modules/aios-kit"; fi
if [ "$TEMPLATE_DIR_EXPLICIT" -eq 0 ]; then TEMPLATE_DIR="$AIOS_ROOT/modules/aiops-vault-template"; fi
if [ "$LLL_DIR_EXPLICIT" -eq 0 ]; then LLL_DIR="$AIOS_ROOT/modules/lins-living-loop"; fi
if [ "$VAULT_PATH_EXPLICIT" -eq 0 ]; then VAULT_PATH="$AIOS_ROOT/vault/ops"; fi
if [ "$SKILLS_DIR_EXPLICIT" -eq 0 ]; then SKILLS_DIR="$HOME/.agents/skills"; fi
KIT_DIR="$(validate_path KIT_DIR "$KIT_DIR")"
TEMPLATE_DIR="$(validate_path TEMPLATE_DIR "$TEMPLATE_DIR")"
LLL_DIR="$(validate_path LLL_DIR "$LLL_DIR")"
VAULT_PATH="$(validate_path VAULT_PATH "$VAULT_PATH")"
SKILLS_DIR="$(validate_path SKILLS_DIR "$SKILLS_DIR")"
AIOS_BIN_DIR="$AIOS_ROOT/bin"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P || true)"
if [ -n "$SCRIPT_DIR" ] && [ -x "$SCRIPT_DIR/aios" ] && [ -f "$SCRIPT_DIR/skillpack.yaml" ] && [ "$KIT_DIR_EXPLICIT" -eq 0 ]; then
  KIT_DIR="$SCRIPT_DIR"
fi

check_direct_network() {
  have_cmd curl || return 1
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
    curl -fsSI --noproxy '*' --connect-timeout 6 https://github.com >/dev/null 2>&1
}

install_package_if_missing() {
  cmd="$1"; shift
  if have_cmd "$cmd"; then
    echo "OK $cmd already installed: $(command -v "$cmd")"
    return 0
  fi
  if have_cmd apt-get; then
    run_visible sudo apt-get update
    run_visible sudo apt-get install -y "$@"
  else
    warn "no apt-get found; please install missing command manually: $cmd"
    return 1
  fi
}

reset_sources_to_official() {
  [ "$RESET_SOURCES" -eq 1 ] || return 0
  log "Resetting package sources toward official defaults"
  if have_cmd npm; then run_visible npm config delete registry || true; fi
  if have_cmd python3; then run_visible python3 -m pip config unset global.index-url || true; fi
  if have_cmd apt-get; then
    echo "APT official source reset is distro-specific; keeping existing files unless you provide an OS profile."
  fi
  echo "Docker official repository will be configured by Docker install step when needed."
}

install_mihomo() {
  log "Preparing Mihomo/Clash proxy"
  mihomo_dir="$AIOS_ROOT/network/mihomo"
  mihomo_bin="$mihomo_dir/mihomo"
  config_path="$mihomo_dir/config.yaml"
  provider_dir="$mihomo_dir/providers"
  auto_env="$PROXY_AUTO_ENV"
  [ "$auto_env" = "auto" ] && { if [ "$PROXY_TUN" -eq 1 ]; then auto_env="no"; else auto_env="yes"; fi; }

  if [ -n "$PROXY_PROXIES_FILE" ]; then
    PROXY_PROXIES_FILE="$(validate_path PROXY_PROXIES_FILE "$PROXY_PROXIES_FILE")"
    if [ ! -f "$PROXY_PROXIES_FILE" ]; then echo "invalid --proxy-proxies-file: $PROXY_PROXIES_FILE" >&2; exit 2; fi
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ mkdir -p $mihomo_dir $provider_dir"
    echo "+ generate $config_path from template"
  else
    mkdir -p "$mihomo_dir" "$provider_dir"
    python3 - "$KIT_DIR/templates/mihomo/config.yaml" "$config_path" "$PROXY_TUN" "$PROXY_SUBSCRIPTION_URL" "$PROXY_PROXIES_FILE" "$AIOS_GITHUB_MIRROR_PREFIX" <<'PY'
import re, sys
from pathlib import Path
src, dst, tun, sub_url, proxies_file, mirror_prefix = sys.argv[1:7]
base = Path(src).read_text(encoding='utf-8')
base = re.sub(r'tun:\n  enable: (true|false)', 'tun:\n  enable: ' + ('true' if tun == '1' else 'false'), base)
if mirror_prefix:
    prefix = mirror_prefix.rstrip('/')
    base = re.sub(r'https://[^/]+/https://github\.com/', prefix + '/https://github.com/', base)

def repl_url(match):
    url = match.group(1)
    prefix = mirror_prefix.rstrip('/')
    if prefix and (url.startswith('https://github.com/') or url.startswith('https://raw.githubusercontent.com/')):
        return '"' + prefix + '/' + url + '"'
    return match.group(0)
base = re.sub(r'"(https://github\.com/[^"]+)"', repl_url, base)

if sub_url:
    provider_names = ['airport']
    providers = (
        'proxy-providers:\n'
        '  airport: { type: http, url: "' + sub_url + '", interval: 86400, path: ./providers/airport.yaml }\n'
        'proxies: []\n\n'
    )
elif proxies_file:
    raw = Path(proxies_file).read_text(encoding='utf-8').rstrip() + '\n'
    if re.search(r'^\s*proxies\s*:', raw, re.M):
        proxies_block = raw
    else:
        indented = ''.join(('  ' + line if line.strip() else line) + '\n' for line in raw.splitlines())
        proxies_block = 'proxies:\n' + indented
    provider_names = []
    node_names=[]
    for m in re.finditer(r'^\s*-\s*name\s*:\s*["\']?([^"\'\n#]+)', raw, re.M):
        name=m.group(1).strip()
        if name and name not in node_names:
            node_names.append(name)
    providers = 'proxy-providers: {}\n' + proxies_block + '\n'
else:
    provider_names=[]
    node_names=[]
    providers = 'proxy-providers: {}\nproxies: []\n\n'

def flow_seq(items, fallback='DIRECT'):
    items=[x for x in items if x]
    if not items:
        items=[fallback]
    return '[' + ', '.join(items) + ']'

def flow_seq_prepend(prefix_items, items):
    merged=[]
    for x in list(prefix_items) + list(items):
        if x and x not in merged:
            merged.append(x)
    return '[' + ', '.join(merged) + ']'

if sub_url:
    use = flow_seq(provider_names)
    groups = (
        'proxy-groups:\n'
        f'  - {{ name: AI, type: url-test, interval: 300, tolerance: 100, lazy: true, use: {use}, url: http://www.gstatic.com/generate_204, exclude-filter: "(?i)香港|hk|hong|港|澳门|macao|macau|澳|台湾|台|tw|taiwan|剩余|到期|距离" }}\n'
        f'  - {{ name: Auto, type: url-test, interval: 300, tolerance: 100, lazy: true, use: {use}, url: http://www.gstatic.com/generate_204 }}\n'
        f'  - {{ name: PROXY, type: select, proxies: [Auto, DIRECT], use: {use} }}\n'
        '  - { name: GLOBAL, type: select, proxies: [PROXY, DIRECT, REJECT] }\n'
    )
elif proxies_file:
    nodes = flow_seq(node_names)
    proxy_select = flow_seq_prepend(['Auto', 'DIRECT'], node_names)
    groups = (
        'proxy-groups:\n'
        f'  - {{ name: AI, type: url-test, interval: 300, tolerance: 100, lazy: true, proxies: {nodes}, url: http://www.gstatic.com/generate_204, exclude-filter: "(?i)香港|hk|hong|港|澳门|macao|macau|澳|台湾|台|tw|taiwan|剩余|到期|距离" }}\n'
        f'  - {{ name: Auto, type: url-test, interval: 300, tolerance: 100, lazy: true, proxies: {nodes}, url: http://www.gstatic.com/generate_204 }}\n'
        f'  - {{ name: PROXY, type: select, proxies: {proxy_select} }}\n'
        '  - { name: GLOBAL, type: select, proxies: [PROXY, DIRECT, REJECT] }\n'
    )
else:
    groups = (
        'proxy-groups:\n'
        '  - { name: AI, type: url-test, interval: 300, tolerance: 100, lazy: true, proxies: [DIRECT], url: http://www.gstatic.com/generate_204, exclude-filter: "(?i)香港|hk|hong|港|澳门|macao|macau|澳|台湾|台|tw|taiwan|剩余|到期|距离" }\n'
        '  - { name: Auto, type: url-test, interval: 300, tolerance: 100, lazy: true, proxies: [DIRECT], url: http://www.gstatic.com/generate_204 }\n'
        '  - { name: PROXY, type: select, proxies: [Auto, DIRECT] }\n'
        '  - { name: GLOBAL, type: select, proxies: [PROXY, DIRECT, REJECT] }\n'
    )
base = re.sub(r'proxy-providers: \{\}\nproxies: \[\]\n\nproxy-groups:\n(?s:.*?)\nrules:', providers + groups + '\nrules:', base)
Path(dst).write_text(base, encoding='utf-8')
PY
  fi

  if have_cmd mihomo; then
    echo "OK mihomo already installed: $(command -v mihomo)"
  elif [ -x "$mihomo_bin" ]; then
    echo "OK mihomo already installed: $mihomo_bin"
  else
    arch="$(uname -m)"
    case "$arch" in
      x86_64|amd64) mihomo_arch="amd64" ;;
      aarch64|arm64) mihomo_arch="arm64" ;;
      *) warn "unsupported arch for automatic Mihomo download: $arch"; mihomo_arch="" ;;
    esac
    if [ -n "$mihomo_arch" ]; then
      url="$MIHOMO_DOWNLOAD_URL"
      if [ -z "$url" ]; then
        if [ "$MIHOMO_VERSION" = "latest" ]; then
          tag="$(python3 - <<'PY'
import json, urllib.request
try:
    with urllib.request.urlopen('https://api.github.com/repos/MetaCubeX/mihomo/releases/latest', timeout=20) as r:
        print(json.load(r)['tag_name'])
except Exception:
    print('')
PY
)"
        else
          tag="$MIHOMO_VERSION"
        fi
        if [ -n "$tag" ]; then
          url="$(mirror_url "$MIHOMO_RELEASE_BASE_URL/$tag/mihomo-linux-$mihomo_arch-${tag}.gz")"
        fi
      fi
      if [ -n "$url" ]; then
        if [ "$DRY_RUN" -eq 1 ]; then
          echo "+ curl -fL $url | gzip -dc > $mihomo_bin"
          echo "+ chmod +x $mihomo_bin"
        else
          tmp="$mihomo_dir/mihomo.download.gz"
          curl -fL "$url" -o "$tmp"
          gzip -dc "$tmp" > "$mihomo_bin"
          chmod +x "$mihomo_bin"
          rm -f "$tmp"
        fi
      else
        warn "could not resolve Mihomo release URL; pass --mihomo-url or set MIHOMO_RELEASE_BASE_URL"
      fi
    fi
  fi

  service_bin="$mihomo_bin"
  have_cmd mihomo && service_bin="$(command -v mihomo)"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ install /etc/systemd/system/aios-mihomo.service and enable/start it when systemd is available"
  elif have_cmd systemctl && [ -x "$service_bin" ]; then
    unit="/etc/systemd/system/aios-mihomo.service"
    sudo tee "$unit" >/dev/null <<EOF
[Unit]
Description=AIOS Mihomo proxy service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$mihomo_dir
ExecStart=$service_bin -d $mihomo_dir
Restart=always
RestartSec=5
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
NoNewPrivileges=false

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now aios-mihomo.service || warn "failed to enable/start aios-mihomo.service; check systemctl status aios-mihomo.service"
  else
    warn "systemd or Mihomo binary not available; config generated at $config_path"
  fi

  helpers="$HOME/.bashrc"
  block_start="# AIOS proxy helpers"
  helper_block="$(cat <<'EOF'
# AIOS proxy helpers
export AIOS_PROXY_HOST="127.0.0.1"
export AIOS_PROXY_PORT="7890"
proxy_on() { export http_proxy="http://$AIOS_PROXY_HOST:$AIOS_PROXY_PORT" https_proxy="http://$AIOS_PROXY_HOST:$AIOS_PROXY_PORT" all_proxy="socks5://$AIOS_PROXY_HOST:$AIOS_PROXY_PORT" HTTP_PROXY="$http_proxy" HTTPS_PROXY="$https_proxy" ALL_PROXY="$all_proxy"; }
proxy_off() { unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY; }
proxy_test() { curl -I --max-time 10 https://www.gstatic.com/generate_204; }
proxy_direct_test() { env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY curl -I --max-time 10 https://github.com; }
proxy_restart() { sudo systemctl restart aios-mihomo.service; }
EOF
)"
  if [ "$auto_env" = "yes" ]; then
    helper_block="$helper_block
proxy_on"
  fi
  helper_block="$helper_block
# End AIOS proxy helpers
"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ add proxy_on/proxy_off helpers to $helpers (auto_env=$auto_env)"
    echo "+ configure sudoers env_keep for proxy variables"
  else
    if ! grep -q "$block_start" "$helpers" 2>/dev/null; then
      printf '%s' "$helper_block" >> "$helpers"
    fi
    if have_cmd sudo; then
      printf '%s\n' 'Defaults env_keep += "http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY"' | sudo tee /etc/sudoers.d/aios-proxy-env >/dev/null
      sudo chmod 440 /etc/sudoers.d/aios-proxy-env
    fi
  fi

  if [ -z "$PROXY_SUBSCRIPTION_URL" ] && [ -z "$PROXY_PROXIES_FILE" ]; then
    warn "No proxy subscription or proxies file provided; generated a safe placeholder config. Re-run with --proxy-subscription-url or --proxy-proxies-file for a usable proxy."
  fi
}

install_dev_env() {
  log "Installing/checking development environment"
  install_package_if_missing curl curl
  install_package_if_missing git git
  install_package_if_missing python3 python3 python3-venv
  if have_cmd uv; then echo "OK uv already installed: $(command -v uv)"; else run_visible sh -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'; fi
  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    echo "OK nvm already installed: $HOME/.nvm/nvm.sh"
  else
    nvm_install_url="$(mirror_url https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh)"
    run_visible sh -c "curl -fsSL '$nvm_install_url' | bash"
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ . $HOME/.nvm/nvm.sh && nvm install 24 && nvm alias default 24"
  else
    # shellcheck disable=SC1091
    [ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh" && nvm install 24 && nvm alias default 24 || warn "nvm not available in this shell yet"
  fi
  if have_cmd docker; then
    echo "OK docker already installed: $(command -v docker)"
  else
    run_visible sh -c 'curl -fsSL https://get.docker.com | sh'
  fi
  if have_cmd caddy; then
    echo "OK caddy already installed: $(command -v caddy)"
  elif have_cmd apt-get; then
    run_visible sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gpg
    run_visible sh -c 'curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg'
    run_visible sh -c 'curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null'
    run_visible sudo apt-get update
    run_visible sudo apt-get install -y caddy
  else
    warn "Caddy install is OS-repo specific; install manually or add an OS profile later."
  fi
}

install_hermes_core() {
  log "Installing/checking Hermes core components"
  if have_cmd hermes; then
    echo "OK hermes already installed: $(command -v hermes)"
  else
    hermes_install_url="$(mirror_url "$HERMES_INSTALL_URL")"
    run_visible sh -c "curl -fsSL '$hermes_install_url' | bash"
  fi
  # Hermes external skill directory convention: universal skills live in ~/.agents/skills.
  if have_cmd hermes; then
    run_visible hermes config set skills.external_dirs "$HOME/.agents/skills" || warn "Hermes external_dirs config may differ by version; check hermes config edit"
  else
    echo "Hermes not on PATH yet; after install, set external skill dir to $HOME/.agents/skills"
  fi
}

record_aiops_resource() {
  [ -f "$VAULT_PATH/scripts/aiops.py" ] || return 0
  component="$1"
  echo "Recording $component in OPS vault is template-specific; current fallback appends maintenance log."
  log_file="$VAULT_PATH/maintenance-log.jsonl"
  entry="{\"ts\":\"$(date -Iseconds)\",\"component\":\"$component\",\"event\":\"installed-or-present-by-aios-installer\"}"
  if [ "$DRY_RUN" -eq 1 ]; then echo "+ append $log_file: $entry"; else printf '%s\n' "$entry" >> "$log_file"; fi
}

log "Checking minimal prerequisites"
need_cmd git
need_cmd python3
if ! have_cmd node || ! have_cmd npx; then
  warn "node/npx missing; dev environment phase will install NVM + Node 24 if enabled."
fi

if [ "$WITH_PROXY" = "auto" ]; then
  log "Testing direct external network without proxy environment"
  if check_direct_network; then
    echo "Direct external network works; skipping proxy setup."
    WITH_PROXY="no"
  else
    echo "Direct external network failed; Mihomo/Clash proxy setup is recommended."
    WITH_PROXY="yes"
    if is_interactive; then
      ask_choice WITH_PROXY "Install Mihomo proxy now?" "yes" "yes no"
    fi
  fi
fi

log "Preparing AIOS instance root at $AIOS_ROOT"
if [ "$DRY_RUN" -eq 1 ]; then echo "+ mkdir -p $AIOS_ROOT/modules"; else mkdir -p "$AIOS_ROOT/modules"; fi

log "Preparing aios-kit at $KIT_DIR"
if [ ! -f "$KIT_DIR/aios" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then echo "+ git clone $(mirror_url "$AIOS_KIT_REPO_URL") $KIT_DIR"; else mkdir -p "$(dirname "$KIT_DIR")"; git clone "$(mirror_url "$AIOS_KIT_REPO_URL")" "$KIT_DIR"; fi
else
  if [ -d "$KIT_DIR/.git" ]; then run_visible git -C "$KIT_DIR" pull --ff-only; else echo "using existing non-git kit dir: $KIT_DIR"; fi
fi

log "Installing aios command shim"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "+ mkdir -p $AIOS_BIN_DIR"
  echo "+ ln -sfn $KIT_DIR/aios $AIOS_BIN_DIR/aios"
else
  mkdir -p "$AIOS_BIN_DIR"
  ln -sfn "$KIT_DIR/aios" "$AIOS_BIN_DIR/aios"
fi

if [ "$ADD_TO_PATH" = "ask" ]; then
  if [ "$ASSUME_YES" -eq 1 ]; then ADD_TO_PATH="yes"; else ADD_TO_PATH="no"; fi
fi
if [ "$ADD_TO_PATH" = "yes" ]; then
  path_block='\n# AIOS\nexport PATH="$HOME/aios/bin:$PATH"\n'
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ add AIOS PATH block to $HOME/.bashrc if missing"
  elif ! grep -q 'AIOS' "$HOME/.bashrc" 2>/dev/null; then
    printf '%b' "$path_block" >> "$HOME/.bashrc"
  fi
fi

if [ -n "$GLOBAL_BIN_DIR" ]; then
  GLOBAL_BIN_DIR="$(validate_path GLOBAL_BIN_DIR "$GLOBAL_BIN_DIR")"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ mkdir -p $GLOBAL_BIN_DIR"
    echo "+ ln -s $KIT_DIR/aios $GLOBAL_BIN_DIR/aios"
  else
    mkdir -p "$GLOBAL_BIN_DIR"
    if [ -e "$GLOBAL_BIN_DIR/aios" ] || [ -L "$GLOBAL_BIN_DIR/aios" ]; then
      if [ -L "$GLOBAL_BIN_DIR/aios" ] && [ "$(readlink "$GLOBAL_BIN_DIR/aios")" = "$KIT_DIR/aios" ]; then :; else warn "refusing to replace existing $GLOBAL_BIN_DIR/aios"; fi
    else
      ln -s "$KIT_DIR/aios" "$GLOBAL_BIN_DIR/aios"
    fi
  fi
fi

if [ "$WITH_PROXY" = "yes" ]; then
  install_mihomo
  reset_sources_to_official
fi

if [ "$WITH_DEV_ENV" -eq 1 ]; then install_dev_env; fi

log "Initializing AIOS instance layout"
init_args=("$KIT_DIR/aios" --home "$HOME" init --root "$AIOS_ROOT" --ops "$VAULT_PATH" --skills-dir "$SKILLS_DIR")
[ "$DRY_RUN" -eq 1 ] && init_args+=(--dry-run)
run_visible "${init_args[@]}"

log "Preparing lins-living-loop module at $LLL_DIR"
if [ ! -f "$LLL_DIR/SKILL.md" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then echo "+ git clone $(mirror_url "$LLL_REPO_URL") $LLL_DIR"; else mkdir -p "$(dirname "$LLL_DIR")"; git clone "$(mirror_url "$LLL_REPO_URL")" "$LLL_DIR"; fi
else
  if [ -d "$LLL_DIR/.git" ]; then run_visible git -C "$LLL_DIR" pull --ff-only; else echo "using existing non-git LLL dir: $LLL_DIR"; fi
fi

if [ "$WITH_CORE" -eq 1 ]; then install_hermes_core; fi

if ! have_cmd npx && [ "$DRY_RUN" -eq 0 ]; then
  warn "npx is still missing; cannot install external skillpack entries. Re-run after Node/NVM shell reload."
else
  log "Installing skillpack"
  force_arg=""; [ "$FORCE" -eq 1 ] && force_arg="--force"
  skillpack_args=("$KIT_DIR/aios" --home "$HOME" skillpack sync --mode "$MODE" --target "$TARGET")
  [ "$DRY_RUN" -eq 0 ] && skillpack_args+=(--apply)
  [ -n "$force_arg" ] && skillpack_args+=("$force_arg")
  AIOS_ROOT="$AIOS_ROOT" AIOS_AGENT_SKILLS_DIR="$SKILLS_DIR" run_visible "${skillpack_args[@]}"
  AIOS_ROOT="$AIOS_ROOT" AIOS_AGENT_SKILLS_DIR="$SKILLS_DIR" run_visible "$KIT_DIR/aios" --home "$HOME" skillpack doctor --target "$TARGET"
fi

if [ "$WITH_AIOPS" -eq 1 ]; then
  log "Preparing OPS vault template at $TEMPLATE_DIR"
  if [ ! -f "$TEMPLATE_DIR/scripts/install.py" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then echo "+ git clone $(mirror_url "$AIOPS_TEMPLATE_REPO_URL") $TEMPLATE_DIR"; else mkdir -p "$(dirname "$TEMPLATE_DIR")"; git clone "$(mirror_url "$AIOPS_TEMPLATE_REPO_URL")" "$TEMPLATE_DIR"; fi
  else
    if [ -d "$TEMPLATE_DIR/.git" ]; then run_visible git -C "$TEMPLATE_DIR" pull --ff-only; else echo "using existing non-git template dir: $TEMPLATE_DIR"; fi
  fi
  log "Installing OPS vault at $VAULT_PATH"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ python3 $TEMPLATE_DIR/scripts/install.py --vault $VAULT_PATH --agent auto --skills-dir $SKILLS_DIR"
    echo "+ AIOPS_ROOT=$VAULT_PATH python3 $VAULT_PATH/scripts/aiops.py check"
  else
    python3 "$TEMPLATE_DIR/scripts/install.py" --vault "$VAULT_PATH" --agent auto --skills-dir "$SKILLS_DIR"
    AIOPS_ROOT="$VAULT_PATH" python3 "$VAULT_PATH/scripts/aiops.py" check
  fi
  record_aiops_resource docker
  record_aiops_resource caddy
else
  log "Skipping OPS vault install (--no-aiops)"
fi

log "Done"
echo "AIOS root: $AIOS_ROOT"
echo "aios-kit: $KIT_DIR"
echo "aios command: $AIOS_BIN_DIR/aios"
echo "lins-living-loop: $LLL_DIR"
echo "agent runtime skills: $SKILLS_DIR"
[ "$WITH_AIOPS" -eq 1 ] && echo "OPS vault: $VAULT_PATH"
exit 0
