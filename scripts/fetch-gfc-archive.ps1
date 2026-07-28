# Acquire the frozen GFC archive AS THE WORKER ACCOUNT.  RUN ELEVATED.
#
# Why not simply run it elevated as yourself: the raw-GFC directory carries an
# explicit DENY for the interactive account, and in Windows an explicit deny
# beats an Administrators allow -- an elevated token still carries your user
# SID.  Observed: a 647 MB tile downloaded and verified, then the final rename
# failed with WinError 5, because icacls (R) covers SYNCHRONIZE/READ_CONTROL
# which the rename's open requires.  Acquisition also has to read each tile back
# to hash it and read its geotransform, which is exactly what the deny prevents.
#
# Why a scheduled task rather than Start-Process -Credential: CreateProcessWithLogonW
# (which -Credential uses) fails with "Access is denied" when called from an
# ELEVATED process dropping to a standard user.  A scheduled task uses a batch
# logon instead, and `schtasks /RU /RP` grants SeBatchLogonRight itself.

[CmdletBinding()]
param(
    [string]$Account  = "satclf-gfc-worker",
    [string]$RepoRoot = "C:\Users\josha\OneDrive\Documents\Satellite Image Classifier",
    [string]$Python   = "C:\Users\josha\.venvs\satclf\Scripts\python.exe",
    [string]$TaskName = "SatclfGfcFetch"
)

$ErrorActionPreference = "Stop"

# PowerShell 5.1 turns a native command's stderr into ErrorRecords, and under
# $ErrorActionPreference = "Stop" that is TERMINATING -- so a benign
# "task does not exist" from schtasks /delete would kill the script.  Native
# calls run through this helper and are judged on their exit code instead.
function Invoke-Native {
    param([Parameter(Mandatory)][scriptblock]$Block)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Block 2>&1 } finally { $ErrorActionPreference = $previous }
}

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run elevated. Right-click PowerShell -> Run as Administrator."
}

$artifacts = Join-Path $RepoRoot "forecast\artifacts"

# Logs need a directory the worker can write under a BATCH logon.  C:\Users\Public
# is NOT such a place: its write ACEs are granted to NT AUTHORITY\INTERACTIVE and
# NT AUTHORITY\SERVICE, and a credentialed scheduled task is neither -- it runs as
# BATCH, which appears nowhere in that ACL.  That is why an earlier run reported
# exit code 0 while producing no log files at all: the redirects could not be
# created.  So use a dedicated directory and grant the worker explicitly.
$runDir = "C:\satclf-run"
$outLog = "$runDir\gfc-fetch-out.txt"
$errLog = "$runDir\gfc-fetch-err.txt"
$marker = "$runDir\gfc-fetch-steps.txt"

# A logon session requires group membership; setup-raw-gfc-isolation.ps1 stripped
# every group, which is stricter than useful.  The deny ACE is against the
# INTERACTIVE account and is unaffected by this.
if (-not (Get-LocalGroupMember -Group "Users" -Member $Account -ErrorAction SilentlyContinue)) {
    Add-LocalGroupMember -Group "Users" -Member $Account
    Write-Host "[ok] added $Account to Users (needed for a logon session)"
} else {
    Write-Host "[skip] $Account is already in Users"
}

Write-Host "Granting $Account the minimum access it needs..."
& icacls $RepoRoot /grant "${Account}:(OI)(CI)RX" /T /Q | Out-Null
& icacls $artifacts /grant "${Account}:(OI)(CI)M" /Q | Out-Null
Write-Host "[ok] repo read+execute, artifacts modify"

# The venv lives inside the interactive profile, whose ACL names neither the
# worker nor Users -- so without this the account cannot execute python.exe at
# all, and the task dies before cmd can even create its redirect files.
$venvRoot = Split-Path (Split-Path $Python -Parent) -Parent
& icacls $venvRoot /grant "${Account}:(OI)(CI)RX" /T /Q | Out-Null
Write-Host "[ok] venv read+execute ($venvRoot)"

Write-Host ""
$cred = Get-Credential -UserName $Account -Message "Password for $Account"
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password))

New-Item -ItemType Directory -Force $runDir | Out-Null
& icacls $runDir /grant "${Account}:(OI)(CI)M" /Q | Out-Null
Write-Host "[ok] run directory writable by the worker ($runDir)"
Remove-Item $outLog, $errLog, $marker -ErrorAction SilentlyContinue

# Benign when the task does not exist yet; judged on exit code, not stderr.
Invoke-Native { schtasks /delete /TN $TaskName /F } | Out-Null

