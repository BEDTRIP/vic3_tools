---
name: vic3-modding
description: How Victoria 3 (1.13) really loads and merges mods, and engine facts checked in the game — load order, INJECT / REPLACE / bare keys, which definition wins for records, localization, GUI types and events, silent failures of script values, modifiers, on_actions, goods limits, companies and buildings, CMF / ETF frameworks, diagnostics of crashes and wrong numbers. Use before writing or reviewing any Vic3 mod script, GUI or localization, when explaining why a change has no effect or a mod's content vanished, when two mods touch the same thing, or when reading error.log / debug.log / crashes.
---

# Victoria 3 modding: what the engine really does

Facts here were checked in the game (1.13, exe 1.13.11) or read off its logs; the date and the evidence are in the
references. **Do not rebuild the theory of load order from scratch** — if an observation contradicts something here,
write the observation down next to the rule instead of guessing a new model. Answer in the user's language.

## The core (memorize)

1. **Mod order rules; file names decide only inside one mod** (bytes: `_` before letters, capitals before lower case,
   `~` last). Read the real order from the launcher (`v3 mods`), not from memory.
2. **A later bare body (`key = { … }`) replaces the record and wipes every earlier `INJECT:`** — the most destructive
   conflict, silent. `REPLACE:` replaces the record **whole**: whatever the body does not name is lost.
   `INJECT:` merges; inside a sub-block `value = X` resets what came before.
3. **Exceptions to "later wins":**
   - `scripted_effects`, `scripted_triggers`, `script_values`: a bare repeat does **not** override — `REPLACE_OR_CREATE:`;
   - **localization: the first file wins**; override only from `localization/<lang>/replace/`;
   - **GUI types and templates: the first registration wins**, files ordered by file name across all mods (mod order
     does not count); `gui.log` says "already registered";
   - **events**: duplicated ids resolve by an order that is not the mod order — never override an event by id; switch
     it off through its callers (buttons, decisions, on_actions);
   - an on_action holds **one** `effect` (the last loaded); `on_actions = { … }` lists add up.
4. **Silence is not confirmation.** Missing script values, game rules, modifier types, broken `$ARG$`s, `REPLACE:` of
   a missing key — most of these leave no line in `error.log`; load errors are in `debug.log`, which rotates by
   512 KB (the oldest `debug.N.log` has the start).
5. Repeated keys in one modifier block **add up** — a `0` resets nothing.

Use `v3` to check rather than reason: `v3 winner <folder> KEY` (the whole chain: creates, replaces, merges, ignored),
`v3 winner loc KEY`, `v3 winner gui TYPE`, `v3 refs NAME` (who writes, who reads), `v3 lint` (tiger + these rules).

## References — read the one for the task

| topic | file |
| --- | --- |
| load order, the override directives, categories that are not conflicts, history order | [references/load-and-override.md](references/load-and-override.md) |
| script: arguments, iterators, pulses, scopes, what the engine exposes, `script_docs` | [references/script.md](references/script.md) |
| companies, buildings, goods (128 cap, 3 prestige goods), notifications, journal buttons | [references/economy-content.md](references/economy-content.md) |
| GUI: lookups by name, types, blocks, constants, journal widgets, formats; checked with a probe | [references/gui.md](references/gui.md) |
| CMF and ETF frameworks, `*_is_active` flags, stale copies inside other mods | [references/frameworks.md](references/frameworks.md) |
| diagnostics: crashes, logs, playsets, "nothing crashes but numbers are odd" | [references/diagnostics.md](references/diagnostics.md) |
| what not to do (each rule paid for by a mistake) | [references/dont.md](references/dont.md) |

Merging two mods, compatibility patches, megapacks and generators — the skill `vic3-compat`. GUI work — `vic3-gui`.
