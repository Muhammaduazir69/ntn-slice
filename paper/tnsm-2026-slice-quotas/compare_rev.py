#!/usr/bin/env python3
"""Compare every old output key of the check rows (standalone binaries) with the rows of the original campaign."""
import json, os, sys
O = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
L = lambda f: [json.loads(l) for l in open(os.path.join(O, f))]
old = {}
for f, st in (("tenants.jsonl", "tenants"), ("tsens.jsonl", "tenants"), ("pass.jsonl", "pass")):
    for r in L(f):
        old[(st, r["pol"], r.get("period", 0), r["seed"])] = r
SKIP = {"bin", "libs", "study", "pol", "period", "seed", "diag", "diag_win", "q_trace"}
same = bad = 0; out = []
for r in L("rev_check.jsonl"):
    k = (r["study"], r["pol"], r.get("period", 0), r["seed"])
    if "error" in r:
        print(k, r["error"]); bad += 1; continue
    o = old[k]
    a = json.dumps({x: o[x] for x in sorted(o) if x not in SKIP}, sort_keys=True)
    b = json.dumps({x: r[x] for x in sorted(r) if x not in SKIP}, sort_keys=True)
    eq = a == b; same += eq; bad += not eq
    out.append(dict(key=k, identical=eq, old_bin=o["bin"], new_bin=r["bin"], libs=r["libs"]))
    print(k, "identical" if eq else "DIFFERENT")
    if not eq:
        for x in sorted(o):
            if x not in SKIP and o[x] != r.get(x):
                print("   differs in", x, str(o[x])[:200], "||", str(r.get(x))[:200])
json.dump(dict(same=same, different=bad, rows=out), open(os.path.join(O, "rev_check.json"), "w"), indent=1)
print("identical", same, "different", bad)
