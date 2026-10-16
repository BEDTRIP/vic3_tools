# Replacement patches, blocks, add-ons, megapacks, generators

## A replacement patch

When another patch is broken and needs more than two or three fixes, a standalone mod replacing it is cheaper than a
layer on top.

- **Why.** A layer needs the other patch enabled, loaded earlier and unchanged in shape; break any of the three and the
  `INJECT:`s land on keys that do not exist. And on top you can only add the right key — the broken one stays.
- **How.** A fresh unpacked copy of the other patch in `<name> out`; a generator copies all its files **byte for
  byte** except those it fixes; fixed ones keep **their own names**, so no key is defined twice.
- **No header of yours on copied files and no BOM added** — the diff against its next version stays byte-exact.
- Broken keys fixed in place (a list of replacements in the generator); workaround blocks removed from your files.
- `metadata.json` and README say plainly: **run INSTEAD of the other patch, not with it.**

## Blocks and pairs

A set is described by **blocks**, not single mods: a block is a mod plus the companions that always go with it (a mod
+ its hotfix, an author's pack of eight mods). Compatibility is counted by blocks: **n blocks → n(n−1)/2 pairs**.

## Add-ons

A megapack covers its blocks. A new block on top is a new layer:
`base pack → megapack → block A → add-on A → block B → add-on B → …`. Add-on N closes the pairs "block N × each block
below". Order the blocks so add-ons stay small: the block that touches less goes later.

- **One add-on for every variant cannot be made**: an add-on file carries a merged body naming both mods' entities;
  without one of them the body points at a missing `pmg_` / key (`REPLACE:` of a missing key — a load error).
- **But an add-on does not touch every block**: if its pairs with some mods are "not needed", it works with builds
  lacking them as it is.
- **In an add-on one file = one pair.** Then "a build variant" is just a list of files. **Exception — files depending
  on two pairs** (two pairs `REPLACE:` one record): their header starts with "needs both mods: X and Y".
- **A separate patch "pack + one mod" always works** — keep pair patches as separate folders even if only the build
  is published.

## Building a megapack or add-on

**Contents: every pair of the set except those marked "not needed".** Variants differ only in which pairs drop out.

- **Build from the patches, never by editing the previous build** (it lags behind every rename; you can no longer tell
  "renamed" from "deleted"). Cycle: the target file list from current patches → everything else moved to
  `_to_delete/<name>_rebuild_<date>/` → copy the targets over.
- **Coverage check is mandatory**: compare every file of every patch with the build byte for byte; three numbers per
  patch (files, missing, different), **any non-zero has a written reason** (replaced by a merged version, not needed in
  the build, a build-only file). Then the same against the game's live folder (`diff -rq`).
- **The typical build conflict: two patches `REPLACE:` one record, each for its own line.** Each is right alone;
  together the later file name wins and the other's line silently vanishes. Fix: a `zzzz_megapack_<what>.txt` loaded
  last with the united body. **The same when only ONE side is `REPLACE_OR_CREATE:` and the others `INJECT:`** into the
  same record — that the inject files sort above is an accident of the alphabet, not a guarantee. Search for "more
  than one patch writes into one (category, key), and at least one of them is not `INJECT:`/`TRY_INJECT:`".
- **"The build overrides a mod" is not caught by an internal check**: run `v3 conflicts <build> <each mod>` plus path
  overlaps.
- **Count goods again along the whole chain** with every new mod.
- **Localization — check per language folder**, or eleven languages read as eleven duplicates.
- **A declared "duplicate is fine" goes stale silently** when the patches change: resolve the final bodies across the
  playset and look for a method group repeated in `production_method_groups` — the engine does not collapse it.
- **Never switch events off by re-issuing their id** — through their callers.

### Build-only files

- Named `zzzz_megapack_<what>.txt` / `zzzz_addon_<what>.txt`, to load after everything in the build.
- **The header starts with "this file is in no patch"**, then: which files conflict and in what order they load, what
  exactly is lost, how it looks in the game (often: it does not — say so); plus `!! MAINTENANCE !!`: which file the
  body is derived from and what to re-derive after the other mod updates.
- If needed only with both mods of a pair — the first line says so (the variant generator reads it).
- **Derive the body from the file that wins now**, replacing exactly the missing lines — not written anew.

### Optional dependencies: marked files and `.off` pairs

When a build works without an optional mod, each file that exists because of it says so in its first line:

- **the whole file belongs to the optional mod** → `=== <MOD>-ONLY FILE ===`: "delete this file to play without
  <mod>";
- **the optional mod is mixed into a file another, required patch owns** → `=== CARRIES A <MOD> LAYER ===` on the
  active file plus an inert `<name>.txt.off` next to it — the same without the layer (the game ignores unknown
  extensions); on the `.off` file `=== INACTIVE -- NO-<MOD> VARIANT (.off) ===` with "delete the active file, drop
  `.off` from this one";
- **checked and nothing added** → the file is not touched or tagged; the decision goes into its header.

In the generator: build the base body (without the optional mod) first, then lay the optional layer on THAT base —
both files from one base, not two merges that can drift apart. The "what to delete / rename" table goes into the
owning patch's README and into the add-on's README ("Playing without X"). A third way — a separate patch for the
optional mod loaded after the add-on, importing the add-on generator's body functions rather than recomputing.

### Metadata and README of a build

- `metadata.json` **without a BOM** (the launcher: "Failed to process metadata").
- **The launcher finds a dependency by the `id` in the mod's own `metadata.json`**, not the Workshop number; an empty
  `"id"` cannot be a dependency (mention it in the description only). Take the `id` from the target's own file.
- `relationships` list **every** mod of the set, including companions not inside the build.
- README: the load order with all of them and **why the build loads after X**; the **order requirements that "not
  needed" pairs rely on**; "what only this build does" — a line per build-only file; version, `supported_game_version`
  = `1.13.*`, `tested_with`.

## Generators

Everything that rewrites another mod's file is a script, not a hand edit.

- **Take the source of truth from the other mod itself**, not from your own table (a hand list "tag → entity" loses the
  race with their roster); your table only for priority, not membership.
- Check what you read against keys that exist (a mod's own list says `company_BankSBoBS`, the company is
  `company_BankSBoBSA`; `REPLACE:` of a missing key is a load error).
- **Watch the prefix when gluing**: a block taken with its `REPLACE:` plus another on top → `REPLACE:REPLACE:x`, the
  record silently does not load. Keep `^[A-Z_]+:[A-Z_]+:` in the self-check — and separately `^[A-Z_]+::` (an empty
  double colon, `TRY_INJECT::`, not caught by the first).
- No long `if/else_if` chains (145 branches = 145 stack frames); flat `if`s with a flag variable behave the same.
- The generator prints what it fixed this run, and it goes into the file header; an empty list or a new item = the
  source changed, read it.
- Self-check at the end: brace balance, encoding, duplicate keys (per category, not per file; `INJECT:` /
  `TRY_INJECT:` repeats are normal), doubled prefixes.
- Stale output is not deleted silently — moved to `_to_delete/rebuild_<date>/`, and the move printed.
- **Every generator has `--check`** (did it drift; writes nothing; exit code 1). **If `--check` finds no `<name> out`
  folder it must fail, not print "missing" and exit 0** — that looks like "all matched". Keep the `out` folder.
