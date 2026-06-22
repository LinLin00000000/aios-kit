#!/usr/bin/env bash
# One-command installer for aios-kit deployments.
# Default path is interactive and conservative; all major choices also have
# flags for non-interactive automation.
set -euo pipefail

AIOS_GITHUB_MIRROR_PREFIX="${AIOS_GITHUB_MIRROR_PREFIX:-}"
AIOS_KIT_REPO_URL="${AIOS_KIT_REPO_URL:-https://github.com/LinLin00000000/aios-kit.git}"
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
AIOS_INSTALL_RELEASE_TAG="${AIOS_INSTALL_RELEASE_TAG:-latest}"
AIOS_INSTALL_RELEASE_BASE_URL="${AIOS_INSTALL_RELEASE_BASE_URL:-https://github.com/LinLin00000000/aios-kit/releases}"
AIOS_INSTALL_SCRIPT_URL="${AIOS_INSTALL_SCRIPT_URL:-https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh}"

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
INSTALL_WIZARD="auto"
SKIP_SKILLPACK=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Capability model:
  Core features are the portable AIOS base: local instance root, aios-kit and
  LLL modules, command shims, runtime skills target, work/vault/config/state
  directories, and local-on-demand use when the machine is powered on. These
  are intended to be cross-platform; this Bash backend currently targets
  Ubuntu/Debian-style Linux, while install.ps1 provides the Windows native core.

  Add-on features are platform/server capabilities: Mihomo/TUN, source reset,
  Docker/Caddy/dev-env bootstrap, Hermes setup, OPS vault template install, and
  Linux service/24x7 operation. They are useful on Linux servers but are not
  required for the base AIOS install.

Default: run an interactive AIOS bootstrap for a Linux machine. The same flow
can be automated with flags for repeatable operations.

Core options:
  --root PATH              AIOS instance root (default: $AIOS_ROOT or ~/aios)
  --kit-dir PATH           aios-kit checkout (default: current repo when run from a checkout, otherwise $AIOS_ROOT/modules/aios-kit)
  --lll-dir PATH           lins-living-loop checkout (default: $AIOS_ROOT/modules/lins-living-loop)
  --vault PATH             OPS vault path (default: $AIOS_ROOT/vault/ops)
  --skills-dir PATH        Agent runtime skills dir (default: ~/.agents/skills)
  --global-bin DIR         Link `aios` and `lll` into DIR, e.g. ~/.local/bin; refuses conflicts
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
  --with-hermes            Install/check Hermes Agent and configure its external skill dir (default)
  --no-hermes              Skip Hermes Agent install/config; useful for Codex/Claude/OpenClaw users
  --with-core              Legacy alias for --with-hermes
  --no-core                Legacy alias for --no-hermes
  --with-aiops             Install/update OPS vault template too (default)
  --no-aiops               Skip OPS vault template

Skillpack:
  --target TARGET          universal|hermes|both (default: universal)
  --mode MODE              copy|symlink (default: copy)
  --force                  Overwrite locally modified managed skill copies
  --skip-skillpack         Skip skillpack sync/doctor; intended for core smoke tests only

Automation:
  --non-interactive        Never prompt; use defaults/flags
  --interactive            Prompt even when stdin is not detected as TTY
  -y, --yes                Non-interactive yes for optional recommended steps
  --dry-run                Print actions without changing files
  --wizard                 Launch the modern Go/huh AIOS installer wizard
  --no-wizard              Use the built-in Bash prompts instead of the modern wizard
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
require_arg() {
  opt="$1"
  count="$2"
  if [ "$count" -lt 2 ]; then
    echo "missing value for $opt" >&2
    usage >&2
    exit 2
  fi
}

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


