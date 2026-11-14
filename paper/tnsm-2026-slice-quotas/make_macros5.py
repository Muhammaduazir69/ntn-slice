#!/usr/bin/env python3
"""Write ../macros_p10.tex from the definitive campaign (run_final.py: out/pass.jsonl, sens.jsonl, tenants.jsonl, tsens.jsonl,
test seeds 101 to 112) and the calibration passes (out/calib*.json, seed 99). Statistics: medians over seeds with min and
max; paired Wilcoxon signed-rank tests by seed, Holm over every test; percentile bootstrap intervals of the median paired
ratio. A window violates the delay target when more than 1 % of its delay-critical packets exceed D = 50 ms (5QI 79
allows a packet error rate of 1e-2)."""
import json, math, os
import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
POL = {"pf": "Pf", "qos": "Qos", "bwp": "Bwp", "static_hi": "Hi", "static_lo": "Lo", "predict": "Pred",
       "reactive": "React", "queueprop": "Qp", "qos3": "QosG"}
LOAD = {1: "", 2: "Half"}
M = {}
CFG = json.load(open(os.path.join(OUT, "calib_cfg.json")))
CAL = json.loads(open(os.path.join(OUT, "calib.json")).read().strip().splitlines()[-1])


def load(name):
    p = os.path.join(OUT, name)
    return [r for r in map(json.loads, open(p)) if not r.get("error")] if os.path.exists(p) else []


REV = load("rev.jsonl")          # new rows, from the standalone binaries (run_rev.py)
CHK = load("rev_check.jsonl")    # reruns of old rows on them, with the block-level counters
SW = json.load(open(os.path.join(OUT, "rev_sweeps.json"))) if os.path.exists(os.path.join(OUT, "rev_sweeps.json")) else None
R2 = load("r2.jsonl")            # round 2: priority with the delay-critical class as 5QI 3 (GBR), bin/p10-pass-r2
R4 = load("r4.jsonl")            # 5QI 3 priority with decoding errors off, six seeds, bin/p10-pass-r2 (run_r4.py)
rows = load("pass.jsonl") + [r for r in REV if r["study"] == "pass" and r["pol"] == "queueprop"] + [r for r in R2 if r["study"] == "pass"]
SENS = load("sens.jsonl") + [r for r in R2 if r["study"] == "sens"] + [r for r in R4 if r["study"] == "sens"]
TEN = load("tenants.jsonl") + [r for r in REV if r["study"] == "tenants" and r["pol"] == "queueprop"]
_nebest = float(SW["noerrbest"]) if SW else 0.24
TX = (load("tsens.jsonl") + (load("tsens_extra.jsonl") if abs(_nebest - 0.24) < 1e-9 else [])
      + [r for r in REV if r["study"] == "tenants" and r["pol"].startswith("noerr_")])
LIMCELL = [r for r in REV if r["pol"].startswith("lim_")]
RT = [r for r in REV if r["pol"].startswith("r20_") and r["pol"] != "r20_pf"]
INFO = {}   # every paired test: key -> group, label, effect, wins, pairs


def reg(key, group, label, eff, wins, n):
    INFO[key] = dict(group=group, label=label, eff=eff, wins=int(wins), n=int(n))


def tt_ci(x):
    x = np.asarray(x, float)
    hw = stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / math.sqrt(len(x))
    return x.mean(), hw


M["Bins"] = str(len({r["bin"] for r in rows + SENS}))
PRAW = {}


def f(x, d=1):
    return f"{x:.{d}f}"


def fd(x):
    return f"{x:.0f}~ms" if x < 1000 else f"{x / 1000:.1f}~s"


def fp(p):
    if not np.isfinite(p):
        return "--"
    if p >= 0.001:
        return f"{p:.3f}"
    m, e = f"{p:.1e}".split("e")
    return f"\\ensuremath{{{m}\\times10^{{{int(e)}}}}}"


def sel(p, per):
    return {r["seed"]: r for r in rows if r["pol"] == p and r["period"] == per}


def viol(r):
    W = [w for w in r["windows"] if w["crit_miss"] >= 0]
    return 100 * np.mean([w["crit_miss"] > 0.01 for w in W]) if W else float("nan")


def total_thr(r):
    return sum(s["thr_mbps"] for s in r["slices"])


# pass geometry and calibration
el = [w["elev"] for w in CAL["windows"] if w["elev"] > 0]
M["ElevHi"], M["ElevLo"] = f(max(el), 0), f(min(el), 0)
tab = [tuple(map(float, x.split(":"))) for x in CFG["bprTable"].split(",")]
M["BprCalHi"], M["BprCalLo"] = f(tab[-1][1], 0), f(tab[0][1], 0)
M["BprCalDrop"] = f(100 * (1 - tab[0][1] / tab[-1][1]), 0)
SPAN = 117.0     # slots are counted from the 3 s warm-up to the 120 s end
_cal_h = CFG["h"] * 116.5 / SPAN; _cal_S = CFG["S"] * 116.5 / SPAN
M["SlotRate"], M["Nrbg"] = f(_cal_S, 0), f(CFG["N"], 0)
for tag, t in (("full", ""), ("half", "Half")):
    q = CFG[f"q_{tag}"]
    M[f"QHi{t}"] = q["hi"].split(",")[1]; M[f"QLo{t}"] = q["lo"].split(",")[1]
    qs = q["qstar"]
    M[f"QstarStart{t}"] = f(qs[-1][1], 2); M[f"QstarEnd{t}"] = f(qs[0][1], 2)
# Corollary (failure of a fixed quota), from the calibration seed: the highest elevation at which q*(theta), overhead
# included, reaches what the quota is worth: the guaranteed floor(qN)/N, or that plus the RBGs left over by the rounding
# and by the nearly idle mMTC slice, if the slice wins them all
N = CFG["N"]
M["Overhead"] = f(_cal_h, 2)
for tag, t in (("full", ""), ("half", "Half")):
    qv_ = [float(x) for x in CFG[f"q_{tag}"]["hi"].split(",")]
    fl = [math.floor(x * N + 1e-9) for x in qv_]
    left = N - sum(fl) + fl[2]
    qs = sorted(CFG[f"q_{tag}"]["qstar"])          # ascending elevation
    for nm, qeff in (("Guar", fl[1] / N), ("Max", (fl[1] + left) / N)):
        fail = [e for e, q in qs if q >= qeff]
        M[f"FailPred{nm}{t}"] = f(max(fail), 0) if fail else "--"
        M[f"QEff{nm}{t}"] = f(qeff, 2)
    M[f"Kappa{t}"] = f(fl[1] / N / qs[-1][1], 2)
    obs = []
    for r in sel("static_hi", 1 if tag == "full" else 2).values():
        bad = [w["elev"] for w in r["windows"] if w["crit_miss"] > 0.01]
        obs.append(max(bad) if bad else min(w["elev"] for w in r["windows"]))
    if obs:
        M[f"FailObs{t}"] = f(np.median(obs), 0); M[f"FailObsLo{t}"] = f(min(obs), 0)
        M[f"FailObsHi{t}"] = f(max(obs), 0); M[f"FailN{t}"] = str(len(obs))
    # two onsets per seed: the elevation from which every later window violates the target, and the highest elevation
    # at which the slice delivered under 98 % of its offered load
    pers, deliv = [], []
    off = 16.0 if tag == "full" else 8.0
    for r in sel("static_hi", 1 if tag == "full" else 2).values():
        W = [w for w in r["windows"] if w["crit_miss"] >= 0]
        k = len(W)
        while k > 0 and W[k - 1]["crit_miss"] > 0.01:
            k -= 1
        if k < len(W):
            pers.append(W[k]["elev"])
        sh = [w["elev"] for w in W if w["crit_mbps"] < 0.98 * off]
        if sh:
            deliv.append(max(sh))
    M[f"FailPersN{t}"] = str(len(pers)); M[f"FailDelivN{t}"] = str(len(deliv))
    if pers:
        M[f"FailPers{t}"] = f(np.median(pers), 0); M[f"FailPersLo{t}"] = f(min(pers), 0); M[f"FailPersHi{t}"] = f(max(pers), 0)
    if deliv:
        M[f"FailDeliv{t}"] = f(np.median(deliv), 0); M[f"FailDelivLo{t}"] = f(min(deliv), 0); M[f"FailDelivHi{t}"] = f(max(deliv), 0)
