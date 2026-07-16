# LLM-Wiki skill — design

**Date:** 2026-07-16
**What:** A Claude Code skill that implements Karpathy's LLM-wiki pattern (gist: `442a6bf555914893e9891c11519de94f`) over a TK **library** as the raw-source repository. The LLM compiles and maintains a persistent, interlinked wiki *about* a library, kept current as sources change.
**Reference gist saved at:** `/tmp/llm-wiki.md` (Karpathy, verbatim).

## Karpathy's three layers → TK

| Karpathy | TK instantiation |
|---|---|
| **Raw sources** (immutable) | The documents in a TK **library**. Read-only; the skill never edits them. |
| **The wiki** (LLM-owned markdown) | **One TK document** — top-level headings are the "pages" (entities / concepts / overview / synthesis). Sections are the unit the LLM rewrites. |
| **The schema** (CLAUDE.md/AGENTS.md) | This skill's `SKILL.md` — encodes the ingest/query/lint workflows, doc-discovery convention, index/log formats, citation style. |
| **index.md** | A second TK doc: catalog by category, one line + metadata per entry. |
| **log.md** | A third TK doc: append-only chronological history; also holds the last-ingest timestamp. |

Single-doc (not many page-docs) was chosen deliberately: it plays directly to the TK-1823 edit ops and sidesteps the fact that TK has no whole-document delete (see Gaps).

## The "repo": three TK documents, discovered by convention

The skill re-finds its own docs each run — **no external config file**. Every doc carries three tags: `llm-wiki` (marks it as skill-owned), a **library-name tag** (scopes it to one library), and a role tag:

- **Wiki doc** — title `📚 <Library name> — Wiki`, tags `llm-wiki` + `<library name>` + `llm-wiki-page`.
- **Index doc** — title `🗂 <Library name> — Wiki Index`, tags `llm-wiki` + `<library name>` + `llm-wiki-index`.
- **Log doc** — title `🪵 <Library name> — Wiki Log`, tags `llm-wiki` + `<library name>` + `llm-wiki-log`.

Discovery: `search_documents` / `get_recent_documents` filtered to the `llm-wiki` + `<library name>` tags scopes straight to one library's trio (no title-string matching needed); the role tag then identifies which of the three each doc is. If the trio isn't found, the skill is in **build** mode (first run); otherwise **ingest/query/lint** mode. All three are personal, private documents owned by the user (not added to the library). The library is a read-only source.

## Wiki-doc structure (single doc, sections = pages)

Top-level `##` headings are "pages". Each keeps a stable heading `id` (TK assigns it), so:
- `replace_node_contents` rewrites a section's body while preserving its id (and the reader's collapse state) — the TK-1823 headline op.
- `insert_sibling_node` adds a new section (new page) or a bullet/paragraph.
- `delete_node` prunes a stale section (this is why no whole-doc delete is needed).

Suggested standing sections: `## Overview`, `## Synthesis`, then `## Entities`, `## Concepts` groupings (each concrete entity/concept is a `###` under these, or its own `##` if large). Exact taxonomy is domain-driven and co-evolves — documented in `SKILL.md` and refined per library.

## Index-doc structure

Categories as `##` sections: **Sources**, **Skipped (non-source)**, **Entities**, **Concepts**, **Explorations** (filed query answers). Each entry: a link + one-line summary + metadata. The **Sources + Skipped lists together are the processed-set** — the authoritative record of what has been ingested (see Log-doc format and the ingest operation).
- **Source** entries link to the source doc's real TK URL (clickable) + its `updated_at` as of ingest (used for edit-detection) + which wiki sections cover it.
- **Skipped (non-source)** entries record docs deliberately examined and excluded (empty / test noise / duplicate) so they aren't re-read; a transient read *failure* is left unrecorded so it retries automatically next run.
- **Wiki-page** entries reference the wiki section **by title** ("see *X* in the Wiki") — not a clickable deep link yet (TK has no heading anchors; **deferred to TK-1829**). When TK-1829 lands, these become `…/notes/<wiki-doc-id>#<heading-id>` links.

## Log-doc format

Append-only. Entry prefix convention (grep-parseable, per the gist):
```
## [YYYY-MM-DD] ingest | <Source title>
## [YYYY-MM-DD] query  | <question>
## [YYYY-MM-DD] lint   | <summary>
## [YYYY-MM-DD] build  | <N sources compiled>
```
Each entry: what happened and which wiki sections/index entries were touched. The log is a human-readable timeline, **not** the ingest cursor — the index (its `## Sources` + `## Skipped (non-source)` lists) is the authoritative **processed-set** that delta detection diffs against (see the ingest operation). This was corrected after the first trial: a single-timestamp watermark both re-selected the boundary doc (inclusive `since`) and orphaned everything a partial/trial build hadn't reached (sources older than the watermark). Diffing the live library against the index by node id + recorded `updated_at` fixes both.

## Operations

