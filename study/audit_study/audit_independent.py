from pathlib import Path
import random,hashlib,json,csv,math,statistics,bisect
from collections import defaultdict

HERE=Path(__file__).parent
SIM=HERE.parent/'simulation'
CFG=json.loads((SIM/'results.json').read_text())
records=list(csv.DictReader((SIM/'run_metrics.csv').open(encoding='utf-8')))
agg=list(csv.DictReader((SIM/'aggregate_metrics.csv').open(encoding='utf-8')))
paired=list(csv.DictReader((SIM/'paired_contrasts.csv').open(encoding='utf-8')))

def stream(*parts):
    b='|'.join(str(p) for p in ('article1-synthetic-v1',)+parts).encode()
    return random.Random(int.from_bytes(hashlib.sha256(b).digest()[:16],'big'))

def percentile(a,q):
    a=sorted(a); z=(len(a)-1)*q; k=int(z)
    return a[k]+(a[min(k+1,len(a)-1)]-a[k])*(z-k)

def close(a,b,key):
    assert abs(float(a)-float(b))<1e-10,(key,a,b)

sources={(float(r['alpha']),int(r['seed'])):r['history'] for r in csv.DictReader((SIM/'source_histories.csv').open(encoding='utf-8'))}
for (alpha,seed),actual in sources.items():
    r=stream('source',alpha,seed); value=r.randrange(2); bits=[value]
    for _ in range(1199):
        value^=(r.random()<alpha); bits.append(value)
    assert actual==''.join(map(str,bits))

# Independently reconstruct the state at every read with sorted delivery lists
# and binary search, rather than the simulator's event heap or state update loop.
conditions={c['id']:c for c in CFG['conditions']}
comparisons=0
for rec in records:
    cond=conditions[rec['condition']]; seed=int(rec['seed']); mode=rec['publication']
    components=('x','y') if mode=='R0' else ('object',)
    drops=recvr_drops=pending=0
    arrivals={c:[] for c in components}
    ro=stream('outage',seed); bad=ro.random()<.05; env=[]
    for _ in range(1200):
        env.append(bad)
        bad=(ro.random()>=.1) if bad else (ro.random()<(.05*.1/.95))
    delays={c:stream('delay',mode,c,seed) for c in components}
    loss={c:stream('loss',mode,c,seed) for c in components}
    fault=cond['restart']!='none'
    for i in range(1200):
        for c in components:
            t=i*20+delays[c].randint(0,40); u=loss[c].random()
            islost=cond['channel']=='iid05' and u<.05
            if cond['channel']=='burst05': islost=env[i]
            if islost: drops+=1
            elif t>=24000: pending+=1
            elif fault and 12000<=t<12200: recvr_drops+=1
            else: arrivals[c].append((t,i+1))
    for a in arrivals.values(): a.sort()
    phase=stream('read-phase',seed).randrange(5)
    assert phase==int(rec['read_phase_ms'])
    expected=defaultdict(int); ages=[]
    history=sources[(cond['alpha'],seed)]
    for t in range(4000+phase,24000,5):
        origins={}
        for c,a in arrivals.items():
            j=bisect.bisect_right(a,(t,10**6))-1
            if j<0: origin=0
            elif fault and cond['restart']=='clear' and t>=12000 and a[j][0]<12200: origin=0
            else: origin=a[j][1]
            origins[c]=origin
        ox,oy=(origins['x'],origins['y']) if mode=='R0' else (origins['object'],)*2
        online=not(fault and 12000<=t<12200)
        if not online or not ox or not oy:
            expected['unavailable']+=1
            expected['unavailable_downtime' if not online else 'unavailable_missing']+=1
        elif ox==oy:
            expected['coherent']+=1
            age=t-(ox-1)*20; ages.append(age)
            expected['fresh_coherent' if age<=100 else 'stale_coherent']+=1
        else:
            expected['mixed']+=1
            expected['detected_mixed' if history[ox-1]!=history[oy-1] else 'hidden_mixed']+=1
    for k in ('coherent','mixed','unavailable','unavailable_downtime','unavailable_missing','fresh_coherent','stale_coherent','detected_mixed','hidden_mixed'):
        assert expected[k]==int(rec[k]),(rec['condition'],seed,mode,k,expected[k],rec[k])
    assert drops==int(rec['channel_lost']) and recvr_drops==int(rec['receiver_dropped']) and pending==int(rec['pending_at_end'])
    if ages:
        close(sum(ages)/len(ages),rec['coherent_age_mean_ms'],'age mean')
        close(percentile(ages,.95),rec['coherent_age_p95_ms'],'conditional p95')
    comparisons+=1

group=defaultdict(list)
for r in records: group[r['condition'],r['publication']].append(r)
mean_checks=bootstrap_checks=0
selected=('mixed_share','complete_share','V_coverage','fresh_coherent_availability','coherent_age_p95_ms','detection_prediction_residual')
for a in agg:
    vals=[float(r[a['metric']]) for r in group[a['condition'],a['publication']] if r[a['metric']]!='']
    assert len(vals)==int(a['defined_runs'])
    if not vals:
        assert a['mean']==a['ci95_low']==a['ci95_high']==''; continue
    mean=sum(vals)/len(vals); close(mean,a['mean'],'aggregate mean'); mean_checks+=1
    if a['metric'] in selected:
        if min(vals)==max(vals): lo=hi=mean
        else:
            r=stream('bootstrap',(a['condition'],a['publication'],a['metric']))
            boot=[sum(vals[r.randrange(len(vals))] for _ in vals)/len(vals) for _ in range(2000)]
            lo,hi=percentile(boot,.025),percentile(boot,.975)
        close(lo,a['ci95_low'],'bootstrap lo'); close(hi,a['ci95_high'],'bootstrap hi'); bootstrap_checks+=1

paired_checks=0
for p in paired:
    aa={int(r['seed']):r for r in group[p['condition'],'R0']}
    bb={int(r['seed']):r for r in group[p['condition'],'R1']}
    v=[float(aa[s][p['metric']])-float(bb[s][p['metric']]) for s in sorted(aa)]
    close(sum(v)/len(v),p['mean'],'paired mean')
    assert float(p['min_pair'])==min(v) and float(p['max_pair'])==max(v)
    if min(v)==max(v): lo=hi=v[0]
    else:
        r=stream('bootstrap',('paired',p['condition'],p['metric']))
        boot=[sum(v[r.randrange(len(v))] for _ in v)/len(v) for _ in range(2000)]
        lo,hi=percentile(boot,.025),percentile(boot,.975)
    close(lo,p['ci95_low'],'paired ci lo'); close(hi,p['ci95_high'],'paired ci hi'); paired_checks+=1

report={'status':'PASS','source_histories_verified':len(sources),'independent_bisect_timeline_mode_runs':comparisons,
        'read_states_independently_reconstructed':comparisons*4000,'aggregate_means_checked':mean_checks,
        'selected_whole_run_bootstrap_intervals_checked':bootstrap_checks,'paired_contrast_intervals_checked':paired_checks,
        'material_reporting_requirement':'Forty independent seed replicates within each condition;480condition-specificpairs are coupled acrossconditions by common random numbers. Do not call all480pairs mutually independent.',
        'other_required_qualifications':['Raw channel loss fraction uses24s attempted-message denominator; state shares use20s/4000readslots.',
        'Conditional age p95 aggregate is mean of run-level p95s, not pooled p95.',
        'R0 andR1 message units and iid loss realizations differ; not byte-normalized or equal realized loss.',
        'Bootstrap intervals describe simulation variation, not unmeasured equipment or model validity.']}
(HERE/'INDEPENDENT_CHECKS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
