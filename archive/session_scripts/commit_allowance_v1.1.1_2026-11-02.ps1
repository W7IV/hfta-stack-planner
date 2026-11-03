# Commit v1.1.1 (allowance per workspace, time limit for a whole Designer search) and push it to GitHub.
# Run from PowerShell:
#   powershell.exe -ExecutionPolicy Bypass -File .\archive\session_scripts\commit_allowance_v1.1.1_2026-11-02.ps1
# It commits ONLY the files listed below, by path. It does not tag. Tag later with tag_v1.1.1_2026-11-02.ps1.

$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Paul\Documents\GitHub\hfta-stack-planner'

function Stop-Script([string]$why) {
    Write-Host ''
    Write-Host ('STOPPED: ' + $why) -ForegroundColor Red
    exit 1
}

$files = @(
    '.github/workflows/release-readiness.yml',
    'HANDOFF.md',
    'README.md',
    'app.py',
    'archive/session_scripts/commit_public_mode_v1.1.0_2026-11-02.ps1',
    'archive/session_scripts/tag_v1.1.0_2026-11-02.ps1',
    'core/compromise.py',
    'core/limits.py',
    'docs/PUBLIC_MODE_BRIEF.md',
    'docs/RELEASE_NOTES_v1.1.1.md',
    'static/v2.js',
    'templates/welcome.html',
    'tests/test_allowance.py',
    'tests/test_arrl_files.py',
    'v2.py'
)

# 1. Right repository and branch, and the v1.1.0 commit is the last one
$branch = git --no-pager rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) { Stop-Script 'not a git repository' }
if ($branch -ne 'main') { Stop-Script ('on branch ' + $branch + ', expected main') }
$last = git --no-pager log -1 --format='%s'
if ($last -notlike '*public mode*') { Stop-Script ('the last commit is not the v1.1.0 commit: ' + $last) }
Write-Host ('Branch: ' + $branch + '. Files listed: ' + $files.Count)

# 2. Every listed file exists and really differs from the last commit
foreach ($f in $files) {
    if (-not (Test-Path -LiteralPath $f)) { Stop-Script ('missing file: ' + $f) }
    $inHead = git --no-pager ls-files -- $f
    if ($inHead) {
        $now = git --no-pager hash-object -- $f
        $old = git --no-pager rev-parse ('HEAD:' + $f)
        if ($now -eq $old) { Stop-Script ('listed but unchanged since the last commit: ' + $f) }
    }
}
Write-Host 'All listed files exist and are changed or new.'

# 3. Other changed tracked files would stop git pull --rebase: list them and stop
$changed = @(git --no-pager ls-files -m)
$extra = @($changed | Where-Object { $files -notcontains $_ })
if ($extra.Count -gt 0) {
    Write-Host 'Tracked files changed but NOT in this commit:' -ForegroundColor Yellow
    $extra | ForEach-Object { Write-Host ('  ' + $_) }
    Stop-Script 'commit or undo those changes first, then run this script again'
}

# 4. Show what will be committed
git --no-pager status --short -- $files
if ($LASTEXITCODE -ne 0) { Stop-Script 'git status failed' }

# 5. Stage and commit by path (only these files, whatever else is staged)
git --no-pager add -- $files
if ($LASTEXITCODE -ne 0) { Stop-Script 'git add failed' }

$lt = [char]60
$gt = [char]62
$msg = @'
Public copy: allowance per workspace and a time limit per search (v1.1.1)

A measurement of v1.1.0 (Docker image, public mode, 2 CPUs) showed
136 MB peak memory but 45 minutes for one large Designer search:
STAGE_SECONDS limited only the first stage of each antenna group.

- SEARCH_SECONDS (600 s on a public copy, none otherwise): time budget
  of the whole Designer search, shared between the groups. A finer
  stage that would not fit refines fewer layouts (3, then 1) or stops
  at the coarser step; the search summary says what was cut.
- Allowance per workspace, in total: 2 Designer searches, 3 height
  scans, 3 VOACAP tables (LIMIT_DESIGNER_RUNS, LIMIT_SCAN_RUNS,
  LIMIT_VOACAP_TABLES). Only finished calculations count. Kept in a
  file in the workspace. The notice page and the buttons show what is
  left; the refusal points to the free downloads and project import.
- tests/test_allowance.py (9 tests), added to release-readiness.

Copies that are not public are unchanged.
Release notes: docs/RELEASE_NOTES_v1.1.1.md
'@
$msg = $msg + "`n" + 'Co-Authored-By: Claude Opus 5.5 ' + $lt + 'noreply@anthropic.com' + $gt + "`n"
$msgFile = Join-Path $env:TEMP 'hfta_commit_msg.txt'
Set-Content -Path $msgFile -Value $msg -Encoding ASCII
if (-not (Test-Path $msgFile)) { Stop-Script 'could not write the commit message file' }

git --no-pager commit -F $msgFile -- $files
if ($LASTEXITCODE -ne 0) { Stop-Script 'git commit failed' }
Remove-Item $msgFile -ErrorAction SilentlyContinue

# 6. Bring in any remote changes, then push
git --no-pager pull --rebase
if ($LASTEXITCODE -ne 0) { Stop-Script 'git pull --rebase failed: the commit is made but not pushed' }
git --no-pager push
if ($LASTEXITCODE -ne 0) { Stop-Script 'git push failed: the commit is made but not pushed' }

# 7. Proof
Write-Host ''
git --no-pager log -1 --format='%h %s'
$local = git --no-pager rev-parse HEAD
$remote = git --no-pager rev-parse origin/main
if ($local -eq $remote) {
    Write-Host 'DONE: committed and pushed. origin/main is at the new commit.' -ForegroundColor Green
    Write-Host 'Next: on GitHub, Actions, run release-readiness on main. When green, run tag_v1.1.1_2026-11-02.ps1.'
} else {
    Stop-Script 'local main and origin/main differ after the push'
}
