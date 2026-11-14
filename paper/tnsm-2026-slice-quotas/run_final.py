#!/usr/bin/env python3
"""Definitive campaign of the slicing study, all from one build. Seeds 101 to 112 were never used in development (the
development campaigns, seeds 1 to 12 on one fixed UE drop, are in out_dev/); a seed now also draws the UE drop and classes.
Calibration uses seed 99 only. Stages: calib (calibration passes and the fixed-quota sweep), then all (resumable).

  python3 run_final.py calib N      calibration, writes out/calib*.json through make_calib.py and make_calib_t.py
  python3 run_final.py all N        the campaign, primary studies first

Output files: out/pass.jsonl, out/sens.jsonl (delay-critical slice), out/tenants.jsonl, out/tsens.jsonl (tenants).
"""
import hashlib, json, os, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__)); OUTD = os.path.join(HERE, "out")
NS3 = os.path.expanduser("~/6g_ntn_ns3/ns-3-dev")
EX = os.path.join(NS3, "build/contrib/ntn-slice/examples/ns3.43-ntn-slice-{}-leo-optimized")
BP, BT = EX.format("pass"), EX.format("tenants")
HASH = {b: hashlib.sha256(open(b, "rb").read()).hexdigest()[:12] for b in (BP, BT)}
PB = dict(duration=120, ueBehindS=40, numUes=12, embbMbps=30, critBytes=500, satEirpDbm=55, deadlineMs=50, warmupS=3, windowS=5)
TB = dict(duration=120, ueBehindS=40, numUes=12, offeredMbps=30, contractMbps=12, satEirpDbm=55, warmupS=3, windowS=5,
          bIdleStart=50, bIdleStop=70)
SEEDS = list(range(101, 113)); SIX = SEEDS[:6]; FOUR = SEEDS[:4]
QSWEEP = [0.36, 0.38, 0.40, 0.42, 0.44, 0.46, 0.48]


def execute(binary, a):
    d = tempfile.mkdtemp(prefix="p10f_")
    cmd = ["nice", "-n", "5", binary] + [f"--{k}={v}" for k, v in dict(a, outputDir=d).items()]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=43200, cwd=NS3)
        res = json.loads([l for l in r.stdout.strip().splitlines() if l.startswith("{")][-1])
    except Exception as e:
        res = dict(error=f"{type(e).__name__}: {str(e)[:200]}")
    subprocess.run(["rm", "-rf", d])
    res["bin"] = HASH[binary]
    return res


def calib(par):
    jobs = [("calib.json", BP, dict(PB, critPeriodMs=1, RngRun=99, policy="static", quotas="0.10,0.85,0.05")),
            ("calib_t.json", BT, dict(TB, RngRun=99, policy="static", quotas="0.45,0.50,0.05"))]
    jobs += [(f"sweep_{q}.json", BT, dict(TB, RngRun=99, policy="static", quotas=f"{q},{0.95 - q:.2f},0.05")) for q in QSWEEP]

    def work(j):
        n, b, a = j
        p = os.path.join(OUTD, n)
        if not os.path.exists(p):
            r = execute(b, a); open(p, "w").write(json.dumps(r) + "\n")
    with ThreadPoolExecutor(par) as ex:
        list(ex.map(work, jobs))
    subprocess.run([sys.executable, "make_calib.py"], cwd=HERE, check=True)
    subprocess.run([sys.executable, "make_calib_t.py"], cwd=HERE, check=True)
    # smallest fixed share of A whose every busy window meets the contract on the calibration seed
    busy = lambda w: w["t"] + 5 <= 50 or w["t"] >= 70
    cfg = json.load(open(os.path.join(OUTD, "calib_t_cfg.json")))
    tab = {}
    for q in QSWEEP:
        r = json.loads(open(os.path.join(OUTD, f"sweep_{q}.json")).read())
        tab[q] = min(w["a_mbps"] for w in r["windows"] if busy(w))
    feas = [q for q in QSWEEP if tab[q] >= 12.0]
    cfg["sweep_min"] = tab; best = min(feas) if feas else max(QSWEEP)
    cfg["best"] = f"{best},{0.95 - best:.2f},0.05"
    json.dump(cfg, open(os.path.join(OUTD, "calib_t_cfg.json"), "w"), indent=1)
    print("sweep", tab, "best", best)


def pass_pol(name, per):
    C = json.load(open(os.path.join(OUTD, "calib_cfg.json")))
    q = C[f"q_{'full' if per == 1 else 'half'}"]
    return {"pf": dict(policy="pf"), "qos": dict(policy="qos"), "bwp": dict(policy="bwp"),
            "reactive": dict(policy="reactive", initQuotas=q["init"]),
            "static_hi": dict(policy="static", quotas=q["hi"]), "static_lo": dict(policy="static", quotas=q["lo"]),
            "predict": dict(policy="predict", bprTable=C["bprTable"], initQuotas=q["hi"], headroom=round(1.25 * C["h"], 4)),
            "ctrl50": dict(policy="reactive", initQuotas=q["init"], ctrlMs=50),
            "ctrl500": dict(policy="reactive", initQuotas=q["init"], ctrlMs=500),
            "kappa110": dict(policy="reactive", initQuotas=q["init"], headroom=1.10),
            "kappa150": dict(policy="reactive", initQuotas=q["init"], headroom=1.50)}[name]


