# Analysis procedures

## What changed in another mod

- Compare `.metadata/metadata.json`: `version`, `supported_game_version`, `relationships`, `id`. **The `id` changes
  too** — a mod re-uploaded as a new item leaves old `relationships` pointing nowhere. Some mods have empty `version`
  (then only the folder's commit date) or an empty `id` (then it cannot be named in `relationships`).
- **First: did names drift.** An author may rename the whole prefix (`kates_` → `vokaes_`), split part into another
  mod, remove a folder. None of this logs a line. Look up every foreign name the patch uses (`v3 def NAME`), one by one.
- Separately: building lists, PM and PMG names, `building_groups` and their `parent_group`, overridden
  `scripted_triggers`, the goods count.

## Is a patch needed

- `v3 matrix` for all pairs; `v3 conflicts A B` for one. Additive categories are filtered out.
- Empty → a "not needed" candidate. Before marking it, check what the matrix does not catch:
  - goods against 128 along the whole chain;
  - law groups;
  - triggers by `building_group` (inheritance through parents);
  - `.gui`: widget names, duplicate `type`s from differently named files (`v3 winner gui`, `v3 lint` rule
    `gui-type-ignored`);
  - event ids;
  - **whether "no conflict" depends on the load order** — if so, write the order requirement down.
- Overlapping file paths → the load order and whether anything meaningful is lost. Often both `TRY_INJECT` into one
  vanilla file — no conflict.
- Overlapping keys → **compare both definitions with vanilla line by line**; half the matches are cosmetic or verbatim
  vanilla.
- Write the conclusion explicitly: "no conflict, because …".

**Three classes the matrix never sees:**

1. **"One mod added content missing from the other's lists."** The matrix compares keys **both** define; a building,
   goods or law declared by one only is never in the intersection. New content needs **an index of every use of the
   name across the set** (`v3 refs`): who lists buildings by name (company `building_types` /
   `extension_building_types`, hand-written lists of a mod, AI weights, `subsidies`).
2. **Other patches not in the block.** A block defined by one bare mod does not measure patches loaded at the same
   stage; what they override with bare bodies is invisible.
3. **Built megapacks and add-ons.** The set lists source mods only; run every new block against every build made
   before, not only against blocks.

## A mod leaves the set

- **Count files from the repository, not the plan** (headers written by the generator lie less than plans).
- **A dead reference to a foreign entity is silent.** A merge file left without its mod keeps loading: `on_complete`
  points at an event of the removed mod — the branch just never fires.
- **Remove in the patch, not in the build**, and in the same go clean the generator, or the next run writes it back.
- **A patch for three mods at once is a mine** — one file, one pair, also in pair patches.
- **Main: check decisions that leaned on the leaving mod.** "This sub-block we leave to C, it overrides it later" —
  C leaves and a correct default becomes a real loss. Put an assert into the generator when such a decision is made.

## Merging: both mods rewrote the same vanilla record

- **Ask who the common ancestor is.** If both edit a vanilla record, vanilla is the ancestor: **a three-way merge**,
  not choosing a winner. "Two rewrites of politics on 172 keys" turned into 38 small clusters.
- **Measure each side's edits against vanilla, not against each other** ("TGR 8–79 changed lines, VC 141–395" says
  whose body is the base).
- **A shared non-vanilla base is common** (both took one third-party source): merge only each side's own deltas.
- Three rules of a three-way merge tool, each paid for:
  1. **a pure insertion is not a conflict** (one side removes a piece of vanilla, the other inserts inside it);
  2. **check a union for braces and fields** — `ig:x = {` vs `?= {` doubles a line; both sides adding the same field
     must not be united (`multiply = 2.0` after `multiply = 2` multiplies twice; a `limit` with both `> 3` and `= 3` is
     never true) — **comparisons are fields too**;
  3. **do not append a list element at the end** — after one side closed `building_types` and opened
     `extension_building_types`, an appended building lands in the wrong list with balanced braces.
- **Numeric rebalancing — by a rule, not cell by cell**: where sides agree — the base; where one deviates — take it;
  where both — a decision (e.g. the late mod's numbers as base, the early mod's multiplier on top, **derived from its
  own header**, so it survives the late mod's update).
- **Print every disputed cluster.**
- **"A gap in coverage" — measure the base density before fixing.** 236 ideologies, 6–27 speak on each new law group,
  the median of the new mod's own ideologies — 2 of 13: silence was the normal state, not a breakage.
- **Tell a taken position from an absent one.** A mod's ideologies on its own characters only is "a new character
  without an opinion", not "the other mod lost one".

## What to change in an existing patch

- Read the patch's README; per file: what it relies on and whether it is still alive; whether it can be less invasive
  (path override → `REPLACE:` of a record → `TRY_INJECT:` → an additive on_action); whether it is needed at all now.
- **Intent is the difference from vanilla, not a field's presence.** Apply "the later wins" per field:
  1. a field the later mod **moved** from vanilla → stays the later's;
  2. a field it **restated with vanilla's value** while the earlier mod changed it → the earlier's value;
  3. a field it **removed on purpose** (in vanilla, not in its body) → not restored;
  4. a field it lacks that the earlier mod **added** → appended.
  The same one level up: a sub-block both rewrote goes to the later whole; lists unite element-wise by the same four
  rules; a block the later lacks entirely is appended. (Naive "the later wins" lost 28 numbers; naive "add everything"
  restored fields the later removed on purpose.)
- **Merge a record by sub-blocks, not by lines**: a line-based three-way merge lies when one side INSERTS a block where
  the other rewrote a range (a line moved inside a block added a line above — braces still balanced).
- **Build the merge on the structure of the mod loaded last**, carry over the first's meaningful differences only;
  never move the first mod's requirements out of the other's `OR`/gate. Comment whose branch is whose.
- Typical findings: a patch made unnecessary by building-group inheritance (delete); a building list drifted from the
  new version (rebuild, `INJECT:` → `TRY_INJECT:`); overriding a foreign `scripted_effect` for one line (replace with
  your on_action); a yearly-pulse mechanism not working the first year (pair it with a call from `history/global/`);
  pinning a value that the load order already gives (delete).
- Update `metadata.json` (no BOM); **check copies** — a patch's files duplicated in builds must be synced (`diff -q`),
  and one file may live in several patches in different versions.
- Make an in-game checklist, by falling risk, with explicit "good / not good".
