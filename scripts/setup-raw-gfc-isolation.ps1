# Establish elevation-based raw-GFC isolation.  RUN ELEVATED (Administrator).
#
# Goal, unchanged: code running as the ordinary analysis user must not be able
# to READ raw lossyear.  Denying write was never the point.
#
# Mechanism (deviation 2).  The first design gave the tiles to a dedicated
# least-privilege account and denied the interactive one.  Sound, and unusable
# here: launching any process as a second local account failed six ways on
# Windows 11 Home, and it blocks analysis time too, since the sealed worker must
# read the tiles as well.
#
# So the boundary is the UAC split token.  The directory grants Administrators
# and SYSTEM and nothing else.  An UNELEVATED process has no entry, hence no
# access; an ELEVATED one reaches it through Administrators.  Analysis code runs
# unelevated; the sealed worker and the downloader are launched elevated.
#
# NO DENY ACE.  An explicit deny outranks the Administrators allow and locks out
# elevated access as well -- that is exactly what broke acquisition before.
# Absence of a grant is what denies the unelevated user.
#
# Trade-off, stated so it is never glossed: ANY elevated process can read the
# tiles, not only the sealed worker.  This distinguishes privilege levels, where
# the previous design distinguished principals.

[CmdletBinding()]
param(
    [string]$RawRoot   = "C:\Users\josha\ml-data\deforestation-risk\hansen",
    [string]$OldAccount = "satclf-gfc-worker",
    [switch]$RemoveOldAccount
)

$ErrorActionPreference = "Stop"

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run elevated. Right-click PowerShell -> Run as Administrator."
}

$analysisUser = $env:USERNAME
Write-Host "Raw GFC root  : $RawRoot"
Write-Host "Analysis user : $analysisUser (must have NO entry when this finishes)"
Write-Host ""

New-Item -ItemType Directory -Force $RawRoot | Out-Null

Write-Host "Current ACL:"
& icacls $RawRoot
Write-Host ""

# Reset to inherited, then break inheritance again from a clean base.  Doing it
# in this order clears the old deny ACE and the old worker grant without having
# to name every entry.
& icacls $RawRoot /reset /T /Q | Out-Null
& icacls $RawRoot /inheritance:r | Out-Null
Write-Host "[ok] cleared previous ACEs and broke inheritance"

& icacls $RawRoot /grant "Administrators:(OI)(CI)F" /Q | Out-Null
& icacls $RawRoot /grant "SYSTEM:(OI)(CI)F" /Q | Out-Null
Write-Host "[ok] granted Administrators and SYSTEM only"

# Belt and braces: if a grant for the interactive user survived somehow, drop it.
& icacls $RawRoot /remove:g "$analysisUser" /T /Q | Out-Null
Write-Host "[ok] removed any grant for $analysisUser"

if ($RemoveOldAccount) {
    if (Get-LocalUser -Name $OldAccount -ErrorAction SilentlyContinue) {
        Remove-LocalUser -Name $OldAccount
        Write-Host "[ok] deleted the now-unused local account $OldAccount"
    }
} elseif (Get-LocalUser -Name $OldAccount -ErrorAction SilentlyContinue) {
    Write-Host "[note] local account $OldAccount is now unused."
    Write-Host "       Re-run with -RemoveOldAccount to delete it."
}

Write-Host ""
Write-Host "Resulting ACL:"
& icacls $RawRoot
Write-Host ""
Write-Host "Verify from a NORMAL (unelevated) shell -- that is the only context"
Write-Host "in which the boundary is observable:"
Write-Host '  $env:PYTHONPATH = "C:\Users\josha\OneDrive\Documents\Satellite Image Classifier"'
Write-Host '  & C:\Users\josha\.venvs\satclf\Scripts\python.exe -m pytest forecast/tests/test_raw_gfc_isolation.py -q'
