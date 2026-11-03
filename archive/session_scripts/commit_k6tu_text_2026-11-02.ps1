# Commit the corrected K6TU and "this computer" texts (Terrain step, library), and push them to GitHub.
# Run from PowerShell:
#   powershell.exe -ExecutionPolicy Bypass -File .\archive\session_scripts\commit_k6tu_text_2026-11-02.ps1
# It commits ONLY the files listed below, by path. It does not tag: the public copy shows the change after a
# later release (v1.1.2 or newer). Paul's own copy shows it after the next deploy of main.

$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Paul\Documents\GitHub\hfta-stack-planner'

function Stop-Script([string]$why) {
    Write-Host ''
    Write-Host ('STOPPED: ' + $why) -ForegroundColor Red
    exit 1
}

$files = @(
    'static/v2.js',
    'archive/session_scripts/commit_public_live_d5_2026-11-02.ps1'
)

# 1. Right repository and branch, and the D5 commit is the last one
$branch = git --no-pager rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) { Stop-Script 'not a git repository' }
if ($branch -ne 'main') { Stop-Script ('on branch ' + $branch + ', expected main') }
$last = git --no-pager log -1 --format='%s'
if ($last -notlike '*cost decision D5*') { Stop-Script ('the last commit is not the D5 commit (this script may have run already): ' + $last) }
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
Terrain step: correct the K6TU note and the "this computer" notes

- The note said "K6TU sells HFTA-ready one-degree terrain sets". That
  is wrong: K6TU.NET makes HFTA terrain profiles (360 files, one per
  degree of bearing) free of charge for registered users, and
  registration is free (k6tu.net, checked 2 November 2026).
- "A DEM file is processed on this computer only" and "The file stays
  on this computer" were untrue on a hosted copy, where the file goes
  to the server. New text, true on every copy: only this planner reads
  the file; it makes the profiles, then deletes it (v2.py site_dem);
  the file is not sent to any other service.
- The library notes no longer say "on this computer".

Only page text changes. Also adds the previous session script, which
has run.
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