# Proposition (PF): the eight busy UEs (mMTC is sparse) share the cell equally; highest elevation of the calibration
# table where one delay-critical UE's load exceeds its share, against the elevation from which every later window violates
for tag, t, per in (("full", "", 1), ("half", "Half", 2)):
    lam1 = 500e3 / per
    bad = [e for e, b in tab if CFG["h"] * lam1 >= N * CFG["S"] * b / 8]
    M[f"PfPred{t}"] = f(max(bad), 0) if bad else "--"
    pers = []
    for r in sel("pf", per).values():
        W = [w for w in r["windows"] if w["crit_miss"] >= 0]
        k = len(W)
        while k > 0 and W[k - 1]["crit_miss"] > 0.01:
            k -= 1
        if k < len(W):
            pers.append(W[k]["elev"])
    M[f"PfPersN{t}"] = str(len(pers))
    if pers:
        M[f"PfPers{t}"] = f(np.median(pers), 0); M[f"PfPersLo{t}"] = f(min(pers), 0); M[f"PfPersHi{t}"] = f(max(pers), 0)
# per policy and load
for per, tl in LOAD.items():
    for p, tp in POL.items():
        R = sel(p, per)
        if not R:
            continue
        g = lambda s, k: np.array([r["slices"][s][k] for r in R.values()], float)
        up = g(1, "owd_p99"); mi = 100 * g(1, "miss")
        v = np.array([viol(r) for r in R.values()])
        k = f"{tp}{tl}"
        M[f"Up{k}"] = fd(np.median(up)); M[f"UpHi{k}"] = fd(up.max())
        M[f"Miss{k}"] = f(np.median(mi), 2 if np.median(mi) < 1 else 1); M[f"MissHi{k}"] = f(mi.max(), 1)
        M[f"Viol{k}"] = f(np.median(v), 0); M[f"ViolHi{k}"] = f(v.max(), 0)
        M[f"Et{k}"] = f(np.median(g(0, "thr_mbps")), 1)
        M[f"Ct{k}"] = f(np.median(g(1, "thr_mbps")), 1)
        M[f"Tot{k}"] = f(np.median([total_thr(r) for r in R.values()]), 1)
        M[f"Mp{k}"] = fd(np.median(g(2, "owd_p99")))
        M[f"Upt{k}"] = fd(np.median(g(1, "owd_p999")))
        M[f"N{k}"] = str(len(R))
# Lemma (operating point), out of sample: the loop's quota per window against min(kappa q*(theta), 0.85) with q*
# from the calibration seed's table at the window's elevation
qs_full = sorted(CFG["q_full"]["qstar"])
ev, qv = zip(*qs_full)
dev = []
for r in sel("reactive", 1).values():
    for w in r["windows"]:
        if w["q_crit"] > 0 and w["elev"] > 0:
            pred = min(1.25 * float(np.interp(w["elev"], ev, qv)), 0.85)
            dev.append(w["q_crit"] - pred)
if dev:
    M["LoopDevMed"] = f(100 * np.median(np.abs(dev)), 1); M["LoopDevMax"] = f(100 * np.max(np.abs(dev)), 1)
    M["LoopDevBias"] = f(100 * np.median(dev), 1); M["LoopDevN"] = str(len(dev))
# paired tests against the reactive loop: log p99 and violation share
for per, tl in LOAD.items():
    A = sel("reactive", per)
    for p, tp in POL.items():
        if p == "reactive":
            continue
        B = sel(p, per); ks = sorted(set(A) & set(B))
        if len(ks) < 5:
            continue
        x = np.log([A[k]["slices"][1]["owd_p99"] for k in ks]); y = np.log([B[k]["slices"][1]["owd_p99"] for k in ks])
        pv = stats.wilcoxon(x, y).pvalue if np.any(x != y) else float("nan")
        key = f"{tp}{tl}"
        M[f"Ratio{key}"] = f(float(np.exp(np.median(y - x))), 2 if abs(np.median(y - x)) < 2.3 else 0)
        rng = np.random.default_rng(11); dl = y - x
        bs = [np.exp(np.median(rng.choice(dl, len(dl)))) for _ in range(4000)]
        lo_, hi_ = np.percentile(bs, [2.5, 97.5])
        M[f"RatioCi{key}"] = f"{lo_:.2f}--{hi_:.2f}" if hi_ < 10 else f"{lo_:.0f}--{hi_:.0f}"
        M[f"P{key}"] = fp(pv); PRAW[key] = pv
        M[f"Wins{key}"] = str(int(np.sum(x < y))); M[f"Pairs{key}"] = str(len(ks))
        M[f"Wins{key}Rev"] = str(int(np.sum(x > y)))
        reg(key, "Delay" + (", half load" if tl else ", full load"), {"Pf": "PF", "Qos": "priority", "Bwp": "two BWPs", "Hi": "static, start", "Lo": "static, end", "Pred": "ephemeris", "Qp": "queue-proportional", "QosG": "priority, 5QI 3"}[tp],
            (lambda v: f"{v:.2f}" if v < 10 else f"{v:.0f}")(float(np.exp(np.median(y - x)))), np.sum(x < y), len(ks))
M["NSeeds"] = str(max(len(sel("reactive", 1)), 1))
# sensitivity of the loop on the pass, and the 24-UE cell
for p, tp in (("ctrl50", "CtlFast"), ("ctrl500", "CtlSlow"), ("kappa110", "KapLo"), ("kappa150", "KapHi"),
              ("ue24_reactive", "UeReact"), ("ue24_qos", "UeQos"), ("ue24_static_lo", "UeLo"),
              ("noerr_reactive", "NeReact"), ("noerr_qos", "NeQos"), ("noerr_static_lo", "NeLo"), ("noerr_qos3", "NeQosG"),
              ("off_reactive", "OffReact"), ("off_qos", "OffQos")):
    R = [r for r in SENS if r["pol"] == p]
    if R:
        up = [r["slices"][1]["owd_p99"] for r in R]
        M[f"Up{tp}"] = fd(np.median(up)); M[f"UpHi{tp}"] = fd(max(up))
        M[f"Viol{tp}"] = f(np.median([viol(r) for r in R]), 0)
        M[f"Et{tp}"] = f(np.median([r["slices"][0]["thr_mbps"] for r in R]), 1)
        M[f"N{tp}"] = str(len(R))
