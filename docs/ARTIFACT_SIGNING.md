# Microsoft Azure Artifact Signing for HFTA Stack Planner

The HFTA Windows release workflow uses Microsoft's **Artifact Signing** service (formerly
Trusted Signing) for Authenticode signing with RFC3161 timestamps. This does **not**
change the HFTA Stack Planner MIT software license or W7IV project branding.
The Authenticode publisher is the legal individual verified by Azure.

**Status:** Workflow is prepared, but signing cannot run until the repository owner completes the
Azure application/federation and GitHub signing-environment configuration below.
**Do not push a public `v*` tag or claim to have a signed ZIP until a manual signed build passes.**
A signing failure causes the release job to fail closed; no unsigned Windows ZIP will be attached.

## Known resources

- Azure subscription: `HFTACert` (select this one, not the separate `Azure subscription`).
- Resource group: `rg-hfta-signing`.
- Artifact Signing account: `hftasigning2026` in **East US**.
- Endpoint: `https://eus.codesigning.azure.net/`.
- Identity validation: **Individual / Public**, completed 2026-10-31 (expires 2027-10-31).
- Certificate profile: **copy its actual name** from the Azure account's
  **Objects → Certificate profiles** list. A certificate thumbprint is **not** the profile name.
- Signing certificate lifetimes are short; Microsoft rotates them. Timestamped signatures remain verifiable.

## 1. Create a dedicated Microsoft Entra workload identity for GitHub Actions

In the [Azure Portal](https://portal.azure.com), search for **App registrations**
under Microsoft Entra ID, select **New registration**, and name it `hfta-github-release-signer`.
For Supported account types, choose **Accounts in this organizational directory only (Single tenant)**.
No redirect URI is required. After registration, record the following values from the application's
**Overview** page:

- **Application (client) ID** (for `AZURE_CLIENT_ID`);
- **Directory (tenant) ID** (for `AZURE_TENANT_ID`).

The subscription ID for `HFTACert` can be found on **Subscriptions → HFTACert → Overview**
(for `AZURE_SUBSCRIPTION_ID`). These are identifiers, not passwords.
**Do not create a client secret**; the workflow uses GitHub OIDC.

## 2. Grant signing rights to the app, not merely the human Owner account

Open [the Artifact Signing account](https://portal.azure.com) →
`hftasigning2026` → **Access control (IAM)** → **Add role assignment**.

1. Select **Artifact Signing Certificate Profile Signer** under Job function roles.
2. Under **Members**, choose **User, group, or service principal** and search for
   `hfta-github-release-signer` (the app's enterprise application/service principal).
   The selection popup may default to users; switch to service principals if necessary.
3. Select the signer app and **Review + assign**.
4. Verify in **IAM → Check access** that the *service principal* has Certificate Profile Signer.
   The user's **Owner** and **Identity Verifier** assignments do **not** authorize the workflow to sign.

The account resource scope is sufficient. Avoid Contributor or Owner permissions for the build app.

## 3. Set up an OIDC federation for the release environment

In **Microsoft Entra ID → App registrations → hfta-github-release-signer →
Certificates & secrets → Federated credentials → Add credential**:

| Azure field | Value |
| --- | --- |
| Federated credential scenario | GitHub Actions deploying Azure resources |
| Organization | `W7IV` |
| Repository | `hfta-stack-planner` |
| Entity type | **Environment** |
| GitHub environment name | `artifact-signing` |
| Credential name | `hfta-github-artifact-signing` |

The generated subject must be **exactly**
`repo:W7IV/hfta-stack-planner:environment:artifact-signing`.
The issuer should be `https://token.actions.githubusercontent.com` and
the audience `api://AzureADTokenExchange`. Save the credential.
This allows future release tags without creating a new federated credential for each tag.

## 4. Configure GitHub's environment and credentials

On GitHub, open
[W7IV/hfta-stack-planner → Settings → Environments](https://github.com/W7IV/hfta-stack-planner/settings/environments).
Create the environment **`artifact-signing`**.

- Under **Deployment branches and tags**, choose **Selected branches and tags**.
  Allow **Branch: `main`** (manual signing test) and **Tag: `v*`** (versioned releases).
- Consider enabling **Required reviewers** to authorize every signing operation; this adds
  a manual approval step, including for release tags. Do not select *Prevent self-review*
  unless another trusted maintainer can approve your runs.
- Under **Environment secrets**, create **exactly four** secrets:
  - `AZURE_CLIENT_ID`: application (client) ID, not the object ID.
  - `AZURE_TENANT_ID`: directory (tenant) ID.
  - `AZURE_SUBSCRIPTION_ID`: HFTACert subscription ID.
  - `HFTA_CERT_PROFILE`: exact **certificate profile name** from Azure.
- Never enter your Azure password, AU10TIX credential, Microsoft Authenticator recovery
  information, or a signing private key in GitHub.

The `.github/workflows/release.yml` signer job requests only `id-token: write` and
`contents: read`. It uses `azure/login@v3` with the federated identity and
`azure/artifact-signing-action@v2`, using East US and RFC3161 timestamping.
The environment's restrictions are an essential part of the security boundary.

## 5. Perform a manual test before publishing

In [GitHub Actions](https://github.com/W7IV/hfta-stack-planner/actions/workflows/release.yml),
select **release → Run workflow**, choose branch **main**, then start.
The workflow:

1. Builds/tests the Windows package on Ubuntu/Wine.
2. Downloads the unsigned ZIP onto a clean Windows 2025 runner.
3. Finds unsigned `.exe`, `.dll` and `.pyd` components, preserving binaries
   that already have valid third-party Authenticode signatures. It refuses a
   suspiciously large signing batch (more than 1,000 files).
4. Authenticates via Azure OIDC and signs the selected files with a SHA-256
   RFC3161 timestamp from `http://timestamp.acs.microsoft.com`.
5. Verifies each new signature and its timestamp, then re-zips the original
   top-level folder without modifying the application data or legal notices.
6. Uploads the candidate as the **`windows-signed-package`** GitHub Actions artifact.

A manual run on main **does not create a public release**. Download the candidate,
test it on Windows 11 with Smart App Control active, and check the signature
under **Properties → Digital Signatures** (or use PowerShell
`Get-AuthenticodeSignature "Start HFTA Stack Planner.exe"`).
Expect the Azure-verified **legal name**, not the callsign W7IV, as the certificate subject.

## 6. Publish after a successful test

Push a new `v*` release tag only after the signed test passes. The workflow
builds, signs, checks, and publishes the **signed ZIP**. A missing environment secret,
rejected Azure role, federation failure, signing failure, or timestamp verification
failure blocks the release. Docker publishing remains an independent job, but GitHub's
public release is gated on successful Windows signing and Docker building.

You can later replace Azure Artifact Signing with SignPath or another accepted
code-signing provider without changing the application's MIT license. Existing
timestamped releases retain their historical signatures.

## Reference documentation

- [Microsoft Artifact Signing role assignment](https://learn.microsoft.com/en-us/azure/artifact-signing/tutorial-assign-roles).
- [Microsoft's GitHub OIDC signing action](https://github.com/Azure/artifact-signing-action/blob/main/docs/OIDC.md).
- [Microsoft Entra federation with GitHub](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust).
- [GitHub protected environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
