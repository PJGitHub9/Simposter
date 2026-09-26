// Shared "ignore leading article" title-sort helper (GitHub issue #70) --
// sorting by title previously used the raw title everywhere (title.localeCompare()),
// so "The Matrix" sorted under T instead of M, "A Bug's Life" under A instead of B,
// etc. Every library-browsing/batch view (Movies, TV Shows, Logos, Backdrops,
// Square Art, Batch Edit x2, BatchEditModal) had its own independent copy of
// this same comparator with no shared helper to fix once -- this file exists
// specifically so a future title-sort tweak doesn't need to be repeated in
// 8 separate places again.

const LEADING_ARTICLE_RE = /^(the|an?)\s+/i

// Strips a single leading "The"/"A"/"An" (case-insensitive) before sorting,
// matching the convention Plex/Kodi/iTunes/etc. all already use for library
// sorting. Only the FIRST word is ever stripped -- "A Man Called Otto" sorts
// under "Man...", but "The Man in the High Castle" also sorts under "Man...",
// not "Man in the High Castle" (the article is dropped, the rest is untouched).
export function sortableTitle(title: string | null | undefined): string {
  if (!title) return ''
  return title.replace(LEADING_ARTICLE_RE, '').trim()
}

// Ascending comparator (a-z) using the article-stripped title. For a
// descending sort, callers already just negate the result or swap the
// argument order (matching how every existing call site already handles
// asc/desc) -- no separate "compareTitlesDesc" needed.
export function compareTitles(a: string | null | undefined, b: string | null | undefined): number {
  return sortableTitle(a).localeCompare(sortableTitle(b))
}
