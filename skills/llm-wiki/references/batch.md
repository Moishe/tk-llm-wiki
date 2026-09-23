# Large batches: the fan-out recipe

Use this for a `build`, or an `ingest --batch`, whose delta is more than about 40 docs. Reading hundreds of notes in one context doesn't fit, and hand-filtering hundreds of metadata records is error-prone. So the list, the filter, and the coverage check are scripts; agents only read and write.

First proven on a 482-note collection ingest (2026-09-23). Ten Sonnet readers used about 1.7M tokens and one Opus synthesizer about 360K. **Tell the user the scale before starting.**

Work in a local directory (e.g. `~/working-artifacts/llm-wiki-<scope>/`), never `/tmp`.

## 1. Enumerate (one agent, then a script)

- **Collection:** an agent pages `get_recent_documents(limit:100, sort_by:"created_at")` until `has_more` is false. After each page it appends every doc, unfiltered, to `all.tsv` with columns `id, created_at, updated_at, created_by_ai, daily_note_kind, tags ("|"-joined), title`. It reports only row counts and the API `total`.
- **Library:** the same, with `get_library_documents`.
- Write `filter.json` (the index's Scope filter) and `processed.tsv` (`id <TAB> recorded updated_at` for every Sources and Skipped entry). Then run `python3 scripts/delta.py <dir>`. It writes `delta.tsv` and prints the match/delta/departure counts.
- **Sanity-check before going on:** the row count should equal the API total, and the match count should be close to the one recorded at build. Investigate every departure. In the first run, the one departure turned out to be a note the user had deleted and re-imported under a new id.

## 2. Read (about 10 parallel readers)

- Split `delta.tsv` into interleaved batches of about 50 (`rows[i::n]`, so every batch gets a mix of dates).
- Give each Sonnet reader the shared instructions below, its batch file, and its own `digest-NN.md`.
- Ten parallel readers hit MCP rate limits. Readers should retry with short backoff only after an actual error. Once most readers have finished, tell any stragglers to drop fixed sleeps.

Reader instructions (write to `reader-prompt.md`):

- Read-only against TK. For every row, call `get_document_content` (plain_text) and append an entry to the digest. Append as you go; on a read failure write `verdict: error: <reason>` and continue.
- Entry format:

  ```
  ### <id> | <title>
  - url · created_at · updated_at (copied character-for-character from the TSV)
  - verdict: source | skip: <reason> | ai-legacy: <why> | error: <reason>
  - kind, summary (1–2 sentences), themes, entities, notable (1–3 citable claims/quotes ≤25 words), unfinished (yes/no)
  ```

- **skip** when the doc is empty, title-only, template placeholders, or a test note. Also skip an **auto-assembled daily note**: a daily note whose body is mostly generated scaffolding (carried-over todos, weather, recent-notes lists, calendar, briefing text) with little or no prose the user wrote. If the user did write prose in it, it's a `source`, and the digest covers only the user-written part.
- **ai-legacy** only when a collection's `created_by_ai` is unreliable for the doc's date (see *Scopes* in SKILL.md) and the text is clearly machine-generated. If unsure, use `source` and add `(ai?: maybe — why)` to the summary.
- Summarize faithfully; don't infer facts the note doesn't state.

## 3. Check coverage (script)

Run `python3 scripts/check_digests.py <dir>`. It exits non-zero unless every delta id has exactly one entry, with the exact `updated_at` and a verdict. Re-run a reader for any gap; never synthesize over a partial digest set.

## 4. Synthesize (one Opus agent)

The synthesizer reads SKILL.md and conventions, the current trio, and all digests. Before compiling, it:

- **Dedupes.** The same note often exists under two ids, e.g. a TK draft and a Medium import, or a copy. Readers only see their own batch, so this is a synthesis job. Match on the same or near-same title plus matching summary or notable lines. Keep one canonical source per note: the fuller text, with the newer `updated_at` breaking ties. Record the other under Skipped with reason `duplicate of <canonical id>`, so an edit to it still re-enters as a delta.
- **Applies departures and repoints:** drop the departed ids' index entries and repoint re-imported notes' citations.

Then it compiles the wiki (Overview, Synthesis, one `###` per theme, Timeline, Entities, Open drafts; keep it under about 60K characters) and the index (the full catalog). It writes both to local `.md` files first, then publishes. It appends the log entry surgically.

**Whole-body wiki rewrite.** When a batch grows the source count several-fold, every section gets rewritten. At that point, surgical per-section edits aren't practical, so a whole-body `update_document` on the (private) wiki is acceptable. Say so in the log, since it resets the reader's heading collapse state. For a batch that touches only some sections, stay surgical.

## 5. Verify what was published (script)

The synthesizer pastes large bodies into tool calls by hand, and one mistyped UUID becomes a permanent false delta. So after publishing, fetch the index with `get_document_content(format:"json")`. Past the inline limit, the tool saves the result to a file you can parse.

Walk the Tiptap JSON: under the `Sources` heading, collect each list item's `notes/<id>` link and its `ingested @` value. Under `Skipped`, collect the id and its `seen @` value. Diff both against the digests plus the surviving processed-set. `plain_text` drops link URLs, so it can't verify Sources.
