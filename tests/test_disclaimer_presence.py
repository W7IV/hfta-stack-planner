"""Release documentation smoke check: warnings are present in source and distributables."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

expected = {
    "DISCLAIMER.md": ["not a safety analysis", "structural", "OpenHFTA", "MIT License", "AS IS"],
    "README.md": ["Safety, engineering and accuracy notice", "DISCLAIMER.md"],
    "templates/guide.html": ['id="safety-disclaimer"', "qualified", "performance guarantee"],
    "templates/v2.html": ["/guide#safety-disclaimer"],
    "templates/index.html": ["/guide#safety-disclaimer"],
    "core/report.py": ["Important safety and performance limitations", "Software supplied AS IS"],
    "core/exports.py": ["IMPORTANT: COMPARATIVE RADIO PLANNING ONLY", "PLANNING ESTIMATES ONLY"],
    "tools/windows/README-Windows.txt": ["IMPORTANT: LEGAL, PERFORMANCE AND ENGINEERING LIMITATIONS", "DISCLAIMER.md"],
    "tools/build_windows.sh": ['cp "$REPO/DISCLAIMER.md" "$PKG/"'],
}

for filename, phrases in expected.items():
    data = (ROOT / filename).read_text(encoding="utf-8")
    for phrase in phrases:
        if phrase not in data:
            raise AssertionError(f"{filename}: missing {phrase!r}")
print("PASS: disclaimer exists in documentation, UI, exports and Windows packaging")
