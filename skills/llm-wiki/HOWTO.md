# LLM-Wiki — how to use

A Claude Code skill that turns a TK **library** into a persistent, LLM-maintained **wiki**. See `DESIGN.md` for the rationale (Karpathy's LLM-wiki pattern) and `references/conventions.md` for the exact formats.

## What it makes

For a given library, three **private** TK documents (never added to the library):
- **📚 Wiki** — the compiled knowledge; top-level headings are its "pages".
- **🗂 Index** — a scannable catalog (sources with links, entities, concepts, explorations).
- **🪵 Log** — append-only history of every build/ingest/query/lint, and the watermark used for incremental updates.

The library's own documents are the raw sources and are **never modified**.

## Invocation

```
/llm-wiki build  "My Library"     # first-time compile (batch)
/llm-wiki ingest "My Library"     # fold in what changed since last time
/llm-wiki query  "a cross-source question about the library"
/llm-wiki lint   "My Library"     # health-check; proposes fixes
```

- Omit the operation and it defaults to `ingest` if the wiki exists, else offers to `build`.
- You can pass a library UUID instead of a name.
- **Trial build:** ask for a capped first build (e.g. "build the first 15 sources") to validate the shape before compiling a large library.

## Local vs production

Tool names are identical on both MCP servers; the skill picks:
- **`tk-local`** — when working against a local dev instance (say "local"). Needs the local backend + collab running.
- **`tk-remote`** — default, for real production libraries.

## How it stays current

Each `build`/`ingest` writes a **watermark** (the newest source `updated_at` it processed) into the log. The next `ingest` reads that watermark and only pulls sources changed since — so updates are cheap and you never re-read the whole library. Discovery is by tag (`llm-wiki` + the library name), so the skill re-finds its own three docs every run with no config file.

## Interaction model

- **build** — batch; you review the result.
- **ingest** — one source at a time by default, so you can steer emphasis and catch contradictions; `ingest --batch` for unattended delta processing.
- **query** — reads the index first, answers with citations, and offers to file the answer back as an Exploration so it compounds.
- **lint** — applies only *safe* fixes automatically; anything lossy (deleting/merging a section) is proposed for your approval.

## Known limitations

- **No whole-document delete** in the MCP surface → the wiki is one doc and stale *sections* are pruned with `delete_node`; a whole doc can only be archived by editing.
- **No pin tool** → the three docs aren't pinned anywhere; find them by tag/title.
- **No heading deep-links yet** → the index and cross-references say "see *X* section" instead of linking to it. Tracked in **TK-1829**; when it lands these become clickable `…/notes/<id>#<heading-id>` links.

## Deferred / future

- **Shared model** — putting the three docs *in* the library so all members see the LLM-maintained wiki (Karpathy's team example). Kept private for now.
- **Multi-doc split** — if the single wiki doc outgrows a few hundred sections, split by category into several docs.
- **Richer query outputs** — Marp decks, matplotlib charts, canvases.
- **Dedicated wiki search** — TK's own semantic search suffices at this scale; a qmd-style tool if it grows.
