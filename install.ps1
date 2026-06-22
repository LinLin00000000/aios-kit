#requires -Version 5.1
<#
.SYNOPSIS
  Native Windows installer for the AIOS core feature set.

.DESCRIPTION
  This PowerShell installer is intentionally capability-layered.

  Core features (Windows + Ubuntu target):
    - create a local AIOS instance root, defaulting to ~/aios
    - install/update the aios-kit module
    - install/update the Lin's Living Loop module (full LLL runner currently needs Git Bash/WSL)
    - create Windows command shims under ~/aios/bin
    - initialize portable AIOS directories and config files
    - create an agent runtime skills target directory
    - optionally add ~/aios/bin to the user PATH

  Add-on features such as systemd services, Mihomo TUN, Docker/Caddy bootstrap,
  source reset, managed skillpack sync, and 24/7 server operation are Linux/server
  capabilities. They are intentionally not shown or executed by the native Windows
  installer. If you want the full Linux/server stack on Windows, use WSL and install.sh.
#>
[CmdletBinding()]
param(
  [string]$Root = "~/aios",
  [string]$KitRepo = "https://github.com/LinLin00000000/aios-kit.git",
  [string]$LLLRepo = "https://github.com/LinLin00000000/lins-living-loop.git",
  [string]$GitHubMirror = $env:AIOS_GITHUB_MIRROR_PREFIX,
  [switch]$DryRun,
  [switch]$NonInteractive,
  [switch]$Yes,
  [switch]$NoPath,
  [switch]$SkipLLL,
  [switch]$PrintPlan,
  [switch]$Json,
  [switch]$UseBashBackend,
  [switch]$NoWizard
)

$ErrorActionPreference = "Stop"

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
  throw "install.ps1 is the native Windows installer. Use install.sh on Linux/macOS, or pass -UseBashBackend only from Windows when using Git Bash/WSL."
}