# 24 UEs: paired counts between the loop and priority, descriptive
_a = {r["seed"]: r["slices"][1]["owd_p99"] for r in SENS if r["pol"] == "ue24_reactive"}
_b = {r["seed"]: r["slices"][1]["owd_p99"] for r in SENS if r["pol"] == "ue24_qos"}
_k = set(_a) & set(_b)
M["UeWins"] = str(sum(_a[k] < _b[k] for k in _k)); M["UePairs"] = str(len(_k))
# tenants: A's contract and B's rate, windows entirely outside B's pause (50 s to 70 s) unless stated
if TEN and os.path.exists(os.path.join(OUT, "calib_t_cfg.json")):
    CT = json.load(open(os.path.join(OUT, "calib_t_cfg.json")))
    RC = TEN[0]["contract_mbps"]
    M["QTBest"] = CT["best"].split(",")[0]
    M["Contract"] = f(RC, 0); M["OverheadT"] = f(CT["h"] * 116.5 / SPAN, 2)
    tt = [tuple(map(float, x.split(":"))) for x in CT["bprTable"].split(",")]
    M["BprTHi"], M["BprTLo"] = f(tt[-1][1], 0), f(tt[0][1], 0)
    for k_, x_ in (("hi", "Hi"), ("lo", "Lo")):
        M[f"QT{x_}"] = CT[k_].split(",")[0]
    busy = lambda w: w["t"] + 5 <= 50 or w["t"] >= 70
    idle = lambda w: w["t"] >= 50 and w["t"] + 5 <= 70
    TP = {"pf": "Pf", "qos": "Qos", "policed": "Pol", "static_hi": "Hi", "static_lo": "Lo", "contract_eph": "Eph",
          "contract": "Con", "window": "Win", "contract_trim": "Trim", "limiter": "Lim", "static_best": "Best", "queueprop": "Qp"}
    TNAME = {"Pf": "PF", "Qos": "priority", "Pol": "cap, no lending", "Hi": "static, start", "Lo": "static, end", "Eph": "contract, ephemeris",
             "Con": "contract, no trim", "Win": "contract, 5 s", "Lim": "cap, lending", "Best": "best fixed", "Qp": "queue-proportional"}
    tsel = lambda p: {r["seed"]: r for r in TEN if r["pol"] == p}
    def tviol(r):
        # 1 % tolerance: a source limited to exactly R delivers 11.97 to 12.00 Mb/s per window
        return 100 * np.mean([w["a_mbps"] < 0.99 * RC for w in r["windows"] if busy(w)])
    def tshort(r):
        return np.mean([max(RC - w["a_mbps"], 0) for w in r["windows"] if busy(w)])
    def texc(r):
        return np.mean([max(w["a_mbps"] - RC, 0) for w in r["windows"] if busy(w)])
    def tb(r):
        return np.mean([w["b_mbps"] for w in r["windows"] if busy(w)])
    def tidle(r):
        return np.mean([w["a_mbps"] for w in r["windows"] if idle(w)])
    def ta(r):
        return np.mean([w["a_mbps"] for w in r["windows"] if busy(w)])
    def tmin(r):
        return min(w["a_mbps"] for w in r["windows"] if busy(w))
    def ttot(r):
        return ta(r) + tb(r)
    def tcell(r):
        return np.mean([w["a_mbps"] + w["b_mbps"] for w in r["windows"]])
    def tfine(r):
        # share of busy 0.5 s windows in which A received under 0.99 R; first sample starts at the warm-up (3 s)
        v = [x for i, x in enumerate(r["a_fine"]) if (3 + 0.5 * i + 0.5 <= 50 or 3 + 0.5 * i >= 70)]
        return 100 * np.mean([x < 0.99 * RC for x in v])
    def tback(r):
        # time from B's return until A's 0.5 s rate first holds R
        for i, x in enumerate(r["a_fine"]):
            if 3 + 0.5 * i >= 70 and x >= 0.99 * RC:
                return 3 + 0.5 * i - 70
        return float("nan")
    for p, tp in TP.items():
        R = tsel(p)
        if not R:
            continue
        for nm, fn, d in (("TViol", tviol, 0), ("TShort", tshort, 1), ("TExc", texc, 1), ("TB", tb, 1), ("TIdle", tidle, 1),
                          ("TA", ta, 1), ("TMin", tmin, 1), ("TTot", ttot, 1), ("TCell", tcell, 1), ("TFine", tfine, 1)):
            M[f"{nm}{tp}"] = f(np.median([fn(r) for r in R.values()]), d)
        M[f"TN{tp}"] = str(len(R))
        # tenant A's and B's delay, and A's offered traffic and drops in busy windows (offered: 30 Mb/s per A UE, four UEs, or R if limited)
        M[f"TDelayP{tp}"] = f(np.median([r["slices"][0]["owd_p50"] for r in R.values()]), 0)
        M[f"TDelayQ{tp}"] = f(np.median([r["slices"][0]["owd_p99"] for r in R.values()]), 0)
        M[f"TDelayBP{tp}"] = f(np.median([r["slices"][1]["owd_p50"] for r in R.values()]), 0)
        M[f"TDelayBQ{tp}"] = f(np.median([r["slices"][1]["owd_p99"] for r in R.values()]), 0)
        _off = RC if p in ("policed", "limiter") else 120.0
        M[f"TOffer{tp}"] = f(_off, 0)
        M[f"TDrop{tp}"] = f(100 * max(0, 1 - float(np.median([ta(r) for r in R.values()])) / _off), 0)
    # the trimmed contract loop is the reference of the paired tests, and the open-loop one until its runs exist
    REF = "contract_trim" if len(tsel("contract_trim")) >= 5 else "contract"
    A_ = tsel(REF)
    rng_t = np.random.default_rng(10)
    for p, tp in TP.items():
        if p == REF:
            continue
        B_ = tsel(p); ks = sorted(set(A_) & set(B_))
        if len(ks) < 5:
            continue
        rt = np.array([tb(A_[k]) / tb(B_[k]) for k in ks])
        bs = [np.median(rng_t.choice(rt, len(rt))) for _ in range(5000)]
        M[f"RatioTB{tp}"] = f(np.median(rt), 2)
        M[f"RatioTBCi{tp}"] = f"{np.percentile(bs, 2.5):.2f}--{np.percentile(bs, 97.5):.2f}"
        M[f"WinsTB{tp}"] = str(int(sum(tb(A_[k]) > tb(B_[k]) for k in ks))); M[f"PairsTB{tp}"] = str(len(ks))
        for nm, fn in (("TCell", tcell), ("TB", tb)):
            x = np.array([fn(A_[k]) for k in ks]); y = np.array([fn(B_[k]) for k in ks])
            pv_ = stats.wilcoxon(x, y).pvalue if np.any(x != y) else float("nan")
            M[f"P{nm}{tp}"] = fp(pv_); PRAW[f"{nm}{tp}"] = pv_
            reg(f"{nm}{tp}", "Rate, 12 Mb/s, errors on", f"{TNAME[tp]}, {'whole run' if nm == 'TCell' else 'B'}", f"{np.median(x - y):+.2f}", np.sum(x > y), len(ks))
    # the trimmed loop against kappa R, and the share of time B must be idle for the loop to carry more than the policer
    # in cell bytes, from medians: (1-x) P + x R = (1-x) T + x I
    if REF == "contract_trim":
        tgt = CT["kappa"] * RC
        errs = [abs(w["a_mbps"] - tgt) / tgt for r in tsel(REF).values() for w in r["windows"] if busy(w)]
        M["TrimTarget"] = f(tgt, 1); M["TrimErrMed"] = f(100 * np.median(errs), 1); M["TrimErrMax"] = f(100 * max(errs), 1)
        M["TrimWindows"] = str(len(errs))
        M["TrimMinAll"] = f(min(w["a_mbps"] for r in tsel(REF).values() for w in r["windows"] if busy(w)), 1)
        P_, T_ = (np.median([ttot(r) for r in tsel(x).values()]) for x in ("policed", REF))
        I_ = np.median([tidle(r) for r in tsel(REF).values()])
        if P_ > T_:
            M["TBreakEven"] = f(100 * (P_ - T_) / (P_ - T_ + I_ - RC), 0)
    _idl = [float(M[f"TIdle{tp}"]) for p, tp in TP.items() if p != "policed" and f"TIdle{tp}" in M]
    M["TIdleLoAll"], M["TIdleHiAll"] = f(min(_idl), 1), f(max(_idl), 1)
    # recovery after B's return, and how often the best fixed quota missed the contract
    for p, tp in (("contract_trim", "Trim"), ("limiter", "Lim"), ("policed", "Pol")):
        R = tsel(p)
        if R:
            bk = [tback(r) for r in R.values()]
            M[f"TBack{tp}"] = f(np.nanmedian(bk), 1); M[f"TBackHi{tp}"] = f(np.nanmax(bk), 1)
    R = tsel("static_best")
    if R:
        M["BestMissSeeds"] = str(sum(tmin(r) < 0.99 * RC for r in R.values())); M["BestLowest"] = f(min(tmin(r) for r in R.values()), 1)
    for p in ("contract_trim", "limiter", "policed"):
        R = tsel(p)
        if R:
            M[{"contract_trim": "TrimLowSeed", "limiter": "LimLowSeed", "policed": "PolLowSeed"}[p]] = f(min(tmin(r) for r in R.values()), 1)
    # the 0.5 s scale: lowest window, longest run below 0.99 R, and when A holds R for good in the 10 s after B's return
    def fine_busy(r):
        return [(3 + 0.5 * i, x) for i, x in enumerate(r["a_fine"]) if (3 + 0.5 * i + 0.5 <= 50 or 3 + 0.5 * i >= 70)]
    def frun(r):
        m_ = c_ = 0
        for _, x in fine_busy(r):
            c_ = c_ + 1 if x < 0.99 * RC else 0
            m_ = max(m_, c_)
        return 0.5 * m_
    for p, tp in (("contract_trim", "Trim"), ("limiter", "Lim"), ("policed", "Pol"), ("static_best", "Best")):
        R = tsel(p)
        if R:
            M[f"TDip{tp}"] = f(min(x for r in R.values() for _, x in fine_busy(r)), 1)
            M[f"TRun{tp}"] = f(max(frun(r) for r in R.values()), 1)
    # new-data slots per second under the quota scheduler (the priority schedulers do not log them)
    R = tsel("contract_trim")
    M["TSlots"] = f(np.median([r["slots"] / SPAN for r in R.values()]), 0)
    # Proposition (fixed share), out of sample: A's rate per window under the start-of-pass quota against the closed
    # form from the calibration seed; the slice is worth its guaranteed RBGs up to those plus the leftovers
    qv_ = [float(x) for x in CT["hi"].split(",")]; Nt = CT["N"]
    fl = [math.floor(x * Nt + 1e-9) for x in qv_]; left = Nt - sum(fl) + fl[2]
    te, tb_ = zip(*tt); ins, err, above = [], [], []
    for r in tsel("static_hi").values():
        for w in r["windows"]:
            if busy(w) and w["elev"] > 0:
                base = CT["S"] * float(np.interp(w["elev"], te, tb_)) / CT["h"] * 8 / 1e6
                lo_, hi_ = fl[0] * base, (fl[0] + left) * base
                ins.append(lo_ <= w["a_mbps"] <= hi_); above.append(w["a_mbps"] > hi_)
                err.append(abs(w["a_mbps"] - (lo_ + hi_) / 2) / w["a_mbps"])
    if ins:
        M["ShareInBracket"] = f(100 * np.mean(ins), 0); M["ShareErrMed"] = f(100 * np.median(err), 0)
        M["ShareWindows"] = str(len(ins))
        M["ShareAbove"] = f(100 * np.mean(above), 0)
