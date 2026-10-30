# Local Expense Agent

## Goal
A small command-line agent that answers questions about **fake** personal expenses stored in SQLite, and adds new expenses after the user confirms. It runs **fully locally** with a small open model (Hugging Face `transformers`): no API keys, no paid services, no agent framework.
It shows, in about 520 lines of plain Python (plus a 190-line `smoke_test.py`), the patterns from the *Agentic AI* course labs: tool use, reflection with external feedback, planning, human-in-the-loop, error visibility and evaluation.

Example requests: *"How much did I spend on food in September 2026?"*, *"What is my most expensive category this year?"*, *"Add a 12.50 euro lunch for today."*, *"Make a chart of spending per category."*

| File | Role |
|---|---|
| `db.py` | fake data (seed 42) + SQLite helpers |
| `llm.py` | load the local model once, `chat()`, `extract_json()` |
| `tools.py` | 4 tools + registry, read-only SQL guard, confirmation |
| `sql_agent.py` | text-to-SQL with reflection |
| `agent.py` | planner + plan validation + executor + CLI |
| `eval.py` | 10-question eval, with vs without reflection |
| `smoke_test.py` | checks grouped in 6 steps: `python smoke_test.py 6` |

## Setup
```
python -m venv .venv
.venv\Scripts\activate          (Windows)
source .venv/bin/activate       (macOS/Linux)
pip install -r requirements.txt
python db.py                    # creates expenses.db with 300 fake expenses (seed 42)
python agent.py --trace
```
Run once instead of interactively: `python agent.py --trace "How much did I spend on food in September 2026?"`.
Checks and evaluation: `python smoke_test.py 6` (55 checks, a few minutes), `python eval.py --limit 3` (quick) or `python eval.py` (all 10 questions). Both eval commands overwrite `outputs/results.md`.

**Model.** The default is `Qwen/Qwen2.5-1.5B-Instruct` (~3 GB download on first run, cached in `~/.cache/huggingface`). Choose another with the `MODEL_NAME` environment variable:
`Qwen/Qwen2.5-0.5B-Instruct` (~1 GB, faster, less accurate) for weak PCs, `Qwen/Qwen2.5-3B-Instruct` (~6 GB, slower, better) for strong ones.
```
MODEL_NAME=Qwen/Qwen2.5-0.5B-Instruct python agent.py      (macOS/Linux)
set MODEL_NAME=Qwen/Qwen2.5-0.5B-Instruct                  (Windows, then run python agent.py)
```
Optionally, `REFLECT_MODEL` picks a different model for the reflection step only (default: the same as `MODEL_NAME`), e.g. a bigger model reviewing a smaller one's SQL:
```
REFLECT_MODEL=Qwen/Qwen2.5-3B-Instruct python eval.py     (macOS/Linux; both models are loaded, ~9 GB RAM)
```
The model runs on an NVIDIA GPU (CUDA) or Apple Silicon GPU (MPS) if present, otherwise on the CPU. Loading takes a few seconds once cached; each answer takes seconds (GPU) to tens of seconds (CPU).

## Architecture
```
 user request
      │
      ▼
 ┌──────────────┐   tool descriptions (describe_tools)
 │   PLANNER    │◄─ + today + categories + 3 examples
 │  (LLM, JSON) │
 └──────┬───────┘
        │ {"steps": [{"tool", "args", "why"}]}   parsed with extract_json
        ▼
 ┌──────────────┐   unknown tool / missing args / >5 steps / not a list
 │ validate_plan│──────────────► ⚠️ "Planning failed, nothing was executed"
 └──────┬───────┘
        │ valid plan
        ▼
 ┌────────────────────────── EXECUTOR (our code runs each step) ──────────────────────────┐
 │  get_today   run_sql (read-only guard)   add_expense (Confirm? y/n)   make_chart (PNG) │
 │                                                                                        │
 │  ask_sql_agent ──► SQL AGENT:  generate V1 ─► execute ─► reflect on REAL result/error  │
 │                                                              ─► V2 ─► execute          │
 └──────────────┬──────────────────────────────────────────────┬──────────────────────────┘
                │ results                                       │ exception
                ▼                                               ▼
 ┌──────────────┐                                  ⚠️ "Step N failed: <error>" (logged)
 │ ANSWER (LLM) │──► short friendly answer
 └──────────────┘
```
`--trace` prints the plan, every tool call and every result.

