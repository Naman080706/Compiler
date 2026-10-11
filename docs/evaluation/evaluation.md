# Evaluation write-up (milestone 5)

All numbers come from `python tools/evaluate.py` and are stored in `docs/evaluation/results.json` and `results.md`. The held-out split (20 programs) was evaluated with `--i-am-milestone-5`; held-out programs and sidecars were not edited.

## 1. Setup

- Date: 2026-10-11. Python 3.13.1, Windows 11.
- Hardware: AMD Ryzen (16 logical cores), NVIDIA RTX 3050 6 GB laptop GPU.
- Model: `llama3.1` (8B, Q4_K_M) served by local Ollama through the OpenAI-compatible fallback client: `CEA_LLM_FALLBACK_MODEL=llama3.1`, no primary key. No hosted model (Gemini) was used, so nothing here says anything about Gemini.
- Real run: `CEA_LLM_FALLBACK_MODEL=llama3.1 python tools/evaluate.py --i-am-milestone-5 --llm env --dev-llm env` (about 29 minutes). Without a model, `--llm fake` gives pipeline-only numbers, labelled as such.
- No explanation cache was used, so every latency request is a cold call. The model was warm after the first request (first request 6.7 s).
- Structural metrics (F2, root accuracy) are deterministic. LLM metrics vary a little between runs (temperature 0.2): an earlier run with identical code gave 13/18 verified fixes, the final run 12/18.

## 2. Results against the PRD targets (held-out split)

| Metric | PRD target | Held-out result | Status |
|---|---|---|---|
| Error reduction, single-fault cascading files | >= 70% | 69.6% (23 raw to 7 shown, 7 files) | **Not met** (0.4 points short) |
| Error reduction, all cascading files | (reported) | 64.0% (25 raw to 9 shown, 8 files) | n/a |
| Root-cause accuracy (exact code and line, per program) | >= 85% | 95.0% (19/20); roots: precision 95.7%, recall 100% | Met |
| Verified fix within 3 attempts, `fixable` roots | >= 80% | 66.7% (12/18) with llama3.1 | **Not met** |
| Explanation cites a real rule: the model itself | >= 90% | 47.8% (11/23) | **Not met** |
| Explanation cites a real rule: after validation | >= 90% | 100% (23/23) | Met, see caveat |
| Citations to non-existent rules | 0 | 0 | Met |
| Latency, default explanation (50 requests, cold cache) | < 5 s | median 5.81 s, p90 6.70 s | **Not met** (local 8B model) |
| Learner usefulness (user study) | better than raw | not run; protocol in `user-study.md` | Open |

Dev split for comparison (real llama3.1 too): single-fault 72.5% (40 to 11), all-cascade 60.0% (50 to 20), root accuracy 100%, verified fixes 24/48 = 50.0%, model-cited 35.6%, validated 94.9%, latency median 6.21 s / p90 7.23 s. With the oracle FakeLLM (pipeline-only, not a model result) dev verified fixes are 43/48 = 89.6%.

Verified-fix detail (held-out): the 12 verified fixes used 10 first tries, 1 second try and 1 third try. Median 5.1 s per program; 8 of 12 would also fit the product's 10 s budget (the evaluation used 180 s). The 6 failures: new error introduced (2), original error remains (1), guardrail rejection for touching lines far from the error (1), for deleting code (1), for commenting code out (1).

## 3. Discussion

**Targets met.** Root-cause accuracy and the zero-non-existent-citations rule hold on unseen programs. The one inexact program (`016-guess-check-empty-condition.c`) shows the true root plus one extra WRN-UNREACHABLE-CODE warning the sidecar does not list. Recall is 100%: no injected fault was hidden.

**F2 and the acceptance wording.**
- The PRD acceptance ("one missing semicolon that produced 10 or more errors shows 1 root") cannot be demonstrated: a missing semicolon yields 1 raw record under our recovery (`docs/error-recovery.md` section 10).
- The percentage target is therefore measured on single-fault cascading files, with the all-cascade figure beside it (decision in `plans/README.md`). Held-out gives 69.6%, just under 70%; dev gave 72.5%. Five of the seven held-out files are 2-raw to 1-shown cascades, worth only 50% each, so the figure is sensitive to the mix. We did not change recovery or clustering to reach 70%; that would be tuning on the test set.
- All 7 single-fault held-out cascades display exactly one root, and the multi-fault file displays its 2 roots. Whether the target counts as met depends on the wording the owner chooses (`docs/prd-revision-notes.md`).

**Oracle vs real LLM.** The oracle FakeLLM replays fixes found by search over the compiler plus hand-written entries; its 89.6% only shows the verifier pipeline works. A real 8B model gets 50% on dev and 66.7% on held-out. Held-out being higher is noise on 18 versus 48 units, not generalisation. Failures are mostly the guardrails doing their job (non-local or code-deleting patches) and patches that swap one error for another. "Verified" means "compiles and the error is gone", not "correct".

**Grounding.**
- The model itself cites a retrieved rule in 47.8% of explanations. After `Agent.validate_citations` the figure is 100%, because an explanation that cites nothing valid is attributed to the chunk it was grounded on (its own rule). That is true by construction of the retrieval, not evidence that the model used the rule, so the honest figure is the first and it is not met.
- **Bug found by this evaluation.** In the first real run the model cited 0/23 and latency was 37 s: `EXPLAIN_SCHEMA` did not list `citations`, and Ollama's schema-constrained decoding cannot emit an unlisted field, so the model rambled to the token cap, gave invalid JSON and hit the fallback text. The fix (an optional `citations` array in the schema, `PROMPT_VERSION` bumped) is in `src/cea/agent.py`. The as-found run is kept in `docs/evaluation/run1-as-found/`. It was found on the held-out run; it is a schema defect, not corpus-specific tuning, and is disclosed here.
- The remaining gap is model behaviour (llama3.1 often leaves `citations` empty). It was not tuned on held-out.

**Latency.** The 5 s target is not met with a local 8B model on a 6 GB laptop GPU (median 5.8 s). It is plausible with a hosted model or a smaller local one, but we have no measurement for either. Cache hits are instant, but the target is defined on cold requests.

**Held-out discipline.** Recovery, clustering, the catalog and the oracle fixes were designed on dev only. The held-out split was first read in this milestone, and the tool refuses it without `--i-am-milestone-5`. The only code change made after seeing held-out numbers is the schema field above. No corpus or sidecar file was modified.

**Limitations.**
- Small sets: 20 held-out programs, 7 single-fault cascades, 18 fixable units. One program moves a percentage by 4 to 14 points.
- Programs and sidecars were written by the compiler's author.
- One local model, one machine, one temperature; LLM results vary run to run.
- No Gemini measurement; no user study yet.
- A verified fix is not a proven-correct fix. Root accuracy compares sidecar (code, line) pairs, not a human reading of the message.
- Warning roots count as displayed errors in F2.

## 4. User study

Not run. The ready-to-run protocol (counterbalanced within-subjects design, dev-split task programs, timing sheet, consent note that code snippets go to the LLM provider unless Ollama is used) is in `docs/evaluation/user-study.md`.

## 5. Reproduce

```
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
CEA_LLM_FALLBACK_MODEL=llama3.1 python tools/evaluate.py --i-am-milestone-5 --llm env --dev-llm env
python tools/evaluate.py --llm fake --splits dev       # no model needed, pipeline-only
```
