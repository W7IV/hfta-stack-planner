# HFTA Stack Planner v1.1.0: release notes

Released: to be tagged by Paul after the commit of 2 November 2026. Previous release: v1.0.6.

## In one line

The planner can now run as a **public copy**: any radio amateur opens it in a browser, with no account and no
installation. A public copy is off by default. Copies on your own computer and password-protected copies work as
before.

## New: public copy (`PUBLIC_MODE=1`)

- **No account.** A first visit shows a short notice ("planning estimates only"). The button *I understand* makes a
  private workspace tied to that browser. Visitors never see each other's projects, files or calculations.
- **Automatic deletion.** A workspace not used for 30 days is deleted with its files. Visitors keep their work by
  exporting the project zip.
- **ARRL files.** A visitor may upload their own `.PRN` files into their own workspace only. They are never shared or
  listed. The setting `PRN_UPLOAD=off` refuses ARRL files completely.
- **Fair use limits.** One calculation per workspace; two at a time on the server, others wait in line; a memory
  guard; 5 projects and 50 MB per workspace; 25 MB uploads; 3 VOACAP tables and 20 online terrain fetches per
  workspace per day; a shorter Designer search. Each limit gives a plain message and has a setting.
- **Shared terrain cache.** Elevation tiles are kept once for all visitors, with a size limit.
- **Pages.** A footer on every page (operator, licence, source, downloads, OpenStreetMap credit) and a privacy page
  (`/privacy`).
- **Usage counts.** Daily totals only, with no address and no workspace number, for the operator at `/stats`
  (needs `STATS_PASSWORD`).

All settings are listed in the README, section "Public copy".

## Changes that affect every copy

- **Calculation processes.** Without `HFTA_WORKERS`, a hosted copy now starts at most 4 calculation processes
  (a public copy 2). A host reports the CPUs of the whole machine; 24 were seen on Railway. On your own computer the
  default is still all CPUs.
- **Classic optimiser jobs** now belong to the person who started them, like Designer jobs. Another user can no
  longer read or cancel them.
- **One upload limit** (`MAX_UPLOAD_MB`, 512 MB by default). An earlier 8 MB setting was overwritten later in the
  code and had no effect.
- **Login lock-out on a hosted copy** now uses the address added by the hosting proxy (`TRUSTED_PROXY_HOPS`), so a
  forged `X-Forwarded-For` header cannot avoid it.
- **Terrain tiles.** Two requests for the same tile at the same moment no longer fail on Windows.

## Not changed

- No calculation changed. OpenHFTA is used unchanged, and every FOM can still be repeated in the original HFTA.
- The Windows package and the Docker image are built as before.

## Before a public copy is announced

See `docs/PUBLIC_MODE_BRIEF.md`, sections "After release" and "Acceptance checks". Open items: the real memory use
of a Designer run at the public limits (measure in the Docker image), the operator contact text, and the attorney
check on ARRL files.
