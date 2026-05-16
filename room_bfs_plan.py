"""Room-graph BFS spanning tree (same ordering as the centralized planner demo)."""

from __future__ import annotations

from collections import deque


def rooms_root_to_u(parent: dict[int, int | None], root: int, u: int) -> list[int]:
    """Rooms on the unique tree path root → ``u`` (inclusive), root-first order."""
    seq: list[int] = []
    cur = u
    while True:
        seq.append(cur)
        if cur == root:
            break
        nxt = parent[cur]
        assert nxt is not None
        cur = nxt
    seq.reverse()
    return seq


def bfs_plan(
    adjacency: dict[int, tuple[int, ...]], root: int
) -> tuple[dict[int, int | None], list[tuple[int, int]], list[list[int]]]:
    """Breadth-first spanning tree over the floorplan room adjacency graph."""
    parent: dict[int, int | None] = {root: None}
    edges: list[tuple[int, int]] = []
    queue_snapshots: list[list[int]] = []
    q: deque[int] = deque([root])
    while q:
        u = q.popleft()
        for v in sorted(adjacency[u]):
            if v not in parent:
                parent[v] = u
                edges.append((u, v))
                q.append(v)
                queue_snapshots.append(list(q))
    return parent, edges, queue_snapshots
