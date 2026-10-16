# Diagnostics

The order that actually saves rounds. The first seven points are about a crash; then "it works but wrong", which turned
out more expensive than crashes.

1. **`crashes/` first, not the logs.** `crashes/<date>/exception.txt` has the exception and the stack;
   `EXCEPTION_STACK_OVERFLOW` = recursion or too deep nesting. Next to it a snapshot of `logs/` at the crash — more
   useful than the current one.
2. **Count stack frames:** `grep -c victoria3.exe exception.txt`. A number hitting the same value (4182 / 4187) across
   different edits = **infinite recursion**, not a long chain.
3. **Summaries instead of reading logs in a row:**
   `sed -E 's/^\[[0-9:]+\]//' error.log | sed -E 's/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -40`.
   Load errors are in `debug.log` (rotates by 512 KB: the oldest `debug.N.log` has the start); GUI registrations in
   `gui.log`; duplicated events in `debug.log` ("Duplicated event ID").
4. **`content_load.json`** — what was enabled at the last start, with paths (Workshop or local folder).
5. **The launcher's `launcher-v2.sqlite`** (`v3 playsets`, `v3 mods`) — the whole playset. **There may be several
   playsets, and the active one is not necessarily the working one.** It shows what is invisible otherwise: **one mod
   enabled twice — Workshop and local `mod/` — the wrong copy on**; a needed patch off; the order not the one a README
   requires. It is the source of truth for "who overrides whom".
6. **Cycles in effects.** Build the call graph of `scripted_effects` (`v3 refs`) and look for cycles. If the cycle is
   only in another mod and touches none of your keys — say so plainly instead of "fixing" blindly.
7. Edit your files only once 1–6 narrowed the place.

## When nothing crashes but the numbers are odd

8. **Ask which countries show it and which do not.** The cheapest and most informative request.
9. **Do the arithmetic right on the screenshot.** 1.22M of production against 214K of demand is about the number of
   central banks in the market — "each takes the whole market for itself".
10. **Periodicity is the signature of a mechanism.** Exactly once a year, each country in its own month = a yearly
    pulse.
11. **Read your own generated files' headers and old commits.**
12. **Check that a "reset" resets anything.** "Here we return the value to 0" is a claim, not a fact.
13. **A screenshot of a building's panel is the cheapest way to see who won a key.** The number of method groups shows
    whose body won. One load of the game closes a question that otherwise takes half a session of reasoning (the
    sandbox — skill `vic3-sandbox`).