## Concept map

| Course concept | File : function |
|---|---|
| Tool use (manual tool calling, tool registry/schema) | `tools.py`: `TOOLS`, `describe_tools()`; executed in `agent.py` |
| Sandboxing (read-only SQL guard) | `tools.py`: `run_sql()` |
| Human-in-the-loop | `tools.py`: `add_expense()` (`Confirm? (y/n)`) |
| Reflection with external feedback | `sql_agent.py`: `answer_with_sql()`, `reflect_sql()` (gets the real result/error from `execute()`) |
| LLM output is untrusted (parse + validate) | `llm.py`: `extract_json()`; `sql_agent.py`: `ask_for_json()` |
| Planning (LLM writes a JSON plan) | `agent.py`: `PLANNER_PROMPT`, `make_plan()` |
| Validate before executing | `agent.py`: `validate_plan()` |
| Error visibility (no silent `None`) | `agent.py`: `handle()` (always returns a string, `⚠️ Step N failed`), `logging` |
| Defence in depth | a plan with `DELETE` passes `validate_plan` but is still blocked by `tools.run_sql` |

## Evaluation
`python eval.py` runs 10 questions (date ranges, counts, averages, max, "most spent category", group-by, a two-month comparison, an average of monthly totals) through `sql_agent.answer_with_sql`, once **without** and once **with** reflection, and compares the result with a hand-written ground-truth SQL (numbers ±0.01, row order and extra label columns ignored).
**This is a component-level eval: it evaluates only the SQL step**, not the planner or the final natural-language answer.

**Run A**: generation and reflection both `Qwen/Qwen2.5-1.5B-Instruct` (Apple Silicon MPS, copied from `outputs/results.md`):

**Accuracy without reflection: 6/10 → with reflection: 6/10.** Total runtime: 53 s.