ask_yes_no() {
  prompt="$1"; default="$2"
  if ! is_interactive; then
    case "$default" in y|Y|yes|YES|1|true) return 0 ;; *) return 1 ;; esac
  fi
  while true; do
    case "$default" in
      y|Y|yes|YES|1|true) suffix="Y/n" ;;
      *) suffix="y/N" ;;
    esac
    printf "%s [%s]: " "$prompt" "$suffix"
    read -r ans || ans=""
    ans="${ans:-$default}"
    case "$ans" in
      y|Y|yes|YES|1|true) return 0 ;;
      n|N|no|NO|0|false) return 1 ;;
    esac
    printf 'Please enter yes or no.\n'
  done
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
    --root) require_arg "$1" "$#"; AIOS_ROOT="$2"; shift 2 ;;
    --kit-dir) require_arg "$1" "$#"; KIT_DIR="$2"; KIT_DIR_EXPLICIT=1; shift 2 ;;
    --lll-dir) require_arg "$1" "$#"; LLL_DIR="$2"; LLL_DIR_EXPLICIT=1; shift 2 ;;
    --vault) require_arg "$1" "$#"; VAULT_PATH="$2"; VAULT_PATH_EXPLICIT=1; shift 2 ;;
    --skills-dir) require_arg "$1" "$#"; SKILLS_DIR="$2"; SKILLS_DIR_EXPLICIT=1; shift 2 ;;
    --global-bin) require_arg "$1" "$#"; GLOBAL_BIN_DIR="$2"; GLOBAL_BIN_EXPLICIT=1; shift 2 ;;
    --add-to-path) require_arg "$1" "$#"; ADD_TO_PATH="$2"; shift 2 ;;
    --github-mirror) require_arg "$1" "$#"; AIOS_GITHUB_MIRROR_PREFIX="$2"; shift 2 ;;
    --proxy) require_arg "$1" "$#"; WITH_PROXY="$2"; shift 2 ;;
    --proxy-tun) PROXY_TUN=1; shift ;;
    --no-proxy-tun) PROXY_TUN=0; shift ;;
    --proxy-subscription-url) require_arg "$1" "$#"; PROXY_SUBSCRIPTION_URL="$2"; shift 2 ;;
    --proxy-proxies-file) require_arg "$1" "$#"; PROXY_PROXIES_FILE="$2"; shift 2 ;;
    --proxy-auto-env) require_arg "$1" "$#"; PROXY_AUTO_ENV="$2"; shift 2 ;;
    --mihomo-url) require_arg "$1" "$#"; MIHOMO_DOWNLOAD_URL="$2"; shift 2 ;;
    --mihomo-version) require_arg "$1" "$#"; MIHOMO_VERSION="$2"; shift 2 ;;
    --reset-sources) RESET_SOURCES=1; shift ;;
    --no-reset-sources) RESET_SOURCES=0; shift ;;
    --with-dev-env) WITH_DEV_ENV=1; shift ;;
    --no-dev-env) WITH_DEV_ENV=0; shift ;;
    --with-hermes|--with-core) WITH_HERMES=1; WITH_CORE=1; shift ;;
    --no-hermes|--no-core) WITH_HERMES=0; WITH_CORE=0; shift ;;
    --with-aiops) WITH_AIOPS=1; shift ;;
    --no-aiops) WITH_AIOPS=0; shift ;;
    --target) require_arg "$1" "$#"; TARGET="$2"; shift 2 ;;
    --mode) require_arg "$1" "$#"; MODE="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --skip-skillpack) SKIP_SKILLPACK=1; shift ;;
    --non-interactive) INTERACTIVE="no"; shift ;;
    --interactive) INTERACTIVE="yes"; shift ;;
    -y|--yes) ASSUME_YES=1; INTERACTIVE="no"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --wizard) INSTALL_WIZARD="yes"; shift ;;
    --no-wizard) INSTALL_WIZARD="no"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

case "$TARGET" in universal|hermes|both) ;; *) echo "invalid --target: $TARGET" >&2; exit 2 ;; esac
case "$MODE" in copy|symlink) ;; *) echo "invalid --mode: $MODE" >&2; exit 2 ;; esac
case "$WITH_PROXY" in auto|yes|no) ;; *) echo "invalid --proxy: $WITH_PROXY" >&2; exit 2 ;; esac
case "$ADD_TO_PATH" in yes|no|ask) ;; *) echo "invalid --add-to-path: $ADD_TO_PATH" >&2; exit 2 ;; esac
case "$PROXY_AUTO_ENV" in auto|yes|no) ;; *) echo "invalid --proxy-auto-env: $PROXY_AUTO_ENV" >&2; exit 2 ;; esac
case "$INSTALL_WIZARD" in auto|yes|no) ;; *) echo "invalid wizard setting: $INSTALL_WIZARD" >&2; exit 2 ;; esac

