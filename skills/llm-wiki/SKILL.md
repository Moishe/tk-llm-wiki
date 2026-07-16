---
name: llm-wiki
description: Build and maintain a persistent LLM-authored wiki over a TK library (Karpathy's LLM-wiki pattern). The library's documents are the raw sources; the skill compiles them into three private TK docs — a wiki, an index, and a log — and keeps them current as sources change. Triggers on "/llm-wiki", "llm wiki", "build the wiki for <library>", "ingest into the wiki", "update the wiki", "query the wiki", "lint the wiki", or "compile a wiki from <library>". Operations — build | ingest | query | lint — dispatched as `llm-wiki <operation> <library>`.
---

# LLM Wiki

Compile a TK **library** into a persistent, interlinked **wiki** and keep it current, so knowledge accumulates instead of being re-derived on every question (Karpathy's LLM-wiki pattern; the idea file is in `DESIGN.md`).

Three layers:
- **Raw sources** = the documents in a TK library. Read-only — **never modify a source doc**.
- **The wiki** = three private TK documents this skill owns: a **wiki** doc (top-level headings are its "pages"), an **index** doc (catalog), and a **log** doc (append-only history).
- **The schema** = this file. It defines the conventions and workflows. Formats live in `references/conventions.md`.

You (the human) curate sources, ask questions, and steer. The skill does the reading, summarizing, cross-referencing, filing, and bookkeeping.

**Dispatch:** `llm-wiki <build|ingest|query|lint> <library-name-or-id>`. If no operation is given, default to `ingest` when the wiki exists, else offer `build`.

**MCP server:** use the `tk-remote` tools by default (production); use `tk-local` when the user is working against a local dev instance (or says "local"). Tool names are identical on both.

## Resilience rule

Reading a single source can fail (auth, rate limit, a malformed doc). If one source errors, **do not abort the whole run** — note it inline (`⚠️ skipped <title>: <reason>`), continue with the rest, and surface the skipped list in the final summary. A partial pass that finishes is better than a clean pass that never lands.

A transiently-failed source needs no retry bookkeeping: because the processed-set is authoritative (see below), any source not recorded in the index is simply picked up as a delta on the next ingest. Only *deliberate* exclusions (a genuinely empty/noise doc you decided is not a source) get recorded, so they aren't re-read every run.

## Conventions (read `references/conventions.md` for the exact templates)

- The three docs are **personal and private** — created with `create_document`, **never** added to the library (`add_document_to_library` is not called here). The shared model is deferred.
- **Tags on each doc:** `llm-wiki` + `<library name>` + a role tag (`llm-wiki-page` / `llm-wiki-index` / `llm-wiki-log`).
- **Titles:** `📚 <Library> — Wiki`, `🗂 <Library> — Wiki Index`, `🪵 <Library> — Wiki Log`.
- **Wiki edits** go through `edit_document`: `replace_node_contents` to rewrite a section (keeps the heading id → stable + preserves the reader's collapse state), `insert_sibling_node` to add a top-level section/block, `delete_node` to prune a stale section.
- **Link everything linkable in the wiki body** (not just the index). Whenever the prose names something with a stable TK URL, make it a markdown link — on first mention per section:
  - a **person who is a TK user** → their profile `https://tk.xyz/@<username>` (`/@<username>` on local). Build an author → username map from source metadata (`author_username`) as you read, and reuse it wherever that person is named (contributors, "Source:" bylines, entity pages).
  - a **source / document** → its note URL (`…/notes/<id>`).
  - a **URL a source states verbatim** (e.g. a project's own site) → link it.
  Do **not** fabricate external URLs (tool/product homepages you don't have from a source) — link only TK profiles/docs you can resolve and URLs actually present in the sources. `replace_node_contents` carries these links, so linking is a normal part of writing/rewriting a section.
- **The index is the processed-set, and is authoritative.** A source is "ingested" iff the index catalogs it (a Sources entry, or a Skipped-non-source entry). Each Sources entry records the source `updated_at` as of ingest, so a later edit is detectable. Delta detection diffs the live library against the index by node id — no timestamp cursor. (The log may still note a watermark, but only descriptively; it is not the cursor.)
- **Index maintenance uses whole-body `update_document`**, not surgical ops — the index is a private, regenerable catalog of bulleted lists with no collaborators or heading-collapse state, and `edit_document` currently has no op to append a list item (**TK-1831**). The **wiki** doc is always maintained surgically with `edit_document` (that is where merge-safety and collapse matter). When TK-1831 lands, the index can move to surgical appends too.
- **Log entries** are append-only, prefixed `## [YYYY-MM-DD] <op> | <detail>`.

## Step 0 — Resolve target + discover the wiki (every operation runs this first)

1. **Resolve the library.** If given a UUID, use it. Otherwise `get_user_libraries` / `search_libraries` to match the name; if ambiguous, ask the user which one.
2. **Discover the trio.** Find the skill's own docs by tag. **Note: TK's tag filter is OR, not AND** — passing `["llm-wiki", "<library name>"]` returns docs matching *either* tag (i.e. every library's wiki docs). So query by the more specific `<library name>` tag alone (`get_recent_documents tags:["<library name>"]`), then **keep only results that also carry the `llm-wiki` tag**, and identify each of the three by its role tag. (Equivalently: query `llm-wiki` and post-filter to those whose tags include `<library name>`.) Never assume a returned doc belongs to this library without confirming *both* tags are present.
3. **Branch on what you found:**
   - Trio present → run the requested operation (default `ingest`).
   - Trio absent → the wiki doesn't exist yet. If the user asked for `build`, proceed. If they asked for `ingest`/`query`/`lint`, tell them there's no wiki for this library yet and offer to `build` it.
   - Partial trio (1–2 of 3) → report it; offer to repair by recreating the missing doc(s) from the survivors rather than a full rebuild.

## Operation: build

First-time compilation of an existing library into the wiki. Batch — the user reviews the result, you don't ask per-source questions mid-build.

1. Run Step 0. **If the trio already exists, stop** and tell the user (suggest `ingest` to update, or that a rebuild would duplicate). Do not create a second set.
2. Enumerate sources: `get_library_documents(library_id, limit:100)`, paginating on `has_more` via `offset`. (For a **trial**, the user may cap this — e.g. the first ~15 by `added_at` — say so in the summary so a partial build isn't mistaken for complete.)
3. Read each source: `get_document_content` (for long docs, `get_document_hierarchy` first to decide what to pull). Apply the resilience rule.
4. Cluster the material into entities / concepts / topics. Draft the three docs per `references/conventions.md` — an `## Overview` and `## Synthesis`, then entity/concept sections; an index cataloguing sources (clickable URLs) and wiki pages (by title); a log seeded with the build entry.
5. Create the docs: `create_document` for wiki, index, log — each with the tag scheme + title. **Do not add them to the library.**
6. In the index, record **every source examined**: real ones under `## Sources` (each with its `updated_at` as of ingest), and deliberately-excluded empty/noise docs under a `## Skipped (non-source)` list (id + reason) so they aren't re-read. Transient read failures are left unrecorded (they reappear as deltas next run). Append the build log entry: `## [<today>] build | <N> sources compiled` and (if a trial) the cap used.
7. Summarize to the user: the three doc URLs, the wiki's section list, source count, and any skipped sources.

## Operation: ingest

Incremental — fold in only what changed since the last pass. Default one source at a time, interactive.

1. Run Step 0 (trio must exist; else offer `build`).
2. Read the **processed-set** from the index: the node ids under `## Sources` (with each entry's recorded `updated_at`) and under `## Skipped (non-source)`.
3. Compute the delta. Enumerate the live library (`get_library_documents`, paginated). A source is a delta if its id is **not** in the processed-set, **or** it is under Sources but its live `updated_at` is newer than the recorded one. (For a large library you may pre-filter with `since` as an accelerator, but the id/timestamp diff — not a cursor — decides correctness, so a trial/partial build never orphans the un-ingested remainder.) If the delta is empty → report "wiki is current (N sources)" and stop.
4. For each delta source (default: one at a time — read it, discuss the key takeaways with the user, then apply):
   - Revise affected wiki sections with `replace_node_contents`; add a new `## <page>` with `insert_sibling_node`; `delete_node` anything now stale. **Explicitly note contradictions** with existing claims rather than silently overwriting.
   - Update the index (whole-body `update_document`): add or refresh the source's `## Sources` entry with its current `updated_at`, or add it to `## Skipped (non-source)` if it has no real content; refresh any wiki-page summaries that changed.
   - Append an `ingest` log entry naming the touched sections/entries.
5. `--batch` variant: process all deltas with one end summary instead of per-source discussion.

## Operation: query

Answer a question against the wiki, with citations, and optionally compound the answer back in.

1. Run Step 0.
2. Read the **index doc first** to pick the relevant wiki sections + sources; read them. If the index is thin for this question, fall back to `search_library_documents` / `search_document_content` over the library.
3. Synthesize an answer **with citations** — sources as clickable TK URLs, wiki pages by section title.
4. **File valuable answers back** (Karpathy's key insight — don't let synthesis vanish into chat): when the answer contains new synthesis worth keeping, offer to add `## Exploration: <question>` to the wiki (`insert_sibling_node`), an entry under `## Explorations` in the index, and a `query` log line. Skip filing for trivial lookups.
5. Answer format v1 = markdown (tables inline). Slide decks / charts / canvas are deferred.

## Operation: lint

Periodic health check. **Propose, never silently destroy.**

1. Run Step 0.
2. Read the wiki + index and scan for: contradictions between sections; stale claims superseded by newer sources; orphan sections (no inbound "see X" reference); concepts mentioned but lacking their own section; missing cross-references; data gaps a web search could fill.
3. Apply **safe** fixes automatically (add a cross-reference, correct an index entry) via `edit_document`. Anything lossy — deleting or merging a section — is **presented to the user for approval first**.
4. Suggest new questions to investigate and sources to look for.
5. Append a `lint` log entry summarizing findings and what was applied vs proposed.

## Known limits (see `HOWTO.md`)

- No whole-document delete in the MCP surface → the single-doc model prunes *sections* (`delete_node`); a whole doc can only be archived by editing.
- No pin tool → the trio isn't pinned in any list; tags + titles are how you find them.
- No heading anchors yet → index/cross-references say "see *X* section" instead of deep-linking (tracked in **TK-1829**).
