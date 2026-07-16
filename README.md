# LLM-Wiki for TK

A Claude Code plugin that turns a **TK library** into a persistent, self-maintaining **wiki** — Andrej Karpathy's [LLM-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) applied to TK. Instead of re-deriving knowledge from the raw documents on every question, the agent compiles the library once into a structured, interlinked wiki and then *keeps it current* as sources change.

The library's documents are the read-only **sources**. The skill owns three **private** TK docs per library:

- **📚 Wiki** — the compiled knowledge; top-level headings are its "pages."
- **🗂 Index** — a scannable catalog of every source (also the authoritative record of what's been ingested).
- **🪵 Log** — an append-only history of every build/ingest/query/lint.

Nothing is ever written into the shared library, and source documents are never modified.

## Operations

```
/llm-wiki build  "My Library"     # first-time compile of the whole library (batch)
/llm-wiki ingest "My Library"     # fold in only what changed since last time
/llm-wiki query  "a question spanning several sources"   # cited answer; can file it back
/llm-wiki lint   "My Library"     # health-check; proposes fixes, never deletes silently
```

Omit the operation and it defaults to `ingest` if a wiki exists, else offers to `build`. You can pass a library UUID instead of a name. See `skills/llm-wiki/HOWTO.md` for the full usage guide and `skills/llm-wiki/DESIGN.md` for the design rationale.

## Prerequisites

- A **TK** account, and the **TK MCP server connected in Claude Code** (`tk-remote` for production; `tk-local` for a local dev instance). The skill uses the standard TK document/library tools.
- You must be a **member** of the library you point it at (enumerating a library requires membership).
- The **surgical edit ops** must be available on your TK deployment — the skill maintains the wiki with `edit_document`'s `replace_node_contents` / `insert_sibling_node` / `delete_node` (TK-1818 / TK-1823). If your TK backend predates those, `build`/`query` still work but `ingest`/`lint` edits will fall back or fail.

> Note: the docs reference internal TK Linear tickets (TK-1818, TK-1823, TK-1829, TK-1831) as design context and known-gap tracking. They're informational; the skill doesn't require access to them.

## Install (as a plugin)

Once this repo is pushed somewhere your coworkers can reach (e.g. GitHub):

```
/plugin marketplace add <owner>/llm-wiki      # or a git URL, or a local path to this repo
/plugin install llm-wiki@llm-wiki
```

To install from a **local clone** without pushing:

```
/plugin marketplace add /path/to/llm-wiki
/plugin install llm-wiki@llm-wiki
```

Update by re-pulling the repo (and re-running `/plugin marketplace update llm-wiki`).

> If you previously had this skill as a personal skill at `~/.claude/skills/llm-wiki/`, remove that copy after installing the plugin so the skill isn't registered twice.

## What it creates

For each library, three private docs tagged `llm-wiki` + `<library name>` + a role tag (`llm-wiki-page` / `-index` / `-log`), discovered by tag on every run — no config file. The wiki is maintained surgically (heading ids preserved, so per-user collapse state and links survive); the index is a small regenerable catalog.

## Known limits

- **No whole-document delete** in TK's MCP surface → the wiki is a single doc and stale *sections* are pruned; a whole doc can only be archived by editing.
- **No heading deep-links yet** (TK-1829) → cross-references say "see *X* section" rather than linking to it.
- **No list-item-append op yet** (TK-1831) → the index (bulleted lists) is maintained with whole-body rewrites; the wiki stays surgical.
- **Shared model deferred** — the three docs are private; a "wiki lives in the library, visible to members" mode is future work.

## Repo layout

```
.claude-plugin/
  plugin.json          # plugin manifest
  marketplace.json     # marketplace manifest (this repo is its own marketplace)
skills/llm-wiki/
  SKILL.md             # the skill (the "schema" layer: workflows + conventions)
  references/
    conventions.md     # exact templates: tags, index/log formats, MCP cheat-sheet
  HOWTO.md             # usage guide
  DESIGN.md            # design rationale (Karpathy mapping, decisions, trade-offs)
README.md
```
