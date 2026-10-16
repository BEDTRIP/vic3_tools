# Frameworks (CMF, ETF) and junk inside other mods

## CMF and ETF

- **CMF carries other mods inside it whole.** CMF 1.63 holds all six files of the Multi-line Production Methods
  Framework (`gui/00_MPM_*.gui`, `MPM_custom_types.gui`) in a fresher version than the standalone MPM 1.7.3. **Before
  adding a "dependency" as a separate mod, check whether CMF already has it and whose version is fresher.** A separate
  mod loaded later overrides CMF's files by path and rolls them back; whatever hooked into CMF's `block`s stops working.
- **CMF keeps a registry of `*_is_active` flags** for a couple dozen known mods (`community_framework_is_active`,
  `Grey_USU_is_active`…), declared `always = no`. A mod must override its own flag with **`REPLACE_OR_CREATE:`** —
  a bare key does not override a scripted trigger, and the flag silently stays `no`.
- Vanilla-style fallbacks like `community_framework_is_active = { always = no }` inside other mods are normal: CMF
  overrides them from `zz_com_detection_trigger.txt` (`REPLACE_OR_CREATE`, `always = yes`).
- **A `*_is_active` flag is declared by exactly two: CMF (`no`) and the detected mod itself (`yes`). A third mod must
  not declare it**: it does not know its position relative to the detected mod and, loaded later, switches it off. A
  real case: a mod shipped `REPLACE_OR_CREATE:is_usfp_active = { always = no }` "in case Hail Columbia is absent",
  loaded after Hail Columbia and **switched it off entirely**. When checking a new mod: look for `always = no` next to
  other mods' flag names.
- **A fallback file may be written for the "order by file name" model** ("loads right after CMF's
  `com_law_blocker_triggers.txt`"). With the real order (by mods) it lands later than any mod and switches them off.
  Such headers are a reason to re-check, not to relax.

## Stale copies inside mods

**A mod may carry an outdated copy of a vanilla file with not one line of its own.** LLWA ships
`common/ai_strategies/03_political_strategies.txt` — 125 lines away from current vanilla, the word "LLWA" nowhere. It
rolls vanilla back and, with bare bodies, wipes everything other mods injected there.

Related: not a file but **a record's body copied from an old vanilla**: a mod declared for 1.12 whose culture bodies
lack `seal_and_signature_texture` that 1.13 added; `TRY_REPLACE` with such a body quietly rolls back what the game
added since. Sign: an old game-version tag in `metadata.json` and bodies longer than vanilla's — a copy, not a patch.
`v3 audit stale <mod>` lists full bodies missing fields vanilla has.

Check: for each file of a mod that overrides a vanilla path, grep the mod's own prefix. **Zero matches = a forgotten
copy suspected.** Fix in a patch: put current vanilla back on that path and re-apply the others' `INJECT:`s on top;
worth a note to the author.
