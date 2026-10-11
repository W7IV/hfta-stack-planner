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
import heapq, itertools, math, time
import numpy as np
import engine
from . import antennas as A, terrain as TR, project as P, guys as G, spacing as SP
from .evaluate import switch_options, target_azimuths, band_freq, run_one, aoa_status

RUN_BUDGET = 25000   # unique HFTA runs per search stage before the height grid is coarsened
NODE_BUDGET = 3_000_000   # combinations examined by the branch-and-bound search before it stops and says so
MAX_GROUP_LAYOUTS = 200_000   # layouts of one group; above this the request is refused before any work

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
        self.n_fom = 0; self.stages = []          # counters for the search summary
        self.n_failed = 0; self.n_filled = 0
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
        self.job.update(phase=label, done=0, total=len(keys)); self.stages.append({"stage": label, "runs": len(keys)})
        jobs = [(i, self.spec(*k), str(self.sdir)) for i, k in enumerate(keys)]
        for i, pat, note in self.pool.map(run_one, jobs, chunksize=8):
            self.pat[keys[i]] = None if pat is None else np.array(pat, dtype=np.float32); self.job["done"] += 1
            if pat is None: self.n_failed += 1
            elif note and note.get("filled_deg"): self.n_filled += 1
            if self.job.get("cancel"): raise RuntimeError("Cancelled")
    def aoa_for(self, tg, freq):
        aoa, why = aoa_status(self.proj, self.slug, tg, freq, self.aoa)
        if why: raise ValueError(f"{tg['name']}: {why}")
        return aoa
    def score(self, model, bands, c, mode):
        """{target_id: {band: (switched FOM, heights used)}}"""
        out = {}
        for tg in self.targets:
            out[tg["id"]] = {}
            for b in bands:
                if b not in tg["bands"]: continue
                f, t = band_freq(self.proj, b), A.hfta_type(model, b); aoa = self.aoa_for(tg, f); best = None
                for opt in switch_options(len(c), mode):
                    hs = tuple(c[i] for i in opt); num = den = 0.0; ok = True
                    for az, w in target_azimuths(tg):
                        k, file = TR.nearest(self.idx, az); pat = self.pat[(file, f, t, hs)]
                        if pat is None: ok = False; break       # failed run: this switch setting has no value
                        v = engine.fom(pat, aoa); self.n_fom += 1
                        if v is None: ok = False; break
                        num += w * v; den += w
                    if ok and den and (best is None or num / den > best[0]): best = (num / den, list(hs))
                if best: out[tg["id"]][b] = (round(best[0], 3), best[1])
        return out

