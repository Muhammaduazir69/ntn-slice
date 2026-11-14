#!/usr/bin/env python3
"""Data figures of the slicing study, from the same rows as make_macros.py."""
import os, sys
import numpy as np
from figstyle import *  # noqa: F401,F403
import make_macros as MM

FIG = os.path.join(MM.HERE, "..", "figures")
POLS = [("pf", "PF, no slices", GREY, "s", DASH["dot"]), ("bwp", "Static BWPs", PURPLE, "^", DASH["dashdot"]),
        ("static", "Static quota 0.40", GOLD, "D", DASH["longdash"]),
        ("statictuned", "Static quota 0.58", ORANGE, "v", DASH["dash"]),
        ("oracle", "Oracle quota", INK, "x", DASH["dot"]), ("reactive", "Reactive loop", BLUE, "o", DASH["solid"])]


def fig_policies():
    """URLLC p99 delay and eMBB throughput against elevation, median over seeds with min-max bars."""
    fig, axs = plt.subplots(1, 2, figsize=(PAGE, 2.3))
    for p, lab, c, m, ls in POLS:
        for ax, s, k in ((axs[0], 1, "owd_p99"), (axs[1], 0, "thr_mbps")):
            xs, md, lo, hi = [], [], [], []
            for o in MM.OFFS:
                R = MM.sel(p, o)
                if not R:
                    continue
                v = np.array([r["slices"][s][k] for r in R.values()])
                xs.append(MM.elev(o)); md.append(np.median(v)); lo.append(v.min()); hi.append(v.max())
            if not xs:
                continue
            md, lo, hi = map(np.array, (md, lo, hi))
            ax.errorbar(xs, md, yerr=[md - lo, hi - md], color=c, marker=m, ls=ls, mfc="white" if p == "oracle" else c,
                        mec=c, capsize=1.5, elinewidth=0.6, label=lab)
    axs[0].set_yscale("log"); axs[0].set_ylabel("URLLC 99th-percentile delay (ms)")
    axs[1].set_ylabel("eMBB throughput (Mb/s)")
    for ax in axs:
        ax.set_xlabel("Elevation at the start of the run (deg)"); ax.invert_xaxis()
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=6, bbox_to_anchor=(0.5, 1.07))
    fig.tight_layout(w_pad=1.5)
    fig.savefig(os.path.join(FIG, "fig2_policies.pdf")); print("wrote fig2_policies.pdf")


def fig_model():
    """(a) predicted minimum quota against the measured URLLC share; (b) p99 delay against utilization."""
    fig, axs = plt.subplots(1, 2, figsize=(PAGE, 2.3))
    pts = {"statictuned": [], "oracle": [], "reactive": []}
    for r in MM.rows:
        s = r["slices"][1]
        if r["pol"] not in pts or "bytes_per_rbg" not in s or s["bytes_per_rbg"] <= 0:
            continue
        q = MM.LAM / ((r["slots"] / MM.TRAFFIC_S) * r["rbg_per_slot"] * s["bytes_per_rbg"])
        quota = {"statictuned": 0.58, "oracle": {4: 0.68, 8: 0.82}.get(r["offset"], 0.58)}.get(r["pol"], s["mean_quota"])
        full = s["thr_mbps"] > 0.98 * MM.LAM * 8 / 1e6
        pts[r["pol"]].append((q, s["rbg_share"], q / quota, s["owd_p99"], full, MM.elev(r["offset"])))
    for p, lab, c, m, ls in POLS:
        if p not in pts or not pts[p]:
            continue
        a = np.array(pts[p], float)
        full = a[:, 4] > 0
        axs[0].plot(a[full, 0], a[full, 1], ls="none", marker=m, color=c, mfc="white" if p == "oracle" else c, label=lab)
        axs[1].plot(a[:, 2], a[:, 3], ls="none", marker=m, color=c, mfc="white" if p == "oracle" else c, label=lab)
    lim = [0.35, 0.85]
    axs[0].plot(lim, lim, color=INK2, lw=0.7, ls="-")
    axs[0].set_xlim(lim); axs[0].set_ylim(lim)
    axs[0].set_xlabel(r"Predicted minimum quota $q^{\ast}$"); axs[0].set_ylabel("Measured URLLC share of RBGs")
    axs[1].set_yscale("log"); axs[1].axvline(1.0, **THRESH)
    axs[1].set_xlabel(r"Utilization $\rho=q^{\ast}/q_{\mathrm{u}}$"); axs[1].set_ylabel("URLLC 99th-percentile delay (ms)")
    axs[0].legend(loc="upper left")
    fig.tight_layout(w_pad=1.5)
    fig.savefig(os.path.join(FIG, "fig3_model.pdf")); print("wrote fig3_model.pdf")


if __name__ == "__main__":
    setup()
    os.makedirs(FIG, exist_ok=True)
    for w in (sys.argv[1:] or ["policies", "model"]):
        {"policies": fig_policies, "model": fig_model}[w]()
