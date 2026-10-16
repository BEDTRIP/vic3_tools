# Load order and overriding

## Order

**The order of mods is the main order. A file name decides only inside one mod.**

Checked in the game 2026-08-24: LLWA and its patches loaded last, their bare body of `building_railway` won, and the
railway's panel showed three method groups instead of nine — neither E&F's nor T&R's. Had the order been by file name
across one shared file system, `LLWA_rails.txt` would have loaded right after vanilla's `11_private_infrastructure.txt`
and lost. Second proof: E&F puts `REPLACE:pm_company_headquarter_privately_owned` in
`11_ef_private_infrastructure.txt`, vanilla defines it in `14_companies.txt`; by file name that would be a `REPLACE:`
of a missing key — a load error for each of fifteen methods. `error.log` has none.

**Inside a mod: by bytes of the file name.**

- `_` (0x5F) sorts **before** letters: `zz_ef_` < `zz_pb_` < `zz_tr_` < `zzef_` < `zztr_` < `zzz_` < `zzzz_`;
- `~` (0x7E) after all letters: `~zzzzMoG_USU_railways.txt` is a mod's last file;
- capitals before lower case: `zz_LLWAMR_` < `zz_ef_`;
- `zztr_vanilla_buildings.txt` loads **after** `zz_tr_kai_tgr_buildings.txt`, not as it reads by eye.

In doubt — compute (`sorted(names, key=str.encode)`), do not estimate. The real order and what is enabled: the
launcher's `launcher-v2.sqlite` (`v3 playsets`, `v3 mods`) — it also shows a mod enabled twice (Workshop and local).

## Directives

- `INJECT:` `TRY_INJECT:` `REPLACE:` `TRY_REPLACE:` `REPLACE_OR_CREATE:` `INJECT_OR_CREATE:` are the right way to edit
  another mod's record. `INJECT:` into a list adds, it does not replace.