SCRIPT_DIR=""
SCRIPT_SOURCE="${BASH_SOURCE[0]:-}"
SCRIPT_BASENAME="${SCRIPT_SOURCE##*/}"
case "$SCRIPT_BASENAME" in bash|sh|-bash|-sh) SCRIPT_SOURCE="" ;; esac
if [ -n "$SCRIPT_SOURCE" ] && [ -f "$SCRIPT_SOURCE" ]; then
  SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" 2>/dev/null && pwd -P || true)"
fi
aios_install_platform() {
  os="$(uname -s 2>/dev/null || true)"
  arch="$(uname -m 2>/dev/null || true)"
  case "$os" in
    Linux) goos="linux" ;;
    Darwin) goos="darwin" ;;
    *) return 1 ;;
  esac
  case "$arch" in
    x86_64|amd64) goarch="amd64" ;;
    aarch64|arm64) goarch="arm64" ;;
    *) return 1 ;;
  esac
  printf '%s_%s\n' "$goos" "$goarch"
}

aios_install_release_url() {
  asset="$1"
  case "$AIOS_INSTALL_RELEASE_TAG" in
    latest) printf '%s\n' "$(mirror_url "$AIOS_INSTALL_RELEASE_BASE_URL/latest/download/$asset")" ;;
    *) printf '%s\n' "$(mirror_url "$AIOS_INSTALL_RELEASE_BASE_URL/download/$AIOS_INSTALL_RELEASE_TAG/$asset")" ;;
  esac
}

verify_sha256_file() {
  checksum_file="$1"
  archive="$2"
  expected_name="$3"
  expected="$(awk -v name="$expected_name" '$2 == name { print $1; found=1; exit } END { if (!found) exit 1 }' "$checksum_file" || true)"
  if [ -z "$expected" ]; then
    echo "checksum entry not found for $expected_name" >&2
    return 1
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$expected" "$archive" | sha256sum -c - >/dev/null
  elif command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$archive" | awk '{print $1}')"
    [ "$actual" = "$expected" ]
  else
    echo "missing sha256sum or shasum for checksum verification" >&2
    return 1
  fi
}

download_aios_install() {
  platform="$(aios_install_platform)" || { warn "unsupported OS/arch for aios-install release binary: $(uname -s 2>/dev/null || echo unknown)/$(uname -m 2>/dev/null || echo unknown)"; return 1; }
  asset="aios-install_${platform}.tar.gz"
  archive_url="$(aios_install_release_url "$asset")"
  checksums_url="$(aios_install_release_url aios-install_checksums.txt)"
  tmp_dir="$(mktemp -d)"
  archive="$tmp_dir/$asset"
  checksums="$tmp_dir/aios-install_checksums.txt"
  bin="$tmp_dir/aios-install"

  echo "Downloading aios-install wizard: $archive_url" >&2
  curl -fsSL "$archive_url" -o "$archive" || { rm -rf "$tmp_dir"; return 1; }
  curl -fsSL "$checksums_url" -o "$checksums" || { rm -rf "$tmp_dir"; return 1; }
  verify_sha256_file "$checksums" "$archive" "$asset" || { rm -rf "$tmp_dir"; return 1; }
  tar -xzf "$archive" -C "$tmp_dir" || { rm -rf "$tmp_dir"; return 1; }
  chmod +x "$bin" || { rm -rf "$tmp_dir"; return 1; }
  printf '%s\n' "$bin"
}

