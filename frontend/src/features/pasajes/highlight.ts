/**
 * Finds a chunk's text inside a rendered document and highlights it (CSS Custom Highlight API: nothing in
 * the DOM changes, and the highlight can span paragraphs, lists, bold text…).
 *
 * The backend rebuilds a document by joining its chunks and trimming the overlap between them, and the
 * Markdown is then rendered, so the chunk text is never guaranteed to appear verbatim. Matching therefore
 * ignores case, accents, whitespace and punctuation (only letters and digits are compared) and, when the
 * whole chunk isn't found, aligns several short probes taken from it and highlights the span they cover.
 */
export const HIGHLIGHT_NAME = "chunk-hl";

const KEEP = /[\p{L}\p{N}]/u;
const base = (ch: string) => ch.normalize("NFD")[0].toLowerCase()[0];

/** letters/digits only, lowercase, accents stripped */
export const normalizeText = (s: string) => {
  let out = "";
  for (const ch of s) if (KEEP.test(ch)) out += base(ch);
  return out;
};

const PROBE = 30;
const STEP = 15;
const MAX_MATCHES = 30;

/** Every index where `needle` occurs in `haystack` (capped). */
function allIndexes(haystack: string, needle: string): number[] {
  const out: number[] = [];
  for (let i = haystack.indexOf(needle); i >= 0 && out.length < MAX_MATCHES; i = haystack.indexOf(needle, i + 1)) out.push(i);
  return out;
}

/**
 * Range of `root`'s text that corresponds to `chunkText`, or null if it can't be located.
 * `hint` (0..1) is the chunk's expected relative position in the document (e.g. chunk 6 of 31): when the
 * same passage appears more than once (articles often repeat a paragraph), the occurrence closest to it is used.
 * `occurrences` is how many equally good places there were.
 */
export function locateChunk(
  root: HTMLElement,
  chunkText: string,
  hint?: number
): { range: Range; occurrences: number } | null {
  const needle = normalizeText(chunkText);
  if (needle.length < 20) return null;

  // Normalised text of the whole document, remembering the DOM position of every kept character.
  const nodes: Text[] = [];
  const nodeIdx: number[] = [];
  const nodeOff: number[] = [];
  const chars: string[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n as Text;
    const idx = nodes.push(t) - 1;
    for (let i = 0; i < t.data.length; i++) {
      if (KEEP.test(t.data[i])) {
        chars.push(base(t.data[i]));
        nodeIdx.push(idx);
        nodeOff.push(i);
      }
    }
  }
  const doc = chars.join("");
  const target = (hint ?? 0) * doc.length;
  const closest = (starts: number[]) => starts.reduce((a, b) => (Math.abs(b - target) < Math.abs(a - target) ? b : a));

  let start: number;
  let end: number;
  let occurrences = 1;
  const whole = allIndexes(doc, needle);
  if (whole.length) {
    start = closest(whole);
    end = start + needle.length;
    occurrences = whole.length;
  } else {
    // Probes taken along the chunk; each place where one occurs implies an alignment (doc position - chunk offset).
    const hits: { pos: number; diff: number }[] = [];
    for (let off = 0; off + PROBE <= needle.length; off += STEP) {
      for (const pos of allIndexes(doc, needle.slice(off, off + PROBE))) hits.push({ pos, diff: pos - off });
    }
    if (!hits.length) return null;
    // Cluster probes that agree on the alignment; the biggest cluster(s) are where the chunk is.
    hits.sort((a, b) => a.diff - b.diff);
    const clusters: (typeof hits)[] = [];
    for (const h of hits) {
      const last = clusters[clusters.length - 1];
      if (last && h.diff - last[last.length - 1].diff <= 12) last.push(h);
      else clusters.push([h]);
    }
    const biggest = Math.max(...clusters.map((c) => c.length));
    if (biggest < 2 && needle.length > 4 * PROBE) return null;
    const good = clusters.filter((c) => c.length >= Math.max(2, Math.ceil(biggest * 0.7)) || c.length === biggest);
    const startOf = (c: typeof hits) => Math.min(...c.map((h) => h.pos));
    const chosen = good.find((c) => startOf(c) === closest(good.map(startOf)))!;
    start = startOf(chosen);
    end = Math.max(...chosen.map((h) => h.pos + PROBE));
    occurrences = good.length;
    // The probes cover the chunk only up to their granularity: grow the span while document and chunk keep agreeing.
    const first = chosen.find((h) => h.pos === start)!;
    const last = chosen.find((h) => h.pos + PROBE === end)!;
    for (let o = start - first.diff; start > 0 && o > 0 && doc[start - 1] === needle[o - 1]; o--) start--;
    for (let o = end - last.diff; end < doc.length && o < needle.length && doc[end] === needle[o]; o++) end++;
  }

  const range = document.createRange();
  range.setStart(nodes[nodeIdx[start]], nodeOff[start]);
  range.setEnd(nodes[nodeIdx[end - 1]], nodeOff[end - 1] + 1);
  return { range, occurrences };
}

export const supportsHighlight = () => typeof CSS !== "undefined" && "highlights" in CSS;

export function setHighlight(range: Range) {
  const H = (window as unknown as { Highlight: new (r: Range) => unknown }).Highlight;
  (CSS as unknown as { highlights: Map<string, unknown> }).highlights.set(HIGHLIGHT_NAME, new H(range));
}

export function clearHighlight() {
  if (supportsHighlight()) (CSS as unknown as { highlights: Map<string, unknown> }).highlights.delete(HIGHLIGHT_NAME);
}

/** Scrolls the (nearest scrollable ancestor of the) range into view, centred. */
export function scrollToRange(range: Range) {
  const el = range.startContainer.parentElement;
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
}