# sensitivity of the tenant study
if TX:
    RC = TEN[0]["contract_mbps"] if TEN else 12
    busy = lambda w: w["t"] + 5 <= 50 or w["t"] >= 70
    for p, tp in (("noerr_contract_trim", "NeTrim"), ("noerr_limiter", "NeLim"), ("noerr_qos", "NeQos"), ("noerr_pf", "NePf"),
                  ("noerr_contract", "NeCon"), ("noerr_static_best", "NeBest"), ("noerr_queueprop", "NeQp"), ("off_contract_trim", "OffTrim"), ("off_limiter", "OffLim"),
                  ("off_static_best", "OffBest"), ("gain25", "GainLo"), ("gain100", "GainHi"), ("kappa102", "KapLo"),
                  ("kappa110", "KapHi"), ("rate8", "RateLo"), ("rate16", "RateHi")):
        R = [r for r in TX if r["pol"] == p]
        if not R:
            continue
        ca = lambda r: r["contract_mbps"]
        M[f"X{tp}A"] = f(np.median([np.mean([w["a_mbps"] for w in r["windows"] if busy(w)]) for r in R]), 1)
        M[f"X{tp}B"] = f(np.median([np.mean([w["b_mbps"] for w in r["windows"] if busy(w)]) for r in R]), 1)
        M[f"X{tp}Min"] = f(np.median([min(w["a_mbps"] for w in r["windows"] if busy(w)) for r in R]), 1)
        M[f"X{tp}Under"] = f(np.median([100 * np.mean([w["a_mbps"] < 0.99 * ca(r) for w in r["windows"] if busy(w)]) for r in R]), 0)
        M[f"X{tp}Cell"] = f(np.median([np.mean([w["a_mbps"] + w["b_mbps"] for w in r["windows"]]) for r in R]), 1)
        M[f"X{tp}N"] = str(len(R))
    R = [r for r in TX if r["pol"] == "noerr_contract_trim"]
    M["NeSlots"] = f(np.median([r["slots"] / SPAN for r in R]), 0)
    M["QNeBest"] = f(_nebest, 2)
    def xb(p):
        return {r["seed"]: np.mean([w["b_mbps"] for w in r["windows"] if busy(w)]) for r in TX if r["pol"] == p}
    for a_, b_, nm in (("noerr_contract_trim", "noerr_limiter", "NeTrimLim"), ("noerr_contract_trim", "noerr_static_best", "NeTrimBest"),
                       ("off_contract_trim", "off_limiter", "OffTrimLim"), ("off_contract_trim", "off_static_best", "OffTrimBest")):
        A_, B_ = xb(a_), xb(b_); ks = sorted(set(A_) & set(B_))
        rt = np.array([A_[k] / B_[k] for k in ks])
        M[f"XR{nm}"] = f(np.median(rt), 2); M[f"XW{nm}"] = str(int(np.sum(rt > 1))); M[f"XP{nm}"] = str(len(ks))
    R = [r for r in TX if r["pol"] == "noerr_static_best"]
    M["NeBestMissSeeds"] = str(sum(min(w["a_mbps"] for w in r["windows"] if busy(w)) < 0.99 * RC for r in R))
    M["NeBestLowest"] = f(min(min(w["a_mbps"] for w in r["windows"] if busy(w)) for r in R), 1)
    R = [r for r in TX if r["pol"] == "noerr_contract_trim"]
    M["NeTrimLowest"] = f(min(min(w["a_mbps"] for w in r["windows"] if busy(w)) for r in R), 1)
    off = [r for r in TX if r["pol"].startswith("off_")]
    if off:
        M["ElevOff"] = f(np.median([r["windows"][0]["elev"] for r in off]), 0)
        M["ElevOffLo"] = f(np.median([r["windows"][-1]["elev"] for r in off]), 0)

# ---- revision blocks ------------------------------------------------------------------------------------------------
def holmtest(key, group, label, A, B, fn, ratio=False):
    ks = sorted(set(A) & set(B))
    if len(ks) < 5:
        return None
    x = np.array([fn(A[k]) for k in ks]); y = np.array([fn(B[k]) for k in ks])
    pv_ = stats.wilcoxon(x, y).pvalue if np.any(x != y) else float("nan")
    PRAW[key] = pv_; M[f"P{key}"] = fp(pv_)
    M[f"W{key}"] = str(int(np.sum(x > y))); M[f"N{key}"] = str(len(ks))
    M[f"D{key}"] = f(np.median(x - y), 2)
    reg(key, group, label, f"{np.exp(np.median(np.log(x) - np.log(y))):.2f}" if ratio else f"{np.median(x - y):+.2f}", np.sum(x > y), len(ks))
    return x, y


