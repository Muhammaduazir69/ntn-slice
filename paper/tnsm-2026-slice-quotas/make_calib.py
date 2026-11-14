#!/usr/bin/env python3
"""Turn the calibration pass (out/calib.json, seed 99, delay-critical quota 0.85 so the slice is never starved) into
out/calib_cfg.json: the table elevation -> bytes per RBG of the delay-critical slice used by the ephemeris policy,
and the static quotas sized with headroom 1.25 for the start and for the end of the pass, at both loads."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
d = json.loads(open(os.path.join(OUT, "calib.json")).read().strip().splitlines()[-1])
W = [w for w in d["windows"] if w["bpr_crit"] > 0 and w["elev"] > 0]
S = d["slots"] / (d["duration"] - 0.5 - 3.0)          # DL slots per second over the measured span
N = d["rbg_per_slot"]
KAPPA, MMTC = 1.25, 0.05
# transport-block bytes per application byte of the slice on the calibration seed (headers, padding): the bytes per
# RBG are in transport-block bytes, the offered load in application bytes
_s = d["slices"][1]
H = _s["rbg"] * _s["bytes_per_rbg"] / (_s["thr_mbps"] * 1e6 / 8 * (d["duration"] - 0.5 - 3.0))
tab = sorted((round(w["elev"], 1), round(w["bpr_crit"], 1)) for w in W)
cfg = {"S": S, "N": N, "h": H, "bprTable": ",".join(f"{e}:{b}" for e, b in tab)}
for tag, period in (("full", 1.0), ("half", 2.0)):
    lam = 4 * 500 / (period / 1000)                    # four UEs, 500 B every period, bytes/s
    qs = [H * lam / (S * N * b) for _, b in tab]
    hi = min(KAPPA * qs[-1], 0.85)                     # start of the pass: highest elevation, last in the table
    lo = min(KAPPA * max(qs), 0.85)                    # the most demanding point of the pass
    init = min(KAPPA * qs[-1] / H, 0.85)               # warm start of the loop, as in the first campaign
    cfg[f"q_{tag}"] = {"hi": f"{1 - hi - MMTC:.3f},{hi:.3f},{MMTC}", "lo": f"{1 - lo - MMTC:.3f},{lo:.3f},{MMTC}",
                       "init": f"{1 - init - MMTC:.3f},{init:.3f},{MMTC}",
                       "qstar": [[e, round(q, 3)] for (e, _), q in zip(tab, qs)]}
json.dump(cfg, open(os.path.join(OUT, "calib_cfg.json"), "w"), indent=1)
print("S", round(S), "N", N, "elev", tab[0][0], "to", tab[-1][0])
for tag in ("full", "half"):
    print(tag, cfg[f"q_{tag}"]["hi"], cfg[f"q_{tag}"]["lo"])
