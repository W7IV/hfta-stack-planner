"""
Best compromise for ONE tower over several targets (regions). Every candidate is scored only with HFTA runs:
for each target and band, the best stack-switch setting of the weighted mean over the target's headings
(the same arithmetic as the Compare step). A candidate layout is then scored as:
    per target  = mean over all bands of the switched FOM
    overall     = weighted mean over targets (weights chosen by the user; equal by default)
Antennas are given as groups with separate bands (e.g. 3 tribanders and 2 x 40 m). Rules: spacing inside a group,
optional equal spacing, minimum gap between groups, maximum height, and optionally the guy and ice clearance of a
tower's guy plan.
"""
from __future__ import annotations
import itertools, math
import numpy as np
import engine
from . import antennas as A, terrain as TR, project as P, guys as G, spacing as SP
from .evaluate import switch_options, target_azimuths, band_freq, run_one

RUN_BUDGET = 25000   # unique HFTA runs per search stage before the height grid is coarsened

def _axis(lo, hi, step): return [round(lo + i * step, 2) for i in range(int(math.floor((hi - lo) / step + 1e-9)) + 1)]

def _rules(g, rules):
    r = dict(rules)
    for k in ("min_spacing", "max_spacing", "equal_tol"):
        if g.get(k) not in (None, ""): r[k] = float(g[k])
    return r

def group_candidates(g, step, rules, allowed):
    """Height layouts for one group: every combination of count antennas (count .. count_max when a range is
    given) on the height grid that keeps the group's spacing rules."""
    rules = _rules(g, rules)
    hs = [h for h in _axis(g["lo"], g["hi"], step) if h <= rules["max_height"] and allowed(g, h)]
    out = []
    counts = range(g["count"], (g.get("count_max") or g["count"]) + 1)
    for c in (c for n in counts for c in itertools.combinations(hs, n)):
        gaps = [b - a for a, b in zip(c, c[1:])]
        if gaps and min(gaps) < rules["min_spacing"] - 1e-9: continue
        if gaps and rules.get("max_spacing") and max(gaps) > rules["max_spacing"] + 1e-9: continue
        if gaps and rules.get("equal_tol") is not None and max(gaps) - min(gaps) > rules["equal_tol"] + 1e-9: continue
        out.append(c)
    return out

def refine(cands_top, g, step, coarse, rules, allowed):
    rules = _rules(g, rules); out = set()
    for c in cands_top:
        axes = [[h + d for d in _axis(-coarse / 2, coarse / 2, step)] for h in c]
        for combo in itertools.product(*axes):
            if any(h < g["lo"] or h > g["hi"] or h > rules["max_height"] or not allowed(g, h) for h in combo): continue
            if any(b <= a for a, b in zip(combo, combo[1:])): continue
            gaps = [b - a for a, b in zip(combo, combo[1:])]
            if gaps and min(gaps) < rules["min_spacing"] - 1e-9: continue
            if gaps and rules.get("max_spacing") and max(gaps) > rules["max_spacing"] + 1e-9: continue
            if gaps and rules.get("equal_tol") is not None and max(gaps) - min(gaps) > rules["equal_tol"] + 1e-9: continue
            out.add(tuple(round(h, 2) for h in combo))
    return sorted(out)

class Scorer:
    """Caches patterns by HFTA run and FOMs by run and elevation file."""
    def __init__(self, proj, slug, site, targets, pool, job):
        self.proj, self.slug, self.site, self.targets, self.pool, self.job = proj, slug, site, targets, pool, job
        self.sdir = P.site_dir(slug, site); self.idx = TR.profile_index(self.sdir)
        s = proj["settings"]; self.ground = (s["epsr"], s["sigma"], s["diffraction"])
        self.pat, self.aoa = {}, {}
    def spec(self, file, freq, t, hs):
        e, sg, d = self.ground
        return {"site": self.site, "file": file, "freq": freq, "hfta_type": t, "heights_ft": list(hs), "phases": [1] * len(hs), "epsr": e, "sigma": sg, "diffraction": d}
    def needed(self, model, bands, cands, mode):
        need = {}
        for c in cands:
            for opt in switch_options(len(c), mode):
                hs = tuple(c[i] for i in opt)
                for b in bands:
                    f, t = band_freq(self.proj, b), A.hfta_type(model, b)
                    for tg in self.targets:
                        if b not in tg["bands"]: continue
                        for az, w in target_azimuths(tg):
                            k, file = TR.nearest(self.idx, az)
                            key = (file, f, t, hs)
                            if key not in self.pat: need[key] = 1
        return list(need)
    def compute(self, keys, label):
        self.job.update(phase=label, done=0, total=len(keys))
        jobs = [(i, self.spec(*k), str(self.sdir)) for i, k in enumerate(keys)]
        for i, pat in self.pool.map(run_one, jobs, chunksize=8):
            self.pat[keys[i]] = np.array(pat, dtype=np.float32); self.job["done"] += 1
            if self.job.get("cancel"): raise RuntimeError("Cancelled")
    def aoa_for(self, prn, freq):
        k = (prn, freq)
        if k not in self.aoa: self.aoa[k] = engine.parse_aoa((P.prn_dir(self.slug) / prn).read_text(errors="ignore"), freq)
        return self.aoa[k]
    def score(self, model, bands, c, mode):
        """{target_id: {band: (switched FOM, heights used)}}"""
        out = {}
        for tg in self.targets:
            out[tg["id"]] = {}
            for b in bands:
                if b not in tg["bands"]: continue
                f, t = band_freq(self.proj, b), A.hfta_type(model, b); aoa = self.aoa_for(tg["prn"], f); best = None
                for opt in switch_options(len(c), mode):
                    hs = tuple(c[i] for i in opt); num = den = 0.0
                    for az, w in target_azimuths(tg):
                        k, file = TR.nearest(self.idx, az); v = engine.fom(self.pat[(file, f, t, hs)], aoa)
                        if v is not None: num += w * v; den += w
                    if den and (best is None or num / den > best[0]): best = (num / den, list(hs))
                if best: out[tg["id"]][b] = (round(best[0], 3), best[1])
        return out

