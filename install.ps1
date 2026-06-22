#requires -Version 5.1
<#
.SYNOPSIS
  Thin Windows PowerShell bootstrap for the AIOS installer wizard.

.DESCRIPTION
  Downloads the aios-install release binary, verifies aios-install_checksums.txt,
  downloads install.sh as the stable backend contract, then launches the wizard.

  The current backend is install.sh, so executing the final install on Windows
  requires a Bash provider such as Git Bash or WSL. Without Bash, this script
  prints a durable command instead of pretending the install completed.
#>
[CmdletBinding()]
param(
  [string]$ReleaseTag = $env:AIOS_INSTALL_RELEASE_TAG,
  [string]$ReleaseBaseUrl = $env:AIOS_INSTALL_RELEASE_BASE_URL,
  [string]$ScriptUrl = $env:AIOS_INSTALL_SCRIPT_URL,
  [string]$GitHubMirror = $env:AIOS_GITHUB_MIRROR_PREFIX,
  [switch]$NoWizard,
  [switch]$PrintCommand,
  [switch]$Json,
  [switch]$DryRun,
  [string]$Root = "~/aios"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ReleaseTag)) { $ReleaseTag = "latest" }
if ([string]::IsNullOrWhiteSpace($ReleaseBaseUrl)) { $ReleaseBaseUrl = "https://github.com/LinLin00000000/aios-kit/releases" }
if ([string]::IsNullOrWhiteSpace($ScriptUrl)) { $ScriptUrl = "https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh" }

function Mirror-Url([string]$Url) {
  if ([string]::IsNullOrWhiteSpace($GitHubMirror)) { return $Url }
  if ($Url.StartsWith("https://github.com/") -or $Url.StartsWith("https://raw.githubusercontent.com/")) {
    if ($GitHubMirror.EndsWith("/")) { return "$GitHubMirror$Url" }
    return "$GitHubMirror/$Url"
  }
  return $Url
}

function Get-PlatformName {
  if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw "install.ps1 is intended for Windows. Use install.sh on Linux/macOS."
  }
  $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
  switch ($arch) {
    "x64" { return "windows_amd64" }
    "arm64" { return "windows_arm64" }
    default { throw "Unsupported Windows architecture: $arch" }
  }
}

function Get-AssetUrl([string]$Asset) {
  if ($ReleaseTag -eq "latest") {
    return Mirror-Url "$ReleaseBaseUrl/latest/download/$Asset"
  }
  return Mirror-Url "$ReleaseBaseUrl/download/$ReleaseTag/$Asset"
}

function Download-File([string]$Url, [string]$OutFile) {
  Write-Host "Downloading $Url"
  try {
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
  }
  catch {
    throw "Failed to download $Url. If this is a new aios-kit version, release assets may not have been published yet. Use Git Bash/WSL with install.sh, or retry after a GitHub Release is created. Original error: $($_.Exception.Message)"
  }
}

function Verify-Checksum([string]$ChecksumFile, [string]$Archive, [string]$ExpectedName) {
  $line = Get-Content -LiteralPath $ChecksumFile | Where-Object {
    $parts = ($_ -split '\s+', 2)
    $parts.Count -eq 2 -and $parts[1] -eq $ExpectedName
  } | Select-Object -First 1
  if (-not $line) { throw "checksum entry not found for $ExpectedName" }
  $expected = ($line -split '\s+', 2)[0].ToLowerInvariant()
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
  if ($actual -ne $expected) { throw "checksum mismatch for $ExpectedName" }
}

function Print-DurableCommand {
  $url = Mirror-Url $ScriptUrl
  $cmd = "bash -c `"`$(curl -fsSL $url)`""
  if ($NoWizard) { $cmd += " -- --no-wizard" }
  elseif ($DryRun) { $cmd += " -- --dry-run" }
  Write-Host "Use Git Bash or WSL to run:"
  Write-Host $cmd
}

if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
  Write-Warning "bash was not found. The current AIOS backend is install.sh, so Windows execution requires Git Bash or WSL."
  Print-DurableCommand
  exit 0
}

if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
  throw "tar is required to extract the aios-install release archive. Install a recent Windows, Git for Windows, or use WSL."
}

$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("aios-kit-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
  $platform = Get-PlatformName
  $asset = "aios-install_$platform.tar.gz"
  $archive = Join-Path $temp $asset
  $checksums = Join-Path $temp "aios-install_checksums.txt"
  $installSh = Join-Path $temp "install.sh"

  Download-File (Get-AssetUrl $asset) $archive
  Download-File (Get-AssetUrl "aios-install_checksums.txt") $checksums
  Verify-Checksum $checksums $archive $asset

  tar -xzf $archive -C $temp
  $wizardExe = Join-Path $temp "aios-install.exe"
  if (-not (Test-Path -LiteralPath $wizardExe)) { throw "archive did not contain aios-install.exe" }

  Download-File (Mirror-Url $ScriptUrl) $installSh

  $args = @()
  if ($NoWizard) { $args += "--no-wizard" } else { $args += "--wizard" }
  $args += @("--script", $installSh, "--root", $Root)
  if ($GitHubMirror) { $args += @("--github-mirror", $GitHubMirror) }
  if ($DryRun) { $args += "--dry-run" }
  if ($PrintCommand) { $args += "--print-command" }
  if ($Json) { $args += "--json" }

  & $wizardExe @args
  exit $LASTEXITCODE
}
finally {
  Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
