# HFTA Stack Planner v1.1.3: release notes

Status: prepared 3 November 2026. Previous release: v1.1.2.

## In one line

Changes found in the first days of the public-copy trial: the Rohn 65G guy button is removed, a public workspace
may make 7 VOACAP tables, error messages are never empty, and the operator's usage page fits the screen.

## Towers: no more "Rohn 65G 160 ft standard" button

The button filled the guy table with one tower's guy heights and anchor distances, and set the tower height to
160 ft without saying so. An engineered tower may have more guy levels, or other heights, for the wind load at its
site. Every user now enters the guys from their own tower's engineering drawings. Guy tables already saved in
projects are kept.

## Public copy: 7 VOACAP tables per workspace

The public copy allowed 3 VOACAP tables per workspace (one region is one table). The trial refused a worldwide set,
which is 7 regions. Both values are now 7: in total, and per day. The limit is there for server CPU time, not for
storage. A user makes the tables once and they stay in the project's library.

Comparing two sites far apart needs a set of tables for each site. That is what the free Windows and Docker versions
are for (Paul, 3 November); the public copy is for trying the planner.

Only a public copy (`PUBLIC_MODE=1`) has these limits. The Windows and Docker versions have none.

## Error messages are never empty

When the server refused a request with a reply that was not JSON, the page showed an empty message (""). Over
HTTP/2, which Railway uses, the browser gives no status text. The page now shows the error number and what to do,
for example "The upload is too large for this server (error 413)."

## Usage page (operator only)

The by-day table of `/stats` no longer needs a sideways slider. Column headings wrap, and the reasons for refusals
are on their own line under each day.

## Not changed

- No HFTA calculation changed. OpenHFTA is used unchanged.
- The Designer, Evaluate and Compare give the same results as in v1.1.2.

## Known small point (not fixed)

On a public copy, the daily VOACAP count goes up when a request is accepted; the total goes up only when a table
finishes. So a table that fails or is cancelled still uses part of that day's limit (not the total).

## Checked

`tests/test_allowance.py` (7 tables accepted; one more refused with "1 left; this one needs 2"),
`tests/test_limits.py` (the default values), `tests/test_stats.py` (the usage page), and the full release-readiness
run on GitHub.

## For the public copy after release

Set the image to `ghcr.io/w7iv/hfta-stack-planner:v1.1.3` and deploy. The variables `LIMIT_VOACAP_TABLES=7` and
`LIMIT_VOACAP_PER_DAY=7` are now the defaults; they may stay or be removed.