if TEN:
    _b = lambda w: w["t"] + 5 <= 50 or w["t"] >= 70
    _ta = lambda r: float(np.mean([w["a_mbps"] for w in r["windows"] if _b(w)]))
    _tb = lambda r: float(np.mean([w["b_mbps"] for w in r["windows"] if _b(w)]))
    _tt = lambda r: _ta(r) + _tb(r)
    _tc = lambda r: float(np.mean([w["a_mbps"] + w["b_mbps"] for w in r["windows"]]))
    _tmin = lambda r: min(w["a_mbps"] for w in r["windows"] if _b(w))
    _sel = lambda rs, p: {r["seed"]: r for r in rs if r["pol"] == p}
    _T = lambda p: _sel(TEN, p)
    # m6: the 0.5 s comparison includes the cap with lending; macro TFineLim exists already
    # C1: the loop against the best fixed quota, split into A, B and the busy total
    _a, _c = _T("contract_trim"), _T("static_best")
    _k = sorted(_a)
    M["CAExc"] = f(np.median([_ta(_c[k]) - _ta(_a[k]) for k in _k]), 2)
    M["CBGain"] = f(np.median([_tb(_a[k]) - _tb(_c[k]) for k in _k]), 2)
    _d = [_tt(_a[k]) - _tt(_c[k]) for k in _k]
    M["CTotDiff"] = f(abs(float(np.median(_d))), 2); M["CTotSign"] = "lower" if np.median(_d) < 0 else "higher"
    M["PCTot"] = fp(stats.wilcoxon(_d).pvalue); PRAW["CTot"] = stats.wilcoxon(_d).pvalue
    reg("CTot", "Rate, 12 Mb/s, errors on", "best fixed, busy total", f"{np.median(_d):+.2f}", sum(x > 0 for x in _d), len(_d))
    # how many seeds the cap with lending, PF and priority beat the loop in the whole run
    # M1: 2 x 2, A saturated or limited at the source, QoS or quota scheduler
    if LIMCELL:
        G = "A's backlog, busy total"
        for p, tp in (("lim_static_best", "LS"), ("lim_contract_trim", "LT")):
            R = _sel(LIMCELL, p)
            for nm, fn, d in (("TA", _ta, 1), ("TB", _tb, 1), ("TTot", _tt, 1), ("TCell", _tc, 1), ("TMin", _tmin, 1)):
                M[f"{nm}{tp}"] = f(np.median([fn(r) for r in R.values()]), d)
            M[f"TDelayP{tp}"] = f(np.median([r["slices"][0]["owd_p50"] for r in R.values()]), 0)
            M[f"TDelayQ{tp}"] = f(np.median([r["slices"][0]["owd_p99"] for r in R.values()]), 0)
        LS, LT = _sel(LIMCELL, "lim_static_best"), _sel(LIMCELL, "lim_contract_trim")
        holmtest("OneQos", G, "priority: limited vs saturated", _T("policed"), _T("qos"), _tt)
        holmtest("OneBest", G, "quota 0.42: limited vs saturated", LS, _T("static_best"), _tt)
        holmtest("OneTrim", G, "trim: limited vs saturated", LT, _T("contract_trim"), _tt)
        holmtest("LimQuota", G, "A limited: quota 0.42 vs priority", LS, _T("policed"), _tt)
        holmtest("LimTrim", G, "A limited: trim vs cap, lending", LT, _T("limiter"), _tt)
        # A held at R by the source: B's rate under the quota scheduler against the priority scheduler
        holmtest("LimBQuota", G, "A limited: quota 0.42 vs priority, B", LS, _T("policed"), _tb)
        M["GapTotal"] = f(np.median([_tt(_T("limiter")[k]) - _tt(_a[k]) for k in _k]), 1)
        M["GapBack"] = f(np.median([_tt(LT[k]) - _tt(_a[k]) for k in sorted(LT)]), 1)
        M["GapQuota"] = f(np.median([_tt(_T("limiter")[k]) - _tt(LT[k]) for k in sorted(LT)]), 1)
        M["GapQosBack"] = f(np.median([_tt(_T("policed")[k]) - _tt(_T("qos")[k]) for k in _k]), 1)
    # M1, test 4: the cell before and during B's pause, t = 43 s and 53 s, windows of the trim, PF, priority and the cap
    for p, tp in (("contract_trim", "Trim"), ("pf", "Pf"), ("qos", "Qos"), ("limiter", "Lim")):
        R = _T(p).values()
        cw = lambda r, t0: next(w["a_mbps"] + w["b_mbps"] for w in r["windows"] if abs(w["t"] - t0) < 1e-6)
        M[f"JumpA{tp}"] = f(np.median([cw(r, 43) for r in R]), 1); M[f"JumpB{tp}"] = f(np.median([cw(r, 53) for r in R]), 1)
    # M3: drops are the complement of the rate on a saturating flow
    # M2: a binding contract, R = 20 Mb/s
    if RT:
        G = "Rate, 20 Mb/s, errors on"
        rt_ = lambda p: _sel(RT, p)
        Rr = 20.0
        M["ContractHi"] = "20"
        M["QRtBest"] = f(float(SW["r20best"]), 2)
        for tp, R in (("Trim", rt_("r20_contract_trim")), ("Lim", rt_("r20_limiter")), ("Best", rt_("r20_static_best")), ("Pf", _T("pf")),
                      ("Qos", _T("qos")), ("Qp", _T("queueprop"))):
            if not R:
                continue
            vs = lambda r: 100 * np.mean([w["a_mbps"] < 0.99 * Rr for w in r["windows"] if _b(w)])
            for nm, fn, d in (("RtA", _ta, 1), ("RtB", _tb, 1), ("RtTot", _tt, 1), ("RtCell", _tc, 1), ("RtMin", _tmin, 1), ("RtViol", vs, 0)):
                M[f"{nm}{tp}"] = f(np.median([fn(r) for r in R.values()]), d)
            M[f"RtLow{tp}"] = f(min(_tmin(r) for r in R.values()), 1)
            M[f"RtMiss{tp}"] = str(sum(_tmin(r) < 0.99 * Rr for r in R.values()))
            M[f"RtDelayP{tp}"] = f(np.median([r["slices"][0]["owd_p50"] for r in R.values()]), 0)
            M[f"RtDelayQ{tp}"] = f(np.median([r["slices"][0]["owd_p99"] for r in R.values()]), 0)
            M[f"RtIdle{tp}"] = f(np.median([np.mean([w["a_mbps"] for w in r["windows"] if w["t"] >= 50 and w["t"] + 5 <= 70]) for r in R.values()]), 1)
        A_, Li, Be = rt_("r20_contract_trim"), rt_("r20_limiter"), rt_("r20_static_best")
        for key, lab, B_, fn in (("RtBLim", "cap, lending, B", Li, _tb), ("RtCLim", "cap, lending, whole run", Li, _tc), ("RtBBest", "best fixed, B", Be, _tb),
                                 ("RtCBest", "best fixed, whole run", Be, _tc), ("RtBPf", "PF, B", _T("pf"), _tb)):
            holmtest(key, G, lab, A_, B_, fn)
        _r = np.array([_tb(A_[k]) / _tb(Be[k]) for k in sorted(A_)])
        M["RtRatioBest"] = f(np.median(_r), 2); M["RtRatioBestW"] = str(int(np.sum(_r > 1)))
        _r = np.array([_tb(A_[k]) / _tb(Li[k]) for k in sorted(A_)])
        M["RtRatioLim"] = f(np.median(_r), 2)
        _el = [w["elev"] for R in (A_, Li, Be, _T("qos")) for r in R.values() for w in r["windows"] if _b(w) and w["a_mbps"] < 0.99 * Rr]
        M["RtMissElLo"], M["RtMissElHi"] = f(min(_el), 0), f(max(_el), 0)
        M["RtLowMin"] = f(min(_tmin(r) for R in (A_, Li, Be, _T("qos")) for r in R.values()), 1)
        M["RtLowMax"] = f(max(min(_tmin(r) for r in R.values()) for R in (A_, Li, Be, _T("qos"))), 1)
        M["RtErr"] = f(100 * max(abs(w["a_mbps"] - 1.05 * Rr) / (1.05 * Rr) for r in A_.values() for w in r["windows"] if _b(w)), 1)
        # identity of a policy that ignores R, run with R = 20 Mb/s on one seed
        _p = next((r for r in REV if r["pol"] == "r20_pf"), None)
        if _p is not None:
            _o = _T("pf")[_p["seed"]]
            M["RtPfSame"] = "yes" if _o["windows"] == _p["windows"] else "NO"
            assert M["RtPfSame"] == "yes", "PF depends on R"
    # sweep rows below 0.24 (m11)
    if SW:
        M["QNeLowest"] = f(min(float(k) for k in SW["noerr"]), 2)
        _sw = {float(k): v for k, v in SW["noerr"].items()}
        M["NeSweepNonMono"] = str(sum(1 for a_, b_ in zip(sorted(_sw), sorted(_sw)[1:]) if _sw[b_] < _sw[a_]))
        _f = sorted(k for k, v in _sw.items() if v >= 12)
        _inf = [k for k in sorted(_sw) if k < min(_f)]
        M["NeBelowBest"] = f(max(_inf), 2) if _inf else "--"
        M["NeBelowBestMin"] = f(_sw[max(_inf)], 1) if _inf else "--"
    # M5, the no-error arm in the tested family, 12 seeds
    _x = lambda p: {r["seed"]: r for r in TX if r["pol"] == p}
    if _x("noerr_contract_trim") and len(_x("noerr_contract_trim")) >= 12:
        G = "Rate, 12 Mb/s, errors off"
        A_ = _x("noerr_contract_trim")
        for p, tp, lab in (("noerr_limiter", "Lim", "cap, lending"), ("noerr_static_best", "Best", "best fixed"), ("noerr_qos", "Qos", "priority"),
                           ("noerr_pf", "Pf", "PF"), ("noerr_contract", "Con", "contract, no trim"), ("noerr_queueprop", "Qp", "queue-proportional")):
            if _x(p):
                holmtest(f"NeB{tp}", G, f"{lab}, B", A_, _x(p), _tb)
                holmtest(f"NeC{tp}", G, f"{lab}, whole run", A_, _x(p), _tc)
        B_ = _x("noerr_limiter"); ks = sorted(set(A_) & set(B_))
        _dl = np.array([_tb(A_[k]) - _tb(B_[k]) for k in ks]); mn, hw = tt_ci(_dl)
        M["NeTieMean"] = f(mn, 2); M["NeTieLo"] = f(mn - hw, 2); M["NeTieHi"] = f(mn + hw, 2)
        _rt = np.array([_tb(A_[k]) / _tb(B_[k]) for k in ks]); rng_e = np.random.default_rng(12)
        bs = [np.median(rng_e.choice(_rt, len(_rt))) for _ in range(5000)]
        M["NeTieRatioLo"], M["NeTieRatioHi"] = f(np.percentile(bs, 2.5), 2), f(np.percentile(bs, 97.5), 2)
        M["NeTieSd"] = f(_dl.std(ddof=1), 2)
        _dc = np.array([_tc(A_[k]) - _tc(B_[k]) for k in ks]); mn, hw = tt_ci(_dc)
        M["NeCellMean"] = f(mn, 2); M["NeCellLo"] = f(mn - hw, 2); M["NeCellHi"] = f(mn + hw, 2)
        _all = {p: float(np.median([_tc(r) for r in _x(p).values()])) for p in ("noerr_limiter", "noerr_static_best", "noerr_qos", "noerr_pf", "noerr_contract", "noerr_contract_trim") if _x(p)}
        M["NeTotLo"], M["NeTotHi"] = f(min(_all.values()), 1), f(max(_all.values()), 1)
        _dt = [_tt(A_[k]) - _tt(_x("noerr_static_best")[k]) for k in sorted(A_)]
        M["NeBestADiff"] = f(np.median([_ta(_x("noerr_static_best")[k]) - _ta(A_[k]) for k in sorted(A_)]), 2)
        M["NeBestBDiff"] = f(np.median([_tb(A_[k]) - _tb(_x("noerr_static_best")[k]) for k in sorted(A_)]), 2)
        M["NeBestTDiff"] = f(np.median(_dt), 2)
        for p, tp in (("noerr_limiter", "Lim"), ("noerr_static_best", "Best"), ("noerr_qos", "Qos"), ("noerr_pf", "Pf"), ("noerr_contract", "Con"), ("noerr_contract_trim", "Trim"), ("noerr_queueprop", "Qp")):
            if _x(p):
                M[f"NeDelayP{tp}"] = f(np.median([r["slices"][0]["owd_p50"] for r in _x(p).values()]), 0)
                M[f"NeDelayQ{tp}"] = f(np.median([r["slices"][0]["owd_p99"] for r in _x(p).values()]), 0)
                M[f"NeMiss{tp}"] = str(sum(_tmin(r) < 0.99 * RC for r in _x(p).values()))
        M["NeSeeds"] = str(len(ks))
