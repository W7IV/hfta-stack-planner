"""Release safety: unsigned Windows artifacts must never reach public releases.
No live Azure or GitHub credentials are needed for this static regression.
"""
from pathlib import Path
repo = Path(__file__).resolve().parent.parent
wf = (repo / ".github/workflows/release.yml").read_text()
ps = (repo / "tools/windows/artifact_signing.ps1").read_text()
doc = (repo / "docs/ARTIFACT_SIGNING.md").read_text()

assert "environment: artifact-signing" in wf
assert "id-token: write" in wf and "uses: azure/login@v3" in wf
assert "azure/artifact-signing-action@v2" in wf
assert "endpoint: https://eus.codesigning.azure.net/" in wf
assert "signing-account-name: hftasigning2026" in wf
assert "timestamp-rfc3161: http://timestamp.acs.microsoft.com" in wf
assert "timestamp-digest: SHA256" in wf and "file-digest: SHA256" in wf
assert "secrets.HFTA_CERT_PROFILE" in wf
assert "secrets.AZURE_CLIENT_ID" in wf
assert "secrets.AZURE_TENANT_ID" in wf
assert "secrets.AZURE_SUBSCRIPTION_ID" in wf
assert "exclude-azure-cli-credential: false" in wf
assert "exclude-environment-credential: true" in wf
assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in wf
assert "needs: [windows-sign, docker]" in wf, "Public release must depend on signing."
assert "name: windows-signed-package, path: dist" in wf
assert "with: { name: windows-package, path: dist }" not in wf, "Never publish original unsigned ZIP."
assert "files: ${{ steps.targets.outputs.files }}" in wf
assert "Get-AuthenticodeSignature" in ps
assert "TimeStamperCertificate" in ps
assert "NotSigned" in ps and "'Valid'" in ps
for target in ("Start HFTA Stack Planner.exe", "OpenYTWCore.dll", "voacapl.exe"):
    assert target in ps, f"Mandatory Windows binary missing: {target}"
for ext in ("'.exe'", "'.dll'", "'.pyd'"):
    assert ext in ps, f"PE image type missing: {ext}"
assert "1000" in ps, "Require explicit signing budget safeguard"
assert "repo:W7IV/hfta-stack-planner:environment:artifact-signing" in doc
assert "Certificate Profile Signer" in doc
print("PASS: signing workflow gates public releases on Azure OIDC and verified timestamped PE images")
