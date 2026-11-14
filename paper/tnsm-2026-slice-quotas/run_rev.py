#!/usr/bin/env python3
"""Revision campaign, from the standalone binaries in bin/ (ns3_patch/build.sh). Resumable: every row is fsynced to
out/rev.jsonl (or out/rev_check.jsonl), keyed by study, pol, period, seed. At most 3 jobs at nice 19. Each row stores a hash of the
binary and a hash of the shared libraries it links against (m10). The driver stops launching if free disk falls under 2 GB or
if a library changes under it. Its pid is in out/rev.pid; SIGTERM ends it and its children by pid.

  python3 run_rev.py check N    rerun of existing seeds, compared with the old rows by compare_rev.py
  python3 run_rev.py all N      the new runs
"""
import hashlib, json, os, shutil, signal, subprocess, sys, tempfile, threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__)); OUTD = os.path.join(HERE, "out")
BP, BT = os.path.join(HERE, "bin/p10-pass"), os.path.join(HERE, "bin/p10-tenants")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]
HASH = {b: sha(b) for b in (BP, BT)}
NS3 = os.path.expanduser("~/6g_ntn_ns3/ns-3-dev"); NS3B = os.path.join(NS3, "build/lib")


def libs_of(b):
    o = subprocess.run(["ldd", b], capture_output=True, text=True).stdout
    return sorted({l.split("=>")[1].split()[0] for l in o.splitlines() if NS3B in l})


LIBS = sorted(set(libs_of(BP)) | set(libs_of(BT)))
LIBHASH = hashlib.sha256("".join(sha(p) for p in LIBS).encode()).hexdigest()[:12]
LIBSTAT = [(p, os.stat(p).st_size, os.stat(p).st_mtime) for p in LIBS]
PB = dict(duration=120, ueBehindS=40, numUes=12, embbMbps=30, critBytes=500, satEirpDbm=55, deadlineMs=50, warmupS=3, windowS=5)
TB = dict(duration=120, ueBehindS=40, numUes=12, offeredMbps=30, contractMbps=12, satEirpDbm=55, warmupS=3, windowS=5,
          bIdleStart=50, bIdleStop=70)
SEEDS = list(range(101, 113)); LATE = SEEDS[6:]
CP = json.load(open(os.path.join(OUTD, "calib_cfg.json"))); CT = json.load(open(os.path.join(OUTD, "calib_t_cfg.json")))
LT = dict(overhead=round(CT["h"], 4), headroom=CT["kappa"], initQuotas=CT["hi"])
quota = lambda q: f"{q},{0.95 - q:.2f},0.05"
busy = lambda w: w["t"] + 5 <= 50 or w["t"] >= 70
QP = CP["q_full"]
children, stop = set(), threading.Event()


def ten(name):
    return {"pf": dict(policy="pf"), "qos": dict(policy="qos"), "limiter": dict(policy="limiter"), "queueprop": dict(policy="queueprop", initQuotas=CT["hi"]),
            "contract": dict(policy="contract", **LT), "contract_trim": dict(policy="contract_trim", **LT),
            "static_best": dict(policy="static", quotas=CT["best"])}[name]


def execute(binary, a):
    d = tempfile.mkdtemp(prefix="p10r_")
    cmd = ["nice", "-n", "19", binary] + [f"--{k}={v}" for k, v in dict(a, outputDir=d).items()]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=NS3)
        children.add(p)
        o, _ = p.communicate(timeout=86400)
        children.discard(p)
        res = json.loads([l for l in o.strip().splitlines() if l.startswith("{")][-1])
    except Exception as e:
        res = dict(error=f"{type(e).__name__}: {str(e)[:200]}")
    shutil.rmtree(d, ignore_errors=True)
    res["bin"], res["libs"] = HASH[binary], LIBHASH
    return res


def guard():
    if shutil.disk_usage(HERE).free < 2e9:
        print("STOP free disk under 2 GB", flush=True); stop.set()
    if [(p, os.stat(p).st_size, os.stat(p).st_mtime) for p in LIBS] != LIBSTAT:
        print("STOP a shared library changed", flush=True); stop.set()
    return not stop.is_set()


def load(fn):
    p = os.path.join(OUTD, fn)
    return [r for r in map(json.loads, open(p)) if "error" not in r] if os.path.exists(p) else []


def run(jobs_, fn, par):
    key = lambda r: (r["study"], r["pol"], r.get("period", 0), r["seed"])
    done = {key(r) for r in load(fn)}
    todo = [j for j in jobs_ if key(j[2]) not in done]
    print(len(todo), "runs to do of", len(jobs_), flush=True)
    lock = threading.Lock(); out = os.path.join(OUTD, fn)

    def work(j):
        b, a, tag = j
        if not guard():
            return
        r = execute(b, a); r.update(tag)
        if stop.is_set() and "error" in r:
            return
        with lock, open(out, "a") as fh:
            fh.write(json.dumps(r) + "\n"); fh.flush(); os.fsync(fh.fileno())
        print(tag, "ERR " + r["error"] if "error" in r else "ok", flush=True)
    with ThreadPoolExecutor(par) as ex:
        list(ex.map(work, todo))


def J_ten(pol, seed, a):
    return (BT, a, dict(study="tenants", pol=pol, seed=seed))


def J_pass(pol, seed, a):
    return (BP, a, dict(study="pass", pol=pol, period=1, seed=seed))


