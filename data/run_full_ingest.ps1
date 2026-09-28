# Full-collection ingest: fetch -> merge -> index, unattended.
#
# Runs every stage of the pipeline over the whole archive.org gov.in.is.*
# collection and logs to data/archive/full_ingest.log. The running API keeps
# serving its old corpus until it is restarted; nothing here restarts it.
#
# Everything the run overwrites is backed up first to data/archive/backup/,
# so a failure part-way leaves a restorable previous state.
#
#   powershell -File data/run_full_ingest.ps1
#   powershell -File data/run_full_ingest.ps1 -From index   # resume a failed run

param([ValidateSet('fetch', 'merge', 'index')][string]$From = 'fetch')

$ErrorActionPreference = 'Stop'
$root   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$log    = Join-Path $root 'data\archive\full_ingest.log'
$backup = Join-Path $root 'data\archive\backup'

function Say($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Run($label, [string[]]$pyArgs, $extraEnv = @{}) {
    Say "=== $label ==="
    foreach ($k in $extraEnv.Keys) { Set-Item -Path "env:$k" -Value $extraEnv[$k] }
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUNBUFFERED = '1'
    # Windows PowerShell 5.1 turns every stderr line of a native program into
    # an error record. Under 'Stop' the first one -- a model-loading progress
    # bar -- aborted the whole script mid-index, twice. Success is judged by
    # the exit code alone, and output is stringified so the log stays UTF-8.
    $ErrorActionPreference = 'Continue'
    & $python @pyArgs 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $log -Encoding utf8
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -ne 0) { Say "FAILED: $label (exit $code)"; exit $code }
    Say "done: $label"
}

Set-Location $root
Set-Content -Path $log -Value '' -Encoding utf8
Say "full ingest started (from: $From)"
$stages = @('fetch', 'merge', 'index')
$start = [array]::IndexOf($stages, $From)

# --- back up what this run overwrites ---
# Only on a fresh run: a resumed run starts from a half-finished state, and
# backing that up would overwrite the last consistent backup with it.
if ($start -eq 0) {
    New-Item -ItemType Directory -Force $backup | Out-Null
    Copy-Item 'data\archive\ingested_standards.json' $backup -Force
    Copy-Item 'data\standards_corpus_full.json' $backup -Force
    Copy-Item 'data\eval_set_full.json', 'data\train_queries_full.json' $backup -Force
    $indexBackup = Join-Path $backup 'index_standards_corpus_full'
    if (Test-Path $indexBackup) { Remove-Item $indexBackup -Recurse -Force }   # else Copy-Item nests into it
    Copy-Item 'standards-retrieval\data\index\standards_corpus_full' $indexBackup -Recurse -Force
    Say "backed up ingest, corpus, query sets and index to data\archive\backup"
}

# --- 1. fetch every standard in the collection (cached texts are reused) ---
if ($start -le 0) { Run 'fetch' @('data\ingest_archive.py', '--limit', '30000', '--scan', '30000', '--overfetch', '1') }

# --- 2. merge into the served corpus and remap the query sets, then add the
#        editions BIS lists that the archive lacks and apply BIS's status ---
if ($start -le 1) {
    Run 'merge' @('data\build_full_corpus.py')
    Run 'add BIS standards' @('data\add_bis_standards.py')
    Run 'apply BIS status' @('data\apply_bis_status.py')
}

# --- 3. rebuild the dense and BM25 indexes for the full corpus ---
Run 'index' @('standards-retrieval\indexing\build.py') @{
    STANDARDS_CORPUS = 'full'
    PYTHONPATH = (Join-Path $root 'standards-retrieval')
}

Say "ALL STAGES COMPLETE - restart the API to serve the new corpus"