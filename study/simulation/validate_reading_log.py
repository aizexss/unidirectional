"""Independent streamed reconstruction of every recorded evaluation read.

Does not import the simulator or use its monitor implementation.
"""
from pathlib import Path
from collections import Counter,defaultdict
import csv,gzip,json,math

HERE=Path(__file__).parent
cfg=json.loads((HERE/'results.json').read_text())
alpha={c['id']:c['alpha'] for c in cfg['conditions']}
histories={(float(r['alpha']),int(r['seed'])):r['history'] for r in csv.DictReader((HERE/'source_histories.csv').open())}
expected={(r['condition'],int(r['seed']),r['publication']):r for r in csv.DictReader((HERE/'run_metrics.csv').open())}
expected_lag={(r['condition'],int(r['seed']),r['publication'],int(r['lag'])):(int(r['mixed_slots']),int(r['detected_slots'])) for r in csv.DictReader((HERE/'lag_counts_per_run.csv').open())}
active_key=None
counter=Counter()
ages=[]
lags=defaultdict(lambda:[0,0])
total_readings=total_runs=0

def pct(values,q):
    values=sorted(values)
    i=(len(values)-1)*q
    lo,hi=int(math.floor(i)),int(math.ceil(i))
    return values[lo]+(i-lo)*(values[hi]-values[lo])

def finish(key,c,ages,lags):
    global total_runs
    if key is None: return
    record=expected[key]
    for name in ('slots','coherent','mixed','unavailable','unavailable_downtime','unavailable_missing','detected_mixed','hidden_mixed','naive_false_coherent','fresh_coherent','stale_coherent'):
        assert int(record[name])==c[name],(key,name,record[name],c[name])
    assert int(record['I_conclusive'])==c['coherent']+c['mixed']
    assert int(record['V_conclusive'])==c['detected_mixed']
    assert int(record['G_conclusive'])==(c['coherent'] if key[2]=='R1' else c['detected_mixed'])
    if ages:
        assert abs(float(record['coherent_age_mean_ms'])-sum(ages)/len(ages))<1e-9
        assert abs(float(record['coherent_age_p95_ms'])-pct(ages,.95))<1e-9
    expected_detection=0.0
    for lag,counts in lags.items():
        assert tuple(counts)==expected_lag[key+(lag,)],(key,lag)
        # Independently iterate the two-state transition recurrence.
        probability=0.0
        for _ in range(lag): probability=alpha[key[0]]+(1-2*alpha[key[0]])*probability
        expected_detection+=counts[0]*probability
    assert abs(float(record['predicted_detected_mixed'])-expected_detection)<1e-7
    total_runs+=1

with gzip.open(HERE/'readings.csv.gz','rt',encoding='utf-8',newline='') as f:
    for r in csv.DictReader(f):
        key=(r['condition'],int(r['seed']),r['publication'])
        if key!=active_key:
            finish(active_key,counter,ages,lags)
            active_key=key; counter=Counter(); ages=[]; lags=defaultdict(lambda:[0,0])
        t,online,ox,oy=map(int,(r['read_time_ms'],r['online'],r['x_origin'],r['y_origin']))
        counter['slots']+=1; total_readings+=1
        if not online or ox==0 or oy==0:
            counter['unavailable']+=1
            counter['unavailable_downtime' if not online else 'unavailable_missing']+=1
            continue
        source=histories[alpha[key[0]],key[1]]
        x,y=int(source[ox-1]),int(source[oy-1])
        if ox==oy:
            assert x==y
            counter['coherent']+=1
            age=t-(ox-1)*cfg['generation_period_ms']
            assert age>=0
            ages.append(age)
            counter['fresh_coherent' if age<=cfg['freshness_threshold_ms'] else 'stale_coherent']+=1
        else:
            assert key[2]=='R0'
            counter['mixed']+=1
            detected=x!=y
            counter['detected_mixed' if detected else 'hidden_mixed']+=1
            counter['naive_false_coherent']+=not detected
            lags[abs(ox-oy)][0]+=1
            lags[abs(ox-oy)][1]+=detected
finish(active_key,counter,ages,lags)
assert total_readings==cfg['total_evaluation_readings'] and total_runs==cfg['total_mode_runs']
report=dict(status='PASS',method='Independent streamed reconstruction without importing simulator',
            readings_verified=total_readings,mode_runs_verified=total_runs,
            checked=['reference counts','availability reasons','values-only detection and hidden mixing',
                     'naive false coherence','V/I/G conclusive coverage','fresh/coherent state availability',
                     'conditional coherent mean and p95 age','per-run lag counts','Markov lag prediction via recurrence'])
(HERE/'INDEPENDENT_REANALYSIS.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
