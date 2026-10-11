# User study protocol (PRD "Learner usefulness")

Question: do students fix compiler errors faster with the assistant than with raw compiler output? This is a pilot, so the result is indicative, not statistically strong. The study has not been run yet.

## Participants and design
- 6 to 10 classmates who have written some C or C-like code. Record only a participant number (P1, P2, ...) and self-rated C experience (1 to 5). No names, no student IDs in the data sheet.
- **Within-subjects, counterbalanced.** Each participant fixes two task sets, one in each condition:
  - **A (raw):** the compiler's records printed as plain text by `python -m cea file.c` (message, line, column; no explanation, no clustered view, no assistant).
  - **B (assistant):** the web UI with clustered roots, the short explanation, Expand, and verified fixes.
- Two task sets of 3 programs each (Set X, Set Y) of similar difficulty. Counterbalance both the order and which set goes with which condition by rotating participants through four orders: A-on-X then B-on-Y, A-on-Y then B-on-X, B-on-X then A-on-Y, B-on-Y then A-on-X. Fix the assignment on the timing sheet before the first session.

## Task programs (from the dev split only; held-out stays unused)
Choose six dev programs, each with `"fixable": true`, a cascade where possible, matched by error type so each set has one lexical or syntax fault, one semantic fault and one undeclared-variable cascade. Pick them from `tests/corpus/dev/` by reading the sidecars, and write the six filenames on the timing sheet before the study begins. Never use `tests/corpus/heldout/`. Copy the `.c` files only (no `.expected.json`) and rename them `task1.c` to `task6.c`, so the filename gives nothing away.

## Procedure (about 30 minutes each)
1. Consent (below) and a 3-minute warm-up on a dev program not used in the study.
2. For each condition the participant gets three programs, one at a time, with the instruction "make it compile with no fatal errors; do not change what the program does". The facilitator starts a stopwatch when the file is opened and stops it when `python -m cea task.c` reports no fatal error (check it; do not trust the participant). Stop after 5 minutes and record 300 s with "not fixed".
3. After each condition, two ratings: "How clear was the help? (1 to 5)" and "How confident were you in your fix? (1 to 5)".
4. No hints from the facilitator. Asking the assistant questions is allowed in condition B only.

## Timing sheet (one row per participant and program)

| Participant | Experience (1-5) | Order | Program | Condition (A/B) | Start | Stop | Seconds | Fixed? (Y/N) | Clarity (1-5) | Confidence (1-5) | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|

## Analysis (decided before collecting data)
- Primary: per participant, mean time-to-fix in B minus mean in A (unfixed counts as 300 s). Report the median difference, how many participants were faster in B, and a paired Wilcoxon signed-rank test (exact p). With n of 10 or fewer the test has little power; say so.
- Secondary: share fixed within 5 minutes, and the ratings, per condition.
- Threats: order and learning effects (mitigated by counterbalancing), unequal set difficulty (matched by error type; check per-program times), participants who know the project (exclude its author), small n.

## Consent note (read aloud and print on the sheet)
"You are asked to fix compile errors in short C programs while being timed. Your times and ratings are recorded under a participant number only; no name or student ID is stored. In the assistant condition, the error details and a few lines of the program you are fixing are sent to the language-model provider to produce the explanation. If the study uses the hosted Gemini free tier, that provider may keep or use the submitted text, so do not type personal information into the editor. If the study uses the local Ollama model, nothing leaves this computer. Taking part is voluntary and you may stop at any time without giving a reason. You can ask for your row to be deleted until the results are written up."

Before the study, the facilitator checks which LLM is configured (`python tools/llm_smoke.py`) and reads the matching sentence.
