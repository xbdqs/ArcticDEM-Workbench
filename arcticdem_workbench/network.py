from __future__ import annotations
from collections import deque
from itertools import combinations
import numpy as np

def candidate_edges(n, mode='sparse'):
    if n < 2:
        raise ValueError("At least two epochs are needed.")
    if mode == 'all':
        return list(combinations(range(n),2))
    if mode == 'chain':
        return [(i,i+1) for i in range(n-1)]
    if mode != 'sparse':
        raise ValueError("Network must be sparse, all or chain.")
    # Neighbours + two-step neighbours + a reference star; triangles retain redundancy.
    return sorted(set([(i,i+1) for i in range(n-1)] + [(i,i+2) for i in range(n-2)] + [(0,j) for j in range(1,n)]))

def vector(edge):
    return np.array([edge['sampling_dx_m'],edge['sampling_dy_m'],edge['add_dz_m']],dtype=float)

def _cycle_row(nodes, closure, kind):
    return {"cycle": '-'.join(map(str,nodes)), "kind": kind,
            "closure_dx_m": float(closure[0]), "closure_dy_m": float(closure[1]),
            "closure_dz_m": float(closure[2]), "closure_norm_m": float(np.linalg.norm(closure)),
            "interpretation": "pre-adjustment internal consistency; not an accuracy or significance test"}

def solve_network(n, edges):
    """Equal-edge-weight translation graph adjustment; epoch 0 fixes the arbitrary gauge.

    Edge translations are independently fitted before this function. No cycle statistic
    is constructed from differences of the final common stack.
    """
    if not edges:
        raise ValueError("No accepted registration edges.")
    adjacency = {i:[] for i in range(n)}
    pairs = {}
    for e in edges:
        i,j = int(e['i']),int(e['j'])
        if i >= j or not 0 <= i < j < n or (i,j) in pairs:
            raise ValueError("Network edges must be unique and oriented from smaller to larger index.")
        pairs[i,j] = vector(e)
        adjacency[i].append(j); adjacency[j].append(i)
    visited={0}; queue=deque([0]); parent={0:None}; tree=set()
    while queue:
        i=queue.popleft()
        for j in adjacency[i]:
            if j not in visited:
                visited.add(j);parent[j]=i;tree.add(tuple(sorted((i,j))));queue.append(j)
    if len(visited) != n:
        raise ValueError(f"Registration network disconnected. Unconnected epoch indices: {sorted(set(range(n))-visited)}. Inspect failed edges or reduce selected epochs.")
    def signed(i,j):
        return pairs[i,j] if i<j else -pairs[j,i]
    cycles=[]
    for i,j,k in combinations(range(n),3):
        if (i,j) in pairs and (j,k) in pairs and (i,k) in pairs:
            cycles.append(_cycle_row([i,j,k,i],pairs[i,j]+pairs[j,k]-pairs[i,k],"triangle"))
    # A full independent fundamental-cycle basis also covers graphs without triangles.
    basis=[]
    for i,j in pairs:
        if (i,j) in tree:
            continue
        tree_adj={k:[] for k in range(n)}
        for a,b in tree:
            tree_adj[a].append(b);tree_adj[b].append(a)
        q=deque([j]); prev={j:None}
        while q:
            a=q.popleft()
            if a==i:break
            for b in tree_adj[a]:
                if b not in prev:prev[b]=a;q.append(b)
        path=[i]
        while path[-1]!=j:path.append(prev[path[-1]])
        path=list(reversed(path))
        closure=signed(i,j).copy()
        for a,b in zip(path[:-1],path[1:]):closure+=signed(a,b)
        basis.append(_cycle_row([i]+path,closure,"fundamental"))
    A=np.zeros((len(edges),n-1)); observed=np.vstack([vector(e) for e in edges])
    for row,e in enumerate(edges):
        if e['i']>0:A[row,e['i']-1]=-1
        if e['j']>0:A[row,e['j']-1]=1
    fitted=np.linalg.lstsq(A,observed,rcond=None)[0]
    offsets=np.vstack([np.zeros(3),fitted])
    residual=A@fitted-observed
    diagnostics=[]
    for e,r in zip(edges,residual):
        diagnostics.append({"i":e['i'],"j":e['j'],"residual_dx_m":float(r[0]),"residual_dy_m":float(r[1]),"residual_dz_m":float(r[2]),"residual_norm_m":float(np.linalg.norm(r))})
    return {"offsets":offsets.tolist(),"triangles":cycles,"cycle_basis":basis,"edge_residuals":diagnostics,
            "cycle_rank":len(edges)-n+1,"anchor_epoch":0,"weighting":"equal per accepted edge; no calibrated covariance model",
            "limitations":["Node-consistent biases and common-mode errors can close perfectly.",
                           "A bad loop does not uniquely identify its bad edge.",
                           "Shared DEMs correlate edge errors; network residuals are not independent accuracy estimates.",
                           "Tree edges without redundant cycles cannot be checked by closure.",
                           "Post-adjustment closure follows from the model and is not validation."]}
