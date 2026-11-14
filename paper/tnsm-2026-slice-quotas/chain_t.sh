#!/bin/bash
# tenant calibration now, the tenant campaign once the pass reruns have ended
cd "$(dirname "$0")"
D=$(mktemp -d)
(cd ~/6g_ntn_ns3/ns-3-dev && nice -n 5 build/contrib/ntn-slice/examples/ns3.43-ntn-slice-tenants-leo-optimized --policy=static --quotas=0.45,0.45,0.1 --duration=120 --ueBehindS=40 --bIdleStop=0 --RngRun=99 --outputDir=$D) > out/calib_t.json 2> out/calib_t.err
rm -rf "$D"
python3 make_calib_t.py > out/calib_t.log 2>&1
P=$(cat out/ns3_pass8.pid); while kill -0 "$P" 2>/dev/null; do sleep 60; done
python3 run_ns3_tenants9.py 10 > out/ns3_tenants9.log 2>&1
