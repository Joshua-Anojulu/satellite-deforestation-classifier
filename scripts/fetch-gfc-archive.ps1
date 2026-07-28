# Acquire the frozen GFC archive.  RUN ELEVATED (Administrator).
#
# Under elevation-based isolation (see setup-raw-gfc-isolation.ps1) the raw-GFC
# directory grants Administrators and SYSTEM only, so an elevated process
# reaches it directly.  No second account, no scheduled task, no wrapper: those
# existed only to work around the deny ACE the previous model needed, and every
# one of them failed differently on Windows 11 Home.
#
# Acquisition is a deliberate privileged step.  Analysis code runs unelevated
# and remains locked out, which is the property that matters.

[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\Users\josha\OneDrive\Documents\Satellite Image Classifier",
    [string]$Python   = "C:\Users\josha\.venvs\satclf\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run elevated. Right-click PowerShell -> Run as Administrator."
}

if (-not (Test-Path $Python)) { throw "interpreter not found: $Python" }

Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot

Write-Host "Acquiring the GFC archive: 21 tiles x 3 layers = 63 files, ~10.92 GB."
Write-Host "Resumable -- anything already present and verified is skipped."
Write-Host ""

& $Python -m forecast.gfc_archive
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
    Write-Host "[ok] archive certified."
    Write-Host "Now re-verify isolation from a NORMAL (unelevated) shell:"
    Write-Host '  $env:PYTHONPATH = "C:\Users\josha\OneDrive\Documents\Satellite Image Classifier"'
    Write-Host '  & C:\Users\josha\.venvs\satclf\Scripts\python.exe -m pytest forecast/tests/test_raw_gfc_isolation.py -q'
} else {
    Write-Host "[FAIL] acquisition exited $code. Nothing was certified."
}
exit $code