def search(proj, slug, body, pool, job):
    targets = [t for t in proj["targets"] if t["id"] in (body.get("targets") or [t["id"] for t in proj["targets"]])]
    weights = {t["id"]: float((body.get("weights") or {}).get(t["id"], 1.0)) for t in targets}
    rules = {"min_spacing": float(body.get("min_spacing", 30)), "max_spacing": body.get("max_spacing"), "equal_tol": body.get("equal_tol"),
             "max_height": float(body.get("max_height", 200)), "min_gap": float(body.get("min_gap", 15))}
    mode = body.get("switching", "stackmatch")
    all_bands = {b for t in targets for b in t["bands"]}
    groups = []
    for j, g in enumerate(body["groups"]):
        el = {b: int(n) for b, n in (g.get("el") or {}).items() if n}
        hi = g.get("hi"); hi = rules["max_height"] if hi in (None, "") else min(float(hi), rules["max_height"])
        step = float(g.get("step") or 5); lo = g.get("lo"); lo = step if lo in (None, "") else float(lo)
        cm = g.get("count_max"); cm = int(cm) if cm not in (None, "") else None
        g = {**g, "count": int(g["count"]), "count_max": cm, "lo": lo, "hi": hi, "step": step, "el": el}
        g["ant"] = {"el": el}
        g["name"] = (g.get("name") or "").strip() or A.describe(g["ant"])
        for b in el: A.hfta_type(el[b])          # raises for an element count HFTA does not have
        g["bands"] = [b for b in A.bands_of(g["ant"]) if b in all_bands]
        if not g["bands"]: raise ValueError(f"{g['name']}: none of its bands is used by the chosen targets")
        if not 1 <= g["count"] <= 4: raise ValueError("A group can have 1 to 4 antennas (HFTA limit per band)")
        if g["count_max"] is not None and not g["count"] <= g["count_max"] <= 4: raise ValueError(f"{g['name']}: 'up to' must be between Count and 4")
        groups.append(g)
    for a, b in itertools.combinations(groups, 2):
        if set(a["bands"]) & set(b["bands"]): raise ValueError(f"{a['name']} and {b['name']} share a band; HFTA needs one antenna type per band")
    # guy limits (optional)
    allowed = lambda g, h: True
    tw = next((t for t in proj["towers"] if t["id"] == body.get("guys_from_tower")), None)
    if tw and (tw.get("guys") or {}).get("levels"):
        gp = tw["guys"]
        for g in groups:
            if g.get("turning_radius") in (None, ""):
                raise ValueError(f"{g['name']}: enter the turning radius (and element droop) to use the guy check")
        def allowed(g, h, _c={}):
            k = (g["name"], h)
            if k not in _c:
                r = G.check([{"name": g["name"], "h": h, "turning_radius": float(g["turning_radius"]), "droop": float(g.get("droop") or 0)}],
                            gp["levels"], float(gp.get("ice_in", 1.0)), float(gp.get("margin_ft", 2.0)))[0]
                _c[k] = r["clearance"] is None or r["clearance"] >= 0
            return _c[k]
    sc = Scorer(proj, slug, body["site"], targets, pool, job)
    if not sc.idx: raise ValueError("The chosen site has no terrain profiles")
    per_group = []
    for gi, g in enumerate(groups):
        step = g["step"]; cands = group_candidates(g, step, rules, allowed); coarse = None
        while cands and len(sc.needed(g["ant"], g["bands"], cands, mode)) > RUN_BUDGET:
            coarse = (coarse or step) * 2; cands = group_candidates(g, coarse, rules, allowed)
        if not cands: raise ValueError(f"No heights fit the rules for {g['name']} (spacing, height limits or guys)")
        sc.compute(sc.needed(g["ant"], g["bands"], cands, mode), f"{g['name']}: {'coarse ' if coarse else ''}search, {len(cands)} layouts")
        scored = {c: sc.score(g["ant"], g["bands"], c, mode) for c in cands}
        if coarse:
            def gscore(s): return sum(weights[t] * np.mean([v[0] for v in s[t].values()]) for t in s if s[t]) / sum(weights[t] for t in s if s[t])
            top = sorted(scored, key=lambda c: -gscore(scored[c]))[:6]
            fine = [c for c in refine(top, g, step, coarse, rules, allowed) if c not in scored]
            if fine:
                sc.compute(sc.needed(g["ant"], g["bands"], fine, mode), f"{g['name']}: fine search, {len(fine)} layouts")
                for c in fine: scored[c] = sc.score(g["ant"], g["bands"], c, mode)
        per_group.append(scored)
    # combine groups
    def tscore(parts):
        """parts: list of group score dicts -> {target: mean over all bands}"""
        out = {}
        for t in targets:
            vals = [v[0] for s in parts for v in s[t["id"]].values()]
            out[t["id"]] = round(float(np.mean(vals)), 3) if vals else None
        return out
    def overall(ts):
        ok = [(weights[t], v) for t, v in ts.items() if v is not None]
        return sum(w * v for w, v in ok) / sum(w for w, _ in ok)
    tops = []
    for scored in per_group:
        ranked = sorted(scored, key=lambda c: -overall(tscore([scored[c]])))
        tops.append(ranked[:60])
    # Score of each group against height, for the chart: for one antenna, score at each height; for a stack,
    # the best layout whose top antenna is at that height. Per target too, so the user can see why a height won.
    curves = []
    for g, scored in zip(groups, per_group):
        by_top = {}
        for c, sc_ in scored.items():
            ts = tscore([sc_]); o = overall(ts)
            if o == o and (max(c) not in by_top or o > by_top[max(c)][0]): by_top[max(c)] = (o, ts, list(c))
        hs = sorted(by_top)
        curves.append({"name": g["name"], "heights": hs, "overall": [round(by_top[h][0], 3) for h in hs],
                       "targets": {t["id"]: [by_top[h][1][t["id"]] for h in hs] for t in targets}, "layouts": [by_top[h][2] for h in hs]})
    order = body.get("order") or "any"
    def combo_ok(combo):
        """Minimum gap between groups, and the chosen group order (every antenna of an upper group above every
        antenna of a lower group)."""
        hs_all = [(h, gi) for gi, c in enumerate(combo) for h in c]
        if any(abs(a - b) < rules["min_gap"] - 1e-9 for (a, ga), (b, gb) in itertools.combinations(hs_all, 2) if ga != gb): return False
        if order in ("first_top", "first_bottom"):
            for (c1, c2) in zip(combo, combo[1:]):
                if order == "first_top" and min(c1) <= max(c2): return False
                if order == "first_bottom" and max(c1) >= min(c2): return False
        return True
    rows = []
    for combo in itertools.product(*tops):
        if not combo_ok(combo): continue
        parts = [per_group[gi][c] for gi, c in enumerate(combo)]; ts = tscore(parts)
        rows.append({"layout": [list(c) for c in combo], "overall": round(overall(ts), 3), "targets": ts,
                     "detail": {t["id"]: {b: v for p in parts for b, v in p[t["id"]].items()} for t in targets}})
    if not rows: raise ValueError("No combination keeps the minimum gap and the group order. Lower the gap, widen the height ranges, or change the order.")
    rows.sort(key=lambda r: -r["overall"])
    # best for each target alone, with the same rules (spacing, guys, gap between groups)
    keep = 60 if len(per_group) <= 2 else 20
    own_best, own_layout = {}, {}
    for t in targets:
        tid = t["id"]
        def gsum(scored, c): return sum(v[0] for v in scored[c][tid].values())
        ranked = [sorted(scored, key=lambda c, s=scored: -gsum(s, c))[:keep] for scored in per_group]
        best = None
        for combo in itertools.product(*ranked):
            if not combo_ok(combo): continue
            tot = sum(gsum(per_group[gi], c) for gi, c in enumerate(combo)); n = sum(len(per_group[gi][c][tid]) for gi, c in enumerate(combo))
            if n and (best is None or tot / n > best[0]): best = (tot / n, [list(c) for c in combo])
        own_best[tid] = round(best[0], 3) if best else None; own_layout[tid] = best[1] if best else []
    for r in rows:
        r["loss"] = {t: (None if v is None or own_best[t] is None else round(v - own_best[t], 2)) for t, v in r["targets"].items()}
    spr = proj["settings"]["spacing"]
    for r in rows[: int(body.get("top", 25))]:
        ants = [{"h": h, "el": groups[gi]["el"]} for gi, c in enumerate(r["layout"]) for h in c]
        r["spacing"] = SP.check(ants, lambda b: band_freq(proj, b), spr)
    return {"groups": [{"name": g["name"], "el": g["el"], "count": g["count"], "bands": g["bands"], "turning_radius": g.get("turning_radius"),
                        "droop": g.get("droop")} for g in groups], "weights": weights, "spacing_rules": spr,
            "own_best": own_best, "own_layout": own_layout, "curves": curves, "rows": rows[: int(body.get("top", 25))], "evaluated": len(rows), "runs": len(sc.pat),
            "targets": [{"id": t["id"], "name": t["name"]} for t in targets]}
