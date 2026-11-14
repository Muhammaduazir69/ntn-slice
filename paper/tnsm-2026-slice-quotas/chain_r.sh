#!/bin/bash
# resume after reboot: finish the pass reruns, then the tenant campaign; both resume from their jsonl
cd "$(dirname "$0")"
python3 run_ns3_pass8.py 4 >> out/ns3_pass8.log 2>&1
python3 run_ns3_tenants9.py 11 > out/ns3_tenants9.log 2>&1
