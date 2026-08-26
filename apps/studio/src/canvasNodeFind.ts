export type CanvasFindHit = {
  id: string;
  name: string;
};

function scoreHit(hit: CanvasFindHit, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const name = hit.name.toLowerCase();
  const id = hit.id.toLowerCase();
  if (name === q || id === q) return 3;
  if (name.startsWith(q) || id.startsWith(q)) return 2;
  if (name.includes(q) || id.includes(q)) return 1;
  return -1;
}

/** Rank canvas nodes by visible name (type / group title) or id. Empty query keeps canvas order. */
export function rankCanvasFindHits(hits: CanvasFindHit[], query: string): CanvasFindHit[] {
  if (!query.trim()) return hits;
  return hits
    .map((hit, index) => ({ hit, index, score: scoreHit(hit, query) }))
    .filter((entry) => entry.score >= 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map((entry) => entry.hit);
}
