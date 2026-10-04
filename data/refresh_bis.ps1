# Bring the served corpus up to date with BIS, unattended: meant to run weekly.
#
#   1. list what BIS has published or revised since its Know Your Standard
#      snapshot (1 October 2025), from its new standards portal
#   2. read BIS's record for anything new, and re-read any record older than
#      -RecheckDays, which is how withdrawals and new amendments are noticed
#   3. combine, then merge into the corpus and rebuild the indexes
#      (run_full_ingest.ps1 -From merge)
#
# Logs to data/archive/refresh_bis.log. The running API keeps serving the old
# corpus until it is restarted; nothing here restarts it.
#
#   powershell -File data\refresh_bis.ps1                      # weekly
#   powershell -File data\refresh_bis.ps1 -RecheckDays 0       # new standards only
#
# To run it every Sunday at 02:00 (Windows Task Scheduler):
#   schtasks /Create /SC WEEKLY /D SUN /ST 02:00 /TN "Standards engine BIS refresh" ^
#     /TR "powershell -NoProfile -File D:\Projects\ai-compliance\data\refresh_bis.ps1"

param([double]$RecheckDays = 30)

$ErrorActionPreference = 'Stop'
$root   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$log    = Join-Path $root 'data\archive\refresh_bis.log'

function Say($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Run($label, [string[]]$pyArgs) {
    Say "=== $label ==="
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUNBUFFERED = '1'
    # As in run_full_ingest.ps1: stderr lines are not failures, the exit code is.
    $ErrorActionPreference = 'Continue'
    & $python @pyArgs 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $log -Encoding utf8
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -ne 0) { Say "FAILED: $label (exit $code)"; exit $code }
    Say "done: $label"
}

Set-Location $root
Say "BIS refresh started (recheck records older than $RecheckDays days)"
Run 'portal: published since the snapshot' @('data\bis_portal.py', 'published')
Run 'portal: records' @('data\bis_portal.py', 'details', '--recheck-days', "$RecheckDays")
Run 'portal: combine' @('data\bis_portal.py', 'combine')

Say "=== merge and index (run_full_ingest.ps1 -From merge) ==="
& powershell -NoProfile -File (Join-Path $root 'data\run_full_ingest.ps1') -From merge
if ($LASTEXITCODE -ne 0) { Say "FAILED: merge and index (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
Say "BIS refresh complete - restart the API to serve the new corpus"
