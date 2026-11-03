# HFTA Stack Planner v1.1.2: release notes

Status: prepared 2 November 2026, not yet released. Previous release: v1.1.1.

## In one line

The Stack Designer no longer lists layouts with an antenna that does nothing, and it no longer starts a group's
height search at 5 ft. Some page texts about K6TU and about where files are processed are corrected.

## Designer: antennas that are never selected

Found by Paul on the public copy, 2 November 2026. A search with one or two 40 m Yagis and stack switching listed
"40 m Yagi 5 / 145", "15 / 145" and "25 / 145" as three rows with exactly the same score.

The cause: with switching, each target and band uses the best setting of the switch box (the whole stack or one
antenna alone). Here the 145 ft Yagi alone was best everywhere. The lower Yagi was never selected, so its height
changed nothing, and every height gave the same score. The HFTA calculations were correct; the Designer showed
the result wrongly. The original HFTA does not search heights, so it never shows this.

Now:
- A layout with an antenna that no target selects is left out when the layout without that antenna was also
  searched (for example a group of "1 to 2" antennas) and scores at least as well.
- When the number of antennas is fixed, one such layout is kept for each set of used antennas, and the row says
  "Never selected: 40 m Yagi at 55 ft ...".
- Of two layouts with the same score, the one with fewer antennas is listed first.
- The search summary says how many layouts were left out for this reason.

## Designer: the lowest height of a group

An empty "From" field used to mean "one step above the ground", so 5 ft with a 5 ft step. It now means a quarter
wavelength on the group's lowest band, rounded up to the step: 35 ft for 40 m, 20 ft for a 20-15-10 m tribander,
70 ft for 80 m. A lower height can still be typed in. The inputs line of the result shows the height used.

## Page text

- K6TU.NET makes HFTA terrain profiles (360 files, one per degree of bearing) free of charge for registered users;
  registration is free. The old text said K6TU sells them.
- "A DEM file is processed on this computer only" was untrue on a hosted copy. The text now says what happens on
  every copy: only this planner reads the file, makes the profiles and then deletes the file.

## Not changed

- No HFTA calculation changed. OpenHFTA is used unchanged. Evaluate and Compare are not affected.
- Results of a search with no unused antennas, and with a typed lowest height, are the same as in v1.1.1.

## Checked

`tests/test_designer_unused.py` (3 tests, added to release-readiness): 171 two-antenna layouts with an unused
lower antenna are left out when single antennas are searched too; with a fixed count of two, one row per top height
is kept and names the unused antenna, and real stacks are all kept; the empty lowest height is 20 ft (tribander) and
35 ft (40 m), and a typed 5 ft is used as it is.
