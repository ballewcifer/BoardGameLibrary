<#
.SYNOPSIS
  Sets up Board Game Library (desktop/web + mobile) on a new Windows machine.

.DESCRIPTION
  Clones both repos into a plain local folder, installs dependencies, and
  checks the CLI tools/auth needed to build and release. Safe to re-run —
  an existing clone is pulled instead of re-cloned, and every step reports
  OK/WARN/FAIL rather than assuming a clean machine.

  Deliberately does NOT clone into a cloud-sync folder (OneDrive/Dropbox/
  etc). Git is the sync mechanism for this project — file-sync tools fight
  git's internals (.git/, node_modules/) and would silently upload the
  credentials/ secrets to the cloud provider. Run this from a plain local
  path (default: C:\Dev).

.PARAMETER DevRoot
  Parent folder both repos are cloned into. Defaults to C:\Dev.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup-new-machine.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup-new-machine.ps1 -DevRoot D:\Code
#>
param(
    [string]$DevRoot = "C:\Dev"
)

function Section($title) { Write-Host "`n=== $title ===" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  OK    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  WARN  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "  FAIL  $msg" -ForegroundColor Red }

$DesktopRepo = Join-Path $DevRoot "BoardGameLibrary"
$MobileRepo  = Join-Path $DevRoot "BoardGameLibraryMobile"

# ── Prerequisites ────────────────────────────────────────────────────────────
Section "Checking prerequisites"
$missing = $false
function Require-Cmd($name, $hint) {
    if (Get-Command $name -ErrorAction SilentlyContinue) { Ok "$name found" }
    else { Fail "$name not found -- $hint"; $script:missing = $true }
}
Require-Cmd git    "install from https://git-scm.com/download/win"
Require-Cmd node   "install from https://nodejs.org (LTS)"
Require-Cmd npm    "comes with Node.js"
Require-Cmd python "install from https://python.org (check 'Add to PATH' during install)"
if ($missing) {
    Write-Host "`nInstall the missing tool(s) above, then re-run this script." -ForegroundColor Red
    exit 1
}

# ── Dev folder ───────────────────────────────────────────────────────────────
Section "Dev folder"
New-Item -ItemType Directory -Force -Path $DevRoot | Out-Null
Ok $DevRoot
if ($DevRoot -match "OneDrive|Dropbox|Google ?Drive|iCloud") {
    Warn "This path looks like it's inside a cloud-sync folder. See the script header -- use a plain local path instead."
}

# ── Clone or update both repos ──────────────────────────────────────────────
function Clone-Or-Pull($name, $url, $path) {
    Section $name
    if (Test-Path $path) {
        Warn "$path already exists -- pulling latest instead of cloning"
        try {
            Push-Location $path
            git pull --ff-only
            Ok "up to date"
        } catch {
            Warn "git pull failed (local changes may conflict) -- check manually: $path"
        } finally {
            Pop-Location
        }
    } else {
        try {
            git clone $url $path
            Ok "cloned to $path"
        } catch {
            Fail "clone failed: $_"
            exit 1
        }
    }
}
Clone-Or-Pull "Desktop/web repo" "https://github.com/ballewcifer/BoardGameLibrary.git" $DesktopRepo
Clone-Or-Pull "Mobile repo"      "https://github.com/ballewcifer/BoardGameLibraryMobile.git" $MobileRepo

# ── Dependencies ─────────────────────────────────────────────────────────────
Section "Desktop/web Python dependencies"
try {
    Push-Location $DesktopRepo
    pip install pyinstaller pillow certifi keyring | Out-Null
    if (Test-Path "requirements-web.txt") { pip install -r requirements-web.txt | Out-Null }
    Ok "installed"
} catch {
    Fail "pip install failed: $_"
} finally {
    Pop-Location
}

Section "Mobile dependencies (npm install -- can take a few minutes)"
try {
    Push-Location $MobileRepo
    npm install
    Ok "node_modules installed"
} catch {
    Fail "npm install failed: $_"
} finally {
    Pop-Location
}

# ── CLI auth status (report only -- these are interactive logins) ──────────
Section "GitHub CLI"
if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh auth status *> $null
    if ($LASTEXITCODE -eq 0) { Ok "gh already authenticated" }
    else { Warn "gh installed but not logged in -- run: gh auth login" }
} else {
    Warn "GitHub CLI not installed -- install from https://cli.github.com, then run: gh auth login"
}

Section "EAS CLI (mobile builds)"
try {
    Push-Location $MobileRepo
    # 2>$null (not 2>&1) -- merging native stderr into the pipeline wraps each
    # line in a NativeCommandError in PowerShell 5.1 even on success.
    $easOutput = npx --yes eas-cli whoami 2>$null
    $emailLine = $easOutput | Select-String '@' | Select-Object -Last 1
    if ($emailLine) { Ok "eas-cli already logged in as $($emailLine.ToString().Trim())" }
    else { Warn "not logged in to EAS -- run: npx eas-cli login" }
} finally {
    Pop-Location
}

# ── Store submission credentials (optional) ─────────────────────────────────
Section "Store submission credentials (optional -- only needed to submit releases from this machine)"
$credDir = Join-Path $MobileRepo "credentials"
New-Item -ItemType Directory -Force -Path $credDir | Out-Null
$appleKey = Get-ChildItem $credDir -Filter "AuthKey_*.p8" -ErrorAction SilentlyContinue
$playKey  = Join-Path $credDir "google-play-service-account.json"
if ($appleKey) { Ok "Apple key present: $($appleKey.Name)" }
else { Warn "Apple App Store Connect key missing -- see this project's 'setup-new-machine' Claude Code skill" }
if (Test-Path $playKey) { Ok "Google Play service account key present" }
else { Warn "Google Play service account key missing -- see this project's 'setup-new-machine' Claude Code skill" }

# ── Summary ──────────────────────────────────────────────────────────────────
Section "Summary"
Write-Host "Desktop/web: $DesktopRepo"
Write-Host "Mobile:      $MobileRepo"
Write-Host "`nAddress any WARN/FAIL lines above. For store credentials and verification,"
Write-Host "open Claude Code in $DesktopRepo and run the 'setup-new-machine' skill."
