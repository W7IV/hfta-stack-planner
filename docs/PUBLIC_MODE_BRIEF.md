# Brief: PUBLIC_MODE for HFTA Stack Planner

Prepared 2 November 2026 from commit 82284df (v1.0.6). Status: plan only.
Nothing has been changed in the code or on Railway.

**Goal.** Add a `PUBLIC_MODE` setting so a second Railway copy can serve any
radio amateur without accounts. Paul's own copy must behave exactly as it does
now. Release the result as v1.1.0.

**Design decision (agreed).** Option A: the public rules live in `main`, behind
a flag that is off by default. There is no separate branch. The public Railway
project deploys a tagged image (for example `v1.1.0`), never `main`. Paul's own
copy keeps deploying `main`, so new work is tried there first.

## Decisions (Paul, 2 November 2026)

| No. | Decision | Answer |
|---|---|---|
| D1 | Allow a public copy (changes the rule "processing runs locally") | Yes, with the limits in Step 3 |
| D2 | Access model | One workspace per browser, no accounts, 30-day expiry, plus anonymous usage statistics (Step 9) |
| D2b | What statistics record | Counts only, on our server. No IP address stored, no third-party scripts |
| D3 | ARRL `.PRN` files | Option A: private upload only. Ask an attorney to check |
| D4 | Operator in the footer | Paul F. Merrill, W7IV |
| D5 | Cost limit of the public copy | Changed 2 November 2026 (was "$10 per month hard limit"). Railway sets usage limits for the whole account only, and the account carries other projects (about $350 in October 2026), so an account limit cannot protect this copy. The cost limit is the replica size, 2 vCPU and 1 GB: about $50 per month at most, with full load all month. Paul checks the project's own usage on Railway every week; above about $1 a week, reduce to 1 vCPU or remove the copy. For scale: the whole planner cost $1.43 in October 2026 |
| D6 | Ask K6TU to link both ways | Yes, after the private trial |

Paul is the orchestrator. Claude is the developer and carries out the steps.

## Rules for the whole task

- `PUBLIC_MODE` is off by default. With it off, no behaviour changes.
- Work in small steps, one commit per step, tests passing before the next step.
- Do not touch Paul's Railway project. Do not tag or publish releases (Paul
  does that from his laptop).
- If a step needs a change outside the files named, stop and ask.
- Never store, list or export ARRL `.PRN` files outside the owner's own
  workspace.
- File names below come from a reading of the GitHub files. Confirm each one
  before editing. `v2.py` and `core/users.py` were not read.

## Before any code (Paul)

1. **Memory outage (W1).** Read the Railway deploy log for the 14 October
   failure. If it shows an out-of-memory kill, set `HFTA_WORKERS=2` on the
   present copy.
2. **Decisions.** D3 (ARRL files: option A or B), D4 (operator name and
   domain), D5 (monthly spending limit on Railway). Steps 1 to 4 do not depend
   on them.
3. **Image visibility.** Set the `ghcr.io/w7iv/hfta-stack-planner` package to
   public (HANDOFF.md, open task 2).

## Step 1: Fix three faults that affect both copies

**Status: done in the working folder on 2 November 2026, not committed.**
Tests: `tests/test_hardening.py` (6 tests, also added to
`.github/workflows/release-readiness.yml`). `test_accounts.py` still passes.
`test_hfta_match.py` and `test_wrapper.py` fail on the laptop, with and without
these changes, because the native OpenHFTA library is not built there. CI builds it.

Done first because public mode would make each one worse.

- **Job ownership.** Designer jobs in `v2.py` already set `owner`. Only the
  classic optimiser in `app.py` created jobs without one, so anyone could read
  or cancel them. Now every job has an owner, and a job without an owner is
  visible to nobody. Test: user B cannot read or cancel user A's job.
- **Upload limit.** `MAX_CONTENT_LENGTH` is set to 8 MB, then overwritten
  later in the file with 512 MB. Make this one setting. Keep 512 MB for the
  present copy if Paul needs large terrain files. Public mode gets its own
  lower limit in Step 3.
- **Client address.** The login rate limit trusts the first `X-Forwarded-For`
  value, which a client can forge. Use the address added by Railway's proxy
  (the last value). Test with a forged header.

Done when: the three tests pass and the existing tests still pass.

## Step 2: Workspaces (new `core/workspaces.py`)

**Status: done in the working folder on 2 November 2026, not committed.**
Files: `core/workspaces.py` (new), `templates/welcome.html` (new),
`app.py`, `tests/test_public_mode.py` (11 tests, also added to the CI
workflow). The workspace folder is `public/<id>/` and its projects are in
`public/<id>/projects`. A `.last_used` file in the folder records use (renewed
at most every 10 minutes) for the clean-up in Step 4. The page script needed no
change: an API call without a workspace gets the same 401 answer as a login,
and `/login` sends the visitor to `/welcome`.

