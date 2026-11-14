#!/usr/bin/env python3
"""Priority with the delay-critical class as 5QI 3 with decoding errors off, on the six seeds of the errors-off delay arm,
from bin/p10-pass-r2. First one stored errors-off row (5QI 79, a configuration the program leaves untouched) is rerun and
compared with the stored row field by field. Resumable, fsynced rows in out/r4.jsonl, at most 3 jobs at nice 19, launched
from the ns-3 tree, pid in out/r4.pid."""
import json, os, sys, signal
import run_rev as RV
from run_rev import PB, OUTD, HERE
B2 = os.path.join(HERE, "bin/p10-pass-r2")
RV.HASH[B2] = RV.sha(B2)
SIX = list(range(101, 107))
CHECK = [(B2, dict(PB, critPeriodMs=1, RngRun=101, blockErrors=0, policy="qos"), dict(study="r4check", pol="noerr_qos", period=1, seed=101))]
J = [(B2, dict(PB, critPeriodMs=1, RngRun=s, blockErrors=0, policy="qos", critFiveQi=3), dict(study="sens", pol="noerr_qos3", period=1, seed=s))
     for s in SIX]
if __name__ == "__main__":
    signal.signal(signal.SIGTERM, RV.term)
    open(os.path.join(OUTD, "r4.pid"), "w").write(str(os.getpid()))
    print("bin", RV.HASH[B2], "libs", RV.LIBHASH, flush=True)
    RV.run(CHECK, "r4.jsonl", 1)
    old = {(r["pol"], r["period"], r["seed"]): r for r in map(json.loads, open(os.path.join(OUTD, "sens.jsonl")))}
    SKIP = {"bin", "libs", "study", "pol", "period", "seed", "diag", "diag_win", "q_trace"}
    bad = 0
    for r in map(json.loads, open(os.path.join(OUTD, "r4.jsonl"))):
        if r["study"] != "r4check":
            continue
        o = old[(r["pol"], r["period"], r["seed"])]
        same = json.dumps({k: o[k] for k in o if k not in SKIP}, sort_keys=True) == json.dumps({k: r[k] for k in r if k not in SKIP}, sort_keys=True)
        print("check", r["pol"], r["seed"], "identical" if same else "DIFFERENT", flush=True); bad += not same
    if bad:
        print("STOP check row differs", flush=True); sys.exit(1)
    RV.run(J, "r4.jsonl", 3)
    print("R4_DONE", flush=True)
