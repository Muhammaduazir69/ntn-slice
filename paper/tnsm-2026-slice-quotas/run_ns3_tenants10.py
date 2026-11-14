"""Campaign v10: the contract loop with the delivered-rate trim, on the v9 scenario, plus a regression of the open-loop
policy (seed 1) that shows the rebuilt binary reproduces v9."""
import hashlib, json, os, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
NS3 = os.path.expanduser("~/6g_ntn_ns3/ns-3-dev")
BIN = os.path.join(NS3, "build/contrib/ntn-slice/examples/ns3.43-ntn-slice-tenants-leo-optimized")
OUT = os.path.join(HERE, "out", "ns3_tenants10.jsonl")
CFG = json.load(open(os.path.join(HERE, "out", "calib_t_cfg.json")))
BASE = dict(duration=120, ueBehindS=40, numUes=12, offeredMbps=30, contractMbps=12, satEirpDbm=55, warmupS=3,
            windowS=5, bIdleStart=50, bIdleStop=70)
LOOP = dict(overhead=round(CFG["h"], 4), headroom=CFG["kappa"], initQuotas=CFG["hi"])
POL = {"contract_trim": dict(policy="contract_trim", **LOOP)}
SEEDS = range(1, 13)
BINHASH = hashlib.sha256(open(BIN, "rb").read()).hexdigest()[:12]


def run(job):
    p, s = job
    a = dict(BASE, RngRun=s, **POL[p])
    d = tempfile.mkdtemp(prefix="p10t_")
    a["outputDir"] = d
    cmd = ["nice", "-n", "5", BIN] + [f"--{k}={v}" for k, v in a.items()]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=21600, cwd=NS3)
        res = json.loads([l for l in r.stdout.strip().splitlines() if l.startswith("{")][-1])
    except Exception as e:
        res = dict(error=f"{type(e).__name__}: {str(e)[:200]}")
    subprocess.run(["rm", "-rf", d])
    res.update(pol=p, seed=s, bin=BINHASH)
    return res


def main(par):
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT):
            r = json.loads(l)
            if "error" not in r:
                done.add((r["pol"], r["seed"]))
    todo = [("contract_trim", s) for s in SEEDS if ("contract_trim", s) not in done]
    print(len(todo), "runs to do", flush=True)
    lock = threading.Lock()

    def work(j):
        r = run(j)
        with lock:
            open(OUT, "a").write(json.dumps(r) + "\n")
        print(*j, "ERR" if "error" in r else "ok", flush=True)

    with ThreadPoolExecutor(par) as ex:
        list(ex.map(work, todo))


def regress():
    r = run(("contract", 1))
    open(os.path.join(HERE, "out", "ns3_tenants10_regress.jsonl"), "w").write(json.dumps(r) + "\n")


if __name__ == "__main__":
    POL["contract"] = dict(policy="contract", **LOOP)   # regression only
    th = threading.Thread(target=regress)
    th.start()
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
    th.join()
