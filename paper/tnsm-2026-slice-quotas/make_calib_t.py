#!/usr/bin/env python3
"""Turn the tenant calibration pass (out/calib_t.json, seed 99, tenant A quota 0.45) into out/calib_t_cfg.json: the
table elevation -> bytes per RBG of tenant A, A's transport-block overhead, and the static quotas that give A its
contract at the start and at the end of the pass, with the same headroom as the contract policies."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
d = json.loads(open(os.path.join(OUT, "calib_t.json")).read().strip().splitlines()[-1])
W = [w for w in d["windows"] if w["bpr_a"] > 0 and w["elev"] > 0]
span = d["duration"] - 0.5 - 3.0
S, N = d["slots"] / span, d["rbg_per_slot"]
s = d["slices"][0]
H = s["rbg"] * s["bytes_per_rbg"] / (s["thr_mbps"] * 1e6 / 8 * span)
KAPPA, MMTC, R = 1.05, 0.05, 12e6 / 8
tab = sorted((round(w["elev"], 1), round(w["bpr_a"], 1)) for w in W)
qs = [H * R / (S * N * b) for _, b in tab]
hi, lo = KAPPA * qs[-1], min(KAPPA * max(qs), 0.85)
cfg = {"S": S, "N": N, "h": H, "kappa": KAPPA, "bprTable": ",".join(f"{e}:{b}" for e, b in tab),
       "hi": f"{hi:.3f},{1 - hi - MMTC:.3f},{MMTC}", "lo": f"{lo:.3f},{1 - lo - MMTC:.3f},{MMTC}",
       "qstar": [[e, round(q, 3)] for (e, _), q in zip(tab, qs)]}
json.dump(cfg, open(os.path.join(OUT, "calib_t_cfg.json"), "w"), indent=1)
print("S", round(S), "N", N, "h", round(H, 3), "elev", tab[0][0], "to", tab[-1][0], "b", tab[-1][1], "to", tab[0][1])
print("hi", cfg["hi"], "lo", cfg["lo"])
