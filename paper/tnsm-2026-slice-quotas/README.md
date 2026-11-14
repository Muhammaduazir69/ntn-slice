# Code and data: matching the slicing mechanism to the promise on a receding LEO satellite

Companion material for M. Uzair, "Quota, Priority or Rate Cap? Matching the Slicing Mechanism to the Promise on a Receding Low Earth Orbit Satellite," 2026.

The study runs a 5G-LENA cell on a LEO satellite as it recedes and compares slice quotas, priorities and rate caps for eMBB and URLLC tenants, with measurement-driven quota control.

| Path | Contents |
|---|---|
| `ns3_patch/` | Campaign example source of record (slice-quota scheduler scenario) and build script |
| `run_ns3_*.py`, `run_*.py`, `chain_*.sh` | Campaign drivers for the pass and tenant studies and their sensitivity runs |
| `out/`, `out_dev/`, `diag/` | Result files, development runs and HARQ diagnostics |
| `make_calib*.py`, `regress_pass.py`, `compare_rev.py` | Calibration and regression checks |
| `make_macros*.py`, `make_figs*.py` | Numbers and figures, generated from the results |

Contact: Muhammad Uzair, muhammaduzairr69@gmail.com, ORCID 0009-0002-4104-2680. License: as the repository (GPL-2.0-only for code).
