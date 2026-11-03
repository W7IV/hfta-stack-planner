"""Designer: antennas that no switch setting uses, and the default lowest height of a group (2 Nov 2026: a 40 m Yagi at
5, 15 or 25 ft under one at 145 ft gave three equal rows). Run: python tests/test_designer_unused.py (no native core)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["PROJECTS_DIR"] = str(Path(tempfile.mkdtemp(prefix="hfta-unused-")) / "projects")
os.environ.pop("PUBLIC_MODE", None)
REPO = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO))
from core import compromise as CM, project as P

PASSED = []
def test(fn):
    fn(); PASSED.append(fn.__name__); print("ok ", fn.__name__); return fn

class FakeScorer:
    """Stands in for the HFTA runs. The top antenna alone is the best switch setting, peaking at 145 ft. With STACK on,
    a layout whose antennas are all at 60 ft or more is better as a whole stack (+0.5), so every antenna is used."""
    STACK = False
    def __init__(self, proj, slug, site, targets, pool, job):
        self.targets, self.idx, self.pat, self.stages = targets, {0.0: "f"}, {}, []
        self.n_fom = self.n_failed = self.n_filled = 0; self.workers = 1
    def calibrate(self, model, bands, c, mode): return 0.01
    def needed(self, model, bands, cands, mode): return [c for c in cands if c not in self.pat]
    def compute(self, keys, label):
        self.stages.append({"stage": label, "runs": len(keys)})
        for k in keys: self.pat[k] = 1
    def score(self, model, bands, c, mode):
        v = -abs(max(c) - 145) / 10; used = [max(c)]
        if self.STACK and len(c) > 1 and min(c) >= 60: v += 0.5; used = list(c)
        return {t["id"]: {b: (round(v, 3), used) for b in bands if b in t["bands"]} for t in self.targets}

def search(groups, stack=False, bands=("40",)):
    proj = P.validate(P.default_project("T"))
    proj["targets"] = [{"id": "t1", "name": "T", "bands": list(bands), "heading": 0}]
    body = {"site": "s1", "max_height": 200, "top": 200, "groups": groups}
    old = (CM.Scorer, CM.aoa_status, FakeScorer.STACK)
    CM.Scorer, CM.aoa_status, FakeScorer.STACK = FakeScorer, (lambda *a: ({}, None)), stack
    try: return CM.search(proj, "x", body, None, {})
    finally: CM.Scorer, CM.aoa_status, FakeScorer.STACK = old

YAGI_40 = {"name": "40 m Yagi", "el": {"40": 3}, "lo": 5, "hi": 150, "step": 5, "min_spacing": 60}

@test
def a_layout_with_an_unused_antenna_is_dropped_when_the_smaller_one_exists():
    r = search([{**YAGI_40, "count": 1, "count_max": 2}])
    # Heights 5..150 by 5 = 30 heights. Pairs at least 60 ft (12 steps) apart: sum of 1..18 = 171. In every pair the
    # lower antenna is never used, and the single antenna at the same top height scores the same: all 171 go.
    assert r["stats"]["unused_dropped"] == 171, r["stats"]["unused_dropped"]
    assert all(len(row["layout"][0]) == 1 and row["unused"] == [[]] for row in r["rows"]), r["rows"][:3]
    assert r["rows"][0]["layout"] == [[145.0]], r["rows"][0]

@test
def with_a_fixed_count_one_row_is_kept_and_names_the_unused_antenna():
    r = search([{**YAGI_40, "count": 2}], stack=True)
    idle = [row for row in r["rows"] if row["unused"] != [[]]]
    tops = [max(row["layout"][0]) for row in idle]
    assert len(tops) == len(set(tops)), tops                     # one row per top height, not one per spare height
    best_idle = next(row for row in idle if max(row["layout"][0]) == 145)
    # The kept layout has the highest spare antenna that is still unused: below 60 ft, so 55 ft (gap 90 ft).
    assert best_idle["layout"] == [[55.0, 145.0]] and best_idle["unused"] == [[55.0]], best_idle
    # Real stacks (both antennas used, both at 60 ft or more) are all kept, with no note, and rank first.
    assert r["rows"][0]["unused"] == [[]] and min(r["rows"][0]["layout"][0]) >= 60, r["rows"][0]
    assert sum(1 for row in r["rows"] if row["unused"] == [[]] and max(row["layout"][0]) == 145) == 6   # 60, 65 .. 85 under 145

@test
def an_empty_lowest_height_is_a_quarter_wave_on_the_lowest_band():
    groups = [{"name": "Tribander", "el": {"20": 4, "15": 4, "10": 4}, "count": 1, "lo": "", "hi": "", "step": 5, "min_spacing": 30},
              {"name": "40 m Yagi", "el": {"40": 3}, "count": 1, "lo": "", "hi": "", "step": 5, "min_spacing": 60}]
    r = search(groups, bands=("40", "20", "15", "10"))
    # 245.9 / 14.2 MHz = 17.3 ft, rounded up to the 5 ft step: 20 ft. 245.9 / 7.1 MHz = 34.6 ft: 35 ft.
    assert [g["lo"] for g in r["groups"]] == [20.0, 35.0], r["groups"]
    curves = {c["name"]: c["heights"] for c in r["curves"]}
    assert min(curves["Tribander"]) == 20 and min(curves["40 m Yagi"]) == 35, curves
    r = search([{**YAGI_40, "count": 1, "lo": 5}])                # a typed height is used as it is
    assert r["groups"][0]["lo"] == 5.0 and min(r["curves"][0]["heights"]) == 5, r["groups"]

if __name__ == "__main__":
    print(f"\nPASS: {len(PASSED)} tests")