function Convert-ToNativePath([string]$PathValue) {
  if ([string]::IsNullOrWhiteSpace($PathValue)) { throw "path must not be empty" }
  if ($PathValue -eq "~") { return $HOME }
  if ($PathValue.StartsWith("~/") -or $PathValue.StartsWith("~\")) {
    return Join-Path $HOME $PathValue.Substring(2)
  }
  return [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($PathValue))
}

function Mirror-Url([string]$Url) {
  if ([string]::IsNullOrWhiteSpace($GitHubMirror)) { return $Url }
  if ($Url.StartsWith("https://github.com/") -or $Url.StartsWith("https://raw.githubusercontent.com/")) {
    if ($GitHubMirror.EndsWith("/")) { return "$GitHubMirror$Url" }
    return "$GitHubMirror/$Url"
  }
  return $Url
}

function Write-Step([string]$Message) {
  Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Plan([string]$Message, [scriptblock]$Action) {
  if ($DryRun) {
    Write-Host "+ $Message"
    return
  }
  Write-Host "+ $Message"
  & $Action
}

function Test-Command([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-PythonCommand {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return $python.Source }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return $py.Source }
  return $null
}

function Get-GitHubZipUrl([string]$RepoUrl) {
  $url = $RepoUrl.TrimEnd('/')
  if ($url.EndsWith('.git')) { $url = $url.Substring(0, $url.Length - 4) }
  return Mirror-Url "$url/archive/refs/heads/main.zip"
}

function Ensure-Directory([string]$PathValue) {
  Invoke-Plan "mkdir $PathValue" { New-Item -ItemType Directory -Force -Path $PathValue | Out-Null }
}

function Install-Repo([string]$Name, [string]$RepoUrl, [string]$Destination) {
  Write-Step "Preparing $Name at $Destination"
  if (Test-Path -LiteralPath (Join-Path $Destination ".git")) {
    if (Test-Command git) {
      Invoke-Plan "git -C $Destination pull --ff-only" { git -C $Destination pull --ff-only }
      return
    }
    Write-Warning "$Name exists as a git checkout but git is not available; leaving it unchanged."
    return
  }
  if (Test-Path -LiteralPath $Destination) {
    Write-Host "using existing non-git $Name directory: $Destination"
    return
  }
  Ensure-Directory ([System.IO.Path]::GetDirectoryName($Destination))
  if (Test-Command git) {
    $url = Mirror-Url $RepoUrl
    Invoke-Plan "git clone $url $Destination" { git clone $url $Destination }
    return
  }

  $zipUrl = Get-GitHubZipUrl $RepoUrl
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("aios-" + [guid]::NewGuid().ToString("N"))
  $zip = Join-Path $tmp "$Name.zip"
  Invoke-Plan "download and expand $zipUrl to $Destination" {
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
      Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
      Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
      $expanded = Get-ChildItem -LiteralPath $tmp -Directory | Where-Object { $_.Name -ne [System.IO.Path]::GetFileNameWithoutExtension($zip) } | Select-Object -First 1
      if (-not $expanded) { $expanded = Get-ChildItem -LiteralPath $tmp -Directory | Select-Object -First 1 }
      if (-not $expanded) { throw "downloaded archive did not contain a directory" }
      Move-Item -LiteralPath $expanded.FullName -Destination $Destination
    }
    finally {
      Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

function Write-FileUtf8NoBom([string]$PathValue, [string]$Content) {
  New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($PathValue)) | Out-Null
  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($PathValue, $Content, $encoding)
}

function Write-FileIfMissing([string]$PathValue, [string]$Content) {
  Invoke-Plan "write $PathValue if missing" {
    if (Test-Path -LiteralPath $PathValue) { return }
    Write-FileUtf8NoBom $PathValue $Content
  }
}

function Write-TextFile([string]$PathValue, [string]$Content) {
  Invoke-Plan "write $PathValue" { Write-FileUtf8NoBom $PathValue $Content }
}

function Add-UserPath([string]$BinDir) {
  if ($NoPath) { return }
  Invoke-Plan "add $BinDir to current user's PATH if missing" {
    $normalized = [System.IO.Path]::GetFullPath($BinDir).TrimEnd('\')
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($current)) { $parts = $current -split ';' }
    $exists = $false
    foreach ($part in $parts) {
      if ([string]::IsNullOrWhiteSpace($part)) { continue }
      try { $p = [System.IO.Path]::GetFullPath($part).TrimEnd('\') } catch { $p = $part.TrimEnd('\') }
      if ([string]::Equals($p, $normalized, [System.StringComparison]::OrdinalIgnoreCase)) { $exists = $true; break }
    }
    if (-not $exists) {
      $new = if ([string]::IsNullOrWhiteSpace($current)) { $normalized } else { "$current;$normalized" }
      if ($new.Length -gt 30000) { throw "User PATH would become too long; add $normalized manually." }
      [Environment]::SetEnvironmentVariable("Path", $new, "User")
      $env:Path = "$env:Path;$normalized"
    }
  }
}

function Write-Shims([string]$BinDir, [string]$KitDir, [string]$LLLDir) {
  $aiosShim = @"
`$ErrorActionPreference = "Stop"
`$kit = "$KitDir"
`$script = Join-Path `$kit "scripts\aios.py"
`$python = Get-Command python -ErrorAction SilentlyContinue
if (-not `$python) { `$python = Get-Command py -ErrorAction SilentlyContinue }
if (-not `$python) { throw "Python 3 is required to run aios. Install Python 3, then retry." }
& `$python.Source `$script @args
exit `$LASTEXITCODE
"@
  Write-TextFile (Join-Path $BinDir "aios.ps1") $aiosShim

  $aiosCmd = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0aios.ps1`" %*`r`n"
  Write-TextFile (Join-Path $BinDir "aios.cmd") $aiosCmd

  if (-not $SkipLLL) {
    $lllShim = @"
`$ErrorActionPreference = "Stop"
`$lll = "$LLLDir"
`$bash = Get-Command bash -ErrorAction SilentlyContinue
if (`$bash) {
  & `$bash.Source (Join-Path `$lll "lll") @args
  exit `$LASTEXITCODE
}
Write-Error "LLL module is installed at `$lll, but the full LLL CLI currently requires Git Bash or WSL on Windows."
exit 127
"@
    Write-TextFile (Join-Path $BinDir "lll.ps1") $lllShim
    $lllCmd = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0lll.ps1`" %*`r`n"
    Write-TextFile (Join-Path $BinDir "lll.cmd") $lllCmd
  }
}

function Initialize-CoreLayout([string]$RootPath, [string]$KitDir, [string]$LLLDir, [string]$SkillsDir) {
  $dirs = @(
    $RootPath,
    (Join-Path $RootPath "bin"),
    (Join-Path $RootPath "config"),
    (Join-Path $RootPath "modules"),
    (Join-Path $RootPath "vault"),
    (Join-Path $RootPath "vault\ops"),
    (Join-Path $RootPath "vault\ops\projects"),
    (Join-Path $RootPath "work"),
    (Join-Path $RootPath "skills"),
    $SkillsDir,
    (Join-Path $RootPath "state"),
    (Join-Path $RootPath "logs"),
    (Join-Path $RootPath "cache")
  )
  foreach ($dir in $dirs) { Ensure-Directory $dir }

  Write-FileIfMissing (Join-Path $RootPath "README.md") "# AIOS instance`n`nThis is the local AIOS instance root. Core AIOS works when the machine is on; 24/7 service mode is an optional Linux/server add-on.`n"
  Write-FileIfMissing (Join-Path $RootPath "work\README.md") "# AIOS work`n`nLLL and agent workdirs live here.`n"
  Write-FileIfMissing (Join-Path $RootPath "skills\README.md") "# AIOS skills`n`nMetadata/cache area. Agent-loadable skills are installed one-by-one into the agent runtime skills directory. Windows native install initializes this target; managed skillpack sync is currently a Linux/WSL add-on path.`n"
  Write-FileIfMissing (Join-Path $SkillsDir "README.aios-kit.md") "# Agent skills target for aios-kit`n`nWindows native install initializes this target and leaves existing skills alone. Managed skillpack sync is currently supported through Linux/WSL install.sh.`n"
  Write-FileIfMissing (Join-Path $RootPath "modules\README.md") "# AIOS modules`n`nReusable module checkouts used by this AIOS instance.`n"
  Write-FileIfMissing (Join-Path $RootPath "vault\ops\projects\registry.jsonl") ""
  Write-FileIfMissing (Join-Path $RootPath "vault\ops\projects\aliases.yaml") "aliases: {}`n"

  $lllCapability = if ($SkipLLL) { "    # lins-living-loop-module skipped by -SkipLLL" } else { "    - lins-living-loop-module`n    - lll-command-shim-requires-git-bash-or-wsl" }
  $lllPath = if ($SkipLLL) { "" } else { "  lll: $LLLDir" }
  $instance = @"
version: 1
instance_id: windows-local-default
platform: windows
root: $RootPath
capabilities:
  core:
    - local-aios-instance
    - aios-kit-module
$lllCapability
    - command-shims
    - local-agent-workdirs
    - agent-skills-target-initialized
  windows_limitations:
    - managed-skillpack-sync-currently-requires-linux-or-wsl
    - full-lll-cli-currently-requires-git-bash-or-wsl
  addons_skipped_on_windows:
    - systemd-24x7-service
    - mihomo-tun-service
    - apt-docker-caddy-source-bootstrap
paths:
  modules: $(Join-Path $RootPath "modules")
  kit: $KitDir
$lllPath
  work: $(Join-Path $RootPath "work")
  agent_skills: $SkillsDir
"@
  Write-TextFile (Join-Path $RootPath "config\instance.yaml") $instance
}

function Print-BashBackendCommand([string]$RootValue) {
  $scriptUrl = Mirror-Url "https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh"
  $cmd = "bash -c `"`$(curl -fsSL $scriptUrl)`" -- --root `"$RootValue`""
  if ($NoWizard) { $cmd += " --no-wizard" }
  if ($DryRun) { $cmd += " --dry-run" }
  Write-Host "Use Git Bash or WSL for the Linux/server backend:"
  Write-Host $cmd
}

$rootPath = Convert-ToNativePath $Root
$modulesDir = Join-Path $rootPath "modules"
$kitDir = Join-Path $modulesDir "aios-kit"
$lllDir = Join-Path $modulesDir "lins-living-loop"
$binDir = Join-Path $rootPath "bin"
$skillsDir = Join-Path $HOME ".agents\skills"
$pythonCommand = Get-PythonCommand

if ($UseBashBackend) {
  Print-BashBackendCommand $Root
  exit 0
}

$coreFeatures = @(
  "local AIOS instance root",
  "aios-kit module checkout/download",
  "Windows command shims in bin/",
  "portable config/work/vault/skills/state/logs/cache directories",
  "agent runtime skills target directory",
  "optional user PATH update"
)
if (-not $SkipLLL) { $coreFeatures += "Lin's Living Loop module checkout/download (full CLI requires Git Bash/WSL)" }

$plan = [ordered]@{
  platform = "windows"
  root = $rootPath
  core_features = $coreFeatures
  prerequisites = @{ python = [bool]$pythonCommand; python_command = $pythonCommand; git = (Test-Command git) }
  skipped_addons = @(
    "managed skillpack sync (use Linux/WSL install.sh)",
    "systemd 24/7 service mode",
    "Mihomo TUN service bootstrap",
    "apt/npm/pip/Docker/Caddy source reset/bootstrap",
    "Linux server full-stack install.sh backend"
  )
  dry_run = [bool]$DryRun
}

if ($Json) {
  $plan | ConvertTo-Json -Depth 5
  exit 0
}

Write-Host "AIOS Windows native installer" -ForegroundColor Green
Write-Host "Core features are cross-platform by design; this script installs the Windows core path."
Write-Host "Linux/server add-ons are hidden here; use WSL/install.sh for those."

if ($PrintPlan) {
  $plan | Format-List
  exit 0
}

if (-not $pythonCommand -and -not $DryRun) {
  throw "Python 3 is required for the Windows core aios command. Install Python 3 from python.org or Microsoft Store, then retry."
}

if (-not $NonInteractive -and -not $Yes -and -not $DryRun) {
  $answer = Read-Host "Install AIOS core to $rootPath ? [Y/n]"
  if ($answer -match '^(n|no)$') { Write-Host "Cancelled."; exit 0 }
}

Write-Step "Installing AIOS core feature set"
Initialize-CoreLayout $rootPath $kitDir $lllDir $skillsDir
Install-Repo "aios-kit" $KitRepo $kitDir
if (-not $SkipLLL) { Install-Repo "lins-living-loop" $LLLRepo $lllDir }
Write-Shims $binDir $kitDir $lllDir
Add-UserPath $binDir

Write-Step "Done"
Write-Host "AIOS root: $rootPath"
Write-Host "aios command: $(Join-Path $binDir 'aios.ps1')"
if (-not $SkipLLL) { Write-Host "lll command: $(Join-Path $binDir 'lll.ps1') (requires Git Bash/WSL for full CLI)" }
Write-Host "agent runtime skills target: $skillsDir"
if ($DryRun) { Write-Host "dry-run only; no files changed" }
else { Write-Host "Open a new terminal for PATH changes to take effect, then run: aios status" }
