#!/usr/bin/env python3
"""Write ../macros_p10.tex from the ns-3 slicing campaigns (out/ns3_slice1.jsonl: pf, bwp, static 0.40, reactive,
seeds 1-5; out/ns3_slice2.jsonl: static tuned overhead, oracle per elevation, reactive with bytes per RBG, seeds 1-5;
out/ns3_slice3.jsonl: all of them, seeds 6-10). Statistics: medians over the seeds with min and max, paired Wilcoxon
signed-rank tests on log p99 delay (paired by seed, which fixes the UE drop), Holm over every paired test."""
import json, math, os
import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
R_E, H = 6371.0, 550.0
OFFS = {0: "Zen", 4: "Mid", 8: "Low"}
POL = {"pf": "Pf", "bwp": "Bwp", "static": "Static", "statictuned": "Tuned", "oracle": "Oracle", "reactive": "React"}
LAM = 4 * 1000 * 8 / 0.002 / 8          # URLLC bytes/s: four UEs, 1000 B every 2 ms
TRAFFIC_S = 19.0                        # slots are counted from 1 s to the end of the 20 s run


def load(name):
    p = os.path.join(OUT, name)
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


rows = []
for r in load("ns3_slice1.jsonl"):
    if r.get("pol") == "reactive":      # the reactive runs of v2 also record bytes per RBG; keep those
        continue
    rows.append(r)
rows += load("ns3_slice2.jsonl") + load("ns3_slice3.jsonl")
rows = [r for r in rows if not r.get("error")]
M = {}


def f(x, d=1):
    return f"{x:.{d}f}"


def fd(x):
    """A delay in ms: whole ms up to 10 s, then seconds."""
    return f"{x:.0f}~ms" if x < 1000 else f"{x / 1000:.1f}~s"


def sel(p, o):
    return {r["seed"]: r for r in rows if r["pol"] == p and r["offset"] == o}


def elev(g):
    if g == 0:
        return 90.0
    gr = math.radians(g)
    return math.degrees(math.atan2(math.cos(gr) - R_E / (R_E + H), math.sin(gr)))


for o, to in OFFS.items():
    M[f"Elev{to}"] = f(elev(o), 0)
    th = math.radians(elev(o)); d = math.sqrt((R_E + H) ** 2 - R_E ** 2 * math.cos(th) ** 2) - R_E * math.sin(th)
    M[f"Range{to}"] = f(d, 0); M[f"Loss{to}"] = f(20 * math.log10(d / H), 1)
    for p, tp in POL.items():
        R = sel(p, o)
        if not R:
            continue
        g = lambda s, k: np.array([r["slices"][s][k] for r in R.values()], float)
        up = g(1, "owd_p99")
        M[f"Up{tp}{to}"] = fd(np.median(up)); M[f"UpLo{tp}{to}"] = fd(up.min()); M[f"UpHi{tp}{to}"] = fd(up.max())
        M[f"Ut{tp}{to}"] = f(np.median(g(1, "thr_mbps")), 1)
        M[f"Et{tp}{to}"] = f(np.median(g(0, "thr_mbps")), 1)
        M[f"Mp{tp}{to}"] = fd(np.median(g(2, "owd_p99")))
        M[f"N{tp}{to}"] = str(len(R))
        if p == "reactive":
            M[f"Q{tp}{to}"] = f(np.median(g(1, "mean_quota")), 2)
        if "bytes_per_rbg" in next(iter(R.values()))["slices"][1]:
            b = g(1, "bytes_per_rbg"); S = np.array([r["slots"] / TRAFFIC_S for r in R.values()])
            N = np.array([r["rbg_per_slot"] for r in R.values()])
            qs = LAM / (S * N * b)
            M[f"Bpr{tp}{to}"] = f(np.median(b), 0); M[f"Qstar{tp}{to}"] = f(np.median(qs), 2)
            M[f"Share{tp}{to}"] = f(np.median(g(1, "rbg_share")), 2)
            M[f"SlotRate{tp}{to}"] = f(np.median(S), 0); M[f"Nrbg"] = f(np.median(N), 0)
# capacity: total delivered rate of the cell under PF, and the fall of bytes per RBG with elevation (reactive runs)
for o, to in OFFS.items():
    R = sel("pf", o)
    M[f"Cap{to}"] = f(np.median([sum(s["thr_mbps"] for s in r["slices"]) for r in R.values()]), 1)
# PF without slices: rate per busy UE (four eMBB and four URLLC UEs are busy; mMTC is nearly idle) against the
# URLLC UE's own load of 4 Mb/s, Section (analysis)
for o, to in OFFS.items():
    M[f"PfShare{to}"] = f(float(M[f"Cap{to}"]) / 8, 1)
bz = float(M["BprReactZen"]); M["BprDropMid"] = f(100 * (1 - float(M["BprReactMid"]) / bz), 0)
M["BprDropLow"] = f(100 * (1 - float(M["BprReactLow"]) / bz), 0)
# model check: predicted minimum share q* against the measured URLLC share of RBGs, every run that records them
err = []
for r in rows:
    s = r["slices"][1]
    if "bytes_per_rbg" in s and s["bytes_per_rbg"] > 0 and r["pol"] in ("statictuned", "oracle", "reactive"):
        q = LAM / ((r["slots"] / TRAFFIC_S) * r["rbg_per_slot"] * s["bytes_per_rbg"])
        if s["thr_mbps"] > 0.98 * LAM * 8 / 1e6:      # the slice was fully served, so its share is its need
            err.append(abs(s["rbg_share"] - q))
