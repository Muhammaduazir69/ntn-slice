"""Rerun one pass policy and seed on the current libraries and compare with the stored campaign output."""
import json, os, sys, runpy
sys.argv = ["x"]
m = runpy.run_path("run_ns3_pass8.py", run_name="lib")
r = m["run"](("reactive", 1, 1))
open("out/regress_pass.jsonl", "w").write(json.dumps(r) + "\n")
o = [x for f in ("out/ns3_pass5.jsonl", "out/ns3_pass8.jsonl") for x in map(json.loads, open(f)) if x.get("pol") == "reactive" and x.get("seed") == 1 and x.get("period") == 1][0]
print("identical", o["windows"] == r["windows"] and o["slices"] == r["slices"])
print(o["slices"][1]); print(r["slices"][1])
