HFTA Stack Planner for Windows (64-bit)
=======================================

1. Unzip this folder anywhere, for example C:\HFTA-Stack-Planner. Do not put it on a network drive.
2. Double-click "Start HFTA Stack Planner.bat". A black window opens and stays open; that is the program.
   Your browser opens http://localhost:5055 . If it does not, open that address yourself.
3. To stop: close the black window.

Windows 11 Smart App Control may block a downloaded .bat launcher. If the file is blocked,
verify it came from the intended GitHub release; then inspect the extracted launcher
file's Properties for an "Unblock" checkbox. Do not disable Smart App Control.
This package contains no installer and changes nothing outside its own folder.

Your projects, terrain files and elevation-angle files live in the "data" folder next to this file.
To move to a new version, unzip the new package and copy the "data" folder across.

What is in the package
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