M["QstarErrMed"] = f(100 * np.median(err), 1); M["QstarErrMax"] = f(100 * np.max(err), 1); M["QstarErrN"] = str(len(err))
# Lemma (operating point): the loop's quota against min(kappa q*, 1 - floors)
for to in OFFS.values():
    M[f"LoopPred{to}"] = f(min(1.25 * float(M[f"QstarReact{to}"]), 0.85), 2)
# tuned static quota: headroom at the zenith and the bytes per RBG at which Corollary (failure) says it fails
k0 = 0.58 / float(M["QstarTunedZen"]); M["KappaTuned"] = f(k0, 2)
M["BprFailTuned"] = f(float(M["BprTunedZen"]) / k0, 0)
M["UtilTunedMid"] = f(float(M["QstarTunedMid"]) / 0.58, 2); M["UtilTunedLow"] = f(float(M["QstarTunedLow"]) / 0.58, 2)
# paired tests: reactive against each other policy, log URLLC p99, per elevation
PRAW = {}


def fp(p):
    if not np.isfinite(p):
        return "--"
    if p >= 0.001:
        return f"{p:.3f}"
    m, e = f"{p:.1e}".split("e")
    return f"\\ensuremath{{{m}\\times10^{{{int(e)}}}}}"


for o, to in OFFS.items():
    A = sel("reactive", o)
    for p, tp in POL.items():
        if p == "reactive":
            continue
        B = sel(p, o); ks = sorted(set(A) & set(B))
        if len(ks) < 5:
            continue
        x = np.log([A[k]["slices"][1]["owd_p99"] for k in ks]); y = np.log([B[k]["slices"][1]["owd_p99"] for k in ks])
        p_ = stats.wilcoxon(x, y).pvalue if np.any(x != y) else float("nan")
        M[f"Ratio{tp}{to}"] = f(float(np.exp(np.median(y - x))), 1)
        M[f"InvRatio{tp}{to}"] = f(float(np.exp(np.median(x - y))), 1)   # the loop's delay over the other policy's
        M[f"P{tp}{to}"] = fp(p_); PRAW[f"{tp}{to}"] = p_
        M[f"Wins{tp}{to}"] = str(int(np.sum(x < y))); M[f"Pairs{tp}{to}"] = str(len(ks))
        rng = np.random.default_rng(7); dl = y - x
        bs = [np.exp(np.median(rng.choice(dl, len(dl)))) for _ in range(4000)]
        lo_, hi_ = np.percentile(bs, [2.5, 97.5])
        M[f"RatioCi{tp}{to}"] = f"{lo_:.1f}--{hi_:.1f}" if lo_ >= 1 else f"{lo_:.2f}--{hi_:.2f}"
pv = sorted(v for v in PRAW.values() if np.isfinite(v))
M["HolmTests"] = str(len(pv))
M["HolmPass"] = str(sum(1 for i, p_ in enumerate(pv) if all(q <= 0.05 / (len(pv) - k) for k, q in enumerate(pv[:i + 1]))))
# sensitivity of the loop (v4): headroom and control period, at the two lower elevations; measured elevation drift
SENS = [r for r in load("ns3_slice4.jsonl") if not r.get("error")]
for p, tp in (("kappa110", "KapLo"), ("kappa150", "KapHi"), ("ctrl50", "CtlFast"), ("ctrl500", "CtlSlow")):
    for o, to in ((4, "Mid"), (8, "Low")):
        R = [r for r in SENS if r["pol"] == p and r["offset"] == o]
        if R:
            up = np.array([r["slices"][1]["owd_p99"] for r in R])
            M[f"Up{tp}{to}"] = fd(np.median(up)); M[f"UpHi{tp}{to}"] = fd(up.max())
            M[f"Et{tp}{to}"] = f(np.median([r["slices"][0]["thr_mbps"] for r in R]), 1)
            M[f"Q{tp}{to}"] = f(np.median([r["slices"][1]["mean_quota"] for r in R]), 2)
dr = [(r["offset"], r["elev_start"], r["elev_end"]) for r in SENS if "elev_start" in r]
if dr:
    M["ElevDriftMax"] = f(max(abs(e - s) for _, s, e in dr), 0)
    for o, to in ((4, "Mid"), (8, "Low")):
        s_ = [s for oo, s, e in dr if oo == o]; e_ = [e for oo, s, e in dr if oo == o]
        M[f"ElevStart{to}"] = f(np.median(s_), 0); M[f"ElevEnd{to}"] = f(np.median(e_), 0)
M.setdefault("ElevDriftMax", "--")
M["NSeeds"] = str(max(len(sel("reactive", o)) for o in OFFS))
# eMBB cost of the loop against the oracle quota, low elevation
M["EmbbReactVsOracleLow"] = f(float(M["EtReactLow"]) - float(M["EtOracleLow"]), 1)
with open(os.path.join(HERE, "..", "macros_p10.tex"), "w") as fh:
    fh.write("% generated by sim/make_macros.py; do not edit\n")
    for k, v in sorted(M.items()):
        fh.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print(len(M), "macros")
