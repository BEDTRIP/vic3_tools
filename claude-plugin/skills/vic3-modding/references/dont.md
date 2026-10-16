# What not to do

Each line was paid for by a mistake.

- Do not "fix" an author's intent without understanding it. A country without a bank may be gated behind an event,
  not a bug.
- **Do not delete a file as junk before checking it is not half of a working mechanism.** A file that looked like a
  leftover experiment was the second half of central-bank ownership. If it was committed and in a working build, it had
  a reason.
- Do not restore vanilla checks that **both** mods removed independently: that invents behaviour no author wants.
- Do not invent a formula when the data is in the mod — pop needs in `common/buy_packages/`, prices in `common/goods/`.
- Do not build feedback from the market ("fit output to consumption") — it spins up by itself.
- **A divisor the mechanism itself produces is not guarded by `if divisor > 0`** — clamp it from below
  (`divide = { value = X min = 1 }`).
- **Do not zero another mod's modifier with a zero.** `INJECT:` into a modifier block adds up.
- **Do not add a BOM to byte-for-byte copies of other mods' files** (the diff against their next version must stay
  byte-exact).
- Do not trust someone else's analysis unchecked — a review from another model was wrong in 4 points of 7. Nor your own
  old summary, README or file header. If two of your notes contradict each other, say so and resolve it.
- Do not be timid restoring `.gui` — go through the diff line by line, not by volume.
- Do not leave an edit in one place — the repository, the game's live folder and **every** build must match.
- **Do not fix a symptom without knowing what it is a symptom of. Do not "fix" a number without knowing what it
  means.** Three wrong fixes in a row of one symptom came from taking a multiplier for a volume.
- **A cap is not a fix.** "Fix the formula so it stops jumping" is not done by a ceiling.
- **Do not guess more than twice in a row.** After two failed hypotheses go for facts: crashes, the playset's sqlite,
  the call graph. "This is not mine" is a fine result.
- **Ask before an architectural fork** (95 company types → 1 was one question and removed three classes of bugs) — but
  first check it is a fork.
- **Do not rebuild the theory of load order.** It is in `load-and-override.md`, checked in the game. An observation
  that contradicts it goes there, next to the rule.