# The repo path contains spaces ("Satellite Image Classifier"), and schtasks /TR
# re-parses its argument, so an inline command with embedded quotes is read as
# extra options ("Invalid argument/option - 'Image'").  Put the command in a
# wrapper .cmd at a space-free path instead, so /TR needs no quoting at all.
# C:\Users\Public is reachable by the worker; the repo is not, without the grant
# above, and the profile never is.
$wrapper = "$runDir\satclf-gfc-fetch.cmd"
# Step markers so a failure can never again be silent: whatever the last recorded
# step is, that is where the account's reach ended.
@"
@echo off
echo step1-cmd-started >> "$marker"
cd /d "$RepoRoot"
echo step2-cd-repo-exit=%ERRORLEVEL% >> "$marker"
"$Python" -m forecast.gfc_archive > "$outLog" 2> "$errLog"
echo step3-python-exit=%ERRORLEVEL% >> "$marker"
echo step4-done >> "$marker"
"@ | Set-Content -Path $wrapper -Encoding ASCII
Write-Host "[ok] wrote wrapper $wrapper"

# `cd /d` inside the wrapper puts the repo root on sys.path, so `-m` resolves
# without PYTHONPATH having to survive the logon switch.
$command = $wrapper

Write-Host "Registering task as $Account..."
$created = Invoke-Native {
    schtasks /create /TN $TaskName /TR $command /SC ONCE /ST 00:00 `
             /RU $Account /RP $plain /RL LIMITED /F
}
if ($LASTEXITCODE -ne 0) {
    $created | ForEach-Object { Write-Host $_ }
    throw "schtasks /create failed with exit code $LASTEXITCODE"
}

Write-Host "Starting acquisition. ~10.92 GB; resumable if interrupted."
$started = Invoke-Native { schtasks /run /TN $TaskName }
if ($LASTEXITCODE -ne 0) {
    $started | ForEach-Object { Write-Host $_ }
    throw "schtasks /run failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Running. Tailing progress -- Ctrl+C here does NOT stop the task."
Write-Host ""

$lastLine = 0
while ($true) {
    Start-Sleep -Seconds 5
    if (Test-Path $outLog) {
        $lines = @(Get-Content $outLog -ErrorAction SilentlyContinue)
        if ($lines.Count -gt $lastLine) {
            $lines[$lastLine..($lines.Count - 1)] | ForEach-Object { Write-Host $_ }
            $lastLine = $lines.Count
        }
    }
    $query = Invoke-Native { schtasks /query /TN $TaskName /FO LIST }
    if ($LASTEXITCODE -ne 0) { break }
    $status = ($query | Select-String "Status:") -replace '.*:\s*', ''
    if ($status -notmatch "Running") { break }
}

# Capture the task's own exit code BEFORE deleting it.  Discarding this is what
# made the previous failure silent: the wrapper never ran, so both logs were
# absent and there was nothing left to explain why.
$lastResult = $null
try {
    $lastResult = (Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop).LastTaskResult
} catch {
    $lastResult = "unavailable"
}

Write-Host ""
Write-Host "--- final stdout ---"
if (Test-Path $outLog) { Get-Content $outLog -Tail 30 } else { "(no stdout)" }
Write-Host "--- stderr ---"
if (Test-Path $errLog) { Get-Content $errLog -Tail 30 } else { "(no stderr)" }
Write-Host "--- task exit code ---"
if ($lastResult -is [int]) {
    "LastTaskResult = $lastResult (0x{0:X8}){1}" -f $lastResult, $(
        if ($lastResult -eq 0) { " - success" }
        elseif ($lastResult -eq 267011) { " - task never ran" }
        elseif ($lastResult -eq 2147942401) { " - ERROR_FILE_NOT_FOUND: the account cannot reach the wrapper or the interpreter" }
        elseif ($lastResult -eq 2147942405) { " - ERROR_ACCESS_DENIED: the account lacks rights on something in the command" }
        else { "" }
    )
} else {
    "LastTaskResult = $lastResult"
}

Write-Host "--- steps reached ---"
if (Test-Path $marker) {
    Get-Content $marker
} else {
    Write-Host "(marker never created - cmd itself never ran as this account)"
}

Invoke-Native { schtasks /delete /TN $TaskName /F } | Out-Null
$plain = $null
Write-Host ""
# Artifacts are deliberately LEFT IN PLACE: deleting them is what made the
# earlier failures undiagnosable.
Write-Host "Artifacts kept for inspection in $runDir"
Write-Host "  logs   : $outLog / $errLog"
Write-Host "  steps  : $marker"
Write-Host "  wrapper: $wrapper"
