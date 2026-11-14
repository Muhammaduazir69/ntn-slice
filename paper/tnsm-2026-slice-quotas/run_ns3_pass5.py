"""ns-3 campaign v5 of the slicing study (after the first review): falling passes. Resumable, one jsonl line per run.

Every run is 120 s of one NR cell while the satellite recedes from the UE cluster (cluster at the sub-satellite
point 40 s before the start), from about 75 deg to the mid twenties of elevation. Twelve UEs: four eMBB (30 Mb/s
each, 5QI 9), four delay-critical (500 B every 1 ms each, 5QI 79, D = 50 ms), four mMTC (5QI 9). Policies:
  pf, qos, bwp                     schedulers without quotas
  static_hi                        quota sized from the calibration pass for the start of the pass, headroom 1.25
  static_lo                        quota sized for the end of the pass, headroom 1.25
  predict                          ephemeris: bytes per RBG from the calibration table, every 100 ms
  reactive                         measured loop, every 100 ms
Load sweep: critical load halved (500 B every 2 ms) for pf, qos, static_hi, predict, reactive.
Calibration (seed 99, out/calib.json) is never used as a test seed. All runs come from one build, whose binary hash
is recorded in every line.
"""
import hashlib, json, os, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
NS3 = os.path.expanduser("~/6g_ntn_ns3/ns-3-dev")
BIN = os.path.join(NS3, "build/contrib/ntn-slice/examples/ns3.43-ntn-slice-pass-leo-optimized")
OUT = os.path.join(HERE, "out", "ns3_pass5.jsonl")
CFG = json.load(open(os.path.join(HERE, "out", "calib_cfg.json")))
BASE = dict(duration=120, ueBehindS=40, numUes=12, embbMbps=30, critBytes=500, satEirpDbm=55, deadlineMs=50,
            warmupS=3, windowS=5)
SEEDS = range(1, 9)


def pol(name, period):
    q = CFG[f"q_{'full' if period == 1 else 'half'}"]
    return {"pf": dict(policy="pf"), "qos": dict(policy="qos"), "bwp": dict(policy="bwp"),
            "static_hi": dict(policy="static", quotas=q["hi"]), "static_lo": dict(policy="static", quotas=q["lo"]),
            "predict": dict(policy="predict", bprTable=CFG["bprTable"], initQuotas=q["hi"]),
            "reactive": dict(policy="reactive", initQuotas=q["hi"])}[name]


def jobs():
    J = [(p, 1, s) for s in SEEDS for p in ("pf", "qos", "bwp", "static_hi", "static_lo", "predict", "reactive")]
    J += [(p, 2, s) for s in SEEDS for p in ("pf", "qos", "static_hi", "predict", "reactive")]
    return J


BINHASH = hashlib.sha256(open(BIN, "rb").read()).hexdigest()[:12]


def run(job):
    p, period, s = job
    a = dict(BASE, critPeriodMs=period, RngRun=s, **pol(p, period))
    d = tempfile.mkdtemp(prefix="p10p_")
    a["outputDir"] = d
    cmd = ["nice", "-n", "5", BIN] + [f"--{k}={v}" for k, v in a.items()]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=21600, cwd=NS3)
        res = json.loads([l for l in r.stdout.strip().splitlines() if l.startswith("{")][-1])
    except Exception as e:
        res = dict(error=f"{type(e).__name__}: {str(e)[:200]}")
    subprocess.run(["rm", "-rf", d])
    res.update(pol=p, period=period, seed=s, bin=BINHASH)
    return res


def main(par):
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            r = json.loads(l)
            if "error" not in r:
                done.add((r["pol"], r["period"], r["seed"]))
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
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