| Question | Correct without reflection | Correct with reflection | V1 SQL | V2 SQL |
|---|---|---|---|---|
| How much did I spend on transport in March 2026? | ❌ | ❌ | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date LIKE '%2026-03' AND category = 'transport';` | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date LIKE '%2026-03%'` |
| How many expenses did I have in total in 2026? | ✅ | ✅ | `SELECT COUNT(*) FROM expenses WHERE strftime('%Y', date) = '2026';` | `SELECT COUNT(*) FROM expenses WHERE strftime('%Y', date) = '2026'` |
| What is the average amount of a food expense? | ✅ | ✅ | `SELECT AVG(amount) FROM expenses WHERE category = 'food'` | `SELECT AVG(amount) FROM expenses WHERE category = 'food'` |
| How many health expenses were there in July 2026? | ❌ | ❌ | `SELECT COUNT(*) FROM expenses WHERE date LIKE '%2026-07' AND category = 'health'` | `SELECT COUNT(*) FROM expenses WHERE date LIKE '%2026-07' AND category = 'health'` |
| What was my single most expensive shopping purchase? | ✅ | ✅ | `SELECT MAX(amount) AS max_spent FROM expenses WHERE category = 'shopping';` | `SELECT MAX(amount) AS max_spent FROM expenses WHERE category = 'shopping'` |
| How much did I spend on entertainment between 2026-04-01 and 2026-06-30? | ✅ | ✅ | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date BETWEEN '2026-04-01' AND '2026-06-30' AND category = 'entertainment';` | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date BETWEEN '2026-04-01' AND '2026-06-30' AND category = 'entertainment'` |
| Which category did I spend the most on from January to June 2026? | ✅ | ✅ | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y-%m', date) BETWEEN '2026-01' AND '2026-06' GROUP BY category ORDER BY total_spent DESC LIMIT 1;` | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y-%m', date) BETWEEN '2026-01' AND '2026-06' GROUP BY category ORDER BY total_spent DESC LIMIT 1;` |
| How much did I spend in total per category in 2026? | ✅ | ✅ | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY category ORDER BY total_spent DESC;` | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY category ORDER BY total_spent DESC` |
| What were my total food expenses in August 2026 and in September 2026? One total per month. | ❌ | ❌ | `SELECT SUM(amount) AS total FROM expenses WHERE strftime('%Y-%m', date) IN ('2026-08', '2026-09') AND category = 'food'` | `SELECT SUM(amount) AS total FROM expenses WHERE strftime('%Y-%m', date) IN ('2026-08', '2026-09') AND category = 'food'` |
| What is my average total spending per month in 2026, over all categories? | ❌ | ❌ | `SELECT strftime('%Y-%m', date) AS month, AVG(amount) FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY strftime('%Y-%m', date);` | `SELECT strftime('%Y-%m', date) AS month, AVG(amount) FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY strftime('%Y-%m', date)` |

**Interpretation.** Reflection did **not** improve accuracy here. In 9 of 10 questions the model answered "the query is correct" and returned the same SQL, even when the result was a suspicious `0`. It only changed the SQL when the result was clearly marked EMPTY (Q1), and then it fixed the date filter but dropped the category filter, so the answer was still wrong. The failures are mostly date filters written as `LIKE '%2026-03'` (wrong pattern) and harder aggregations (one total per month, average of monthly totals). A 1.5B model is weak at judging its own SQL; next steps would be to flag suspicious results like `0` as well, try a bigger reflection model (done below), and tune prompts on separate dev questions (two eval questions influenced one prompt iteration).

### A bigger model as the critic (`REFLECT_MODEL`)
Same generation model, prompts and questions; only the reflection step uses a different model (`REFLECT_MODEL=Qwen/Qwen2.5-3B-Instruct python eval.py`).

| Run | Generation | Reflection | Without reflection | With reflection | Runtime |
|---|---|---|---|---|---|
| A | 1.5B | 1.5B | 6/10 | 6/10 | 53 s |
| B | 1.5B | **3B** | 6/10 | **8/10** | 309 s (155 s loading the 3B model) |

The "without reflection" column is identical in both runs (same V1 SQL, greedy decoding), so the +2 comes only from the better critic. The 3B reviewer fixed both broken date patterns: Q1 (`LIKE '%2026-03'` → `'2026-03-%'`) and Q4, where the wrong result was a believable `0` that our EMPTY marker doesn't flag. It still approved the two queries with the wrong *structure* (Q9: no GROUP BY per month; Q10: average of single expenses instead of monthly totals), because those return plausible numbers. So reflection with external feedback works when the critic is strong enough to read the feedback, and a small model is a weak judge of its own output. A bigger critic helps with errors that show in the result, not with wrong logic behind a believable number. Be careful with this conclusion: 10 questions is a small sample, both fixes are the same kind of error, the prompts were tuned while using the 1.5B model, and run B was ~6× slower and needs ~9 GB of RAM for both models. Full tables for both runs are in `outputs/results.md`.

## Limitations
- **Small model, slow hardware.** A 1.5B model makes SQL mistakes (wrong date patterns, wrong aggregation) and often approves its own wrong SQL during reflection. On a CPU each answer takes tens of seconds; small prompt changes can flip unrelated answers.
- **The eval covers only the SQL component**, with 10 questions. It doesn't measure planning quality or the final answer text, and 10 questions is too few for strong conclusions.
- **Fake data only.** 300 generated rows with a fixed seed; real bank data would be messier (refunds, currencies, typos).
- **The planner prompt contains few-shot examples**; unusual requests can still produce a wrong tool choice. Invalid plans are rejected, but a *valid but wrong* plan is not detected.
- **Read-only guard is simple, not production-grade.** `run_sql` strips comments, then allows only one statement starting with `SELECT`. It is a text check, not a SQL parser:
  a `;` or `--` *inside a string literal* (e.g. `WHERE description = 'a;b'`) is wrongly rejected or altered, and `WITH ... SELECT` queries are rejected. A real system would also open the database in read-only mode or use a database user without write rights.

## AI-assistance statement
Code generated with Claude Code; specified, validated, tested and explained by Nick Golovanov.
