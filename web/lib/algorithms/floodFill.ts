export function labelRegions(
  wallGrid: Uint8Array,
  rows: number,
  cols: number,
): { labels: Int16Array; count: number } {
  const labels = new Int16Array(rows * cols);
  labels.fill(-1);
  let nextId = 0;

  for (let i = 0; i < rows * cols; i++) {
    if (wallGrid[i] === 1) continue;
    if (labels[i] !== -1) continue;

    const id = nextId++;
    const stack: number[] = [i];
    labels[i] = id;

    while (stack.length > 0) {
      const idx = stack.pop()!;
      const r = (idx / cols) | 0;
      const c = idx - r * cols;

      const neighbors = [
        [r - 1, c],
        [r + 1, c],
        [r, c - 1],
        [r, c + 1],
      ];
      for (const [nr, nc] of neighbors) {
        if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) continue;
        const nIdx = nr * cols + nc;
        if (wallGrid[nIdx] === 1) continue;
        if (labels[nIdx] !== -1) continue;
        labels[nIdx] = id;
        stack.push(nIdx);
      }
    }
  }
  return { labels, count: nextId };
}
