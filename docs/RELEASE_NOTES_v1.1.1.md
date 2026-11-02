# HFTA Stack Planner v1.1.1: release notes

Released: to be tagged by Paul after the commit of 2 November 2026. Previous release: v1.1.0.

## In one line

The public copy now has a **fixed allowance per workspace** and a **time limit for a whole Designer search**.
Copies on your own computer and password-protected copies work as before.

## Why

A measurement of v1.1.0 on 2 November 2026 (Docker image, public mode, 2 CPUs) showed:

| Measurement | Result |
|---|---|
| Peak memory of the whole container, one large Designer search | 136 MB |
| Time of that search | 45 minutes (20,238 HFTA runs) |

Memory is not a problem. Time is: the 60-second limit (`STAGE_SECONDS`) applied only to the first, coarse stage of
each antenna group. The later, finer stages had no limit and took 40 of the 45 minutes. The public server runs two
calculations at once, so one such search held half of the server for 45 minutes.

## New on a public copy (`PUBLIC_MODE=1`)

- **Time limit for the whole Designer search** (`SEARCH_SECONDS`, 600 s = 10 minutes). The time is shared between the
  antenna groups. When a finer stage would not fit in the time left, the search refines around fewer of the best
  layouts (3, then 1), or stops at the coarser height step. The search summary says exactly what was cut, for
  example "Tribanders: the fine search stopped at a 10 ft grid". The FOM values themselves are unchanged: every
  result is still a plain HFTA calculation.
- **Allowance per workspace, in total (not per day).** 2 Designer searches, 3 height scans and 3 VOACAP tables
  (`LIMIT_DESIGNER_RUNS`, `LIMIT_SCAN_RUNS`, `LIMIT_VOACAP_TABLES`; a negative value means no limit).
  - Only a calculation that finishes is counted. One that stops with an error, or is cancelled, is not.
  - Evaluate and Compare are not counted.
  - The count is a small file in the workspace, so a restart of the server does not reset it.
  - The notice page lists the allowance. The Designer, height scan and VOACAP buttons show what is left.
  - When it is used, the message points to the free Windows and Docker downloads. The exported project zip can be
    imported there, so no work is lost.

## Checked with the real engine (2 November 2026)

The same large search, rebuilt from this code, same 2 CPUs:

| | v1.1.0 | v1.1.1 |
|---|---|---|
| Time | 45 min | 7.3 min |
| HFTA runs | 20,238 | 4,038 |
| Peak memory | 136 MB | 107 MB |
| Best overall FOM | 14.37 dB | 14.09 dB |

The tribander group stopped at a 20 ft grid, and the summary said so. The best result was 0.28 dB lower, which is
within the 0.3 dB that the Compare step calls not significant. The finished search was counted once in the
workspace allowance.

## Not changed

- On your own computer and on a password-protected copy, there is no allowance and no time limit for the whole
  search (`SEARCH_SECONDS` is 0). Results are exactly as in v1.1.0.
- No calculation changed. OpenHFTA is used unchanged.

## Railway settings for the public copy

Replica: 2 vCPU and 1 GB of memory. Variable `LIMIT_MEMORY_MB=1024`. Image `ghcr.io/w7iv/hfta-stack-planner:v1.1.1`.