def ten_pol(name):
    C = json.load(open(os.path.join(OUTD, "calib_t_cfg.json")))
    L = dict(overhead=round(C["h"], 4), headroom=C["kappa"], initQuotas=C["hi"])
    return {"pf": dict(policy="pf"), "qos": dict(policy="qos"), "policed": dict(policy="policed"),
            "limiter": dict(policy="limiter"),
            "static_hi": dict(policy="static", quotas=C["hi"]), "static_lo": dict(policy="static", quotas=C["lo"]),
            "static_best": dict(policy="static", quotas=C["best"]),
            "contract_eph": dict(policy="contract_eph", bprTable=C["bprTable"], **L),
            "contract": dict(policy="contract", **L), "contract_trim": dict(policy="contract_trim", **L),
            "window": dict(policy="contract", ctrlMs=5000, **L)}[name]


def jobs():
    J = []
    # primary: tenants, then the delay-critical slice
    for s in SEEDS:
        for p in ("contract_trim", "policed", "limiter", "static_best", "static_lo", "static_hi", "contract", "qos", "pf",
                  "contract_eph", "window"):
            J.append(("tenants", BT, dict(pol=p, seed=s), dict(TB, RngRun=s, **ten_pol(p))))
    for s in SEEDS:
        for p in ("reactive", "qos", "static_lo", "static_hi", "predict", "pf", "bwp"):
            J.append(("pass", BP, dict(pol=p, period=1, seed=s), dict(PB, critPeriodMs=1, RngRun=s, **pass_pol(p, 1))))
        for p in ("reactive", "qos", "static_hi", "pf"):
            J.append(("pass", BP, dict(pol=p, period=2, seed=s), dict(PB, critPeriodMs=2, RngRun=s, **pass_pol(p, 2))))
    # sensitivity without decoding errors, hence without retransmissions; a pass that peaks near 58 degrees
    for s in SIX:
        for p in ("contract_trim", "limiter", "qos", "pf", "contract"):
            J.append(("tsens", BT, dict(pol="noerr_" + p, seed=s), dict(TB, RngRun=s, blockErrors=0, **ten_pol(p))))
        for p in ("contract_trim", "limiter", "static_best"):
            J.append(("tsens", BT, dict(pol="off_" + p, seed=s), dict(TB, RngRun=s, clusterOffsetDeg=3, **ten_pol(p))))
        for p in ("reactive", "qos", "static_lo"):
            J.append(("sens", BP, dict(pol="noerr_" + p, period=1, seed=s), dict(PB, critPeriodMs=1, RngRun=s, blockErrors=0, **pass_pol(p, 1))))
        for p in ("reactive", "qos"):
            J.append(("sens", BP, dict(pol="off_" + p, period=1, seed=s), dict(PB, critPeriodMs=1, RngRun=s, clusterOffsetDeg=3, **pass_pol(p, 1))))
    # parameters of the two loops
    for s in FOUR:
        for nm, x in (("gain25", dict(trimGain=0.25)), ("gain100", dict(trimGain=1.0)), ("kappa102", dict(headroom=1.02)),
                      ("kappa110", dict(headroom=1.10)), ("rate8", dict(contractMbps=8)), ("rate16", dict(contractMbps=16))):
            J.append(("tsens", BT, dict(pol=nm, seed=s), dict(dict(TB, RngRun=s, **ten_pol("contract_trim")), **x)))
        for p in ("ctrl50", "ctrl500", "kappa110", "kappa150"):
            J.append(("sens", BP, dict(pol=p, period=1, seed=s), dict(PB, critPeriodMs=1, RngRun=s, **pass_pol(p, 1))))
    # a priority class that itself holds many UEs
    for s in SEEDS:
        for p in ("reactive", "qos", "static_lo"):
            J.append(("sens", BP, dict(pol="ue24_" + p, period=1, seed=s), dict(PB, critPeriodMs=2, numUes=24, RngRun=s, **pass_pol(p, 1))))
    return J


def run_all(par):
    done = set()
    for st in ("tenants", "pass", "sens", "tsens"):
        p = os.path.join(OUTD, st + ".jsonl")
        if os.path.exists(p):
            for l in open(p):
                r = json.loads(l)
                if "error" not in r:
                    done.add((st, r["pol"], r.get("period", 0), r["seed"]))
    todo = [j for j in jobs() if (j[0], j[2]["pol"], j[2].get("period", 0), j[2]["seed"]) not in done]
    print(len(todo), "runs to do", flush=True)
    lock = threading.Lock()

    def work(j):
        st, b, tag, a = j
        r = execute(b, a); r.update(tag)
        with lock:
            open(os.path.join(OUTD, st + ".jsonl"), "a").write(json.dumps(r) + "\n")
        print(st, tag, "ERR" if "error" in r else "ok", flush=True)
    with ThreadPoolExecutor(par) as ex:
        list(ex.map(work, todo))


if __name__ == "__main__":
    {"calib": calib, "all": run_all}[sys.argv[1]](int(sys.argv[2]))
