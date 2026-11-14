#!/usr/bin/env python3
"""Data figures of the falling-pass study (out/ns3_pass5.jsonl), full delay-critical load."""
import os, sys
import numpy as np
from figstyle import *  # noqa: F401,F403
import make_macros5 as MM

FIG = os.path.join(MM.HERE, "..", "figures")
POLS = [("pf", "PF, no slices", GREY, "s", DASH["dot"]), ("qos", "5QI priority (79)", PURPLE, "^", DASH["dashdot"]),
        ("bwp", "Two BWPs", TEAL, "<", DASH["dot"]), ("static_hi", "Static, start of pass", ORANGE, "v", DASH["dash"]),
        ("static_lo", "Static, end of pass", GOLD, "D", DASH["longdash"]),
        ("predict", "Ephemeris", INK, "x", DASH["dashdot"]), ("queueprop", "Queue-proportional", "#8d6e63", "P", DASH["dashdot"]),
        ("qos3", "5QI priority (3)", RED, "*", DASH["dash"]),
        ("reactive", "Measured loop", BLUE, "o", DASH["solid"])]


def series(p, key, per=1):
    """Median over seeds of a window quantity, against the median elevation of the window."""
    R = list(MM.sel(p, per).values())
    if not R:
        return None, None
    n = min(len(r["windows"]) for r in R)
    el = np.median([[r["windows"][i]["elev"] for i in range(n)] for r in R], axis=0)
    v = np.median([[r["windows"][i][key] for i in range(n)] for r in R], axis=0)
    return el, v


def fig_pass():
    fig, axs = plt.subplots(1, 2, figsize=(PAGE, 2.1))
    for p, lab, c, m, ls in [x for x in POLS if x[0] != "queueprop"]:   # its delay runs to tens of seconds; Table V
        el, v = series(p, "crit_p99")
        if el is None:
            continue
        axs[0].plot(el, v, color=c, marker=m, ls=ls, ms=2.8, markevery=3, mfc="white" if p == "predict" else c, label=lab)
        el, v = series(p, "crit_miss")
        axs[1].plot(el, 100 * np.maximum(v, 1e-4), color=c, marker=m, ls=ls, ms=2.8, markevery=3,
                    mfc="white" if p == "predict" else c)
    axs[0].axhline(50, **THRESH); axs[1].axhline(1, **THRESH)
    axs[0].set_yscale("log"); axs[1].set_yscale("log")
    axs[0].set_ylabel("Delay-critical 99th pct. delay (ms)"); axs[1].set_ylabel("Packets over 50 ms (%)")
    for ax in axs:
        ax.set_xlabel("Elevation (deg)"); ax.invert_xaxis()
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=8, bbox_to_anchor=(0.5, 1.08), fontsize=5.9, columnspacing=0.8, handlelength=1.7)
    fig.tight_layout(w_pad=1.5)
    fig.savefig(os.path.join(FIG, "fig2_pass.pdf")); print("wrote fig2_pass.pdf")


def fig_quota():
    fig, axs = plt.subplots(1, 2, figsize=(PAGE, 2.0))
    ev, qv = zip(*sorted(MM.CFG["q_full"]["qstar"]))
    axs[0].plot(ev, qv, color=INK2, lw=0.9, ls="-", label=r"$q^{\ast}(\theta)$, calibration seed")
    axs[0].plot(ev, np.minimum(1.25 * np.array(qv), 0.85), color=INK2, lw=0.9, ls=(0, (3, 2)),
                label=r"$\min(\kappa q^{\ast},0.85)$")
    for p, lab, c, m, ls in POLS:
        if p in ("reactive", "predict"):
            el, v = series(p, "q_crit")
            axs[0].plot(el, v, color=c, marker=m, ls="none", ms=3, mfc="white" if p == "predict" else c, label=lab)
        if p == "queueprop":
            continue
        el, v = series(p, "embb_mbps")
        if el is not None:
            axs[1].plot(el, v, color=c, marker=m, ls=ls, ms=2.8, markevery=3, mfc="white" if p == "predict" else c,
                        label=lab)
    for p, lab, c, m, ls in POLS:
        if p in ("static_hi", "static_lo"):
            q = float(MM.CFG["q_full"]["hi" if p == "static_hi" else "lo"].split(",")[1])
            axs[0].axhline(q, color=c, ls=ls, lw=0.8, label=lab)
    axs[0].set_ylabel("Delay-critical quota"); axs[1].set_ylabel("eMBB throughput (Mb/s)")
    for ax in axs:
        ax.set_xlabel("Elevation (deg)"); ax.invert_xaxis()
    axs[0].legend(loc="upper left", fontsize=6)
    fig.tight_layout(w_pad=1.5)
    fig.savefig(os.path.join(FIG, "fig3_quota.pdf")); print("wrote fig3_quota.pdf")


