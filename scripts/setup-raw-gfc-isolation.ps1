# Provision raw-GFC process isolation.  RUN ELEVATED (Administrator).
#
# Why this exists: child processes inherit the parent's Windows token, so
# `icacls` alone cannot separate the sealed GFC worker from analysis code
# running under the same account.  Anything the worker can read, a sibling
# child of the analysis account can read too.  Real separation needs a second
# security principal, and creating one requires administrator rights -- which
# is why this is a script a human runs once rather than something the pipeline
# attempts on its own.
#
# After running it, verify from a NORMAL (non-elevated) shell:
#   $env:PYTHONPATH = "<repo root>"
#   & C:\Users\josha\.venvs\satclf\Scripts\python.exe -m pytest forecast/tests/test_raw_gfc_isolation.py -q
# The live both-directions test stops skipping and must pass.

[CmdletBinding()]
param(
    [string]$Account = "satclf-gfc-worker",
    [string]$RawRoot = "C:\Users\josha\ml-data\deforestation-risk\hansen",
    [string]$AnalysisUser = $env:USERNAME
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run elevated. Right-click PowerShell -> Run as Administrator."
}

Write-Host "Account      : $Account"
Write-Host "Raw GFC root : $RawRoot"
Write-Host "Denying read : $AnalysisUser"
Write-Host ""

# 1. The dedicated least-privilege principal.
if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) {
    Write-Host "[skip] local account already exists"
} else {
    $password = Read-Host -AsSecureString "Password for $Account"
    New-LocalUser -Name $Account `
                  -Description "Sealed GFC reader" `
                  -Password $password `
                  -PasswordNeverExpires | Out-Null
    Write-Host "[ok] created local account"
}

# Keep it out of every group that would grant interactive reach.
foreach ($group in @("Users", "Administrators")) {
    if (Get-LocalGroupMember -Group $group -Member $Account -ErrorAction SilentlyContinue) {
        Remove-LocalGroupMember -Group $group -Member $Account -ErrorAction SilentlyContinue
        Write-Host "[ok] removed $Account from $group"
    }
}

# 2. The raw tile directory.
New-Item -ItemType Directory -Force $RawRoot | Out-Null

# 3. ACLs.  Inheritance is broken FIRST: an inherited grant to the interactive
#    account would otherwise survive the deny ACE and silently defeat it.
& icacls $RawRoot /inheritance:r | Out-Null
Write-Host "[ok] broke ACL inheritance"

& icacls $RawRoot /grant "${Account}:(OI)(CI)F" | Out-Null
& icacls $RawRoot /grant "Administrators:(OI)(CI)F" | Out-Null
& icacls $RawRoot /deny  "${AnalysisUser}:(OI)(CI)R" | Out-Null
Write-Host "[ok] granted worker + Administrators, denied $AnalysisUser"

Write-Host ""
Write-Host "Effective permissions:"
& icacls $RawRoot

Write-Host ""
Write-Host "Done. Re-run the isolation tests from a NORMAL shell to confirm both"
Write-Host "directions: the worker succeeds and the analysis account is denied."
