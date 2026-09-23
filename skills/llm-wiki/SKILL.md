---
name: llm-wiki
description: Build and maintain a persistent LLM-authored wiki over a TK library, or over a filtered collection of your own notes (e.g. "all my notes not created by the assistant or MCP") — Karpathy's LLM-wiki pattern. The sources are compiled into three private TK docs — a wiki, an index, and a log — kept current as sources change. Triggers on "/llm-wiki", "llm wiki", "build the wiki for <library>", "build a wiki from my notes", "ingest into the wiki", "update the wiki", "query the wiki", "lint the wiki", or "compile a wiki from <library>". Operations — build | ingest | query | lint — dispatched as `llm-wiki <operation> <library | filter>`.
---

# LLM Wiki

Compile a TK **library** — or a **filtered collection** of your own notes — into a persistent, interlinked **wiki** and keep it current, so knowledge accumulates instead of being re-derived on every question (Karpathy's LLM-wiki pattern; the idea file is in `DESIGN.md`).

Three layers:
- **Raw sources** = the documents in the **scope**: a TK library, or a filtered collection (see *Scopes*). Read-only — **never modify a source doc**.
- **The wiki** = three private TK documents this skill owns: a **wiki** doc (top-level headings are its "pages"), an **index** doc (catalog), and a **log** doc (append-only history).
- **The schema** = this file. It defines the conventions and workflows. Formats live in `references/conventions.md`.

You (the human) curate sources, ask questions, and steer. The skill does the reading, summarizing, cross-referencing, filing, and bookkeeping.

**Dispatch:** `llm-wiki <build|ingest|query|lint> <library-name-or-id | filter description>`. If no operation is given, default to `ingest` when the wiki exists, else offer `build`.

**MCP server:** use the `tk-remote` tools by default (production); use `tk-local` when the user is working against a local dev instance (or says "local"). Tool names are identical on both.

## Scopes

A wiki compiles one **scope**. Two kinds:

- **Library** — a TK library, named or by UUID. Sources = `get_library_documents(library_id)`.
- **Collection** — a filter over the user's **own** notes, from a description like "all my notes that weren't created by the assistant or MCP". Sources = `get_recent_documents` (it returns only docs the user owns), paginated `limit:100` + `offset` until `has_more` is false, then filtered **client-side** on the returned metadata.

Deciding which: if the argument matches a library (exact name or UUID), it's a library. Otherwise treat it as a collection description. If it's ambiguous, ask.

**Translating a description into a filter.** Map the description onto these **deterministic** fields only, so the same filter always selects the same docs on every re-run:

| Field | Meaning | Source |
|---|---|---|
| `created_by_ai` | `false` = not created by the assistant, MCP `create_document`, or `create_daily_note` | doc metadata |
| `created_after` / `created_before` | `created_at` bounds (ISO date) | doc metadata |
| `tags_any` / `tags_none` | tag include/exclude | doc metadata |
| `daily_note_kind_none` | drop daily notes of these kinds (`scratch` = template scratch pad, `prompt` = writing-prompt note) | `daily_note_kind` |
| `title_excludes` | title substrings/patterns to drop | doc metadata |

Topical criteria ("notes about hiring") are **not** filter fields: semantic search ranks, it doesn't select, so re-running it would add and drop sources. If the description has a topical part, say so and offer tags or a library instead.

**Always-on exclusions for collections** (apply even if the description doesn't mention them):
- Any doc tagged `llm-wiki` — this skill's own output, for any scope.
- **`created_by_ai` is unreliable before 2026-08-05.** The column was added then with no backfill, so every earlier doc reads `false`, including AI-created ones. When the filter uses `created_by_ai:false`, **ask** how to treat legacy docs. The default is **AI-tag exclusion**: collect every tag that appears on any `created_by_ai:true` doc (e.g. `morning-brief`, `session-log`), show the list to the user, and add the approved tags to `tags_none`. Recurring headless jobs tag their output consistently, so this catches them deterministically. Don't include tags that are also common on the user's own writing (e.g. a broad `tk` tag); show each tag's true/false split so the user can prune. The stricter alternative is `created_after: 2026-08-05`. Legacy AI docs with no tags can still get in; build drops the obvious ones into `## Skipped (non-source)` with reason `looks AI-generated (pre-flag legacy)`.

Before a `build`, **echo the resolved filter and the matching count** to the user and confirm. A collection over hundreds of docs is a big build, so offer a trial cap.

**Naming.** A collection gets a short **scope name** (e.g. `My Notes (human-written)`) used exactly where a library name would be: in titles and as the scope tag. Propose one and let the user override it. The filter is **persisted in the index doc** (see `references/conventions.md`), and ingest re-applies that stored filter verbatim — never re-derive it from the name.

## Resilience rule

Reading a single source can fail (auth, rate limit, a malformed doc). If one source errors, **do not abort the whole run** — note it inline (`⚠️ skipped <title>: <reason>`), continue with the rest, and surface the skipped list in the final summary. A partial pass that finishes is better than a clean pass that never lands.

A transiently-failed source needs no retry bookkeeping: because the processed-set is authoritative (see below), any source not recorded in the index is simply picked up as a delta on the next ingest. Only *deliberate* exclusions (a genuinely empty/noise doc you decided is not a source) get recorded, so they aren't re-read every run.

## Conventions (read `references/conventions.md` for the exact templates)

- The three docs are **personal and private** — created with `create_document`, **never** added to any library (`add_document_to_library` is not called here). The shared model is deferred.
- **Tags on each doc:** `llm-wiki` + `<scope name>` (library name, or collection name) + a role tag (`llm-wiki-page` / `llm-wiki-index` / `llm-wiki-log`).
- **Titles:** `📚 <Scope> — Wiki`, `🗂 <Scope> — Wiki Index`, `🪵 <Scope> — Wiki Log`.
- **Wiki edits** go through `edit_document`: `replace_node_contents` to rewrite a section (keeps the heading id → stable + preserves the reader's collapse state), `insert_sibling_node` to add a top-level section/block, `delete_node` to prune a stale section.
- **Link everything linkable in the wiki body** (not just the index). Whenever the prose names something with a stable TK URL, make it a markdown link — on first mention per section:
  - a **person who is a TK user** → their profile `https://tk.xyz/@<username>` (`/@<username>` on local). Build an author → username map from source metadata (`author_username`) as you read, and reuse it wherever that person is named (contributors, "Source:" bylines, entity pages).
  - a **source / document** → its note URL (`…/notes/<id>`).
  - a **URL a source states verbatim** (e.g. a project's own site) → link it.
  Do **not** fabricate external URLs (tool/product homepages you don't have from a source) — link only TK profiles/docs you can resolve and URLs actually present in the sources. `replace_node_contents` carries these links, so linking is a normal part of writing/rewriting a section.
- **The index is the processed-set, and is authoritative.** A source is "ingested" iff the index catalogs it (a Sources entry, or a Skipped-non-source entry). Each Sources entry records the source `updated_at` as of ingest, so a later edit is detectable. Delta detection diffs the live scope against the index by node id — no timestamp cursor. (The log may still note a watermark, but only descriptively; it is not the cursor.)
- **Index maintenance uses whole-body `update_document`**, not surgical ops — the index is a private, regenerable catalog of bulleted lists with no collaborators or heading-collapse state, and `edit_document` currently has no op to append a list item (**TK-1831**). The **wiki** doc is always maintained surgically with `edit_document` (that is where merge-safety and collapse matter). When TK-1831 lands, the index can move to surgical appends too.
- **Log entries** are append-only, prefixed `## [YYYY-MM-DD] <op> | <detail>`.

## Step 0 — Resolve target + discover the wiki (every operation runs this first)

1. **Resolve the scope** (see *Scopes*). Library: if given a UUID, use it; otherwise `get_user_libraries` / `search_libraries` to match the name; if ambiguous, ask which one. Collection: for `build`, resolve the description into a filter + scope name; for other ops, the user names the collection and the filter is read from its index doc.
2. **Discover the trio.** Find the skill's own docs by tag. **Note: TK's tag filter is OR, not AND** — passing `["llm-wiki", "<scope name>"]` returns docs matching *either* tag (i.e. every scope's wiki docs). So query by the more specific `<scope name>` tag alone (`get_recent_documents tags:["<scope name>"]`), then **keep only results that also carry the `llm-wiki` tag**, and identify each of the three by its role tag. (Equivalently: query `llm-wiki` and post-filter to those whose tags include `<scope name>`.) Never assume a returned doc belongs to this scope without confirming *both* tags are present.
3. **Branch on what you found:**
   - Trio present → run the requested operation (default `ingest`).
   - Trio absent → the wiki doesn't exist yet. If the user asked for `build`, proceed. If they asked for `ingest`/`query`/`lint`, tell them there's no wiki for this scope yet and offer to `build` it.
   - Partial trio (1–2 of 3) → report it; offer to repair by recreating the missing doc(s) from the survivors rather than a full rebuild.

## Operation: build

First-time compilation of a scope into the wiki. Batch — the user reviews the result, you don't ask per-source questions mid-build.

1. Run Step 0. **If the trio already exists, stop** and tell the user (suggest `ingest` to update, or that a rebuild would duplicate). Do not create a second set.
2. Enumerate sources: library → `get_library_documents(library_id, limit:100)`; collection → `get_recent_documents(limit:100, sort_by:"created_at")` filtered per *Scopes*. Paginate on `has_more` via `offset`. (For a **trial**, the user may cap this, e.g. the first ~15 by `added_at` / `created_at`. Say so in the summary so a partial build isn't mistaken for complete.) **More than about 40 sources → follow `references/batch.md`** (script-filtered list, parallel readers writing digests, coverage check, one synthesizer, published-index verification) instead of reading them in this context.
3. Read each source: `get_document_content` (for long docs, `get_document_hierarchy` first to decide what to pull). Apply the resilience rule.
4. Cluster the material into entities / concepts / topics. Draft the three docs per `references/conventions.md` — an `## Overview` and `## Synthesis`, then entity/concept sections; an index cataloguing sources (clickable URLs) and wiki pages (by title); a log seeded with the build entry.
5. Create the docs: `create_document` for wiki, index, log — each with the tag scheme + title. **Do not add them to any library.** For a collection, write the resolved filter into the index's `## Scope` block.
6. In the index, record **every source examined**: real ones under `## Sources` (each with its `updated_at` as of ingest), and deliberately-excluded empty/noise docs under a `## Skipped (non-source)` list (id + `updated_at` + reason) so they aren't re-read. Transient read failures are left unrecorded (they reappear as deltas next run). Append the build log entry: `## [<today>] build | <N> sources compiled` and (if a trial) the cap used.
7. Summarize to the user: the three doc URLs, the wiki's section list, source count, and any skipped sources.

## Operation: ingest

Incremental — fold in only what changed since the last pass. Default one source at a time, interactive.

1. Run Step 0 (trio must exist; else offer `build`).
2. Read the **processed-set** from the index: the node ids under `## Sources` (with each entry's recorded `updated_at`) and under `## Skipped (non-source)`.
3. Compute the delta. Enumerate the live scope (library: `get_library_documents`; collection: `get_recent_documents` + the filter stored in the index's `## Scope` block), paginated. A source is a delta if its id is **not** in the processed-set, **or** its live `updated_at` is newer than the one recorded in its Sources **or Skipped** entry (an empty draft or daily note that later gets written becomes a real source). (For a large scope you may pre-filter with `since` as an accelerator, but the id/timestamp diff — not a cursor — decides correctness, so a trial/partial build never orphans the un-ingested remainder.) Also compute **departures**: processed-set ids absent from the live scope (deleted, or no longer matching the filter). For each, drop its index entry and remove or re-attribute its claims in the wiki. If an arriving delta is the same note under a new id (e.g. re-imported), repoint the citations instead of treating it as new material. If both the delta and departures are empty → report "wiki is current (N sources)" and stop.
4. For each delta source (default: one at a time — read it, discuss the key takeaways with the user, then apply):
   - Revise affected wiki sections with `replace_node_contents`; add a new `## <page>` with `insert_sibling_node`; `delete_node` anything now stale. **Explicitly note contradictions** with existing claims rather than silently overwriting.
   - Update the index (whole-body `update_document`): add or refresh the source's `## Sources` entry with its current `updated_at`, or add it to `## Skipped (non-source)` if it has no real content; refresh any wiki-page summaries that changed.
   - Append an `ingest` log entry naming the touched sections/entries.
5. `--batch` variant: process all deltas with one end summary instead of per-source discussion. **More than about 40 deltas → `references/batch.md`.**
6. **Duplicates:** if a delta is the same note as an existing source under another id (a copy, or a Medium import of a TK draft), don't compile it twice. Keep one canonical source (the fuller text, newer `updated_at` on ties) and record the other under Skipped with reason `duplicate of <id>`.

## Operation: query

Answer a question against the wiki, with citations, and optionally compound the answer back in.

1. Run Step 0.
2. Read the **index doc first** to pick the relevant wiki sections + sources; read them. If the index is thin for this question, fall back to `search_library_documents` / `search_document_content` over the library. For a collection, use `search_documents` / `search_document_content` and keep only hits that are in the index's Sources.
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

## Skipping auto-assembled daily notes

A daily note whose body is mostly generated scaffolding (carried-over todos, weather, recent-notes lists, calendar, briefing text) with little or no prose the user wrote is `Skipped` as `auto-assembled daily note`, even when `created_by_ai` is false. Daily-note creation seeds the body without setting the flag. If the user wrote prose in it, it's a source, and the wiki draws only on the user-written part.

## Known limits (see `HOWTO.md`)

- No whole-document delete in the MCP surface → the single-doc model prunes *sections* (`delete_node`); a whole doc can only be archived by editing.
- No pin tool → the trio isn't pinned in any list; tags + titles are how you find them.
- No heading anchors yet → index/cross-references say "see *X* section" instead of deep-linking (tracked in **TK-1829**).