# M8: the 24-UE cell inside the tested family
_ue = lambda p: {r["seed"]: r for r in SENS if r["pol"] == p}
_ow = lambda r: math.log(r["slices"][1]["owd_p99"])
if _ue("ue24_qos"):
    holmtest("UeR", "Delay, 24 UEs", "loop vs priority (log $p_{99}$)", _ue("ue24_qos"), _ue("ue24_reactive"), _ow)
    holmtest("UeL", "Delay, 24 UEs", "static, end vs priority (log $p_{99}$)", _ue("ue24_qos"), _ue("ue24_static_lo"), _ow)
    INFO["UeR"]["eff"] = f"{np.exp(np.median([_ow(_ue('ue24_qos')[k]) - _ow(_ue('ue24_reactive')[k]) for k in _ue('ue24_qos')])):.2f}"
    INFO["UeL"]["eff"] = f"{np.exp(np.median([_ow(_ue('ue24_qos')[k]) - _ow(_ue('ue24_static_lo')[k]) for k in _ue('ue24_qos')])):.2f}"
    M["UeRatio"] = INFO["UeR"]["eff"]
if _ue("ue24_qos3"):
    holmtest("UeRG", "Delay, 24 UEs", "loop vs priority, 5QI 3 (log $p_{99}$)", _ue("ue24_qos3"), _ue("ue24_reactive"), _ow)
    INFO["UeRG"]["eff"] = f"{np.exp(np.median([_ow(_ue('ue24_qos3')[k]) - _ow(_ue('ue24_reactive')[k]) for k in _ue('ue24_qos3')])):.2f}"
    M["UeRatioG"] = INFO["UeRG"]["eff"]
    for p, tp in (("ue24_qos3", "UeQosG"),):
        R = [r for r in SENS if r["pol"] == p]
        M[f"Up{tp}"] = fd(np.median([r["slices"][1]["owd_p99"] for r in R])); M[f"UpHi{tp}"] = fd(max(r["slices"][1]["owd_p99"] for r in R))
        M[f"Viol{tp}"] = f(np.median([viol(r) for r in R]), 0); M[f"Et{tp}"] = f(np.median([r["slices"][0]["thr_mbps"] for r in R]), 1)
    # the priority rival at its best of the two classes, by median 99th-percentile delay
    _m79 = np.median([r["slices"][1]["owd_p99"] for r in SENS if r["pol"] == "ue24_qos"])
    _m3 = np.median([r["slices"][1]["owd_p99"] for r in SENS if r["pol"] == "ue24_qos3"])
    M["UeBestQ"] = "5QI~3" if _m3 < _m79 else "5QI~79"
    M["UeRatioBest"] = M["UeRatioG"] if _m3 < _m79 else M["UeRatio"]
    M["WUeRBest"] = M["WUeRG"] if _m3 < _m79 else M["WUeR"]
    M["PUeRBest"] = M["PUeRG"] if _m3 < _m79 else M["PUeR"]
# block-level counters: three test seeds, reruns of the old rows on the new binaries
def dsum(r, cond):
    # bins: t, slots new only, slots retx only, slots mixed, TBs new, TBs retx, NACKs, kB new
    W = [x for x in r["diag_win"] if cond(x[0])]
    return np.sum(np.array([x[1:] for x in W], float), axis=0)
def dstats(r, cond, span=None):
    sn, sr, sm, tn, tr, na, kb = dsum(r, cond)
    ns = sn + sm; tot = sn + sr + sm
    p = na / max(tn + tr, 1)
    return dict(newshare=100 * ns / max(tot, 1), tot=tot, retx=100 * sr / max(tot, 1), mixed=100 * sm / max(tot, 1), tb=tn / max(ns, 1), nack=100 * p, p=p, n=tn / max(ns, 1),
                pred=100 / (2 - (1 - p) ** (tn / max(ns, 1))), kbs=kb / max(ns, 1), tbretx=tr, S=ns / (len([x for x in r["diag_win"] if cond(x[0])]) * 5.0))