- When `PUBLIC_MODE=1`: on the first visit show the disclaimer page with an
  "I understand" button. Then create a random workspace ID and store it in a
  signed cookie (HttpOnly, SameSite=Lax, Secure).
- Each workspace is a folder `public/<random id>/` on the `/data` volume. Set
  the project root from the cookie, in the same place where `app.py` now sets
  it from the logged-in user.
- No login, no user list. `/admin` returns 404.
- Startup check: stop with a clear error if `PUBLIC_MODE=1` and `APP_PASSWORD`
  is also set. Use a separate secret key for the cookie.
- Without `APP_PASSWORD` the present code uses one shared store, and sessions
  are not set up. Public mode must never fall into that path.

Done when: two browsers cannot see each other's projects or jobs, and
`/admin` returns 404.

## Step 3: Limits

**Status: done in the working folder on 2 November 2026, not committed.**
Files: `core/limits.py` (new), `app.py`, `v2.py`, `core/compromise.py`,
`tests/test_limits.py` (13 tests, also in the CI workflow). Every value below
has an environment setting (`LIMIT_...`, `STAGE_SECONDS`, `MAX_GROUP_LAYOUTS`,
`MAX_UPLOAD_MB`, `HFTA_WORKERS`); see the top of `core/limits.py`. Nothing is
enforced unless `PUBLIC_MODE=1`.

Decisions taken while building, to confirm:
- A VOACAP table is one region. A request for four regions uses four of the
  three daily tables and is refused. Raise `LIMIT_VOACAP_PER_DAY` after the
  trial if this is too tight.
- Daily counts are kept in memory and start again after a restart.
- The memory guard reads the container's memory limit when the host shows it.
  If it does not, set `LIMIT_MEMORY_MB` to the replica limit (for example
  4096). With no limit known, the guard does nothing. The guard never stops a
  job from starting when nothing else is running, so the line cannot stall.
- Public upload limit is 25 MB (`MAX_UPLOAD_MB`), and a project zip may
  unpack to at most the workspace size (50 MB).
- Default calculation processes: 2 on a public copy, at most 4 on any other
  hosted copy, all CPUs on your own computer. This also answers the 24-process
  setting seen on Railway.
- Measured 2 November 2026 in the v1.1.0 image (public mode, 2 CPUs, 4 GB):
  one large Designer search peaks at 136 MB for the whole container, so the
  replica can be 1 GB (`LIMIT_MEMORY_MB=1024`). The same search took 45
  minutes, because `STAGE_SECONDS` limited only the first stage. v1.1.1 adds
  a limit for the whole search (`SEARCH_SECONDS`, 600 s) and, on Paul's
  proposal, an allowance per workspace (2 Designer searches, 3 height scans,
  3 VOACAP tables, in total). See `docs/RELEASE_NOTES_v1.1.1.md`.

Environment settings, with these defaults for public mode only:

