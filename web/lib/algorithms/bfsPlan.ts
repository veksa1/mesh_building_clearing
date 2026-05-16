export interface BfsPlanResult {
  parent: Map<number, number | null>;
  edges: [number, number][];
  queueSnapshots: number[][];
}

export function bfsPlan(adjacency: Map<number, number[]>, root: number): BfsPlanResult {
  const parent = new Map<number, number | null>();
  parent.set(root, null);
  const edges: [number, number][] = [];
  const queueSnapshots: number[][] = [];
  const q: number[] = [root];
  let head = 0;

  while (head < q.length) {
    const u = q[head++];
    const neighbors = (adjacency.get(u) ?? []).slice().sort((a, b) => a - b);
    for (const v of neighbors) {
      if (!parent.has(v)) {
        parent.set(v, u);
        edges.push([u, v]);
        q.push(v);
        queueSnapshots.push(q.slice(head));
      }
    }
  }
  return { parent, edges, queueSnapshots };
}
