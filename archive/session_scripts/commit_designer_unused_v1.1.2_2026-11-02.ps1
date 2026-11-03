# Commit the Designer fixes for v1.1.2 (unused antennas, lowest height of a group) and push them to GitHub.
# Run from PowerShell:
#   powershell.exe -ExecutionPolicy Bypass -File .\archive\session_scripts\commit_designer_unused_v1.1.2_2026-11-02.ps1
# It commits ONLY the files listed below, by path. It does not tag. After it: run release-readiness on GitHub.

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
    'core/compromise.py',
    'static/v2.js',
    'docs/RELEASE_NOTES_v1.1.2.md',
    'tests/test_designer_unused.py',
    'archive/session_scripts/commit_k6tu_text_2026-11-02.ps1'
)

# 1. Right repository and branch, and the K6TU text commit is the last one
$branch = git --no-pager rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) { Stop-Script 'not a git repository' }
if ($branch -ne 'main') { Stop-Script ('on branch ' + $branch + ', expected main') }
$last = git --no-pager log -1 --format='%s'
if ($last -notlike '*K6TU note*') { Stop-Script ('the last commit is not the K6TU text commit (this script may have run already): ' + $last) }
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
Designer: leave out antennas that no switch setting selects (v1.1.2)

Found by Paul on the public copy: with 1 to 2 40 m Yagis and stack
switching, "40 m Yagi 5 / 145", "15 / 145" and "25 / 145" were three
rows with the same score. The 145 ft Yagi alone was the best setting
for every target, so the lower Yagi was never selected and its
height changed nothing. HFTA results were correct; the list was not.

- A layout with an antenna that no target selects is left out when
  the layout without it was searched, is free of such antennas and
  scores at least as well. Otherwise one layout per set of used
  antennas is kept, and the row says "Never selected: ...".
- Equal scores: fewer antennas first. The summary counts the
  layouts left out.
- An empty lowest height of a group is a quarter wavelength on its
  lowest band, rounded up to the step (40 m: 35 ft, 20 m: 20 ft),
  instead of one step (5 ft). A typed height is used as it is.
- tests/test_designer_unused.py (3 tests), added to release-readiness.
- README, HANDOFF, docs/RELEASE_NOTES_v1.1.2.md.

No HFTA calculation changed.
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
    Write-Host 'Next: on GitHub, Actions, run release-readiness on main.'
} else {
    Stop-Script 'local main and origin/main differ after the push'
}
