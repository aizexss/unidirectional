"""Finite checks of the equality-evidence criterion on constant-valued fields.
No hardware or probability model. Standard-library Python3.
"""
from pathlib import Path
from itertools import combinations
import csv,json,hashlib

HERE=Path(__file__).parent/'graph_validation'
HERE.mkdir(exist_ok=True)

def partitions(n):
    def visit(a):
        if len(a)==n:
            yield tuple(a); return
        for x in range(max(a)+2): yield from visit(a+[x])
    yield from visit([0])

rows=[]; inequalities=[]
for n in range(2,6):
    pairs=list(combinations(range(n),2)); parts=list(partitions(n))
    connected=disconnected=checks=0; min_certificate=None
    for mask in range(1<<len(pairs)):
        edges=[pair for j,pair in enumerate(pairs) if mask>>j&1]
        parent=list(range(n))
        def find(x):
            while x!=parent[x]: x=parent[x]
            return x
        for a,b in edges:
            ra,rb=find(a),find(b)
            parent[ra]=rb
        components=len({find(i) for i in range(n)})
        witnesses=[]
        for part in parts:
            checks+=1
            if all(part[a]==part[b] for a,b in edges): witnesses.append(part)
        can_same=any(len(set(p))==1 for p in witnesses)
        can_differ=any(len(set(p))>1 for p in witnesses)
        assert can_same
        assert (not can_differ)==(components==1)
        if components==1:
            connected+=1
            min_certificate=len(edges) if min_certificate is None else min(min_certificate,len(edges))
        else: disconnected+=1
        for a,b in pairs:
            feasible=[p for p in witnesses if p[a]!=p[b]]
            assert bool(feasible)==(find(a)!=find(b))
            if feasible: assert all(len(set(p))>1 for p in feasible)
    assert min_certificate==n-1
    rows.append({'fields':n,'partitions':len(parts),'equality_graphs':1<<len(pairs),
                 'connected_graphs':connected,'ambiguous_graphs':disconnected,
                 'minimum_equality_edges_for_coherence':min_certificate,'partition_checks':checks})

with (HERE/'equality_graph_checks.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
report={'study':'Exact graph/partition enumeration; all field values equal; unrestricted origin identities',
        'rows':rows,'equality_graphs_checked':sum(r['equality_graphs'] for r in rows),
        'partition_checks':sum(r['partition_checks'] for r in rows),'assertions_passed':True,
        'interpretation':'Logical evidence criterion, not a communication or cryptographic lower bound.'}
(HERE/'graph_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
