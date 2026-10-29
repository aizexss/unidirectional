"""Independent finite checks of the extended theory. Standard library only."""
from pathlib import Path
from itertools import product,combinations
from fractions import Fraction
from math import comb
import json,csv

HERE=Path(__file__).parent

def partitions(n):
    def rec(a):
        if len(a)==n:
            yield tuple(a); return
        for x in range(max(a)+2):
            yield from rec(a+[x])
    yield from rec([0])

def components(d,eq):
    parent=list(range(d))
    def find(x):
        while parent[x]!=x:
            x=parent[x]
        return x
    for a,b in eq: parent[find(a)]=find(b)
    return [find(x) for x in range(d)]

def graph_rule(values,eq,neq):
    roots=components(len(values),eq)
    if any(roots[a]==roots[b] and values[a]!=values[b]
           for a,b in combinations(range(len(values)),2)):
        return 'out_of_model'
    if any(roots[a]==roots[b] for a,b in neq): return 'out_of_model'
    if len(set(roots))==1: return 'coherent'
    if len(set(values))==1 and not neq: return 'ambiguous'
    return 'mixed'

def partition_oracle(values,eq,neq):
    possible=set()
    for part in partitions(len(values)):
        if any(part[a]!=part[b] for a,b in eq): continue
        if any(part[a]==part[b] for a,b in neq): continue
        if any(part[a]==part[b] and values[a]!=values[b]
               for a,b in combinations(range(len(values)),2)): continue
        possible.add('coherent' if len(set(part))==1 else 'mixed')
    return ('out_of_model' if not possible else
            'ambiguous' if len(possible)==2 else next(iter(possible)))

graph_rows=[]
for d in (2,3,4):
    edges=list(combinations(range(d),2))
    checked=0
    for mask in range(1<<len(edges)):
        eq=[e for i,e in enumerate(edges) if mask>>i&1]
        for values in product((0,1),repeat=d):
            for neqmask in range(1<<len(edges)):
                neq=[e for i,e in enumerate(edges) if neqmask>>i&1]
                a=graph_rule(values,eq,neq); b=partition_oracle(values,eq,neq)
                assert a==b,(d,values,eq,neq,a,b)
                checked+=1
    graph_rows.append({'fields':d,'checked':checked,'disagreements':0,
                       'difference_edges_tested':'every subset, including conflicts with equality edges'})

count_rows=[]
for m in range(2,6):
    for q in range(1,5):
        n=complete=coherent=mixed=unavailable=detected=hidden=0
        for hist in product(range(q),repeat=m):
            for ox,oy in product(range(m+1),repeat=2):
                n+=1
                if ox==0 or oy==0: unavailable+=1; continue
                complete+=1
                if ox==oy: coherent+=1; continue
                mixed+=1
                if hist[ox-1]!=hist[oy-1]: detected+=1
                else: hidden+=1
        actual=[n,complete,coherent,mixed,unavailable,detected,hidden]
        expected=[q**m*(m+1)**2,q**m*m*m,q**m*m,q**m*m*(m-1),
                  q**m*(2*m+1),q**(m-1)*(q-1)*m*(m-1),q**(m-1)*m*(m-1)]
        assert actual==expected,(m,q,actual,expected)
        count_rows.append({'m':m,'q':q,'configurations':n,'complete':complete,
                           'coherent':coherent,'mixed':mixed,'unavailable':unavailable,
                           'detected':detected,'hidden':hidden,'all_formulas_agree':1})

collision_checks=0
for q in range(1,5):
    for r in range(2,6):
        detected=sum(len(set(vs))>1 for vs in product(range(q),repeat=r))
        assert Fraction(detected,q**r)==1-Fraction(1,q**(r-1))
        collision_checks+=1

markov_rows=[]
for alpha in (Fraction(0),Fraction(1,20),Fraction(1,2),Fraction(19,20),Fraction(1)):
    for k in range(13):
        # A different derivation: odd numbers of independent flips.
        odd=sum((Fraction(comb(k,t))*alpha**t*(1-alpha)**(k-t)
                 for t in range(1,k+1,2)),Fraction(0))
        closed=(1-(1-2*alpha)**k)/2
        assert odd==closed,(alpha,k,odd,closed)
        markov_rows.append({'alpha':str(alpha),'lag':k,'odd_flip_probability':str(odd),
                            'closed_form_probability':str(closed),'agrees':1})

for name,rows in [('graph_checks.csv',graph_rows),('finite_count_checks.csv',count_rows),('markov_checks.csv',markov_rows)]:
    with (HERE/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
result={'graph_checks':sum(r['checked'] for r in graph_rows),'graph_disagreements':0,
        'finite_count_parameter_cells':len(count_rows),'finite_count_configurations':sum(r['configurations'] for r in count_rows),
        'finite_count_disagreements':0,'uniform_collision_parameter_cells':collision_checks,
        'markov_exact_rational_checks':len(markov_rows),'all_checks_pass':True,
        'scope':'Finite diagnostic checks and exact algebra, not independent hardware experiments.'}
(HERE/'theory_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
