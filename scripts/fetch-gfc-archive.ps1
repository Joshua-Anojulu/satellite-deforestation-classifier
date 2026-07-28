# Acquire the frozen GFC archive AS THE WORKER ACCOUNT.  RUN ELEVATED.
#
# Why not just run it elevated as yourself: the raw-GFC directory carries an
# explicit DENY for the interactive account, and in Windows an explicit deny
# beats an Administrators allow -- an elevated token still carries your user
# SID.  Acquisition has to READ each tile back (to hash it and to read its
# geotransform), which is exactly what the deny prevents.  So it runs as
# satclf-gfc-worker, which is the principal the directory belongs to.
#
# This grants the worker the minimum it needs on the repo: read+execute on the
# tree (to import the package and read the manifest) and modify on
# forecast/artifacts (to write the inventory and verification report).  The
# protected asset is the raw tiles, not the source.

[CmdletBinding()]
param(
    [string]$Account  = "satclf-gfc-worker",
    [string]$RepoRoot = "C:\Users\josha\OneDrive\Documents\Satellite Image Classifier",
    [string]$Python   = "C:\Users\josha\.venvs\satclf\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run elevated. Right-click PowerShell -> Run as Administrator."
}

$artifacts = Join-Path $RepoRoot "forecast\artifacts"

# The account needs a logon right to run anything at all.  setup-raw-gfc-isolation.ps1
# stripped it from every local group, which is stricter than useful: with no
# membership it cannot create a logon session, so Start-Process -Credential fails
# with "the user has not been granted the requested logon type".  Membership in
# Users restores that WITHOUT weakening the property that matters -- the deny ACE
# on the raw tiles is against the INTERACTIVE account, and is unaffected.
if (-not (Get-LocalGroupMember -Group "Users" -Member $Account -ErrorAction SilentlyContinue)) {
    Add-LocalGroupMember -Group "Users" -Member $Account
    Write-Host "[ok] added $Account to Users (needed for a logon session)"
}

Write-Host "Granting $Account the minimum repo access it needs..."
# Read+execute over the tree so `python -m forecast.gfc_archive` can import.
& icacls $RepoRoot /grant "${Account}:(OI)(CI)RX" /T /Q | Out-Null
# Modify on artifacts only, so it can write the inventory and report.
& icacls $artifacts /grant "${Account}:(OI)(CI)M" /Q | Out-Null
Write-Host "[ok] repo access granted"
Write-Host ""

Write-Host "Enter the password you set for $Account."
$cred = Get-Credential -UserName $Account -Message "Password for $Account"

Write-Host ""
Write-Host "Starting acquisition as $Account. ~10.92 GB; resumable if interrupted."
Write-Host ""

# -m needs the repo root on sys.path; running with it as the working directory
# is enough, so no PYTHONPATH has to survive the credential switch.
Start-Process -FilePath $Python `
              -ArgumentList "-m", "forecast.gfc_archive" `
              -WorkingDirectory $RepoRoot `
              -Credential $cred `
              -Wait `
              -RedirectStandardOutput (Join-Path $env:TEMP "gfc-fetch-out.txt") `
              -RedirectStandardError  (Join-Path $env:TEMP "gfc-fetch-err.txt")

Write-Host "--- stdout ---"
Get-Content (Join-Path $env:TEMP "gfc-fetch-out.txt") -Tail 40
Write-Host "--- stderr ---"
Get-Content (Join-Path $env:TEMP "gfc-fetch-err.txt") -Tail 20
Write-Host ""
Write-Host "Full logs: $env:TEMP\gfc-fetch-out.txt and gfc-fetch-err.txt"
