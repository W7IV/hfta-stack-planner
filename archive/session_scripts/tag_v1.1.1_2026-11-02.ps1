# Tag release v1.1.1 and push the tag. The push starts the release workflow on GitHub (Windows package, signing,
# Docker image, GitHub release).
# Run ONLY after the commit script has pushed and the release-readiness workflow on GitHub has passed:
#   powershell.exe -ExecutionPolicy Bypass -File .\archive\session_scripts\tag_v1.1.1_2026-11-02.ps1

$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Paul\Documents\GitHub\hfta-stack-planner'
$tag = 'v1.1.1'

function Stop-Script([string]$why) {
    Write-Host ''
    Write-Host ('STOPPED: ' + $why) -ForegroundColor Red
    exit 1
}

git --no-pager fetch origin --tags
if ($LASTEXITCODE -ne 0) { Stop-Script 'git fetch failed' }

$branch = git --no-pager rev-parse --abbrev-ref HEAD
if ($branch -ne 'main') { Stop-Script ('on branch ' + $branch + ', expected main') }

$local = git --no-pager rev-parse HEAD
$remote = git --no-pager rev-parse origin/main
if ($local -ne $remote) { Stop-Script 'local main is not the same as origin/main: run the commit script first, or git pull' }

$exists = git --no-pager tag --list $tag
if ($exists) { Stop-Script ('tag ' + $tag + ' already exists') }

$subject = git --no-pager log -1 --format='%s'
Write-Host ('Tagging ' + $local.Substring(0, 7) + ': ' + $subject)
if ($subject -notlike '*allowance*') { Stop-Script 'the last commit is not the v1.1.1 commit; check before tagging' }

git --no-pager tag -a $tag -m 'HFTA Stack Planner v1.1.1: public copy allowance and search time limit'
if ($LASTEXITCODE -ne 0) { Stop-Script 'git tag failed' }
git --no-pager push origin $tag
if ($LASTEXITCODE -ne 0) { Stop-Script 'git push of the tag failed' }

$remoteTag = git --no-pager ls-remote --tags origin ('refs/tags/' + $tag)
if ($remoteTag) {
    Write-Host ('DONE: ' + $tag + ' is on GitHub. The release workflow is now running (Actions tab).') -ForegroundColor Green
} else {
    Stop-Script 'the tag is not visible on GitHub'
}
