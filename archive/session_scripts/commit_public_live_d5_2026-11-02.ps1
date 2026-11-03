# Commit the record of the live public copy and the changed decision D5 (cost limit), and push it to GitHub.
# Run from PowerShell:
#   powershell.exe -ExecutionPolicy Bypass -File .\archive\session_scripts\commit_public_live_d5_2026-11-02.ps1
# It commits ONLY the files listed below, by path. Documents and scripts only: no code changes.

$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Paul\Documents\GitHub\hfta-stack-planner'

function Stop-Script([string]$why) {
    Write-Host ''
    Write-Host ('STOPPED: ' + $why) -ForegroundColor Red
    exit 1
}

$files = @(
    'HANDOFF.md',
    'docs/PUBLIC_MODE_BRIEF.md',
    'docs/RELEASE_NOTES_v1.1.1.md',
    'archive/session_scripts/commit_allowance_v1.1.1_2026-11-02.ps1',
    'archive/session_scripts/tag_v1.1.1_2026-11-02.ps1'
)

# 1. Right repository and branch, and the v1.1.1 commit is the last one
$branch = git --no-pager rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) { Stop-Script 'not a git repository' }
if ($branch -ne 'main') { Stop-Script ('on branch ' + $branch + ', expected main') }
$last = git --no-pager log -1 --format='%s'
if ($last -notlike '*allowance*') { Stop-Script ('the last commit is not the v1.1.1 commit (this script may have run already): ' + $last) }
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
Record the live public copy (v1.1.1) and the changed cost decision D5

- The public copy runs v1.1.1 on its own Railway project
  (2 vCPU, 1 GB, volume /data). Read-only checks passed.
- D5 changed: Railway sets usage limits for the whole account only,
  and the account carries other projects, so the replica size is the
  cost limit of the public copy (about 50 USD per month at most).
  Paul checks the project's usage every week.
- Brief: lesson from the first deploy (variables stay staged until
  Deploy is pressed). Release notes: v1.1.1 release date.
- The two v1.1.1 session scripts, which have run.
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
} else {
    Stop-Script 'local main and origin/main differ after the push'
}