TPOLS = [("qos", "5QI priority (79)", PURPLE, "^", DASH["dashdot"]), ("policed", "Cap, no lending", GREY, "s", DASH["dot"]), ("limiter", "Cap, lending", GREEN if "GREEN" in globals() else "#2e7d32", "P", DASH["dash"]),
         ("static_hi", "Static, start of pass", ORANGE, "v", DASH["dash"]), ("static_lo", "Static, end of pass", GOLD, "D", DASH["longdash"]), ("static_best", "Best fixed quota", "#8d6e63", ">", DASH["dot"]),
         ("queueprop", "Queue-proportional", "#c2185b", "*", DASH["dashdot"]), ("window", "Contract, 5 s", TEAL, "<", DASH["dot"]), ("contract", "Contract, no trim", INK, "x", DASH["dashdot"]),
         ("contract_trim", "Trimmed loop", BLUE, "o", DASH["solid"])]


def onsets(p, per):
    """Per seed: the elevation from which every later window violates the target, and the first bad window."""
    pers, first = [], []
    for r in MM.sel(p, per).values():
        W = [w for w in r["windows"] if w["crit_miss"] >= 0]
        k = len(W)
        while k > 0 and W[k - 1]["crit_miss"] > 0.01:
            k -= 1
        if k < len(W):
            pers.append(W[k]["elev"])
        bad = [w["elev"] for w in W if w["crit_miss"] > 0.01]
        if bad:
            first.append(max(bad))
    return pers, first


def fig_fail():
    """Failure elevation: the band predicted from the calibration seed against every test seed."""
    fig, ax = plt.subplots(figsize=(COL if "COL" in globals() else 3.5, 1.55))
    M = MM.M
    rows = [("Static, start of pass", "static_hi", 1, float(M["FailPredMax"]), float(M["FailPredGuar"]), ORANGE),
            ("PF, no slices", "pf", 1, float(M["PfBandLo"]), float(M["PfBandHi"]), GREY)]
    for i, (lab, p, per, lo, hi, c) in enumerate(rows):
        y = len(rows) - 1 - i
        ax.barh(y, hi - lo if hi > lo else 0.6, left=min(lo, hi), height=0.56, color=c, alpha=0.28, lw=0)
        pers, first = onsets(p, per)
        rng = np.random.default_rng(3)
        ax.plot(pers, y + rng.uniform(-0.16, 0.16, len(pers)), ls="none", marker="o", ms=3, color=c, mec=INK, mew=0.3, label="Lasting violation" if i == 0 else None)
        ax.plot(first, y + 0.36 + rng.uniform(-0.05, 0.05, len(first)), ls="none", marker="x", ms=2.8, color=INK, mew=0.5, label="First bad window" if i == 0 else None)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1], fontsize=6.8)
    ax.set_ylim(-0.5, len(rows) + 0.15)
    ax.set_xlabel("Elevation (deg)"); ax.invert_xaxis()
    from matplotlib.patches import Patch
    h, l = ax.get_legend_handles_labels()
    ax.legend(h + [Patch(color=GREY, alpha=0.28, lw=0)], l + ["Predicted band"], loc="upper left", fontsize=6, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig5_fail.pdf")); print("wrote fig5_fail.pdf")


def fig_tenants():
    """Tenant A's rate over the pass against its contract, and B's rate; medians over seeds, per window."""
    rows = MM.TEN
    fig, axs = plt.subplots(1, 2, figsize=(PAGE, 2.1))
    for p, lab, c, m, ls in TPOLS:
        R = [r for r in rows if r["pol"] == p]
        if not R:
            continue
        n = min(len(r["windows"]) for r in R)
        t = [R[0]["windows"][i]["t"] + 2.5 for i in range(n)]
        for ax, key in zip(axs, ("a_mbps", "b_mbps")):
            ax.plot(t, np.median([[r["windows"][i][key] for i in range(n)] for r in R], axis=0), color=c, marker=m, ls=ls,
                    ms=2.8, markevery=3, label=lab)
    axs[0].axhline(R[0]["contract_mbps"], **THRESH)
    for ax in axs:
        ax.axvspan(50, 70, color="#e9edf1", lw=0, zorder=0); ax.set_xlabel("Time in the pass (s)")
    axs[0].set_ylabel("Tenant A throughput (Mb/s)"); axs[1].set_ylabel("Tenant B throughput (Mb/s)")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=5, bbox_to_anchor=(0.5, 1.13), fontsize=6.5)
    fig.tight_layout(w_pad=1.5)
    fig.savefig(os.path.join(FIG, "fig4_tenants.pdf")); print("wrote fig4_tenants.pdf")


if __name__ == "__main__":
    setup()
    for w in (sys.argv[1:] or ["pass", "quota", "tenants", "fail"]):
        {"pass": fig_pass, "quota": fig_quota, "tenants": fig_tenants, "fail": fig_fail}[w]()
