# Script (1.13)

- **A missing `has_game_rule` or script value gives no error.** The branch simply never fires — the quietest class of
  breakage; caught only by looking each name up in the other mod (`v3 def NAME`).
- **`$MACRO$` arguments are pasted as text.** `CB_SIZE = var:foo` passes the parser, but inside
  `add_ownership = { company = { levels = $CB_SIZE$ } }` the `var:` read does not resolve → 0 levels, no error. Pass
  literals; a variable value — a ladder of literals by branches.
- **An argument `$X$` is one token: a block `{ value = … multiply = … }` in it does not compile** (`error.log`:
  "Compiling source for <effect> failed for unknown arguments: value, multiply"; the call drops whole). Put the sum
  into a variable first, pass `V = var:x`.
- **An argument the callers pass but the effect does not use is a fatal compile error**
  (`jomini_script_argument.cpp:182`): the whole effect is gone.
- `add_modifier { multiplier = X }` evaluates X **not** in the effect's scope — inside `every_scope_state` any
  `state_*` is none. Compute at the country.
- **Before capping someone's value, find its unit and working range from where it is used.** E&F's
  `target_demand_currency_for_modifier` is a percentage fed into a `*_mult` modifier's multiplier: hundreds of
  thousands are its working range, not an overflow.
- Markets have no variables. To the owner: `market ?= { owner ?= { } }`; keep one number per market on
  `market.owner` and read `market.owner.var:X`.
- **Iterators in a script value work ONLY scoped.** `every_scope_state = { add = 1 }` works (vanilla's
  `country_total_urbanization`); global ones — `every_country` and kin — do not run and silently give 0. Any sum over
  a list: compute in an effect into a variable, let the script value divide.
- Into a goods: `mg:X` in a market, `sg:X` in a state.
- **Pulses are spread over days.** `on_monthly_pulse_country` recomputes ~1/30 of countries each day,
  `on_yearly_pulse_country` ~1/365; each country has its day. "Jumps for everyone, but in different months" = a yearly
  pulse. **No quarterly pulses**: monthly, half-yearly, yearly, five-year, decade (country, state, character) — a
  quarter is a counter on the monthly pulse.
- `is_building_group` walks the chain of parents — often no patch is needed at all.
- **`log = "..."` writes nowhere in 1.13.** `debug_log = "…"` writes to `debug.log`. Build diagnostics on observable
  consequences.
- **Compile and `PostValidate` errors go to `debug.log`**, not `error.log`; the effect simply does not exist.
- Prefer constructs proven in the same code. If a mod commented out its own version of something
  (`any_company = { is_company_type = … }`), do not trust it; `has_company = company_type:X` works.
- **A hyphen in a vanilla name can be real**: `pan-nationalism` is a technology. Look names up before calling them
  typos.
- **An ideology has no opinion on a law variant.** A law with `parent = law_X` inherits its parent's positions; a line
  `law_variant = approve` inside an ideology's `lawgroup_*` must not exist — the price is not "the line does nothing"
  but **the whole law group goes to zero** (2026-08-27: every interest group 99.9 % neutral on all five tax laws, no
  log line). Filter out laws with `parent` before setting positions.
- **`country_law_manager.cpp:464` in the log is almost always vanilla**: "Country X is not permitted to retain law A"
  means a starting law fails `unlocking_technologies` / `disallowing_laws`; vanilla's politics presets give
  `law_per_capita_based_taxation` whose `currency_standards` sits only in the tier-3 tech preset — 30 lines at 1836 on
  bare 1.13.11. Compare with vanilla before calling it a conflict.
- **No error in `error.log` may exist for anything above. Silence is not confirmation.**
- **The full list of what the engine gives scripts: the `script_docs` dump** (the game with `-debug_mode`, console
  `script_docs`) → `Documents/Paradox Interactive/Victoria 3/docs/`: `triggers.log`, `effects.log`,
  `event_targets.log` (values: "Output Scopes: value"), `modifiers.log`, `on_actions.log`. Grep there before claiming
  "the engine does not have it".
- **The GUI sees more than script.** A pop group's income, taxes and goods expenses (`PopsOverviewPanel.GetTaxBurden*`,
  `GetGoodsExpenses*`) are window data only. Script has for a pop: `wealth`, `standard_of_living`, `quality_of_life`,
  `total_size`, `workforce`, `dependents`, `literacy_rate`, `strata`, `is_employed`, `food_security`; for a country:
  `gdp` (yearly forecast), `income` (weekly), `total_income` / `total_expenses`, `fixed_income` / `fixed_expenses`,
  `potential_income`, `tax_waste`, `tax_level`, `investment_pool` (+ `_gross_income`, `_net_income`, `_income`),
  `average_sol`, `average_expected_sol`. **No goods price as a value** — only `market_goods_pricier` / `_cheaper` in
  percent of base, and `base_price`. A GUI value can reach script only through a GUI→script bridge (a hidden widget
  whose `state` calls a scripted GUI with `MakeScopeValue`).
- The engine has **variable maps** (`add_to_variable_map`, `every_key_in_variable_map`), `clamp_variable` /
  `round_variable`, `add_pop_wealth` / `set_pop_wealth`, `start_privately_funded_building_construction`,
  `set_available_for_autonomous_investment` (state), `seize_investment_pool`; modifiers
  `state_<stratum>_consumption_multiplier_add` (aristocrats, capitalists, peasants only),
  `state_<stratum>_investment_pool_efficiency_mult`, `country_disable_investment_pool_bool`.