if CHK and "diag_win" in CHK[0]:
    _busy = lambda t: t + 5 <= 50                        # busy part of the first 60 s
    _pause = lambda t: t >= 50 and t + 5 <= 70
    DG = {}
    for st, p, tp, rowset in (("tenants", "limiter", "Lim", CHK), ("tenants", "qos", "Qos", CHK), ("tenants", "contract_trim", "Trim", CHK),
                              ("tenants", "lim_static_best", "LS", REV), ("tenants", "lim_contract_trim", "LT", REV), ("tenants", "policed", "Pol", [])):
        R = [r for r in rowset if r["study"] == st and r["pol"] == p and r["seed"] in (101, 102, 103)]
        if not R:
            continue
        for tag, c in (("", _busy), ("Pause", _pause)):
            ds = [dstats(r, c) for r in R]
            for k_, nm, d in (("newshare", "New", 0), ("tb", "Tb", 1), ("nack", "Nack", 0), ("pred", "Pred", 0), ("retx", "Retx", 0), ("mixed", "Mix", 1)):
                M[f"Dg{nm}{tp}{tag}"] = f(np.median([x[k_] for x in ds]), d)
            DG[tp + tag] = ds
    if DG:
        M["DgErrMax"] = f(max(abs(x["pred"] - x["newshare"]) for ds in DG.values() for x in ds), 0)
        M["DgRetxTbs"] = f"{int(sum(x['tbretx'] for ds in DG.values() for x in ds)):,}"
    # first study, final build: reactive and priority, first 60 s on three test seeds (m9)
    for p, tp in (("reactive", "React"), ("qos", "Qos"), ("pf", "Pf")):
        R = [r for r in CHK if r["study"] == "pass" and r["pol"] == p]
        ds = [dstats(r, lambda t: t + 5 <= 60) for r in R]
        M[f"DiagNew{tp}"] = f(np.median([x["newshare"] for x in ds]), 0)
        M[f"DiagNack{tp}"] = f(np.median([x["nack"] for x in ds]), 0)
        M[f"DiagTb{tp}"] = f(np.median([x["tb"] for x in ds]), 1)
        M[f"DiagTot{tp}"] = f(np.median([np.mean([sum(s_["thr_mbps"] for s_ in r["slices"])]) for r in R]), 1)
    M["DiagSeeds"] = "three"
    # M7: S measured under PF
    R = [r for r in CHK if r["study"] == "pass" and r["pol"] == "pf"]
    _SP = float(np.median([(r["diag"]["slots_new_only"] + r["diag"]["slots_mixed"]) / SPAN for r in R]))
    M["SPf"] = f(_SP, 0)
    R = [r for r in CHK if r["study"] == "pass" and r["pol"] == "reactive"]
    M["SLoop"] = f(np.median([(r["diag"]["slots_new_only"] + r["diag"]["slots_mixed"]) / SPAN for r in R]), 0)
    M["SPfHi"] = f(max((r["diag"]["slots_new_only"] + r["diag"]["slots_mixed"]) / SPAN for r in [r for r in CHK if r["study"] == "pass" and r["pol"] == "pf"]), 0)
    def pf_theta(Sv, lam1=500e3):
        bad = [e for e, b in tab if _cal_h * lam1 >= N * Sv * b / 8]
        return max(bad) if bad else None
    _hi = pf_theta(_cal_S); _lo = pf_theta(_SP)
    M["PfBandHi"] = f(_hi, 0) if _hi else "--"; M["PfBandLo"] = f(_lo, 0) if _lo else "--"
    _pers = []
    for r in sel("pf", 1).values():
        W = [w for w in r["windows"] if w["crit_miss"] >= 0]; k = len(W)
        while k > 0 and W[k - 1]["crit_miss"] > 0.01:
            k -= 1
        if k < len(W):
            _pers.append(W[k]["elev"])
    _first = [max(w["elev"] for w in r["windows"] if w["crit_miss"] > 0.01) for r in sel("pf", 1).values()]
    M["PfAbove"] = str(sum(x > (_hi or -1) for x in _pers)); M["PfInside"] = str(sum((_lo or 0) <= x <= (_hi or 90) for x in _pers)); M["PfBelow"] = str(sum(x < (_lo or 0) for x in _pers))
    M["PfFirstLo"], M["PfFirstHi"] = f(min(_first), 0), f(max(_first), 0)
    _r4l = os.path.join(OUT, "r4.log")
    if os.path.exists(_r4l):
        _c4 = [l for l in open(_r4l) if l.startswith("check ")]
        assert all("identical" in l for l in _c4)
        M["RfourCheck"] = {1: "one", 2: "two", 3: "three"}.get(len(_c4), str(len(_c4)))
    _r2l = os.path.join(OUT, "r2.log")
    if os.path.exists(_r2l):
        _c = [l for l in open(_r2l) if l.startswith("check ")]
        assert all("identical" in l for l in _c)
        M["RtwoCheck"] = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(len(_c), str(len(_c)))
    # regression of the new binaries
    _cc = json.load(open(os.path.join(OUT, "rev_check.json")))
    M["CheckSame"], M["CheckRows"] = str(_cc["same"]), str(_cc["same"] + _cc["different"])
    M["NewRuns"] = str(len(REV) + len(CHK))
# round 3: priority with 5QI 3 on the objective of (P1), the eMBB rate, and further into the tail
_g = sel("qos3", 1)
if _g:
    _e = lambda r: r["slices"][0]["thr_mbps"]
    _l99 = lambda r: math.log(r["slices"][1]["owd_p99"])
    for ref, tr in (("reactive", "React"), ("static_lo", "Lo")):
        holmtest(f"EmG{tr}", "Delay, full load", f"priority 5QI 3 vs {'loop' if tr == 'React' else 'static, end'}, eMBB", _g, sel(ref, 1), _e)
        if tr == "Lo":
            holmtest("PnGLo", "Delay, full load", "priority 5QI 3 vs static, end (log $p_{99}$)", sel(ref, 1), _g, _l99)
            INFO["PnGLo"]["eff"] = f"{np.exp(np.median([_l99(sel(ref, 1)[k]) - _l99(_g[k]) for k in _g])):.2f}"
    for p, tp in (("qos3", "QosG"), ("reactive", "React"), ("static_lo", "Lo"), ("qos", "Qos")):
        R = sel(p, 1)
        M[f"Upt{tp}"] = fd(np.median([r["slices"][1]["owd_p999"] for r in R.values()]))
        M[f"UptHi{tp}"] = fd(max(r["slices"][1]["owd_p999"] for r in R.values()))
        M[f"Late{tp}"] = f(100 * np.median([r["slices"][1]["miss"] for r in R.values()]), 3)
        M[f"Vt{tp}"] = f(np.median([100 * np.mean([w["crit_miss"] > 0.001 for w in r["windows"] if w["crit_miss"] >= 0]) for r in R.values()]), 0)
    _wins = lambda A, B, fn: sum(fn(A[k]) < fn(B[k]) for k in A)
    _p999 = lambda r: r["slices"][1]["owd_p999"]
    M["WtGReact"] = str(_wins(_g, sel("reactive", 1), _p999)); M["WtGLo"] = str(_wins(_g, sel("static_lo", 1), _p999))
    # the tail beyond the 99th percentile, and the class itself on the objective, in the Holm family
    _l999 = lambda r: math.log(r["slices"][1]["owd_p999"])
    holmtest("PtGReact", "Delay, full load", "priority 5QI 3 vs loop (log $p_{99.9}$)", sel("reactive", 1), _g, _l999)
    INFO["PtGReact"]["eff"] = f"{np.exp(np.median([_l999(sel('reactive', 1)[k]) - _l999(_g[k]) for k in _g])):.2f}"
    holmtest("PtGLo", "Delay, full load", "priority 5QI 3 vs static, end (log $p_{99.9}$)", sel("static_lo", 1), _g, _l999)
    INFO["PtGLo"]["eff"] = f"{np.exp(np.median([_l999(sel('static_lo', 1)[k]) - _l999(_g[k]) for k in _g])):.2f}"
    holmtest("EmGQos", "Delay, full load", "priority 5QI 3 vs 5QI 79, eMBB", _g, sel("qos", 1), _e)
    # without decoding errors (six seeds, descriptive): eMBB of priority against the loop and the end-of-pass quota
    _ne = lambda p: {r["seed"]: r for r in SENS if r["pol"] == p}
    for a_, b_, key in (("noerr_qos3", "noerr_reactive", "NeGReact"), ("noerr_qos", "noerr_reactive", "NeQReact"), ("noerr_qos3", "noerr_static_lo", "NeGLo")):
        A_, B_ = _ne(a_), _ne(b_)
        ks = sorted(set(A_) & set(B_))
        if ks:
            d_ = [_e(A_[k]) - _e(B_[k]) for k in ks]
            M[f"DEm{key}"] = f(np.median(d_), 2); M[f"WEm{key}"] = str(sum(x > 0 for x in d_)); M[f"NEm{key}"] = str(len(ks))
            M[f"TotEm{key}"] = f(np.median([sum(s_["thr_mbps"] for s_ in A_[k]["slices"]) - sum(s_["thr_mbps"] for s_ in B_[k]["slices"]) for k in ks]), 2)
    _ue3 = {r["seed"]: r for r in SENS if r["pol"] == "ue24_qos3"}
    if _ue3:
        UR, UL = _ue("ue24_reactive"), _ue("ue24_static_lo")
        holmtest("EmGUe", "Delay, 24 UEs", "priority 5QI 3 vs loop, eMBB", _ue3, UR, _e)
        holmtest("EmGUeLo", "Delay, 24 UEs", "priority 5QI 3 vs static, end, eMBB", _ue3, UL, _e)
        holmtest("PnGUeLo", "Delay, 24 UEs", "priority 5QI 3 vs static, end (log $p_{99}$)", UL, _ue3, _l99)
        INFO["PnGUeLo"]["eff"] = f"{np.exp(np.median([_l99(UL[k]) - _l99(_ue3[k]) for k in _ue3])):.2f}"
        M["WtGUeReact"] = str(_wins(_ue3, UR, _p999)); M["WtGUeLo"] = str(_wins(_ue3, UL, _p999))
        for p, tp, R in (("ue24_qos3", "UeQosG", _ue3), ("ue24_reactive", "UeReact", UR), ("ue24_static_lo", "UeLo", UL)):
            M[f"Upt{tp}"] = fd(np.median([r["slices"][1]["owd_p999"] for r in R.values()]))
            M[f"Late{tp}"] = f(100 * np.median([r["slices"][1]["miss"] for r in R.values()]), 3)
            M[f"Vt{tp}"] = f(np.median([100 * np.mean([w["crit_miss"] > 0.001 for w in r["windows"] if w["crit_miss"] >= 0]) for r in R.values()]), 0)
            M[f"Et{tp}"] = f(np.median([_e(r) for r in R.values()]), 1)
