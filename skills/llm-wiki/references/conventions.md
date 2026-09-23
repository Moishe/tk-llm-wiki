# LLM-Wiki conventions & templates

The exact formats `SKILL.md` refers to. Keep `SKILL.md` lean; put format detail here.

## The three docs

| Doc | Title | Tags |
|---|---|---|
| Wiki | `📚 <Scope> — Wiki` | `llm-wiki`, `<scope name>`, `llm-wiki-page` |
| Index | `🗂 <Scope> — Wiki Index` | `llm-wiki`, `<scope name>`, `llm-wiki-index` |
| Log | `🪵 <Scope> — Wiki Log` | `llm-wiki`, `<scope name>`, `llm-wiki-log` |

All three are private (never added to any library). `<scope name>` is the library's exact display name, or for a collection the short name chosen at build (e.g. `My Notes (human-written)`). It is also the tag that scopes discovery to one wiki.

**Discovery filter:** TK's tag filter is **OR**, so query by the specific `<scope name>` tag, then keep only results that ALSO carry `llm-wiki` (both tags must be present — a bare `llm-wiki` match belongs to some other scope). The role tag (`llm-wiki-page|index|log`) then says which of the three each is.

## Wiki doc

Top-level `##` headings are the "pages". Each keeps the stable heading `id` TK assigns — so `replace_node_contents` can rewrite a section's body without changing its id (preserves anchors + the reader's collapse state).

Standing sections (adapt per domain):
- `## Overview` — what this library is about, at a glance.
- `## Synthesis` — the current evolving thesis across all sources.
- `## Entities` — people, works, places, products… `###` per entity (promote to `##` when large).
- `## Concepts` — recurring ideas/themes. `###` per concept.
- `## Explorations` — answers filed back from `query` (added over time).

Cross-references between wiki pages: write "see *<section title>*" (prose) — TK has no heading deep-links yet (TK-1829). Links to **sources** use the real TK URL and are clickable.

**Link everything linkable in the body.** As you read sources, keep an author → username map (from `author_username`). Then, on first mention per section:
- a person who is a TK user → `[Name](https://tk.xyz/@<username>)` (`/@<username>` on local);
- a source/document → `[Title](…/notes/<id>)`;
- a URL a source states verbatim → link it.
Never invent external URLs you don't have from a source (tool/product homepages). Example: a "Source: X" byline becomes `*Source: [X](…/notes/<id>) by [Name](https://tk.xyz/@<username>).*`

The taxonomy is domain-driven and co-evolves — refine it as the library's shape becomes clear, and note notable structure choices in the log.

## Index doc

The index is **also the processed-set** (the authoritative record of which sources have been ingested — see SKILL.md). Category sections:

For a **collection** scope, the index opens with a `## Scope` block holding the filter. Ingest re-applies this block verbatim, so edit it (not the scope name) to change what the wiki covers:

```
## Scope
- kind: collection
- description: all my notes that weren't created by the assistant or MCP
- filter: created_by_ai=false · created_after=2026-08-05 · tags_none=[llm-wiki] · title_excludes=[]
- resolved: <YYYY-MM-DD> · <N> matching docs
```

(A library scope needs no Scope block: `- kind: library · id: <uuid>` is enough.)


```
## Sources
- [<source title>](<tk-url>) — <one-line summary> · ingested @ <source updated_at ISO> · covered in: <wiki section(s)>

## Skipped (non-source)
- `<id>` <title> — <reason it carries no wiki content, e.g. empty / test noise / duplicate> · seen @ <source updated_at ISO>
  (standard reasons: `empty`, `template placeholders`, `test note`, `auto-assembled daily note`, `duplicate of <id>`, `looks AI-generated (pre-flag legacy)`)

## Entities
- **<entity name>** — <one-line> · sources: <n>

## Concepts
- **<concept>** — <one-line> · sources: <n>

## Explorations
- **<question>** — <one-line answer> · [<YYYY-MM-DD>]
```

`<tk-url>` is the source's real URL (`http://localhost:5173/notes/<id>` locally, the prod URL for `tk-remote`) — it carries the node id used for delta detection. **`ingested @ <updated_at>`** is the source's `updated_at` at ingest time; the next ingest compares it against the live value to detect edits. **`## Skipped (non-source)`** records docs deliberately examined and excluded so they aren't re-read unless edited (`seen @` works like `ingested @`) (a transient read *failure* is instead left unrecorded, so it retries automatically next run).

The index is read **first** on every `query`, so keep summaries tight and scannable. Maintain it with whole-body `update_document` (it is bulleted lists with no op to append a single item yet — TK-1831).

## Log doc

Append-only. Newest entries appended after the last one (`insert_sibling_node` after the final block). Prefix every entry:

```
## [YYYY-MM-DD] <op> | <detail>
```

`<op>` ∈ `build | ingest | query | lint`. Consistent prefix keeps it greppable. Worked examples:

```
## [2026-07-16] build | 15 sources compiled (trial: first 15 by added_at)
sections created: Overview, Synthesis, Entities (6), Concepts (4)

## [2026-07-17] ingest | "Why I Build My Own Cameras (2)"
touched: Concepts → Craft & Process; Entities → Susan Burnstine; index Sources entry added/refreshed

## [2026-07-17] query | how does the author relate process to meaning?
filed back: Explorations → "process vs meaning"

## [2026-07-18] lint | 1 orphan, 2 missing xrefs
applied: added 2 cross-references. proposed (awaiting user): merge "Alt Processes" into "Craft & Process"
```

The log is a human-readable timeline, **not** the ingest cursor — the index (Sources + Skipped) is the processed-set that delta detection diffs against. A log entry may mention a timestamp descriptively, but nothing reads it back as a watermark.

## MCP cheat-sheet

Base tool names (prefix `tk-remote` by default, `tk-local` for local testing):

| Need | Tool |
|---|---|
| Find the library | `get_user_libraries`, `search_libraries` |
| Enumerate sources (+ deltas) | library: `get_library_documents` (`since`, `sort_by`, `limit`, `offset`, `has_more`); collection: `get_recent_documents` (same paging; filter on `created_by_ai`, `created_at`, `tags`, `title`) |
| Rank sources by a topic | `search_library_documents` |
| Passage-level search (returns `node_id`) | `search_document_content` |
| Read a source | `get_document_content` (`format:"json"` to see node ids/structure) |
| A long source's outline | `get_document_hierarchy` |
| Find the skill's own docs | `search_documents` / `get_recent_documents` (tag filter) |
| Create wiki/index/log | `create_document` (title + tags; do NOT pass `library_id`) |
| Rewrite a section | `edit_document` → `replace_node_contents` (node_id = heading id) |
| Add a section/block / append log | `edit_document` → `insert_sibling_node` |
| Prune a stale section | `edit_document` → `delete_node` |
| Whole-body fallback | `update_document` |

Never call `add_document_to_library` (keeps the wiki private) and never edit a source document.