- **`INJECT:` merges sub-blocks into the record; inside a sub-block the engine counts in order.** `value = X` resets
  everything accumulated before it; named entries (`institution_police`, `combat_unit_group_infantry`) override
  same-named ones; unnamed `add = { }` add up. So re-issuing another mod's `INJECT:` after a later body restores it
  exactly, and a block its author opens with `value =` is taken whole. (TGR's files, 2026-08-25.)
- **`REPLACE:` replaces the record whole** (decided 2026-09-24 on three observations, all one way): in the game
  `REPLACE:building_bank = { ownership_type = self }` removed the central bank entirely; 285 methods re-issued with
  only `building_modifiers` lost `unlocking_laws`; PSC `REPLACE:`s four construction methods without
  `country_modifiers` and construction is not counted twice. Practice: write `REPLACE:` with the **full body**; a
  sub-block to switch off is named empty explicitly. `v3 audit replace <mod>` lists bodies that omit fields.
- **`REPLACE:` is needed exactly when a line must be REMOVED.** Only adding — `INJECT:` (98 four-line injects instead
  of 98 verbatim copies, 7000 lines to re-diff on every update). Before `REPLACE:` ask: what exactly do I remove here?
- **`INJECT:` can also silently erase:** an injected script-value sub-block that opens with `value = X` resets what
  earlier mods accumulated there. PSC writes `ai_value = { value = 2500 … }` into `building_construction_sector`, a
  later AI mod injects `ai_value = { value = 1000 … }` — the base drops to 1000, PSC's bonus is gone, no log line.
  When two mods touch one record, look at whether the sub-block opens with a reset, not only at the prefixes.
- **Repeated keys inside one modifier block add up.** `INJECT:base_values = { country_loan_interest_rate_add = 0 }`
  resets nothing (`0 + (-0.2) = -0.2`). To zero another mod's modifier: (1) override the file it sits in by path, if
  nothing else is there; (2) a counterweight of the opposite sign — right only while it adds up.
- **The same for `goods` in `buy_packages`**: two same keys in one block add up (probe 2026-10-07: both keys 2439,
  first only 2344, second only 1172). To replace a value — one key only.
- **A counterweight of the opposite sign comes back to life silently.** A mod injects exactly minus vanilla's value
  to switch a bonus off; a third mod rewriting the record whole copies vanilla's numbers and the bonus is back. **An
  inject numerically equal to minus vanilla is a switch, not an edit.** Re-issue it after the late mod, and note it
  as maintenance: if the late mod changes the number, the counterweight stops landing on zero.
- **A key without a prefix overrides too.** A later `foo = { }` eats an earlier `REPLACE_OR_CREATE:foo`. **A bare full
  body in a later mod is the most destructive conflict:** it takes every earlier `INJECT:` with it.
- **`scripted_effects` / `scripted_triggers` / `script_values`: a plain repeat in a later file does NOT override** —
  `REPLACE_OR_CREATE:` is needed. Silent: the old definition keeps working, the new one is never called.
- **`effect` of an on_action does not add up**: one `effect`, the last loaded wins (`debug.log`: "There is more than
  one 'effect' defined using most recent"); `on_actions = { … }` add up. Your code into a vanilla or another mod's
  on_action — only `on_actions = { my_hook }` plus `my_hook = { effect = { … } }`.
- **The engine does not create per-goods modifier types itself.** `state_sell_orders_<goods>_add` and the like are
  declared one by one (`00_modifier_types.txt`); for a mod's goods the mod declares them. An undeclared type drops out
  of the static modifier at load, the error only in `debug.log` at start.
- **`scope:x.<script_value>` is not parsed** ("Badly read script value scope:…"), the line drops at load. A value in
  another scope: compute it there into a variable and read `scope:x.var:name`.
- **Load errors are in `debug.log`, not `error.log`** (`pdx_persistent_reader`: Unknown modifier type, Unexpected
  token, Badly read). Both logs rotate by 512 KB; the start of a session goes first.
- **Overriding a file by its relative path is the bluntest tool, and sometimes the only surgical one.** If a file
  holds exactly one record to remove and its key is shared (four files inject `base_values`), `REPLACE:` by key pins
  everyone's contribution, while overriding the path removes exactly that file. Check the file has nothing else; note
  as maintenance that later additions of its author to that file are gone too.
- **Events do not follow the load order; never override an event by id.** `debug.log` (2026-09-24): "Duplicated event
  ID 'joi_flavor_chi.29' found. New Location: …joi_flavor_chi.txt, Previous Location: …zzz_joi_flavor_chi_29_fix.txt"
  — a fix in a mod loaded after was read first and lost ("New" wins); the rule of ordering event files is not derivable
  from the log. Switch an event off through its callers (buttons, decisions, on_actions — records, where the later mod
  wins). Check any such place: grep `debug.log` for `Duplicated event ID`.
- **Localization: the FIRST file defining a key wins**, not the order of mods. Override only from
  `localization/<lang>/replace/` (keys there override those already defined, whatever the order), or by a file with
  the same name (path override). Keys a mod defines that an earlier file already has are dead (`v3 audit loc-dead`).

## Categories that are not conflicts

Leave them out when counting overlaps:

- `common/on_actions` — additive;
- `common/history/*` — the container keys `BUILDINGS`, `GLOBAL`, `POPS`, `TREATIES`, `POLITICAL_MOVEMENTS`,
  `MILITARY_FORMATIONS`, `POWER_BLOCS` add up;
- `common/named_colors` — the key `colors` everywhere;
- `common/modifier_type_definitions` — `decimals`, `color`, `percent` are display only;
- `events` — a shared `namespace` is not a conflict; matching **event ids** are;
- `common/defines` — merged **per define**, not per block (`NEconomy`).

**`history/buildings` runs BEFORE `history/global`.** Laws are not active yet: any `has_law` gate there is false; the
only binding to a country at that stage is its tag.