### `build` (first run — batch)
1. Enumerate the library (`get_library_documents`, paginate all).
2. Read each source (`get_document_content`; for long ones, `get_document_hierarchy` first).
3. Cluster into entities/concepts/topics; draft the wiki doc, index doc, log doc.
4. `create_document` the three docs (private, tagged per convention).
5. Record every examined source in the index — real ones under `## Sources` (with `updated_at`), deliberate exclusions under `## Skipped (non-source)`. Write a `build` log entry with the source-count.
6. Summarize to the user what was compiled. Batch by default; the user reviews the result rather than each source.

### `ingest` (incremental — interactive, one source at a time by default)
1. Read the **processed-set** from the index (`## Sources` ids + recorded `updated_at`, and `## Skipped` ids).
2. Enumerate the live library and diff: a source is a delta if its id is **not** in the processed-set, or it is under Sources with a newer live `updated_at`. (`since=` is an optional accelerator only; the id/timestamp diff decides correctness, so a partial/trial build never orphans the remainder.)
3. For each (default: one at a time, discuss takeaways with the user):
   - Read the source, extract key info.
   - `edit_document` the wiki: `replace_node_contents` to revise affected sections, `insert_sibling_node` for a new page, `delete_node` for anything now stale. Note contradictions with existing claims explicitly.
   - Update the index (whole-body `update_document`): refresh the source's Sources entry with its current `updated_at` (or add to Skipped), and any changed wiki-page summaries.
   - Append a log entry.
4. Batch mode (`ingest --batch`) processes all deltas with a single end summary.

### `query`
1. Read the index first (per the gist) → pick relevant wiki sections + sources.
2. Read them; synthesize an answer **with citations** (links to source URLs; wiki sections by title).
3. Offer to **file the answer back** as a new `## Exploration: <question>` section + an Explorations index entry + a `query` log line — so explorations compound (gist's key insight). v1 answer format: markdown (tables inline). Slide decks / charts / canvas are deferred.

### `lint`
Health-check pass; report + propose, don't auto-destroy:
- Contradictions between sections; stale claims superseded by newer sources.
- Orphan sections (no inbound "see X" references); concepts mentioned but lacking a section.
- Missing cross-references; data gaps a web search could fill.
- Suggest new questions to investigate and sources to look for.
Applies safe fixes (add cross-refs, split/merge sections) via `edit_document`; anything lossy (deleting a section) is proposed to the user first. Appends a `lint` log entry.

## MCP tool coverage

**Used:** `get_user_libraries`, `search_libraries`, `get_library_documents` (enumerate + `since`), `search_library_documents`, `search_document_content`, `get_document_content`, `get_document_hierarchy`, `create_document`, `edit_document` (replace_node_contents / insert_sibling_node / delete_node), `update_document` (whole-body fallback), `search_documents` / `get_recent_documents` (doc discovery).

**Gaps (documented, non-blocking):**
1. **No whole-document delete.** Mitigated by single-doc model — `delete_node` prunes sections. Only bites if we ever go multi-doc.
2. **No pin tool.** Can't pin the trio to the top of the library; N/A while docs are private. Title prefixes + tags suffice.
3. **No heading deep-links** → index/cross-refs use "see X section" prose for now. **Deferred to TK-1829.**
4. **No op to append a list item** (`insert_sibling_node` is top-level-only; `replace_node_contents` is inline-only). So the **index** (bulleted catalogs) is maintained with whole-body `update_document` rather than surgical edits; the **wiki** stays surgical. Acceptable because the index is private, single-editor, and regenerable. **Deferred to TK-1831**; when it lands the index can move to surgical appends.

None blocks v1.

## Skill structure

One skill, `~/.claude/skills/llm-wiki/`:
- `SKILL.md` — the schema (Layer 3): trigger, `llm-wiki <build|ingest|query|lint> <library>` dispatch, all conventions above, MCP usage notes, interaction defaults (batch build / interactive incremental).
- `DESIGN.md` — this file.
- `references/` — as needed (e.g. the index/log format templates, the section taxonomy guidance) to keep `SKILL.md` lean.

Personal skill (like `morning-brief`); uses `tk-local` for local testing and `tk-remote` for production libraries.

## Test plan (local)

Target any library you're a member of (a small one is best for a first run).
1. `build` → verify three private docs created, wiki has sensible sections, index catalogs sources with clickable URLs (and records each source's `updated_at` + a `## Skipped (non-source)` list), log has a `build` entry.
2. Add/edit a source in the library → `ingest` → verify only the delta is processed, the right section is rewritten (id preserved), index + log updated.
3. `query` a cross-source question → verify cited synthesis; file it back → verify Exploration section + index entry appear.
4. `lint` → verify it surfaces at least one real gap/orphan and proposes (doesn't silently delete).

## Deferred / v2
- Shared model (wiki docs added to the library, visible to members) — the user wants to experiment with this later.
- Split the wiki into several docs by category once it outgrows a few hundred sections.
- Heading deep-links (TK-1829) → clickable index/cross-refs.
- List-item append op (TK-1831) → maintain the index surgically instead of whole-body rewrites.
- Richer query outputs (Marp decks, matplotlib charts, canvas).
- A dedicated wiki search tool (qmd-style); TK's own semantic search suffices at this scale.