build_wizard_args() {
  WIZARD_ARGS=(--wizard)
  if [ -n "${WIZARD_SCRIPT:-}" ]; then
    WIZARD_ARGS+=(--script "$WIZARD_SCRIPT")
  fi
  WIZARD_ARGS+=(--root "$AIOS_ROOT")
  [ "$KIT_DIR_EXPLICIT" -eq 1 ] && WIZARD_ARGS+=(--kit-dir "$KIT_DIR")
  [ "$LLL_DIR_EXPLICIT" -eq 1 ] && WIZARD_ARGS+=(--lll-dir "$LLL_DIR")
  [ "$VAULT_PATH_EXPLICIT" -eq 1 ] && WIZARD_ARGS+=(--vault "$VAULT_PATH")
  [ "$SKILLS_DIR_EXPLICIT" -eq 1 ] && WIZARD_ARGS+=(--skills-dir "$SKILLS_DIR")
  [ "$GLOBAL_BIN_EXPLICIT" -eq 1 ] && WIZARD_ARGS+=(--global-bin "$GLOBAL_BIN_DIR")
  WIZARD_ARGS+=(--add-to-path "$ADD_TO_PATH")
  [ -n "$AIOS_GITHUB_MIRROR_PREFIX" ] && WIZARD_ARGS+=(--github-mirror "$AIOS_GITHUB_MIRROR_PREFIX")
  WIZARD_ARGS+=(--proxy "$WITH_PROXY")
  if [ "$PROXY_TUN" -eq 1 ]; then WIZARD_ARGS+=(--proxy-tun); else WIZARD_ARGS+=(--no-proxy-tun); fi
  [ -n "$PROXY_SUBSCRIPTION_URL" ] && WIZARD_ARGS+=(--proxy-subscription-url "$PROXY_SUBSCRIPTION_URL")
  [ -n "$PROXY_PROXIES_FILE" ] && WIZARD_ARGS+=(--proxy-proxies-file "$PROXY_PROXIES_FILE")
  WIZARD_ARGS+=(--proxy-auto-env "$PROXY_AUTO_ENV")
  [ -n "$MIHOMO_DOWNLOAD_URL" ] && WIZARD_ARGS+=(--mihomo-url "$MIHOMO_DOWNLOAD_URL")
  WIZARD_ARGS+=(--mihomo-version "$MIHOMO_VERSION")
  if [ "$RESET_SOURCES" -eq 1 ]; then WIZARD_ARGS+=(--reset-sources); else WIZARD_ARGS+=(--no-reset-sources); fi
  if [ "$WITH_DEV_ENV" -eq 1 ]; then WIZARD_ARGS+=(--with-dev-env); else WIZARD_ARGS+=(--no-dev-env); fi
  if [ "$WITH_HERMES" -eq 1 ]; then WIZARD_ARGS+=(--with-hermes); else WIZARD_ARGS+=(--no-hermes); fi
  if [ "$WITH_AIOPS" -eq 1 ]; then WIZARD_ARGS+=(--with-aiops); else WIZARD_ARGS+=(--no-aiops); fi
  WIZARD_ARGS+=(--target "$TARGET" --mode "$MODE")
  [ "$FORCE" -eq 1 ] && WIZARD_ARGS+=(--force)
  [ "$ASSUME_YES" -eq 1 ] && WIZARD_ARGS+=(--yes)
  [ "$DRY_RUN" -eq 1 ] && WIZARD_ARGS+=(--dry-run)
}

prepare_wizard_script() {
  if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/install.sh" ]; then
    WIZARD_SCRIPT="$SCRIPT_DIR/install.sh"
    WIZARD_TEMP_DIR=""
    return 0
  fi
  have_cmd curl || return 1
  WIZARD_TEMP_DIR="$(mktemp -d)"
  WIZARD_SCRIPT="$WIZARD_TEMP_DIR/install.sh"
  script_url="$(mirror_url "$AIOS_INSTALL_SCRIPT_URL")"
  echo "Downloading install.sh backend for wizard: $script_url" >&2
  curl -fsSL "$script_url" -o "$WIZARD_SCRIPT" || { rm -rf "$WIZARD_TEMP_DIR"; WIZARD_TEMP_DIR=""; WIZARD_SCRIPT=""; return 1; }
  chmod +x "$WIZARD_SCRIPT"
}

cleanup_wizard_temp() {
  [ -z "${WIZARD_TEMP_DIR:-}" ] || rm -rf "$WIZARD_TEMP_DIR"
}

run_installer_wizard_command() {
  set +e
  "$@"
  status=$?
  set -e
  cleanup_wizard_temp
  if [ "$status" -eq 0 ]; then
    exit 0
  fi
  warn "modern AIOS CLI wizard exited with status $status; falling back to the Bash installer."
  return 1
}

