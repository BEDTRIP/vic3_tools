---
name: vic3-repo-rules
description: How an agent keeps a Victoria 3 mod repository in order — committing finished pieces itself, explicit paths, pushing after each commit, commit messages that say how the problem looked in the game, safe writes of game files from Python (temporary file, BOM rules, brace balance), CRLF noise, what never to commit. Use when working in a git repository of Vic3 mods, before committing, and when writing scripts that edit game files.
---

# Repository rules for Vic3 mod work

Project rules (`CLAUDE.md`) win over these where they differ. Answer in the user's language.

## git

- **Commit a finished piece yourself, in the same turn** (a task, a patch with its generator, a rebuild, documents) —
  waiting for "commit" left ~500 uncommitted files mixed across tasks in six days. One commit — one task.
- **Start of a session:** `git pull`, `git status`. A dirty tree from an earlier session: sort it into commits first
  (unclear whose — ask), then the task. **End:** `git status` clean, or say what is left and why.
- **Explicit paths:** `git add -A -- "<folder>" tools/<generator>.py`, never `git add .` / `git add -A` alone —
  another agent may work next to you. `git diff --cached --stat` before committing.
- **Push after each commit** when several sessions (local, remote, cloud, a PC bridge) work on one branch — otherwise
  the others do not see the work. Work in the project's main branch unless told otherwise.
- **The message:** `<area>: <what was done> (<task ids>)`; the body says what was broken, **how it looked in the game**
  (or that the symptom was silent, and which), why this solution. A revert explains why the previous commit was wrong.
- **Never without being asked:** `--amend` or `rebase` of pushed commits, `reset --hard`, `--no-verify`, `stash` of
  someone else's changes, other branches.
- **Never commit:** `_to_delete/`, drafts and scratch files, editor workspace files, live copies of mods in
  `Documents/…/mod/` (not in git).
- `.gitattributes` converting CRLF → LF shows "LF will be replaced by CRLF" and one-character diffs on untouched files:
  line ends, not edits.
- A subagent that edits files commits its own part and reports the hash; the orchestrator checks `git status` on its
  paths afterwards.

## Writing game files from scripts

- **Write through a temporary file and `os.replace(tmp, path)`** — opening the target for writing truncates it before
  anything else can fail (a 2282-line generator was once zeroed this way).
- Several edits of one file — one script with `assert old in text` for each piece.
- Game syntax with backslashes (`\[`, `\d`, `\xEF`) — raw strings in Python; do not pass such text through shell
  heredocs (the shell eats `\n` and backslashes) — write the script with a file tool.
- **BOM:** a script `.txt` with non-ASCII text outside comments needs one; localization `.yml` always; `metadata.json`
  never (the launcher fails); byte-for-byte copies of other mods' files — never add one.
- After each edit: braces balance (`v3 lint --no-tiger --file F`, or count `{` − `}` with comments cut) and no new
  duplicate top-level keys across the mod.
- Every generator has `--check` (writes nothing, exit 1 on drift).

## Writing results

- Comments in code and mod READMEs in English; talk to the user in their language.
- A comment answers "why this and not the obvious way", especially where a mistake was made — quote the log line, or
  say the symptom is silent and which.
- A letter to another mod's author: English, collegial; what was done → numbers → **the bugs found in their mod**
  (most valuable to them) → a link "take what you need".
- At the end of a session: update the project's plan / rules with what was learned and commit — otherwise the next
  session starts from zero.