def check_jobs():
    J = []
    for s in SEEDS[:3]:
        for p in ("limiter", "qos", "contract_trim"):
            J.append(J_ten(p, s, dict(TB, RngRun=s, **ten(p))))
        Qr = dict(reactive=dict(policy="reactive", initQuotas=QP["init"]), qos=dict(policy="qos"), pf=dict(policy="pf"))
        for p, x in Qr.items():
            J.append(J_pass(p, s, dict(PB, critPeriodMs=1, RngRun=s, **x)))
    J.append(J_ten("noerr_limiter", 101, dict(TB, RngRun=101, blockErrors=0, **ten("limiter"))))
    return J


R20 = [0.66, 0.68, 0.70, 0.72, 0.74, 0.78, 0.81, 0.83, 0.85]   # 0.85 leaves B its floor and mMTC its share
NESW = [0.16, 0.18, 0.20, 0.22]


def first_jobs():
    J = []
    for q in R20:
        J.append(J_ten(f"r20sweep_{q}", 99, dict(TB, RngRun=99, contractMbps=20, policy="static", quotas=quota(q))))
    for q in NESW:
        J.append(J_ten(f"nesweep_{q}", 99, dict(TB, RngRun=99, blockErrors=0, policy="static", quotas=quota(q))))
    J.append(J_ten("r20_pf", 101, dict(TB, RngRun=101, contractMbps=20, policy="pf")))  # PF must not depend on R
    # M1: the quota scheduler with A limited at the source
    for s in SEEDS:
        J.append(J_ten("lim_static_best", s, dict(TB, RngRun=s, aLimited=1, policy="static", quotas=CT["best"])))
        J.append(J_ten("lim_contract_trim", s, dict(TB, RngRun=s, aLimited=1, **ten("contract_trim"))))
    return J


def second_jobs():
    rows = load("rev.jsonl")
    busy_min = lambda r: min(w["a_mbps"] for w in r["windows"] if busy(w))
    swr = {float(r["pol"].split("_")[1]): busy_min(r) for r in rows if r["pol"].startswith("r20sweep_")}
    r20f = [q for q in sorted(swr) if swr[q] >= 20.0]
    r20best = min(r20f) if r20f else max(swr)
    old = json.load(open(os.path.join(OUTD, "noerr_sweep.json")))
    swn = {float(k): v for k, v in old["sweep_min"].items()}
    swn.update({float(r["pol"].split("_")[1]): busy_min(r) for r in rows if r["pol"].startswith("nesweep_")})
    nef = [q for q in sorted(swn) if swn[q] >= 12.0]
    nebest = min(nef)
    json.dump(dict(r20=swr, r20best=r20best, noerr=swn, noerrbest=nebest), open(os.path.join(OUTD, "rev_sweeps.json"), "w"), indent=1)
    print("sweeps", swr, r20best, swn, nebest, flush=True)
    J = []
    i20 = round(float(CT["hi"].split(",")[0]) * 20 / 12, 3)
    L20 = dict(LT, initQuotas=f"{i20},{0.95 - i20:.3f},0.05")
    for s in SEEDS:   # M2
        a = dict(TB, RngRun=s, contractMbps=20)
        J.append(J_ten("r20_contract_trim", s, dict(a, policy="contract_trim", **L20)))
        J.append(J_ten("r20_limiter", s, dict(a, policy="limiter")))
        J.append(J_ten("r20_static_best", s, dict(a, policy="static", quotas=quota(r20best))))
    for s in LATE:    # M5: the no-error arm to 12 seeds
        for p in ("contract_trim", "limiter", "qos", "pf", "contract"):
            J.append(J_ten("noerr_" + p, s, dict(TB, RngRun=s, blockErrors=0, **ten(p))))
    sd = LATE if abs(nebest - float(old["best"])) < 1e-9 else SEEDS
    for s in sd:
        J.append(J_ten("noerr_static_best", s, dict(TB, RngRun=s, blockErrors=0, policy="static", quotas=quota(nebest))))
    for s in SEEDS:   # M9
        J.append(J_ten("queueprop", s, dict(TB, RngRun=s, **ten("queueprop"))))
        J.append(J_pass("queueprop", s, dict(PB, critPeriodMs=1, RngRun=s, policy="queueprop", initQuotas=QP["init"])))
    for s in SEEDS:   # the rival in the no-error arm, last
        J.append(J_ten("noerr_queueprop", s, dict(TB, RngRun=s, blockErrors=0, **ten("queueprop"))))
    for s in SEEDS[:4]:   # m1: cold start of the delay-critical loop from its floor
        J.append(J_pass("cold_reactive", s, dict(PB, critPeriodMs=1, RngRun=s, policy="reactive", initQuotas="0.85,0.10,0.05")))
    return J


def term(*_):
    stop.set()
    for p in list(children):
        p.terminate()
    os._exit(1)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, term)
    open(os.path.join(OUTD, "rev.pid"), "w").write(str(os.getpid()))
    par = min(int(sys.argv[2]), 3)
    print("bins", HASH, "libs", LIBHASH, len(LIBS), flush=True)
    if sys.argv[1] == "check":
        run(check_jobs(), "rev_check.jsonl", par)
        print("CHECK_DONE", flush=True)
    else:
        run(first_jobs(), "rev.jsonl", par)
        if not stop.is_set():
            run(second_jobs(), "rev.jsonl", par)
        print("STOPPED" if stop.is_set() else "REV_DONE", flush=True)
