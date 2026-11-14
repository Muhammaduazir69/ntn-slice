"""ns-3 campaign v1 of the slicing study. Resumable, one jsonl line per run.

One NR NTN cell on a Starlink-like 550 km satellite, 12 UEs (4 eMBB saturating at 30 Mb/s each, 4 URLLC at
4 Mb/s each, 4 mMTC), satellite conducted power 55 dBm so that the cell is power-limited and its capacity falls
with elevation. The UE cluster sits 0, 4 or 8 deg north of the sub-satellite point (elevation about 90, 50 and
30 deg). Policies: proportional fair without slicing, static BWP slicing, static quotas tuned for the overhead
pass (URLLC 0.40), and the reactive quota loop. Five seeds per cell.
"""
import json, os, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
NS3 = os.path.expanduser("~/6g_ntn_ns3/ns-3-dev")
BIN = os.path.join(NS3, "build/contrib/ntn-slice/examples/ns3.43-ntn-slice-quota-leo-optimized")
OUT = os.path.join(HERE, "out", "ns3_slice2.jsonl")
BASE = dict(duration=20, numUes=12, embbMbps=30, urllcBytes=1000, urllcPeriodMs=2, satEirpDbm=55)
# v2: static tuned at the overhead need the reactive loop measured (0.58), an oracle static quota per elevation
# (the reactive loop's mean quota there), and the reactive loop again to record bytes per RBG
POL = {"statictuned": dict(policy="static", quotas="0.37,0.58,0.05"),
       "oracle": None, "reactive": dict(policy="reactive")}
ORACLE = {0: "0.37,0.58,0.05", 4: "0.27,0.68,0.05", 8: "0.13,0.82,0.05"}
OFFS = (0, 4, 8)
SEEDS = range(1, 6)


def jobs():
    return [(p, o, s) for s in SEEDS for o in OFFS for p in POL if not (p == "oracle" and o == 0)]


def run(job):
    p, o, s = job
    spec = dict(policy="static", quotas=ORACLE[o]) if p == "oracle" else POL[p]
    a = dict(BASE, ueOffsetDeg=o, RngRun=s, **spec)
    d = tempfile.mkdtemp(prefix="p10_")
    a["outputDir"] = d
    cmd = ["nice", "-n", "5", BIN] + [f"--{k}={v}" for k, v in a.items()]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=14400, cwd=NS3)
        res = json.loads([l for l in r.stdout.strip().splitlines() if l.startswith("{")][-1])
    except Exception as e:
        res = dict(error=f"{type(e).__name__}: {str(e)[:200]}")
    subprocess.run(["rm", "-rf", d])
    res.update(pol=p, offset=o, seed=s)
    return res


def main(par):
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            r = json.loads(l)
            if "error" not in r:
                done.add((r["pol"], r["offset"], r["seed"]))
    todo = [j for j in jobs() if j not in done]
    print(len(todo), "runs to do", flush=True)
    lock = threading.Lock()

    def work(j):
        r = run(j)
        with lock:
            open(OUT, "a").write(json.dumps(r) + "\n")
        print(*j, "ERR" if "error" in r else "ok", flush=True)

    with ThreadPoolExecutor(par) as ex:
        list(ex.map(work, todo))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
