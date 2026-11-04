/** Client-side text A/B compare (WER/CER + word alignment for Inspector). */

export type DiffOp = "equal" | "replace" | "delete" | "insert";

export type DiffSpan = {
  op: DiffOp;
  text: string;
};

export type EditCounts = {
  substitutions: number;
  deletions: number;
  insertions: number;
  hits: number;
  referenceLen: number;
};

export type TextAlignResult = {
  spansA: DiffSpan[];
  spansB: DiffSpan[];
  counts: EditCounts;
  wer: number;
  cer: number;
  werPercent: number;
  cerPercent: number;
  referenceNormalized: string;
  hypothesisNormalized: string;
};

type Token = {
  display: string;
  key: string;
};

/** Light ASR-eval normalization (mirrors executor text_metrics.normalize_text). */
export function normalizeText(text: string, enabled = true): string {
  const value = String(text ?? "");
  if (!enabled) {
    return value.trim().split(/\s+/).filter(Boolean).join(" ");
  }
  return value
    .toLowerCase()
    .replace(/[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenizeForAlign(text: string): Token[] {
  return String(text ?? "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((display) => ({
      display,
      key: normalizeText(display),
    }))
    .filter((tok) => tok.key.length > 0 || tok.display.length > 0);
}

function tokenizeWords(normalized: string): string[] {
  return normalized.split(" ").filter(Boolean);
}

function tokenizeChars(normalized: string): string[] {
  return [...normalized].filter((ch) => !/\s/.test(ch));
}

type BackOp = "H" | "S" | "D" | "I" | "";

function levenshteinBacktrace(reference: string[], hypothesis: string[]): {
  counts: EditCounts;
  ops: Array<{ op: BackOp; ref?: string; hyp?: string }>;
} {
  const n = reference.length;
  const m = hypothesis.length;
  const cost: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  const back: BackOp[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(""));
  for (let j = 1; j <= m; j++) {
    cost[0][j] = j;
    back[0][j] = "I";
  }
  for (let i = 1; i <= n; i++) {
    cost[i][0] = i;
    back[i][0] = "D";
    for (let j = 1; j <= m; j++) {
      if (reference[i - 1] === hypothesis[j - 1]) {
        cost[i][j] = cost[i - 1][j - 1];
        back[i][j] = "H";
      } else {
        const sub = cost[i - 1][j - 1] + 1;
        const del = cost[i - 1][j] + 1;
        const ins = cost[i][j - 1] + 1;
        const best = Math.min(sub, del, ins);
        cost[i][j] = best;
        if (best === sub) back[i][j] = "S";
        else if (best === del) back[i][j] = "D";
        else back[i][j] = "I";
      }
    }
  }

  let i = n;
  let j = m;
  let substitutions = 0;
  let deletions = 0;
  let insertions = 0;
  let hits = 0;
  const opsRev: Array<{ op: BackOp; ref?: string; hyp?: string }> = [];
  while (i > 0 || j > 0) {
    const op = back[i][j];
    if (op === "H") {
      hits += 1;
      opsRev.push({ op, ref: reference[i - 1], hyp: hypothesis[j - 1] });
      i -= 1;
      j -= 1;
    } else if (op === "S") {
      substitutions += 1;
      opsRev.push({ op, ref: reference[i - 1], hyp: hypothesis[j - 1] });
      i -= 1;
      j -= 1;
    } else if (op === "D") {
      deletions += 1;
      opsRev.push({ op, ref: reference[i - 1] });
      i -= 1;
    } else if (op === "I") {
      insertions += 1;
      opsRev.push({ op, hyp: hypothesis[j - 1] });
      j -= 1;
    } else {
      break;
    }
  }

  return {
    counts: {
      substitutions,
      deletions,
      insertions,
      hits,
      referenceLen: n,
    },
    ops: opsRev.reverse(),
  };
}

function rateFromCounts(counts: EditCounts): number {
  if (counts.referenceLen <= 0) {
    const errors = counts.substitutions + counts.deletions + counts.insertions;
    return errors === 0 ? 0 : 1;
  }
  return (counts.substitutions + counts.deletions + counts.insertions) / counts.referenceLen;
}

/**
 * Align original strings with WER-style word edits.
 * A is treated as reference, B as hypothesis (swap call sites to invert).
 */
export function alignTextDiff(reference: string, hypothesis: string): TextAlignResult {
  const refTokens = tokenizeForAlign(reference);
  const hypTokens = tokenizeForAlign(hypothesis);
  const { counts, ops } = levenshteinBacktrace(
    refTokens.map((t) => t.key || t.display.toLowerCase()),
    hypTokens.map((t) => t.key || t.display.toLowerCase()),
  );

  const spansA: DiffSpan[] = [];
  const spansB: DiffSpan[] = [];
  let ri = 0;
  let hi = 0;
  for (const step of ops) {
    if (step.op === "H") {
      spansA.push({ op: "equal", text: refTokens[ri]?.display ?? step.ref ?? "" });
      spansB.push({ op: "equal", text: hypTokens[hi]?.display ?? step.hyp ?? "" });
      ri += 1;
      hi += 1;
    } else if (step.op === "S") {
      spansA.push({ op: "replace", text: refTokens[ri]?.display ?? step.ref ?? "" });
      spansB.push({ op: "replace", text: hypTokens[hi]?.display ?? step.hyp ?? "" });
      ri += 1;
      hi += 1;
    } else if (step.op === "D") {
      spansA.push({ op: "delete", text: refTokens[ri]?.display ?? step.ref ?? "" });
      ri += 1;
    } else if (step.op === "I") {
      spansB.push({ op: "insert", text: hypTokens[hi]?.display ?? step.hyp ?? "" });
      hi += 1;
    }
  }

  const refN = normalizeText(reference);
  const hypN = normalizeText(hypothesis);
  const cerCounts = levenshteinBacktrace(tokenizeChars(refN), tokenizeChars(hypN)).counts;
  const wer = rateFromCounts(counts);
  const cer = rateFromCounts(cerCounts);

  return {
    spansA,
    spansB,
    counts,
    wer,
    cer,
    werPercent: Math.round(wer * 10000) / 100,
    cerPercent: Math.round(cer * 10000) / 100,
    referenceNormalized: refN,
    hypothesisNormalized: hypN,
  };
}

export function computeWerPercent(reference: string, hypothesis: string): number {
  const refN = normalizeText(reference);
  const hypN = normalizeText(hypothesis);
  const counts = levenshteinBacktrace(tokenizeWords(refN), tokenizeWords(hypN)).counts;
  return Math.round(rateFromCounts(counts) * 10000) / 100;
}
