import json,os,subprocess,tempfile
from concurrent.futures import ThreadPoolExecutor
H=os.path.dirname(os.path.abspath(__file__)); NS3=os.path.expanduser("~/6g_ntn_ns3/ns-3-dev")
Q=json.load(open(os.path.join(H,"..","out","calib_cfg.json")))["q_full"]["init"]
A=dict(duration=60,ueBehindS=40,numUes=12,embbMbps=30,critBytes=500,satEirpDbm=55,deadlineMs=50,warmupS=3,windowS=5,critPeriodMs=1)
OUT=os.path.join(H,"d2.jsonl")
def run(j):
    p,s=j; d=tempfile.mkdtemp(prefix="p10d_"); a=dict(A,RngRun=s,policy=p,outputDir=d)
    if p=="reactive": a["initQuotas"]=Q
    r=subprocess.run(["nice","-n","5",os.path.join(H,"diag2")]+[f"--{k}={v}" for k,v in a.items()],capture_output=True,text=True,cwd=NS3)
    subprocess.run(["rm","-rf",d])
    o=dict(pol=p,seed=s)
    for l in r.stderr.splitlines():
        if l.startswith("DIAG2 "): o.update(json.loads(l[6:]))
        if l.startswith("DIAG "): o.update(json.loads(l[5:]))
    x=json.loads([l for l in r.stdout.splitlines() if l.startswith("{")][-1]); o["tot"]=sum(t["thr_mbps"] for t in x["slices"])
    open(OUT,"a").write(json.dumps(o)+"\n")
with ThreadPoolExecutor(6) as e: list(e.map(run,[(p,s) for s in (1,2,3) for p in ("reactive","qos")]))
