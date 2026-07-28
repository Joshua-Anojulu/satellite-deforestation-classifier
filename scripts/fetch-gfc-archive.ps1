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
# Logs go somewhere the worker can write and you can read.  Your profile is not
# such a place -- the worker has no access to it.
$outLog = "C:\Users\Public\gfc-fetch-out.txt"
$errLog = "C:\Users\Public\gfc-fetch-err.txt"

# A logon session requires group membership; setup-raw-gfc-isolation.ps1 stripped
# every group, which is stricter than useful.  The deny ACE is against the
# INTERACTIVE account and is unaffected by this.
if (-not (Get-LocalGroupMember -Group "Users" -Member $Account -ErrorAction SilentlyContinue)) {
    Add-LocalGroupMember -Group "Users" -Member $Account
    Write-Host "[ok] added $Account to Users (needed for a logon session)"
} else {
    Write-Host "[skip] $Account is already in Users"
}

Write-Host "Granting $Account the minimum repo access it needs..."
& icacls $RepoRoot /grant "${Account}:(OI)(CI)RX" /T /Q | Out-Null
& icacls $artifacts /grant "${Account}:(OI)(CI)M" /Q | Out-Null
Write-Host "[ok] repo access granted"

Write-Host ""
$cred = Get-Credential -UserName $Account -Message "Password for $Account"
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password))

Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue
# Benign when the task does not exist yet; judged on exit code, not stderr.
Invoke-Native { schtasks /delete /TN $TaskName /F } | Out-Null

# `cd /d` so `-m` finds the package on sys.path without PYTHONPATH surviving the
# logon switch.
$command = "cmd /c cd /d `"$RepoRoot`" && `"$Python`" -m forecast.gfc_archive > `"$outLog`" 2> `"$errLog`""

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

Write-Host ""
Write-Host "--- final stdout ---"
if (Test-Path $outLog) { Get-Content $outLog -Tail 30 } else { "(no stdout)" }
Write-Host "--- stderr ---"
if (Test-Path $errLog) { Get-Content $errLog -Tail 30 } else { "(no stderr)" }

Invoke-Native { schtasks /delete /TN $TaskName /F } | Out-Null
$plain = $null
Write-Host ""
Write-Host "Task removed. Full logs: $outLog / $errLog"