run_installer_wizard() {
  if ! is_interactive; then
    warn "--wizard requires an interactive TTY; falling back to the Bash installer."
    return 1
  fi
  prepare_wizard_script || { warn "could not prepare install.sh backend for the Go wizard; falling back to the Bash installer."; return 1; }
  build_wizard_args
  if have_cmd aios-install; then
    run_installer_wizard_command command aios-install "${WIZARD_ARGS[@]}" || return 1
  fi
  if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/go.mod" ] && [ -d "$SCRIPT_DIR/cmd/aios-install" ] && [ -f "$SCRIPT_DIR/install.sh" ] && have_cmd go; then
    set +e
    (cd "$SCRIPT_DIR" && command go run ./cmd/aios-install "${WIZARD_ARGS[@]}")
    status=$?
    set -e
    cleanup_wizard_temp
    if [ "$status" -eq 0 ]; then
      exit 0
    fi
    warn "modern AIOS CLI wizard exited with status $status; falling back to the Bash installer."
    return 1
  fi
  if have_cmd curl && have_cmd tar; then
    downloaded_bin="$(download_aios_install)" || { cleanup_wizard_temp; warn "failed to download aios-install release binary; falling back to the Bash installer."; return 1; }
    set +e
    command "$downloaded_bin" "${WIZARD_ARGS[@]}"
    status=$?
    set -e
    rm -rf "$(dirname "$downloaded_bin")"
    cleanup_wizard_temp
    if [ "$status" -eq 0 ]; then
      exit 0
    fi
    warn "modern AIOS CLI wizard exited with status $status; falling back to the Bash installer."
    return 1
  fi
  cleanup_wizard_temp
  warn "AIOS Go installer wizard is not available. Install curl/tar, build aios-install, or use the Bash fallback."
  return 1
}

maybe_run_installer_wizard() {
  case "$INSTALL_WIZARD" in
    no) return 0 ;;
    yes)
      run_installer_wizard || true
      return 0
      ;;
    auto)
      if is_interactive && ask_yes_no "Use the modern AIOS CLI wizard?" "yes"; then
        run_installer_wizard || true
      fi
      return 0
      ;;
  esac
}

maybe_run_installer_wizard

if is_interactive; then
  log "AIOS interactive bootstrap"
  ask_path AIOS_ROOT "AIOS install root" "$AIOS_ROOT"
  ask_choice WITH_PROXY "Proxy setup" "$WITH_PROXY" "auto yes no"
  ask_choice PROXY_TUN "Enable Mihomo TUN mode? (1=yes, 0=no)" "$PROXY_TUN" "0 1"
  ask_choice RESET_SOURCES "Restore apt/npm/pip/Docker sources to official defaults? (1=yes, 0=no)" "$RESET_SOURCES" "0 1"
  ask_text PROXY_SUBSCRIPTION_URL "Proxy subscription URL, leave empty if using a proxies YAML file" "$PROXY_SUBSCRIPTION_URL"
  ask_text PROXY_PROXIES_FILE "Local proxies YAML snippet path, leave empty if using subscription" "$PROXY_PROXIES_FILE"
  ask_choice WITH_DEV_ENV "Install/check Python+UV, Node 24, Docker, Caddy? (1=yes, 0=no)" "$WITH_DEV_ENV" "0 1"
  ask_choice WITH_HERMES "Install/check Hermes Agent? (1=yes, 0=no)" "$WITH_HERMES" "0 1"
  WITH_CORE="$WITH_HERMES"
  ask_choice WITH_AIOPS "Install/update OPS vault template? (1=yes, 0=no)" "$WITH_AIOPS" "0 1"
  ask_choice ADD_TO_PATH "Add AIOS bin to PATH?" "yes" "yes no"
fi

AIOS_ROOT="$(validate_path AIOS_ROOT "$AIOS_ROOT")"
if [ "$KIT_DIR_EXPLICIT" -eq 0 ]; then KIT_DIR="$AIOS_ROOT/modules/aios-kit"; fi
if [ -n "$SCRIPT_DIR" ] && [ -x "$SCRIPT_DIR/aios" ] && [ -f "$SCRIPT_DIR/skillpack.yaml" ] && [ "$KIT_DIR_EXPLICIT" -eq 0 ]; then
  KIT_DIR="$SCRIPT_DIR"
fi
if [ "$TEMPLATE_DIR_EXPLICIT" -eq 0 ]; then TEMPLATE_DIR="$KIT_DIR/modules/aiops-vault-template"; fi
if [ "$LLL_DIR_EXPLICIT" -eq 0 ]; then LLL_DIR="$AIOS_ROOT/modules/lins-living-loop"; fi
if [ "$VAULT_PATH_EXPLICIT" -eq 0 ]; then VAULT_PATH="$AIOS_ROOT/vault/ops"; fi
if [ "$SKILLS_DIR_EXPLICIT" -eq 0 ]; then SKILLS_DIR="$HOME/.agents/skills"; fi
KIT_DIR="$(validate_path KIT_DIR "$KIT_DIR")"
TEMPLATE_DIR="$(validate_path TEMPLATE_DIR "$TEMPLATE_DIR")"
LLL_DIR="$(validate_path LLL_DIR "$LLL_DIR")"
VAULT_PATH="$(validate_path VAULT_PATH "$VAULT_PATH")"
SKILLS_DIR="$(validate_path SKILLS_DIR "$SKILLS_DIR")"
AIOS_BIN_DIR="$AIOS_ROOT/bin"

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

