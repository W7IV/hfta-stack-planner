# Copyright (c) 2026 W7IV. MIT License.
# Prepare and verify Artifact Signing for HFTA Windows ZIP contents.
# Sign only binaries that are not already validly Authenticode-signed.
# Keep existing valid third-party signatures intact.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('Prepare', 'Verify')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$PackageRoot,
    [string]$ManifestPath = 'signing-targets.json'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$extensions = @('.exe', '.dll', '.pyd')
$files = @(Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object { $_.Extension.ToLowerInvariant() -in $extensions })
if ($files.Count -eq 0) { throw 'No Windows executable images found in package.' }
$launcher = Join-Path $root 'Start HFTA Stack Planner.exe'
$engine = Join-Path $root 'openhfta\OpenYTWCore.dll'
$voacap = Join-Path $root 'voacap\bin\voacapl.exe'
foreach ($required in @($launcher, $engine, $voacap)) {
    if (!(Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing bundled executable: $required" }
}
if ($Mode -eq 'Prepare') {
    $toSign = @()
    $alreadySigned = 0
    foreach ($file in $files) {
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        if ($signature.Status -eq 'Valid') {
            $alreadySigned++
        } elseif ($signature.Status -eq 'NotSigned') {
            $toSign += $file.FullName
        } else {
            throw "Cannot safely sign $($file.FullName): existing signature state $($signature.Status). Investigate before publishing."
        }
    }
    if ($toSign.Count -eq 0) { throw 'No unsigned Windows binaries found, unexpected for freshly built HFTA launcher.' }
    # Protect the Basic plan against accidental oversized bulk-signing.
    if ($toSign.Count -gt 1000) { throw "Unexpectedly found $($toSign.Count) unsigned binaries (limit 1000); review before spending signing quota." }
    $toSign | ConvertTo-Json -Depth 2 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
    if (!$env:GITHUB_OUTPUT) { throw 'GITHUB_OUTPUT missing; run this from GitHub Actions.' }
    $marker = 'HFTA_SIGNING_FILES_END'
    "files<<$marker" | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
    $toSign | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
    $marker | Out-File $env:GITHUB_OUTPUT -Append -Encoding utf8
    Write-Host "Signing $($toSign.Count) previously unsigned .exe/.dll/.pyd binaries; preserving $alreadySigned existing valid signatures."
} else {
    if (!(Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Signing manifest missing: $ManifestPath" }
    $toVerify = @(Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json)
    if (!$toVerify.Count) { throw 'Empty signing manifest.' }
    foreach ($path in $toVerify) {
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        if ($signature.Status -ne 'Valid') {
            throw "Artifact Signing verification failed for $path : $($signature.Status) $($signature.StatusMessage)"
        }
        if (!$signature.TimeStamperCertificate) {
            throw "RFC3161 trusted timestamp missing for $path. Signed files must remain valid after short-lived certificate expiry."
        }
    }
    # The launch executable must be covered, not merely DLLs.
    if ($launcher -notin $toVerify) {
        $launcherSignature = Get-AuthenticodeSignature -LiteralPath $launcher
        if ($launcherSignature.Status -ne 'Valid') { throw 'Launcher is not Authenticode valid.' }
    }
    Write-Host "PASS: Verified $($toVerify.Count) signed binaries with trusted timestamps, including the HFTA launcher."
}
