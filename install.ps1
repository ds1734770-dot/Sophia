# Sophia installer for Windows 10/11 (PowerShell).
#
#   irm https://raw.githubusercontent.com/ds1734770-dot/Sophia/main/install.ps1 | iex
#
# Puts Sophia in %USERPROFILE%\Sophia ($env:SOPHIA_DIR to change), Python
# 3.12 and its packages in %USERPROFILE%\.venvs\sophia, adds a `sophia`
# command, then runs the first-run setup (API key, app scan, microphone
# check, voice models). No administrator rights needed.

$ErrorActionPreference = "Stop"

$Repo   = if ($env:SOPHIA_REPO)   { $env:SOPHIA_REPO }   else { "https://github.com/ds1734770-dot/Sophia" }
$Branch = if ($env:SOPHIA_BRANCH) { $env:SOPHIA_BRANCH } else { "main" }
$Dir    = if ($env:SOPHIA_DIR)    { $env:SOPHIA_DIR }    else { Join-Path $HOME "Sophia" }
$Venv   = if ($env:SOPHIA_VENV)   { $env:SOPHIA_VENV }   else { Join-Path $HOME ".venvs\sophia" }
$Bin    = Join-Path $HOME ".local\bin"

Write-Host "Installing Sophia into $Dir" -ForegroundColor Cyan

# 1. The code
if (Test-Path (Join-Path $Dir ".git")) {
    Write-Host "Updating the existing copy..."
    git -C $Dir pull --ff-only
}
elseif ((Test-Path $Dir) -and (Get-ChildItem $Dir -Force | Select-Object -First 1)) {
    throw "$Dir already exists and is not a Sophia checkout. Set `$env:SOPHIA_DIR to another folder."
}
elseif (Get-Command git -ErrorAction SilentlyContinue) {
    git clone --depth 1 --branch $Branch "$Repo.git" $Dir
}
else {
    # no git: download the code as a zip
    $zip = Join-Path $env:TEMP "sophia.zip"
    $tmp = Join-Path $env:TEMP "sophia-src"
    Invoke-WebRequest "$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive $zip -DestinationPath $tmp
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    Move-Item (Join-Path (Get-ChildItem $tmp | Select-Object -First 1).FullName "*") $Dir
    Remove-Item $zip, $tmp -Recurse -Force
}

# 2. Python 3.12 and packages, through uv
$env:Path = "$Bin;$env:Path"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (Python manager, no admin rights)..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$Bin;$env:Path"
}

uv python install 3.12
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    uv venv $Venv --python 3.12
}

Write-Host "Installing packages (a few minutes the first time)..."
$env:VIRTUAL_ENV = $Venv
uv pip install -r (Join-Path $Dir "requirements.txt")
Remove-Item Env:VIRTUAL_ENV

# 3. The `sophia` command
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
$python = Join-Path $Venv "Scripts\python.exe"
$main = Join-Path $Dir "main.py"
Set-Content -Path (Join-Path $Bin "sophia.cmd") -Encoding ASCII -Value "@echo off`r`ncd /d `"$Dir`"`r`n`"$python`" `"$main`" %*"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($userPath -split ";" | Where-Object { $_ -eq $Bin })) {
    [Environment]::SetEnvironmentVariable("Path", "$Bin;$userPath", "User")
}

Write-Host ""
Write-Host "Installed. The 'sophia' command works in new terminal windows." -ForegroundColor Green

# 4. First-run setup
& $python $main --setup