reset_apt_sources_to_official() {
  have_cmd apt-get || return 0
  os_id=""; codename=""
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os_id="${ID:-}"
    codename="${VERSION_CODENAME:-}"
  fi
  if [ "$os_id" != "ubuntu" ] || [ -z "$codename" ]; then
    warn "APT official source reset is currently implemented for Ubuntu only; detected ${os_id:-unknown}/${codename:-unknown}."
    return 0
  fi
  target="/etc/apt/sources.list.d/ubuntu.sources"
  backup_dir="/etc/apt/sources.list.d/aios-backup-$(date +%Y%m%d-%H%M%S)"
  apt_arch="$(dpkg --print-architecture 2>/dev/null || true)"
  ubuntu_uri="http://archive.ubuntu.com/ubuntu"
  security_uri="http://security.ubuntu.com/ubuntu"
  case "$apt_arch" in
    arm64|armhf|ppc64el|s390x|riscv64)
      ubuntu_uri="http://ports.ubuntu.com/ubuntu-ports"
      security_uri="http://ports.ubuntu.com/ubuntu-ports" ;;
  esac
  content="Types: deb
URIs: $ubuntu_uri
Suites: $codename $codename-updates $codename-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: $security_uri
Suites: $codename-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ backup existing /etc/apt/sources.list and /etc/apt/sources.list.d/*.list/*.sources to $backup_dir"
    echo "+ disable old apt source files with .aios-disabled suffix"
    echo "+ write Ubuntu official apt sources to $target ($ubuntu_uri, $security_uri)"
    echo "+ sudo apt-get update"
    return 0
  fi
  sudo mkdir -p "$backup_dir"
  if [ -f /etc/apt/sources.list ]; then
    sudo cp -a /etc/apt/sources.list "$backup_dir/"
    sudo mv /etc/apt/sources.list "/etc/apt/sources.list.aios-disabled-$(date +%Y%m%d-%H%M%S)"
  fi
  for f in /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
    [ -e "$f" ] || continue
    [ "$f" = "$target" ] && continue
    sudo cp -a "$f" "$backup_dir/"
    sudo mv "$f" "$f.aios-disabled-$(date +%Y%m%d-%H%M%S)"
  done
  printf '%s' "$content" | sudo tee "$target" >/dev/null
  run_visible sudo apt-get update
}

reset_sources_to_official() {
  [ "$RESET_SOURCES" -eq 1 ] || return 0
  log "Resetting package sources toward official defaults"
  reset_apt_sources_to_official
  if have_cmd npm; then run_visible npm config delete registry || true; fi
  if have_cmd python3; then run_visible python3 -m pip config unset global.index-url || true; fi
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
  echo "Recording $component in OPS vault maintenance log."
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ AIOPS_ROOT=$VAULT_PATH python3 $VAULT_PATH/scripts/aiops.py append-log --actor aios-installer --type maintenance --scope component:$component --summary installed-or-present-by-aios-installer --status done --object $component --tag installer"
  else
    AIOPS_ROOT="$VAULT_PATH" python3 "$VAULT_PATH/scripts/aiops.py" append-log \
      --actor aios-installer \
      --type maintenance \
      --scope "component:$component" \
      --summary installed-or-present-by-aios-installer \
      --status done \
      --object "$component" \
      --tag installer
  fi
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
  if [ -e "$KIT_DIR/.git" ]; then
    if [ "$KIT_DIR_EXPLICIT" -eq 1 ]; then echo "using explicit git kit dir without auto-pull: $KIT_DIR"; else run_visible git -C "$KIT_DIR" pull --ff-only; fi
  else
    echo "using existing non-git kit dir: $KIT_DIR"
  fi
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
fi

reset_sources_to_official

if [ "$WITH_DEV_ENV" -eq 1 ]; then install_dev_env; fi

log "Initializing AIOS instance layout"
init_args=("$KIT_DIR/aios" --home "$HOME" init --root "$AIOS_ROOT" --ops "$VAULT_PATH" --skills-dir "$SKILLS_DIR")
[ "$DRY_RUN" -eq 1 ] && init_args+=(--dry-run)
run_visible "${init_args[@]}"

log "Preparing lins-living-loop module at $LLL_DIR"
if [ ! -f "$LLL_DIR/SKILL.md" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then echo "+ git clone $(mirror_url "$LLL_REPO_URL") $LLL_DIR"; else mkdir -p "$(dirname "$LLL_DIR")"; git clone "$(mirror_url "$LLL_REPO_URL")" "$LLL_DIR"; fi
else
  if [ -e "$LLL_DIR/.git" ]; then
    if [ "$LLL_DIR_EXPLICIT" -eq 1 ]; then echo "using explicit git LLL dir without auto-pull: $LLL_DIR"; else run_visible git -C "$LLL_DIR" pull --ff-only; fi
  else
    echo "using existing non-git LLL dir: $LLL_DIR"
  fi
fi

log "Installing lll command shim"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "+ mkdir -p $AIOS_BIN_DIR"
  echo "+ ln -sfn $LLL_DIR/lll $AIOS_BIN_DIR/lll"
else
  mkdir -p "$AIOS_BIN_DIR"
  ln -sfn "$LLL_DIR/lll" "$AIOS_BIN_DIR/lll"
fi

if [ -n "$GLOBAL_BIN_DIR" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ ln -s $LLL_DIR/lll $GLOBAL_BIN_DIR/lll"
  elif [ -e "$GLOBAL_BIN_DIR/lll" ] || [ -L "$GLOBAL_BIN_DIR/lll" ]; then
    if [ -L "$GLOBAL_BIN_DIR/lll" ] && [ "$(readlink "$GLOBAL_BIN_DIR/lll")" = "$LLL_DIR/lll" ]; then :; else warn "refusing to replace existing $GLOBAL_BIN_DIR/lll"; fi
  else
    ln -s "$LLL_DIR/lll" "$GLOBAL_BIN_DIR/lll"
  fi
fi

if [ "$WITH_HERMES" -eq 1 ]; then install_hermes_core; else log "Skipping Hermes Agent install/config (--no-hermes)"; fi

if [ "$SKIP_SKILLPACK" -eq 1 ]; then
  log "Skipping skillpack install (--skip-skillpack)"
elif ! have_cmd npx && [ "$DRY_RUN" -eq 0 ]; then
  warn "npx is still missing; cannot install external skillpack entries. Re-run after Node/NVM shell reload."
else
  log "Installing skillpack"
  force_arg=""; [ "$FORCE" -eq 1 ] && force_arg="--force"
  skillpack_args=("$KIT_DIR/aios" --home "$HOME" skillpack sync --mode "$MODE" --target "$TARGET")
  if [ "$DRY_RUN" -eq 1 ]; then skillpack_args+=(--dry-run); else skillpack_args+=(--apply); fi
  [ -n "$force_arg" ] && skillpack_args+=("$force_arg")
  AIOS_ROOT="$AIOS_ROOT" AIOS_AGENT_SKILLS_DIR="$SKILLS_DIR" run_visible "${skillpack_args[@]}"
  AIOS_ROOT="$AIOS_ROOT" AIOS_AGENT_SKILLS_DIR="$SKILLS_DIR" run_visible "$KIT_DIR/aios" --home "$HOME" skillpack doctor --target "$TARGET"
fi

if [ "$WITH_AIOPS" -eq 1 ]; then
  log "Using bundled OPS vault template at $TEMPLATE_DIR"
  if [ ! -f "$TEMPLATE_DIR/scripts/install.py" ]; then
    echo "missing bundled OPS vault template: $TEMPLATE_DIR/scripts/install.py" >&2
    echo "Your aios-kit checkout is incomplete; update or reclone $KIT_DIR." >&2
    exit 1
  fi
  log "Installing OPS vault at $VAULT_PATH"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ python3 $TEMPLATE_DIR/scripts/install.py --vault $VAULT_PATH --agent none"
  else
    python3 "$TEMPLATE_DIR/scripts/install.py" --vault "$VAULT_PATH" --agent none
  fi
  record_aiops_resource docker
  record_aiops_resource caddy
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "+ AIOPS_ROOT=$VAULT_PATH python3 $VAULT_PATH/scripts/aiops.py check"
  else
    AIOPS_ROOT="$VAULT_PATH" python3 "$VAULT_PATH/scripts/aiops.py" check
  fi
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
