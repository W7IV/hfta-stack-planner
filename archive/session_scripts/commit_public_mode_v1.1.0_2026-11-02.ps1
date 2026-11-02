# Commit the public-mode work (Steps 1 to 8, release notes v1.1.0) and push it to GitHub.
# Run from PowerShell:
#   powershell.exe -ExecutionPolicy Bypass -File .\archive\session_scripts\commit_public_mode_v1.1.0_2026-11-02.ps1
# It commits ONLY the files listed below, by path. It does not tag. Tag later with tag_v1.1.0_2026-11-02.ps1.

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
    'core/compromise.py',
    'core/limits.py',
    'core/stats.py',
    'core/terrain.py',
    'core/workspaces.py',
    'docs/PUBLIC_MODE_BRIEF.md',
    'docs/RELEASE_NOTES_v1.1.0.md',
    'static/v2.js',
    'templates/_public_footer.html',
    'templates/guide.html',
    'templates/index.html',
    'templates/privacy.html',
    'templates/stats.html',
    'templates/v2.html',
    'templates/welcome.html',
    'tests/test_arrl_files.py',
    'tests/test_cleanup.py',
    'tests/test_hardening.py',
    'tests/test_limits.py',
    'tests/test_public_mode.py',
    'tests/test_public_pages.py',
    'tests/test_stats.py',
    'tests/test_terrain_cache.py',
    'v2.py'
)

# 1. Right repository and branch
$branch = git --no-pager rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) { Stop-Script 'not a git repository' }
if ($branch -ne 'main') { Stop-Script ('on branch ' + $branch + ', expected main') }
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
Add a public mode for an open copy of the planner (v1.1.0)

PUBLIC_MODE=1 lets any radio amateur use the planner in a browser
with no account. It is off by default; local and password-protected
copies behave as before.

- One private workspace per browser after an "I understand" notice;
  signed cookie; no user list; /admin returns 404.
- Daily clean-up deletes workspaces unused for 30 days.
- Limits: one job per workspace, two on the server with a waiting
  line, memory guard, disk, projects, uploads, VOACAP tables and
  terrain fetches per day, new workspaces per address.
- Shared terrain-tile cache with a size limit and safe temp files.
- ARRL .PRN files stay in the owner's workspace (PRN_UPLOAD=off
  refuses them).
- Footer on every page, /privacy page, anonymous daily usage
  counts at /stats (STATS_PASSWORD).
- Every copy: classic optimiser jobs have an owner; one upload
  limit; login lock-out uses the proxy address; hosted copies
  default to at most 4 calculation processes.

Plan and status: docs/PUBLIC_MODE_BRIEF.md
Release notes: docs/RELEASE_NOTES_v1.1.0.md
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
    Write-Host 'Next: on GitHub, Actions, check that release-readiness passes. Then run tag_v1.1.0_2026-11-02.ps1.'
} else {
    Stop-Script 'local main and origin/main differ after the push'
}