def search(proj, slug, body, pool, job):
    t0 = time.time()
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
    if not targets: raise ValueError("Choose at least one target")
    if sum(weights.values()) <= 0: raise ValueError("The target weights add up to zero")
    # Every target must have usable arrival-angle data on every band it is scored on, before any run is started.
    missing, cache = [], {}
    for t in targets:
        for b in sorted({b for g in groups for b in g["bands"] if b in t["bands"]}, key=A.BANDS.index):
            _, why = aoa_status(proj, slug, t, band_freq(proj, b), cache)
            if why: missing.append(f"{t['name']} {b} m: {why}")
    if missing: raise ValueError("Missing elevation-angle data. " + " ".join(missing))
    # guy limits (optional)
    allowed = lambda g, h: True
    tw = next((t for t in proj["towers"] if t["id"] == body.get("guys_from_tower")), None)
    if tw and (tw.get("guys") or {}).get("levels"):
        gp = tw["guys"]
        for g in groups:
            if g.get("turning_radius") in (None, ""):
                raise ValueError(f"{g['name']}: enter the turning radius (and element droop) to use the guy check")
        def allowed(g, h, _c={}):
            # Keyed by the geometry that decides the clearance, never by the group name.
            k = (float(g["turning_radius"]), float(g.get("droop") or 0), float(h))
            if k not in _c:
                r = G.check([{"name": g["name"], "h": h, "turning_radius": float(g["turning_radius"]), "droop": float(g.get("droop") or 0)}],
                            gp["levels"], float(gp.get("ice_in", 1.0)), float(gp.get("margin_ft", 2.0)), float(gp.get("density", 56)))[0]
                _c[k] = r["clearance"] is None or r["clearance"] >= 0
            return _c[k]
    sc = Scorer(proj, slug, body["site"], targets, pool, job)
    if not sc.idx: raise ValueError("The chosen site has no terrain profiles")
    per_group = []
    for gi, g in enumerate(groups):
        step = g["step"]
        if step <= 0 or g["hi"] < g["lo"]: raise ValueError(f"{g['name']}: check the height range and step")
        # Size check BEFORE listing layouts: if the height grid gives too many layouts, start on a coarser grid
        # (then refine around the best), instead of building a list that does not fit in memory.
        coarse = None
        def n_layouts(st_):
            n_h = int((g["hi"] - g["lo"]) / st_) + 1
            return sum(math.comb(n_h, k) for k in range(g["count"], (g.get("count_max") or g["count"]) + 1))
        while n_layouts(coarse or step) > MAX_GROUP_LAYOUTS:
            coarse = (coarse or step) * 2
        cands = group_candidates(g, coarse or step, rules, allowed)
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
    # Layouts whose score is incomplete (a failed run left a band without a value) cannot be compared: drop them.
    tids = [t["id"] for t in targets]
    expect = {(gi, t["id"]): len([b for b in g["bands"] if b in t["bands"]]) for gi, g in enumerate(groups) for t in targets}
    dropped = 0
    for gi, scored in enumerate(per_group):
        bad = [c for c in scored if any(len(scored[c][t]) != expect[(gi, t)] for t in tids)]
        for c in bad: del scored[c]
        dropped += len(bad)
        if not scored: raise ValueError(f"{groups[gi]['name']}: no layout could be scored (the calculation core failed)")
    # The score. Per target: mean over all its bands (all groups together). Overall: weighted mean over targets.
    # Because each target's band count is fixed, the overall score is a SUM of one term per group, which makes an
    # exact branch-and-bound search possible (below).
    N = {t: sum(expect[(gi, t)] for gi in range(len(groups))) for t in tids}
    W = sum(weights[t] for t in tids if N[t] > 0)
    def tscore(parts):
        """parts: list of group score dicts -> {target: mean over all bands}"""
        out = {}
        for t in targets:
            vals = [v[0] for s in parts for v in s[t["id"]].values()]
            out[t["id"]] = round(float(np.mean(vals)), 3) if vals else None
        return out
    def overall(ts):
        ok = [(weights[t], v) for t, v in ts.items() if v is not None]
        den = sum(w for w, _ in ok)
        return sum(w * v for w, v in ok) / den if den else float("nan")
    def term_all(gi, c):
        sc_ = per_group[gi][c]
        return sum(weights[t] / (N[t] * W) * sum(v[0] for v in sc_[t].values()) for t in tids if N[t] > 0)
    def term_one(tid):
        return lambda gi, c: sum(v[0] for v in per_group[gi][c][tid].values()) / N[tid]
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
    def fits(chosen, gi, c):
        """Can layout c of group gi join the layouts chosen for groups 0..gi-1? Minimum gap between antennas of
        different groups, and the group order (every antenna of an upper group above every antenna of a lower one)."""
        for gj, cj in enumerate(chosen):
            if any(abs(a - b) < rules["min_gap"] - 1e-9 for a in c for b in cj): return False
        if chosen and order in ("first_top", "first_bottom"):
            prev = chosen[-1]
            if order == "first_top" and min(prev) <= max(c): return False
            if order == "first_bottom" and max(prev) >= min(c): return False
        return True
    def best_combos(term, K):
        """Exact top-K combinations by branch and bound. Each group's layouts are sorted by their term; a branch is
        abandoned only when even the best remaining terms cannot beat the K-th best found, so no better feasible
        combination is skipped. Stops after NODE_BUDGET steps and then reports complete=False."""
        G_ = len(per_group)
        lists = [sorted(((term(gi, c), c) for c in per_group[gi]), key=lambda x: -x[0]) for gi in range(G_)]
        rest = [0.0] * (G_ + 1)
        for gi in range(G_ - 1, -1, -1): rest[gi] = rest[gi + 1] + lists[gi][0][0]
        heap, cnt = [], itertools.count(); st = {"nodes": 0, "complete": True}
        def dfs(gi, chosen, partial):
            for val, c in lists[gi]:
                st["nodes"] += 1
                if st["nodes"] > NODE_BUDGET: st["complete"] = False; return True
                if len(heap) == K and partial + val + rest[gi + 1] <= heap[0][0] + 1e-12: break
                if not fits(chosen, gi, c): continue
                if gi == G_ - 1:
                    item = (partial + val, next(cnt), chosen + [c])
                    if len(heap) < K: heapq.heappush(heap, item)
                    else: heapq.heapreplace(heap, item)
                elif dfs(gi + 1, chosen + [c], partial + val): return True
            return False
        dfs(0, [], 0.0)
        return [x[2] for x in sorted(heap, key=lambda x: -x[0])], st
    top_n = max(1, min(int(body.get("top", 25)), 200))
    combos, st_all = best_combos(term_all, top_n)
    if not combos:
        if not st_all["complete"]: raise ValueError("The search limit was reached before any combination met the gap and order rules. Narrow the height ranges.")
        raise ValueError("No combination keeps the minimum gap and the group order. Lower the gap, widen the height ranges, or change the order.")
    rows = []
    for combo in combos:
        parts = [per_group[gi][c] for gi, c in enumerate(combo)]; ts = tscore(parts)
        rows.append({"layout": [list(c) for c in combo], "overall": round(overall(ts), 3), "targets": ts,
                     "detail": {t["id"]: {b: v for p in parts for b, v in p[t["id"]].items()} for t in targets}})
    rows.sort(key=lambda r: -r["overall"])
    # Best for each target alone, with the same rules (spacing, guys, gap between groups) and the same exact search.
    own_best, own_layout, nodes_own, complete_own = {}, {}, 0, True
    for t in targets:
        tid = t["id"]
        if N[tid] == 0: own_best[tid] = None; own_layout[tid] = []; continue
        cb, st1 = best_combos(term_one(tid), 1); nodes_own += st1["nodes"]; complete_own &= st1["complete"]
        if cb:
            own_best[tid] = round(sum(v[0] for gi, c in enumerate(cb[0]) for v in per_group[gi][c][tid].values()) / N[tid], 3)
            own_layout[tid] = [list(c) for c in cb[0]]
        else: own_best[tid] = None; own_layout[tid] = []
    for r in rows:
        r["loss"] = {t: (None if v is None or own_best[t] is None else round(v - own_best[t], 2)) for t, v in r["targets"].items()}
    n_combos = st_all["nodes"]; exhaustive = st_all["complete"] and complete_own
    spr = proj["settings"]["spacing"]
    for r in rows:
        ants = [{"h": h, "el": groups[gi]["el"]} for gi, c in enumerate(r["layout"]) for h in c]
        r["spacing"] = SP.check(ants, lambda b: band_freq(proj, b), spr)
    return {"groups": [{"name": g["name"], "el": g["el"], "count": g["count"], "bands": g["bands"], "turning_radius": g.get("turning_radius"),
                        "droop": g.get("droop")} for g in groups], "weights": weights, "spacing_rules": spr,
            "own_best": own_best, "own_layout": own_layout, "curves": curves,
            "stats": {"hfta_runs": len(sc.pat), "stages": sc.stages, "fom_evaluations": sc.n_fom,
                      "group_layouts": [{"name": g["name"], "layouts": len(sc_)} for g, sc_ in zip(groups, per_group)],
                      "combinations_checked": n_combos, "combinations_kept": len(rows), "own_best_steps": nodes_own,
                      "complete": exhaustive, "coarse_grid": any(st_["stage"].find("coarse") >= 0 for st_ in sc.stages),
                      "failed_runs": sc.n_failed, "filled_runs": sc.n_filled, "layouts_dropped": dropped,
                      "seconds": round(time.time() - t0, 1)}, "rows": rows, "evaluated": len(rows), "runs": len(sc.pat),
            "targets": [{"id": t["id"], "name": t["name"]} for t in targets]}
