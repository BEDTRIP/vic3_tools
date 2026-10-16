# Companies, buildings, goods

- **A company works as a variable-map key and a list element** (probe 2026-10-14): `add_to_variable_map = { key =
  <company> }`, `"variable_map(<map>|scope:<company>)"`, `every_key_in_variable_map`, `add_to_variable_list` behave as
  with a country key. **A company that is gone** (`remove_company`, bankruptcy): its variables vanish but the key
  stays — `is_key_in_variable_map` says yes, `variable_map_size` counts it, but iteration **skips** it and its name is
  empty. Sum over a map only by iterating. Script does not see a company's buildings or HQ (from a company: `owner`,
  `executive`, prosperity only); the window sees `Company.GetProfit`, `Company.GetBuilding` → cash reserves. A
  company's category (`category = bureaucrat_owned`…) is not readable by a trigger — only by the list of types.
- **`building_types` of a company is the only real lock on who may own a building.** A monopoly is a price and
  construction rule, not a lock.
- **`add_ownership` exists only inside `create_building`.** No effect "hand a standing building to a company": the
  building must be born owned; "hand over" = demolish and build again.
- **`level` cannot stand next to `add_ownership`** in one `create_building`: `PostValidate … returned false`, the
  block is dropped whole. Level = the sum of `levels` in the ownerships (vanilla: 3128 blocks with `add_ownership`,
  none with `level`).
- Expanding an existing building gives the NEW levels to the state (observed on a call without `add_ownership`).
- **Re-creating a building costs a month of idleness and takes everything hanging on it.** Call every mod's setup
  effects again, not only the one that sets production methods.
- **Similar `building_group` names of two mods are DIFFERENT groups** (T&R `bg_heavy_industry` vs TGR
  `bg_industry_heavy`, the latter children of `bg_manufacturing` with decrees and laws bound to them). A merge that
  loses one `building_group` line silently drops the building out of half of a mod's mechanics.
- **`has_max_level = yes` + `state_building_<type>_max_level_add`** is a vanilla pair. A mod that `REPLACE:`s such a
  building without `has_max_level` lifts or inherits the cap; wrong inheritance: the building never grows above 1.
- **At most 3 prestige goods per base goods**; only the first three declarations become slots, the number is in the
  exe. Vanilla (2026-08-25): 72 prestige goods on 40 base goods, 17×1, 14×2, 9×3 — nine base goods full before any
  mod. A set of mods overflows it easily and silently; count along the whole chain in load order. ("The first three
  win" is from others, not re-checked in the game.)
- `possible` of a prestige good is evaluated in the country's scope.
- `flavored_company = yes` blocks dynamic names — the name becomes the loc key of the company type: the way to give a
  company a fixed name. A dynamic name puts `$DYNAMIC_NAME_TAG$` into the MIDDLE of the template; a missing key shows
  as `ZZ_…_DYNAMIC_NAME_TAG_SINGULAR` in the name.
- **`ownership_type` (building) and `is_government_funded` (building group) are different switches.** While the second
  is on, the panel calls the building governmental even with a company on the ownership tab.
- **The cap is 128 goods.** 130+ = a crash on entering the game, no log line. Commented ones do not count; vanilla 53.
  **Count by the virtual file system**: walk the mods in load order, map `common/goods/<file name>` → mod (a later
  path overrides), then count keys created there for the first time (bare or `REPLACE_OR_CREATE:`); `REPLACE:` /
  `INJECT:` of vanilla's do not count. Prestige goods are not in the 128. There are no "goods groups" with a limit:
  `category` (`staple` / `industrial` / `luxury` / `military`) has none.
- `normal_modifier_time = 1825` and vanilla feeds it to `days`. A mod writing `months = normal_modifier_time` makes it
  152 years — forever. In a merge take the place from the mod with a literal.
- The launcher's "Failed to process metadata" = `metadata.json` did not parse: BOM first (the usual cause), then
  `json.loads`, then the keys. Extra keys inside `game_custom_data` are tolerated.
- **No nationalization effect** (all effects with text: `common/effect_localization`). There is no effect that takes
  one level off a building either: `add_building_level` is unknown to 1.13 (`error.log`: "Unknown effect
  add_building_level", run 2026-10-16); `remove_building` takes it whole. Raising: `create_building = { building = X
  level = N }` on a standing building raises it to N (PSC's regulator). `ai_nationalization_desire` of a building
  affects the AI only; forbidding the player to privatize by script is impossible.
- **A building's name and icon come from its type.** No "rename a building" effect; per building only in your own
  windows via `Building.GetCustom('<custom loc>')`. Different names and icons of "one" building = different types with
  a shared `building_group` (E&F's 42 financial centres).
- **New buttons — as journal buttons, not widgets.** `scripted_button = X` in a journal entry is drawn for the player
  and pressed by the AI by `ai_chance`; no `.gui` to re-issue.
- **A notification in the feed:** `post_notification = key` in a country scope + `key = { type = country texture = …
  notification_type = feed color = … }` in `common/messages/`, loc `notification_<key>_name` / `_desc` / `_tooltip`
  (vanilla's `exile_notification`).
- **Construction under PSC is throttled at the sectors' output, by a building-type modifier**:
  `building_construction_sector_throughput_add` on the country works (it cuts the sectors' construction goods and
  shows in their tooltip); `state_construction_mult` barely did; any `throughput` on PSC's regulator is cancelled
  within a week (2026-09-24/25).
