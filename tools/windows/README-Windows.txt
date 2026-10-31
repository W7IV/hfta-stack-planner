HFTA Stack Planner for Windows (64-bit)
=======================================

1. Unzip this folder anywhere, for example C:\HFTA-Stack-Planner. Do not put it on a network drive.
2. Double-click "Start HFTA Stack Planner.exe". A console window opens and stays open while the local program runs.
   Your browser opens http://localhost:5055 . If it does not, open that address yourself.
3. To stop: close the black window.

IMPORTANT WHEN UPGRADING: Close every old HFTA console first. Only one instance can use
http://127.0.0.1:5055 at a time. The launcher now refuses to start when that port is
in use, so a newer version never silently opens an older installation in your browser.
If you see an occupied-port error, close the old HFTA window (or stop the service
using port 5055) and launch again.

The program uses a native Windows launcher, not a downloaded batch script.
Official GitHub release ZIPs built through the new Azure Artifact Signing release
workflow contain signed Windows executable components with RFC3161 timestamps.
The signer will be listed under the individual's verified legal name; W7IV is the
project branding, not the certificate subject. Windows may still apply reputation
or policy checks, and locally rebuilt ZIPs are NOT signed automatically.
Only run software downloaded from the official release page after checking its source
and file signature. Do not turn off Smart App Control or antivirus protection to run
the planner. If Windows blocks the release, use Docker locally and report the exact warning
in a GitHub issue.
This package contains no installer and changes nothing outside its own folder.

Your projects, terrain files and elevation-angle files live in the "data" folder next to this file.
To move to a new version, unzip the new package and copy the "data" folder across.

What is in the package
  Start HFTA Stack Planner.exe  Native launcher (no CMD or PowerShell)
  runtime\    Python 3.12 (python-build-standalone) with the libraries the planner needs
  app\        the planner itself (open source, github.com/W7IV/hfta-stack-planner)
  openhfta\   the OpenHFTA calculation core (RioDXGroup, BSD Zero Clause), built from the commit in COMMIT,
              checked against the original HFTA output (app\tests\test_hfta_match.py)
  voacap\     VOACAP (public domain, ITS/NTIA; Linux port by M0DNS built for Windows) for "Generate with VOACAP"
  data\       your projects (made on first start)

"Fetch terrain online" needs an internet connection; everything else runs offline.

IMPORTANT: LEGAL, PERFORMANCE AND ENGINEERING LIMITATIONS
This software is for comparative amateur-radio planning only. It is not a
structural or safety assessment. Do not use its guy/ice, spacing, terrain or
antenna calculations to establish safe loads, clearances, tower heights,
anchor capacity or safe construction. The results do not guarantee RF gain,
coverage, contacts or contest outcomes. Confirm inputs independently and
obtain qualified engineering review for construction and safety decisions.
Provided AS IS without warranty under the MIT license. Read the full
DISCLAIMER.md included at the root of this Windows distribution.

Read "Getting started" from the Help button, or open http://localhost:5055/guide .
