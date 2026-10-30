"""Generate a machine-readable license inventory of Python packages in the running distribution.
Usage: python tools/license_inventory.py OUTPUT_DIRECTORY
"""
from __future__ import annotations
import importlib.metadata as md
import json
import shutil
import sys
from pathlib import Path

out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
licenses = out / "python-package-licenses"
licenses.mkdir(exist_ok=True)
rows = []
for dist in sorted(md.distributions(), key=lambda d: (d.metadata.get("Name") or "").lower()):
    name = dist.metadata.get("Name") or "unknown"
    version = dist.version
    expression = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
    classifiers = [c.removeprefix("License :: ").strip() for c in dist.metadata.get_all("Classifier", []) if c.startswith("License :: ")]
    copied = []
    for f in dist.files or []:
        parts = Path(str(f)).parts
        leaf = parts[-1].lower() if parts else ""
        # Only distributable notice files attached to installed package metadata.
        if not (leaf.startswith(("license", "licence", "copying", "notice", "copyright"))):
            continue
        if not any(".dist-info" in part for part in parts):
            continue
        src = Path(dist.locate_file(f))
        if not src.is_file():
            continue
        dest = licenses / f"{name.replace('/', '_')}-{version}" / "/".join(parts[1:])
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied.append(str(dest.relative_to(out)).replace("\\", "/"))
    rows.append(dict(name=name, version=version, license_expression=expression, license_classifiers=classifiers, notice_files=copied))
(out / "python-dependencies.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
with (out / "PYTHON-DEPENDENCIES.md").open("w", encoding="utf-8") as f:
    f.write("# Installed Python distribution license inventory\\n\\nGenerated from the exact packaged Python runtime. License metadata may be incomplete; review each package's own notice and distribution terms.\\n\\n")
    for r in rows:
        f.write(f"- {r['name']} {r['version']}: {r['license_expression'] or ', '.join(r['license_classifiers']) or 'UNSPECIFIED'}; notice files: {', '.join(r['notice_files']) or 'NONE FOUND'}\\n")
print(f"Inventory: {len(rows)} Python distributions, {sum(len(r['notice_files']) for r in rows)} copied license files")
