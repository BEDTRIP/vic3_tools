---
name: vic3-compat
description: Making Victoria 3 mods work together — whether two mods need a compatibility patch at all, merging two mods' versions of one record (three-way, field by field), writing the minimal patch, a replacement patch for a broken one, megapacks and add-ons built from patches, optional dependencies, generators that rewrite other mods' files, what to check when a mod updates or leaves the set. Use when the user asks for a compatibility patch ("компач"), a merge, a megapack or add-on, an update after another mod changed, or whether two mods conflict.
---

# Compatibility patches for Victoria 3

A **compatibility patch** is a small mod that makes two other mods work together. The goal is always **the minimal
patch**: the fewer files it overrides, the less breaks when the mods update. Special cases: a **replacement patch**
(another patch is broken — carry its files whole and fix them in place), a **megapack** (all patches of a set merged
into one mod), an **add-on** (the same for a block of mods loaded on top of a megapack).

How the engine merges — the skill `vic3-modding` (read its `load-and-override.md` first: a wrong load-order model makes
the whole analysis wrong).

## The tools

| question | command |
| --- | --- |
| what two mods (or groups) both define, with `file:line` on both sides | `v3 conflicts A B` |
| the same counted for every pair of the set | `v3 matrix` (`--groups FILE` for blocks) |
| the whole chain of one record across the set: creates, replaces, merges, ignored | `v3 winner common/<folder> KEY` |
| `REPLACE:` bodies losing fields; bodies copied from an old vanilla; dead loc keys | `v3 audit replace / stale / loc-dead MOD` |
| every use of a name in the set (lists of buildings by name…) | `v3 refs NAME` |
| tiger + our rules on the patch, known reports left out | `v3 lint MOD` |

## Procedures

| task | file |
| --- | --- |
| does the pair need a patch; what the matrix cannot see | [references/analysis.md](references/analysis.md) — "Is a patch needed" |
| both mods rewrote the same vanilla record — a three-way merge | [references/analysis.md](references/analysis.md) — "Merging" |
| what to change in an existing patch; a mod updated or left the set | [references/analysis.md](references/analysis.md) |
| a replacement patch; blocks, pairs, add-ons, megapacks, optional dependencies, metadata | [references/builds.md](references/builds.md) |
| generators: rules and self-checks | [references/builds.md](references/builds.md) — "Generators" |

## Always

- **Intent is the difference from vanilla, not the presence of a field.** A later mod's full body restates fields it
  does not care about; apply "the later wins" per field, against vanilla (four cases in `analysis.md`).
- **Everything that rewrites another mod's file is a script** (a generator with `--check`), not a hand edit.
- **One file — one pair** in add-ons and pair patches; a file that needs both mods of two pairs says so first.
- **`metadata.json` without a BOM**; a dependency is found by the target's `id` from its own `metadata.json`.
- **Write the conclusion explicitly**: "no conflict, because …" with what was checked; a conflict nobody read is a lost
  edit — generators print every disputed cluster and what they chose.
