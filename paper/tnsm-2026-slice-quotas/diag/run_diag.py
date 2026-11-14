import json,os,subprocess,tempfile,sys
from concurrent.futures import ThreadPoolExecutor
H=os.path.dirname(os.path.abspath(__file__)); NS3=os.path.expanduser("~/6g_ntn_ns3/ns-3-dev")
C=json.load(open(os.path.join(H,"..","out","calib_cfg.json"))); q=C["q_full"]
BASE=dict(duration=120,ueBehindS=40,numUes=12,embbMbps=30,critBytes=500,satEirpDbm=55,deadlineMs=50,warmupS=3,windowS=5,critPeriodMs=1)
P={"pf":dict(policy="pf"),"qos":dict(policy="qos"),"bwp":dict(policy="bwp"),"static_lo":dict(policy="static",quotas=q["lo"]),"reactive":dict(policy="reactive",initQuotas=q["init"])}
OUT=os.path.join(H,"diag.jsonl")
def run(j):
    p,s=j; d=tempfile.mkdtemp(prefix="p10d_"); a=dict(BASE,RngRun=s,outputDir=d,**P[p])
    r=subprocess.run(["nice","-n","5",os.path.join(H,"diag_pass")]+[f"--{k}={v}" for k,v in a.items()],capture_output=True,text=True,cwd=NS3)
    subprocess.run(["rm","-rf",d])
    diag=[l for l in r.stderr.splitlines() if l.startswith("DIAG")]
    res=[l for l in r.stdout.splitlines() if l.startswith("{")]
    o=dict(pol=p,seed=s,**(json.loads(diag[-1][5:]) if diag else dict(error=r.stderr[-300:])))
    if res:
        x=json.loads(res[-1]); o["tot"]=sum(t["thr_mbps"] for t in x["slices"]); o["embb"]=x["slices"][0]["thr_mbps"]; o["sched_slots"]=x["slots"]
    open(OUT,"a").write(json.dumps(o)+"\n")
with ThreadPoolExecutor(6) as e: list(e.map(run,[(p,s) for s in (1,2) for p in P]))