_qp = [w["q_crit"] for r in sel("queueprop", 1).values() for w in r["windows"] if w["q_crit"] > 0]
if _qp:
    M["QpCrit"] = f(np.median(_qp), 2)
# m1: cold start of the delay-critical loop
_cold = [r for r in REV if r["pol"] == "cold_reactive"]
if _cold:
    qs0 = float(sorted(CFG["q_full"]["qstar"])[-1][1]); k0, per = 1.25, []
    for r in _cold:
        # first control period in which the quota exceeds q* at the start of the pass, from the floor of 0.1
        tr = [x for x in r["q_trace"]]
        per.append(next((i + 1 for i, x in enumerate(tr) if x[1] > qs0), None))
    M["ColdQstar"] = f(qs0, 2)
    _kp = math.ceil(math.log(1 + (2 - k0) * (qs0 - 0.1) / (2 * (k0 - 1) * qs0)) / math.log(2 / k0))
    M["ColdPred"] = str(_kp); M["ColdMed"] = f(np.median([x for x in per if x]), 0); M["ColdMax"] = str(max(x for x in per if x)); M["ColdN"] = str(len(_cold))
    M["ColdUp"] = fd(np.median([r["slices"][1]["owd_p99"] for r in _cold]))
# m3: B's rate (Eq. rb) under the trimmed loop against the calibration seed
if TEN:
    CT_ = json.load(open(os.path.join(OUT, "calib_t_cfg.json")))
    _cal_t = json.loads(open(os.path.join(OUT, "calib_t.json")).read())
    _Sc, _Nc, _hA = CT_["S"], CT_["N"], CT_["h"]
    _sB = _cal_t["slices"][1]; _hB = _sB["rbg"] * _sB["bytes_per_rbg"] / (_sB["thr_mbps"] * 1e6 / 8 * 116.5)
    _bB = sorted((w["elev"], w["bpr_b"]) for w in _cal_t["windows"] if w["bpr_b"] > 0 and w["elev"] > 0)
    _bA = sorted((w["elev"], w["bpr_a"]) for w in _cal_t["windows"] if w["bpr_a"] > 0 and w["elev"] > 0)
    _ee = []
    for r in TEN:
        if r["pol"] != "contract_trim":
            continue
        for w in r["windows"]:
            if (w["t"] + 5 <= 50 or w["t"] >= 75) and w["elev"] > 0:
                bA = float(np.interp(w["elev"], *zip(*_bA))); bB = float(np.interp(w["elev"], *zip(*_bB)))
                rb = (1 - 0.0 - 1.05 * _hA * 1.5e6 / (_Sc * _Nc * bA)) * _Sc * _Nc * bB / _hB * 8 / 1e6
                _ee.append(abs(rb - w["b_mbps"]) / w["b_mbps"])
    M["RbErrMed"] = f(100 * np.median(_ee), 0); M["RbErrMax"] = f(100 * max(_ee), 0); M["RbWindows"] = str(len(_ee)); M["HB"] = f(_hB, 2)
    # m13: what h is worth
    M["HSpread"] = f(100 * (_cal_h / (CT_["h"] * 116.5 / SPAN) - 1), 0)
    M["HLowRate"] = f(1.05 * (CT_["h"] * 116.5 / SPAN) / _cal_h * 12, 1)
# m14: the delay verdict at other budgets, from the logged per-window p99
for D_ in (25, 50, 100):
    for p, tp in (("reactive", "React"), ("qos", "Qos"), ("static_lo", "Lo"), ("pf", "Pf"), ("queueprop", "Qp")):
        R = sel(p, 1)
        if R:
            M[f"DV{ {25: 'A', 50: 'B', 100: 'C'}[D_] }{tp}"] = f(np.median([100 * np.mean([w["crit_p99"] > D_ for w in r["windows"] if w["crit_p99"] >= 0]) for r in R.values()]), 0)
# delays of A at the first-study queue rival
pv = sorted(v for v in PRAW.values() if np.isfinite(v))
_holm = {}
_srt = sorted(((v, k) for k, v in PRAW.items() if np.isfinite(v)))
_alive = True
for i_, (v_, k_) in enumerate(_srt):
    _alive = _alive and v_ <= 0.05 / (len(_srt) - i_)
    _holm[k_] = _alive
json.dump(dict(pass_={k: bool(v) for k, v in _holm.items()}, raw={k: float(v) for k, v in PRAW.items()}), open(os.path.join(OUT, "holm.json"), "w"), indent=1)
print("Holm failures:", [k for k, v in _holm.items() if not v])
print("not surviving Holm:", [k for k, v in PRAW.items() if np.isfinite(v) and v > 0.05 / (len(pv) - sum(1 for q in pv if q < v))])
M["HolmTests"] = str(len(pv))
M["HolmPass"] = str(sum(1 for i, p_ in enumerate(pv) if all(q <= 0.05 / (len(pv) - k) for k, q in enumerate(pv[:i + 1]))))
# every simulation run behind the article: campaign rows, calibration and sweep runs, revision rows and check rows
import glob as _glob
M["CampaignRuns"] = f"{sum(len(load(x)) for x in ('pass.jsonl', 'sens.jsonl', 'tenants.jsonl', 'tsens.jsonl', 'tsens_extra.jsonl', 'rev.jsonl', 'rev_check.jsonl', 'r2.jsonl', 'r4.jsonl')) + 2 + len(_glob.glob(os.path.join(OUT, 'sweep_*.json'))):,}"
# the family, as a table: comparison, effect, wins of the first-named policy, p, Holm
_grp = {}
for k_, d_ in INFO.items():
    _grp.setdefault(d_["group"], []).append(k_)
_order = ["Delay, full load", "Delay, half load", "Delay, 24 UEs", "Rate, 12 Mb/s, errors on", "Rate, 12 Mb/s, errors off", "A's backlog, busy total", "Rate, 20 Mb/s, errors on"]
_lines = []
for g_ in _order:
    if g_ in _grp:
        _lines.append(("g", g_))
        for k_ in _grp[g_]:
            d_ = INFO[k_]
            _lines.append(("r", d_["label"], "$" + d_["eff"] + "$", f"{d_['wins']}/{d_['n']}", fp(PRAW[k_]), "" if _holm.get(k_) else "$\\times$"))
assert not (set(INFO) ^ set(k for k, v in PRAW.items() if np.isfinite(v))), set(INFO) ^ set(PRAW)
half = (len(_lines) + 1) // 2
if _lines[half][0] == "g":
    half += 1
_cols = lambda L: [("\\multicolumn{5}{@{}l}{\\emph{" + x[1] + "}}" if x[0] == "g" else " & ".join(x[1:])) for x in L]
_right = _lines[half:]
if _right and _right[0][0] == "r":
    _g = [x for x in _lines[:half] if x[0] == "g"][-1][1]
    _right = [("g", _g + ", continued")] + _right
_a, _b_ = _cols(_lines[:half]), _cols(_right)
if len(_b_) > len(_a):
    _a += [" & & & & "] * (len(_b_) - len(_a))
_b_ += [" & & & & "] * (len(_a) - len(_b_))
with open(os.path.join(HERE, "..", "tab_holm.tex"), "w") as fh:
    fh.write("% generated by sim/make_macros5.py; do not edit\n")
    fh.write("\\begin{tabular}{@{}lcccc|lcccc@{}}\n\\toprule\nComparison & Effect & Wins & $p$ & Holm & Comparison & Effect & Wins & $p$ & Holm\\\\\n\\midrule\n")
    for x, y in zip(_a, _b_):
        fh.write(x + " & " + y + " \\\\\n")
    fh.write("\\bottomrule\n\\end{tabular}\n")
M["HolmFail"] = str(sum(1 for v in _holm.values() if not v))
with open(os.path.join(HERE, "..", "macros_p10.tex"), "w") as fh:
    fh.write("% generated by sim/make_macros5.py; do not edit\n")
    for k, v in sorted(M.items()):
        fh.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print(len(M), "macros")
