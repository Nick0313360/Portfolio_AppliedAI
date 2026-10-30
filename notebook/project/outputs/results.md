# Evaluation results: SQL component only

This file combines two runs of `python eval.py` (2026-10-29, Apple Silicon MPS, greedy decoding). Running `eval.py` again overwrites it with a single run.
Both runs use the same generation model, prompts and questions; only `REFLECT_MODEL` differs. This evaluates only `sql_agent.answer_with_sql` (the SQL step).

## Comparison

| Run | Generation model | Reflection model | Without reflection | With reflection | Runtime |
|---|---|---|---|---|---|
| A | Qwen2.5-1.5B-Instruct | Qwen2.5-1.5B-Instruct | 6/10 | 6/10 | 53 s |
| B | Qwen2.5-1.5B-Instruct | Qwen2.5-3B-Instruct | 6/10 | **8/10** | 309 s (155 s of it loading the 3B model) |

| Question | A: 1.5B reflects | B: 3B reflects |
|---|---|---|
| Q1 transport in March 2026 | ❌ (V2 dropped the category filter) | ✅ fixed `LIKE '%2026-03'` → `LIKE '2026-03-%'` |
| Q4 health expenses in July 2026 | ❌ ("the query is correct", result 0) | ✅ fixed `LIKE '%2026-07'` → `LIKE '%2026-07%'` |
| Q9 food per month, Aug + Sep | ❌ | ❌ (one combined total, no GROUP BY) |
| Q10 average monthly total | ❌ | ❌ (AVG of single expenses per month) |
| other 6 questions | ✅ | ✅ |

**Interpretation.** The "without reflection" column is identical in both runs (6/10, same V1 SQL), as expected with the same generation model and greedy decoding, so the difference comes only from the reflection model. With the 1.5B model reviewing its own SQL, reflection changed nothing useful. The 3B reviewer fixed both broken date patterns, including Q4, where the result was a plausible-looking `0` that was not marked EMPTY. It did not fix the two questions that need a different query *structure* (GROUP BY per month, an average of monthly totals): it said they were correct. So a stronger critic helps with errors it can see in the result, not with wrong logic that still returns a believable number. Caveats: 10 questions is a small sample (+2 could be noise), the two fixes are the same kind of error, the prompts were tuned while using the 1.5B model, and run B took ~5.8× longer, mostly the one-time 3B load.

## Run A: reflection with Qwen2.5-1.5B-Instruct
Generation model: `Qwen/Qwen2.5-1.5B-Instruct`, reflection model: `Qwen/Qwen2.5-1.5B-Instruct`. This evaluates only `sql_agent.answer_with_sql` (the SQL step), not the planner or the final natural-language answer.

**Accuracy without reflection: 6/10 → with reflection: 6/10**

Total runtime: 53 s

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

## Run B: reflection with Qwen2.5-3B-Instruct
Generation model: `Qwen/Qwen2.5-1.5B-Instruct`, reflection model: `Qwen/Qwen2.5-3B-Instruct`. This evaluates only `sql_agent.answer_with_sql` (the SQL step), not the planner or the final natural-language answer.

**Accuracy without reflection: 6/10 → with reflection: 8/10**

Total runtime: 309 s

| Question | Correct without reflection | Correct with reflection | V1 SQL | V2 SQL |
|---|---|---|---|---|
| How much did I spend on transport in March 2026? | ❌ | ✅ | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date LIKE '%2026-03' AND category = 'transport';` | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date LIKE '2026-03-%' AND category = 'transport'` |
| How many expenses did I have in total in 2026? | ✅ | ✅ | `SELECT COUNT(*) FROM expenses WHERE strftime('%Y', date) = '2026';` | `SELECT COUNT(*) FROM expenses WHERE strftime('%Y', date) = '2026'` |
| What is the average amount of a food expense? | ✅ | ✅ | `SELECT AVG(amount) FROM expenses WHERE category = 'food'` | `SELECT AVG(amount) FROM expenses WHERE category = 'food'` |
| How many health expenses were there in July 2026? | ❌ | ✅ | `SELECT COUNT(*) FROM expenses WHERE date LIKE '%2026-07' AND category = 'health'` | `SELECT COUNT(*) FROM expenses WHERE date LIKE '%2026-07%' AND category = 'health'` |
| What was my single most expensive shopping purchase? | ✅ | ✅ | `SELECT MAX(amount) AS max_spent FROM expenses WHERE category = 'shopping';` | `SELECT MAX(amount) AS max_spent FROM expenses WHERE category = 'shopping'` |
| How much did I spend on entertainment between 2026-04-01 and 2026-06-30? | ✅ | ✅ | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date BETWEEN '2026-04-01' AND '2026-06-30' AND category = 'entertainment';` | `SELECT SUM(amount) AS total_spent FROM expenses WHERE date BETWEEN '2026-04-01' AND '2026-06-30' AND category = 'entertainment'` |
| Which category did I spend the most on from January to June 2026? | ✅ | ✅ | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y-%m', date) BETWEEN '2026-01' AND '2026-06' GROUP BY category ORDER BY total_spent DESC LIMIT 1;` | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y-%m', date) BETWEEN '2026-01' AND '2026-06' GROUP BY category ORDER BY total_spent DESC LIMIT 1` |
| How much did I spend in total per category in 2026? | ✅ | ✅ | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY category ORDER BY total_spent DESC;` | `SELECT category, SUM(amount) AS total_spent FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY category ORDER BY total_spent DESC` |
| What were my total food expenses in August 2026 and in September 2026? One total per month. | ❌ | ❌ | `SELECT SUM(amount) AS total FROM expenses WHERE strftime('%Y-%m', date) IN ('2026-08', '2026-09') AND category = 'food'` | `SELECT SUM(amount) AS total FROM expenses WHERE strftime('%Y-%m', date) IN ('2026-08', '2026-09') AND category = 'food'` |
| What is my average total spending per month in 2026, over all categories? | ❌ | ❌ | `SELECT strftime('%Y-%m', date) AS month, AVG(amount) FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY strftime('%Y-%m', date);` | `SELECT strftime('%Y-%m', date) AS month, AVG(amount) FROM expenses WHERE strftime('%Y', date) = '2026' GROUP BY strftime('%Y-%m', date);` |
