# Evaluation results

Generated 2026-10-11 by `python tools/evaluate.py` (LLM: OpenAICompatClient(name='fallback', base_url='http://localhost:11434/v1', model='llama3.1', api_key=none)).

## heldout (20 programs; LLM metrics: real model)

| Metric | Target | Result | Status |
|---|---|---|---|
| Error reduction, single-fault cascading files | >= 70% | 69.6% (23 raw -> 7 shown, 7 files) | NOT MET |
| Error reduction, all cascading files (reported, not the target) | - | 64.0% (25 raw -> 9 shown, 8 files) | - |
| Root-cause accuracy, program exact match | >= 85% | 95.0% | met |
| Root-cause accuracy, root precision / recall | - | 95.7% / 100.0% | - |
| Verified-fix rate (3 attempts) | >= 80% | 66.7% (12/18) | NOT MET |
| Grounding, model itself cites a retrieved rule | >= 90% | 47.8% (11/23) | NOT MET |
| Grounding, after citation validation | >= 90% | 100.0% | met |
| Non-existent citations | 0 | 0 | met |
| Latency, default explanation, median / p90 (50 requests) | < 5 s | 5.81 s / 6.7 s | NOT MET |

## dev (54 programs; LLM metrics: real model)

| Metric | Target | Result | Status |
|---|---|---|---|
| Error reduction, single-fault cascading files | >= 70% | 72.5% (40 raw -> 11 shown, 11 files) | met |
| Error reduction, all cascading files (reported, not the target) | - | 60.0% (50 raw -> 20 shown, 15 files) | - |
| Root-cause accuracy, program exact match | >= 85% | 100.0% | met |
| Root-cause accuracy, root precision / recall | - | 100.0% / 100.0% | - |
| Verified-fix rate (3 attempts) | >= 80% | 50.0% (24/48) | NOT MET |
| Grounding, model itself cites a retrieved rule | >= 90% | 35.6% (21/59) | NOT MET |
| Grounding, after citation validation | >= 90% | 94.9% | met |
| Non-existent citations | 0 | 0 | met |
| Latency, default explanation, median / p90 (50 requests) | < 5 s | 6.21 s / 7.23 s | NOT MET |

Dev F8 with the oracle FakeLLM (pipeline-only): 43/48 = 89.6%.

