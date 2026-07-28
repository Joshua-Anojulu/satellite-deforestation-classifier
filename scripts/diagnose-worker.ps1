# Capability map for the worker account.  RUN ELEVATED.
#
# Five launcher attempts have each failed for a different reason, and the last
# one reported exit code 0 while producing no output at all -- which cannot be
# read as success.  So this stops fixing and starts measuring: it runs a probe
# AS THE WORKER that records what it can actually do, one step at a time, and
# leaves every artifact in place for inspection.

[CmdletBinding()]
param(
    [string]$Account  = "satclf-gfc-worker",
    [string]$RepoRoot = "C:\Users\josha\OneDrive\Documents\Satellite Image Classifier",
    [string]$Python   = "C:\Users\josha\.venvs\satclf\Scripts\python.exe",
    [string]$RawRoot  = "C:\Users\josha\ml-data\deforestation-risk\hansen",
    [string]$TaskName = "SatclfWorkerProbe"
)

$ErrorActionPreference = "Stop"

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run elevated. Right-click PowerShell -> Run as Administrator."
}

function Invoke-Native {
    param([Parameter(Mandatory)][scriptblock]$Block)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Block 2>&1 } finally { $ErrorActionPreference = $previous }
}

$probeDir = "C:\Users\Public\satclf-probe"
$marker   = "$probeDir\steps.txt"
$wrapper  = "$probeDir\probe.cmd"

Remove-Item $probeDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $probeDir | Out-Null
# Make sure the worker can write here regardless of Public's defaults.
& icacls $probeDir /grant "${Account}:(OI)(CI)M" /Q | Out-Null

# Each step appends to the marker.  Whatever the LAST recorded step is, that is
# where the account's reach ends.
@"
@echo off
echo step1-cmd-started >> "$marker"
echo step2-can-write-public >> "$marker"
"$Python" --version >> "$marker" 2>&1
echo step3-python-exit=%ERRORLEVEL% >> "$marker"
cd /d "$RepoRoot"
echo step4-cd-repo-exit=%ERRORLEVEL% >> "$marker"
dir /b forecast\gfc_archive.py >> "$marker" 2>&1
echo step5-read-repo-exit=%ERRORLEVEL% >> "$marker"
"$Python" -c "import forecast.gfc_archive as m; print('import-ok', len(m.LAYERS))" >> "$marker" 2>&1
echo step6-import-exit=%ERRORLEVEL% >> "$marker"
echo probe > "$RawRoot\_worker_write_probe.txt"
echo step7-write-hansen-exit=%ERRORLEVEL% >> "$marker"
type "$RawRoot\_worker_write_probe.txt" >> "$marker" 2>&1
echo step8-read-hansen-exit=%ERRORLEVEL% >> "$marker"
echo step9-done >> "$marker"
"@ | Set-Content -Path $wrapper -Encoding ASCII

$cred  = Get-Credential -UserName $Account -Message "Password for $Account"
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password))

Invoke-Native { schtasks /delete /TN $TaskName /F } | Out-Null
Write-Host "Registering probe as $Account..."
Invoke-Native {
    schtasks /create /TN $TaskName /TR $wrapper /SC ONCE /ST 00:00 `
             /RU $Account /RP $plain /RL LIMITED /F
} | Out-Null
if ($LASTEXITCODE -ne 0) { throw "probe /create failed with $LASTEXITCODE" }

Invoke-Native { schtasks /run /TN $TaskName } | Out-Null
Write-Host "Probe started; waiting up to 60s..."

$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $state = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
    if ($state -ne "Running" -and (Test-Path $marker)) { break }
    if ($state -ne "Running" -and (Get-Date) -gt (Get-Date).AddSeconds(-1)) {
        if ((Get-ScheduledTaskInfo -TaskName $TaskName).LastTaskResult -ne 267009) { break }
    }
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "=== task state ==="
Write-Host ("State          : " + (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State)
Write-Host ("LastTaskResult : " + $info.LastTaskResult)
Write-Host ("LastRunTime    : " + $info.LastRunTime)
Write-Host ""
Write-Host "=== how far the worker got ==="
if (Test-Path $marker) { Get-Content $marker } else { Write-Host "(marker never created - cmd itself never ran as this account)" }
Write-Host ""
Write-Host "Artifacts LEFT IN PLACE for inspection:"
Write-Host "  $probeDir"
Write-Host "  task '$TaskName' (delete with: schtasks /delete /TN $TaskName /F)"
$plain = $null
