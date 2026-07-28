# Diagnose and grant SeBatchLogonRight to the worker account.  RUN ELEVATED.
#
# Symptom this fixes: a scheduled task registered with /RU <account> /RP <pw>
# reports LastTaskResult = 267011 (SCHED_S_TASK_HAS_NOT_RUN) -- it never starts.
# A task registered WITHOUT a credential transitions to Running in under a
# second, so the difference is the logon, not the command.
#
# "Log on as a batch job" is what a credentialed task needs.  schtasks is
# documented to grant it, but does not reliably do so here.  Windows 11 Home
# ships no secpol.msc, so this uses secedit, which is present on every edition.

[CmdletBinding()]
param([string]$Account = "satclf-gfc-worker")

$ErrorActionPreference = "Stop"

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run elevated. Right-click PowerShell -> Run as Administrator."
}

$sid = (Get-LocalUser -Name $Account).SID.Value
Write-Host "Account : $Account"
Write-Host "SID     : $sid"
Write-Host ""

$work = Join-Path $env:TEMP "satclf-userrights"
New-Item -ItemType Directory -Force $work | Out-Null
$inf = Join-Path $work "userrights.inf"
$db  = Join-Path $work "userrights.sdb"
Remove-Item $inf, $db -ErrorAction SilentlyContinue

& secedit /export /areas USER_RIGHTS /cfg $inf | Out-Null
if (-not (Test-Path $inf)) { throw "secedit /export produced no file" }

$lines   = Get-Content $inf
$current = $lines | Where-Object { $_ -match '^SeBatchLogonRight' }
Write-Host "Before: $current"

if ($current -match [regex]::Escape($sid)) {
    Write-Host ""
    Write-Host "[skip] $Account ALREADY holds SeBatchLogonRight."
    Write-Host "       The task failure has another cause - do not stop here."
    return
}

# secedit wants SIDs prefixed with *, comma separated.
if ($current) {
    $updated = "$current,*$sid"
    $lines   = $lines | ForEach-Object { if ($_ -match '^SeBatchLogonRight') { $updated } else { $_ } }
} else {
    $updated = "SeBatchLogonRight = *$sid"
    $lines   = $lines | ForEach-Object {
        $_
        if ($_ -match '^\[Privilege Rights\]') { $updated }
    }
}
Write-Host "After : $updated"

Set-Content -Path $inf -Value $lines -Encoding Unicode
& secedit /configure /db $db /cfg $inf /areas USER_RIGHTS | Out-Null
if ($LASTEXITCODE -ne 0) { throw "secedit /configure failed with $LASTEXITCODE" }

# Verify by re-exporting rather than trusting the exit code.
$verifyInf = Join-Path $work "verify.inf"
Remove-Item $verifyInf -ErrorAction SilentlyContinue
& secedit /export /areas USER_RIGHTS /cfg $verifyInf | Out-Null
$after = (Get-Content $verifyInf | Where-Object { $_ -match '^SeBatchLogonRight' })

Write-Host ""
if ($after -match [regex]::Escape($sid)) {
    Write-Host "[ok] SeBatchLogonRight granted and verified."
    Write-Host "     Re-run scripts\fetch-gfc-archive.ps1"
} else {
    Write-Host "[FAIL] the right did not stick. Verified line was:"
    Write-Host "       $after"
    Write-Host "     Do not retry the fetch; the logon will fail again."
}
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