| Setting | Default |
|---|---|
| `HFTA_WORKERS` | 2 |
| Running jobs per workspace | 1 |
| Running jobs on the server | 2; others wait in a queue with a clear message |
| `STAGE_SECONDS` (Designer, per search stage) | 60 (Paul's copy: 240) |
| `MAX_GROUP_LAYOUTS` | 50,000 (the present maximum is 200,000) |
| Projects per workspace | 5 |
| Disk per workspace | 50 MB, including the upload limit |
| VOACAP table runs per workspace per day | 3 |
| Terrain fetches per workspace per day | 20 |
| New workspaces per address per day | 10 |

Each refusal shows a plain message, for example: "The public server allows one
calculation at a time. For larger studies, use the free Windows or Docker
version." Files likely involved: `app.py`, `v2.py`, `core/compromise.py`.

Done when: each limit has a test that shows the refusal message.

## Step 4: Clean-up

**Status: done in the working folder on 2 November 2026, not committed.**
Files: `core/workspaces.py` (clean-up functions added), `app.py` (starts the
daily thread in public mode), `tests/test_cleanup.py` (10 tests, also in the CI
workflow). The expiry is 30 days, or `WORKSPACE_EXPIRY_DAYS`. The first run is
2 minutes after the server starts, then every 24 hours. Rules built in: only
folders named with a workspace number are touched; a workspace with a running
calculation is kept; the last-use time is read again just before deleting;
the result of the latest run is in `workspaces.LAST` for the statistics page
(Step 8). Because the server may restart often, the clean-up also runs shortly
after each start.

A daily thread deletes workspace folders not used for 30 days. It must delete
only folders inside `public/`, and only expired ones. Test with a fake old
folder and a new one: only the old one goes.

## Step 5: Shared terrain cache

**Status: done in the working folder on 2 November 2026, not committed.**
The tile cache `_cache/hgt` already sat outside the workspaces and was shared
by everyone, so the work was to make it safe for many visitors. Files:
`core/terrain.py`, `core/limits.py`, `v2.py`, `tests/test_terrain_cache.py`
(8 tests, also in the CI workflow). Changes: a size limit (`TERRAIN_CACHE_MB`,
default 1000 MB on a public copy, none elsewhere) that removes the tiles used
longest ago; unique temporary file names, and a tolerant replace, because two
requests loading the same tile collided on Windows ("Access is denied"); stale
`.tmp` files older than one hour are removed; at most 2 online fetches at the
same time (`LIMIT_TERRAIN_CONCURRENT`), a third gets a plain "try again in a
minute". The 3DEP fetch (US) is not cached: its temporary file lives in the
visitor's own workspace and is deleted after use. Tests show that no tile is
ever stored inside a workspace and that the clean-up never touches the cache.

Share the tile cache (`_cache/hgt`) across workspaces. Public elevation data
only. Never share `.PRN` files or project files.

## Step 6: ARRL files (after decision D3)

**Status: option A done in the working folder on 2 November 2026, not
committed.** Files: `static/v2.js`, `v2.py`, `core/limits.py`,
`tests/test_arrl_files.py` (6 tests, also in the CI workflow). With the
default (`PRN_UPLOAD=private`) a visitor's `.PRN` files go into their own
workspace only. The Targets page shows: "Upload only files you are entitled to
use ... never shared or listed, and are deleted with the workspace after 30
days without use" (the same words are on the first-use page). Tests show that
another visitor cannot read the file or find it in their library, that the file
exists only in its owner's folder, and that the clean-up deletes it. Option B
is built in as a setting, so it can be chosen without new code:
`PRN_UPLOAD=off` refuses `.PRN` uploads and library copies (403, plain
message), skips `.PRN` files inside an imported project zip, and hides the
upload buttons. The attorney check from decision D3 is still open.

- Option A: upload goes to the private workspace only, with the notice
  "Upload only files you are entitled to use". Deleted with the workspace.
  Ask the operator's attorney about this option.
- Option B: hide the upload in public mode. Users generate VOACAP tables only.

## Step 7: Pages and text

**Status: done in the working folder on 2 November 2026, not committed.**
Files: `templates/_public_footer.html`, `templates/privacy.html` (new);
`app.py`, `templates/v2.html`, `welcome.html`, `guide.html`, `index.html`,
`static/v2.js`, `README.md`; `tests/test_public_pages.py` (8 tests, also in the
CI workflow). The footer is on every page of a public copy: operator, MIT
licence, link to the source, "not affiliated with ARRL or the OpenHFTA
authors", links to the privacy note, the safety limits and the free Windows
and Docker downloads, and the OpenStreetMap credit (the map itself already
carried it). `/privacy` is open without a workspace. The operator comes from
`OPERATOR_NAME` (default "Paul F. Merrill, W7IV"); `OPERATOR_CONTACT` is shown
only when set. **Paul must give a contact text before the trial**: no address
was supplied, and none was invented. The Help text and the README now say what
holds on a public copy. Checked in a browser on a local public-mode server.
The privacy page says "no analytics" until Step 8 sets `USAGE_COUNTS = True`
in `app.py`; Step 8 must do that in the same change that adds the counts.

- Footer on every page: operator name, MIT licence, GitHub link, "not
  affiliated with ARRL or the OpenHFTA authors".
- Privacy note: what is stored, the 30-day deletion, no tracking, the access
  log kept by Railway.
- Link to the Windows and Docker downloads for heavy use.
- OpenStreetMap credit on the map.
- Update the README lines "keep any hosted copy private" and "There is no
  automatic retention or deletion" to say they apply to the password mode only.

## Step 8: Anonymous usage statistics (decision D2b)

**Status: done in the working folder on 2 November 2026, not committed.**
Files: `core/stats.py`, `templates/stats.html`, `tests/test_stats.py` (9 tests,
also in the CI workflow) (new); `app.py`, `v2.py`, `core/limits.py`,
`templates/privacy.html`, `README.md`, `tests/test_public_pages.py`.
Counts per day (UTC) in `stats/usage.json` on the volume: new workspaces,
active workspaces, jobs by type (HFTA runs, Designer, height scans, VOACAP
tables, terrain fetches, classic optimiser), waits in line, and refusals by
limit. Active workspaces are counted once a day with a keyed hash kept in
memory only; the key is random, new each day and never written. After a
restart a workspace may be counted twice that day. `/stats` needs
`STATS_PASSWORD` (any user name, eight failures lock the address for five
minutes); without that setting the page does not exist. It also shows the
present state: workspaces on the volume, space used, tile cache size, jobs
running and waiting, memory share (when known) and the latest clean-up. A
JSON form is at `/stats?format=json`. The privacy page now describes the
counts. Counting never stops a request: a failure is logged and ignored.
Checked in a browser on a local public-mode server.

Purpose: Paul can see how the public copy is used, without identifying anyone.

- Count per day, in a small file or table on the `/data` volume: new
  workspaces, active workspaces, jobs run by type (HFTA, Designer, VOACAP
  table, terrain fetch), limit refusals, and queue waits.
- Store no IP address, no workspace ID and no user agent in the statistics.
  Count each workspace once per day by using a daily random key that is
  discarded at midnight.
- No third-party scripts and no new cookies. The content security policy stays
  as it is.
- A `/stats` page for Paul only. Protect it with a separate `STATS_PASSWORD`
  setting. If the setting is empty, the page returns 404.
- The privacy note (Step 7) must say: "The server keeps daily counts of use.
  They contain no personal data." The README line "no analytics" is updated to
  match.

Done when: counts rise after a test session, no identifier appears in the
stored file, and `/stats` returns 404 without the password.

## Step 9: Release

**Status: v1.1.0 released on 2 November 2026 (commit 8ac22b7). v1.1.1
(allowance and search time limit) committed (d4641af), release-readiness
green, tagged and released the same day.**
The version comes
from the git tag (there is no version file). Release notes:
`docs/RELEASE_NOTES_v1.1.0.md`. README Docker example now names `v1.1.0`.
`HANDOFF.md` has a "Public copy" section with the open items. A clean copy
(HEAD plus exactly the 28 listed files) passed every test that runs on the
laptop. Scripts in `archive/session_scripts/`:
`commit_public_mode_v1.1.0_2026-11-02.ps1` (commits by path, pulls, pushes) and
`tag_v1.1.0_2026-11-02.ps1` (run only after the release-readiness workflow
passes on GitHub). The next commit must include both scripts.

Run the full test suite and `ruff`. Bump the version to v1.1.0 and write the
release notes. **Stop.** Paul tags the release from his laptop, so the
existing workflow builds the image.

## After release (Paul)

**Status, 2 November 2026: steps 1 to 4 done. The public copy runs v1.1.1 at
hfta-stack-planner-production-6f55.up.railway.app. Read-only checks passed:
`/healthz` ok, notice page with the allowance, `/privacy`, `/stats` asks for
its password, `/admin` 404, security headers present. `SECRET_KEY` is not
set: the app keeps a random key on the volume, as Paul's own copy does.
Step 6 replaced by decision D5 (changed). Next: step 7.**

Lesson from the first attempt: Railway deploys as soon as the image is added,
and variables added afterwards stay staged until **Deploy** is pressed. The
first deploy therefore ran without `PUBLIC_MODE` and stopped at the start-up
check ("Hosted copy without APP_PASSWORD"). Set the variables, the volume and
the size first, then press Deploy once.

1. Railway: New Project, then Deploy a Docker image
   `ghcr.io/w7iv/hfta-stack-planner:v1.1.1`. Use a new project, not a new
   service in the present one. Replica limits: 2 vCPU, 1 GB.
2. Add a volume at `/data`.
3. Variables: `PUBLIC_MODE=1`, `HOSTED=1`, `HFTA_WORKERS=2`,
   `LIMIT_MEMORY_MB=1024`, a new `SECRET_KEY`, `STATS_PASSWORD`, operator name
   and contact. Do not copy variables from the present project.
4. Networking: generate a domain, or add a custom domain and its DNS record.
5. Health check path `/healthz`; restart policy "on failure".
6. Cost: no account usage limit (see D5). Check the public project's usage on
   Railway every week.
7. Private trial for one week with 3 to 5 trusted amateurs. Then announce.

## Acceptance checks before announcing

- Two browsers: each sees only its own projects.
- Paul's own copy still works with its login. The two copies share no volume,
  secret or domain.
- One Designer run at the public limits finishes in about 10 minutes or less,
  with no memory stop (check Railway metrics).
- After 2 finished Designer searches, a third is refused with the download
  message, and the Designer step shows "all 2 ... are used".
- A second job from the same browser is refused with the plain message. A
  third browser waits in the queue.
- A workspace older than 30 days is deleted by the clean-up. A newer one is
  kept.
- `/admin` returns 404. No page lists other users or workspaces.
- Disclaimer step shown before first use. Footer, privacy note and
  OpenStreetMap credit present.
- One result checked against the original HFTA, as for every release.
