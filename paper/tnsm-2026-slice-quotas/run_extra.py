#!/usr/bin/env python3
"""Fixed share without decoding errors, sized the same way as static_best: sweep on calibration seed 99, smallest share
whose every busy window meets the contract, then the six test seeds of the other no-error runs. Same binary as run_final.
Writes out/tsens_extra.jsonl and out/noerr_sweep.json; resumable."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
from run_final import BT, HASH, OUTD, SIX, TB, execute

SW = [0.24, 0.26, 0.28, 0.30, 0.32, 0.34, 0.36]
busy = lambda w: w["t"] + 5 <= 50 or w["t"] >= 70
quota = lambda q: f"{q},{0.95 - q:.2f},0.05"
par = int(sys.argv[1])


def sweep(q):
    p = os.path.join(OUTD, f"sweep_noerr_{q}.json")
    if not os.path.exists(p):
        r = execute(BT, dict(TB, RngRun=99, policy="static", blockErrors=0, quotas=quota(q)))
        open(p, "w").write(json.dumps(r) + "\n")
    return q, min(w["a_mbps"] for w in json.load(open(p))["windows"] if busy(w))


with ThreadPoolExecutor(par) as ex:
    tab = dict(ex.map(sweep, SW))
feas = [q for q in SW if tab[q] >= 12.0]
best = min(feas) if feas else None
json.dump(dict(sweep_min=tab, best=best), open(os.path.join(OUTD, "noerr_sweep.json"), "w"), indent=1)
print("sweep", tab, "best", best, flush=True)
if best is None:
    sys.exit("no feasible share in the sweep")
out = os.path.join(OUTD, "tsens_extra.jsonl")
done = {json.loads(l)["seed"] for l in open(out)} if os.path.exists(out) else set()


def run(s):
    r = execute(BT, dict(TB, RngRun=s, policy="static", blockErrors=0, quotas=quota(best)))
    r.update(pol="noerr_static_best", seed=s)
    open(out, "a").write(json.dumps(r) + "\n")
    print(s, "ERR" if "error" in r else "ok", HASH[BT], flush=True)


with ThreadPoolExecutor(par) as ex:
    list(ex.map(run, [s for s in SIX if s not in done]))
print("EXTRA_DONE", flush=True)
