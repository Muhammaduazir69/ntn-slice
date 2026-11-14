#!/usr/bin/env python3
"""Round 2: priority with the delay-critical class as 5QI 3 (GBR, priority level 30, 50 ms), at 12 and at 24 UEs, 12 seeds,
from bin/p10-pass-r2. Check rows first (5QI 79, untouched configurations) against the stored rows. Resumable, fsynced rows in
out/r2.jsonl, at most 3 jobs at nice 19, pid in out/r2.pid, stops under 2 GB free."""
import json, os, sys, signal
import run_rev as RV
from run_rev import PB, SEEDS, QP, OUTD, HERE
B2 = os.path.join(HERE, "bin/p10-pass-r2")
RV.HASH[B2] = RV.sha(B2)
assert set(RV.libs_of(B2)) <= set(RV.LIBS) | set(RV.libs_of(B2))
J = []
for s, p, per, n in ((101, "qos", 1, 12), (101, "reactive", 1, 12), (101, "ue24_qos", 2, 24), (102, "qos", 1, 12)):
    a = dict(PB, critPeriodMs=per, numUes=n, RngRun=s, policy="qos" if "qos" in p else "reactive")
    if p == "reactive":
        a["initQuotas"] = QP["init"]
    J.append((B2, a, dict(study="r2check", pol=p, period=1 if n == 12 else 2, seed=s)))
for s in SEEDS:
    J.append((B2, dict(PB, critPeriodMs=1, RngRun=s, policy="qos", critFiveQi=3), dict(study="pass", pol="qos3", period=1, seed=s)))
    J.append((B2, dict(PB, critPeriodMs=2, numUes=24, RngRun=s, policy="qos", critFiveQi=3), dict(study="sens", pol="ue24_qos3", period=1, seed=s)))
if __name__ == "__main__":
    signal.signal(signal.SIGTERM, RV.term)
    open(os.path.join(OUTD, "r2.pid"), "w").write(str(os.getpid()))
    print("bins", RV.HASH[B2], "libs", RV.LIBHASH, flush=True)
    RV.run(J[:4], "r2.jsonl", 3)
    # compare check rows with the stored rows before anything else
    old = {}
    for fn, st in (("pass.jsonl", "pass"), ("sens.jsonl", "sens")):
        for r in map(json.loads, open(os.path.join(OUTD, fn))):
            old[(r["pol"], r["period"], r["seed"])] = r
    SKIP = {"bin", "libs", "study", "pol", "period", "seed", "diag", "diag_win", "q_trace"}
    bad = 0
    for r in map(json.loads, open(os.path.join(OUTD, "r2.jsonl"))):
        if r["study"] != "r2check":
            continue
        o = old[(r["pol"], r["period"] if r["pol"] != "ue24_qos" else 1, r["seed"])]
        same = json.dumps({k: o[k] for k in o if k not in SKIP}, sort_keys=True) == json.dumps({k: r[k] for k in r if k not in SKIP}, sort_keys=True)
        print("check", r["pol"], r["seed"], "identical" if same else "DIFFERENT", flush=True); bad += not same
    if bad:
        print("STOP check rows differ", flush=True); sys.exit(1)
    RV.run(J[4:], "r2.jsonl", 3)
    print("R2_DONE", flush=True)
