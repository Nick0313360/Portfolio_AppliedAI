import argparse
import time

import db
import sql_agent

QUESTIONS = [
    ("How much did I spend on transport in March 2026?",
     "SELECT SUM(amount) FROM expenses WHERE category = 'transport' AND date BETWEEN '2026-03-01' AND '2026-03-31'"),
    ("How many expenses did I have in total in 2026?",
     "SELECT COUNT(*) FROM expenses WHERE date BETWEEN '2026-01-01' AND '2026-12-31'"),
    ("What is the average amount of a food expense?",
     "SELECT AVG(amount) FROM expenses WHERE category = 'food'"),
    ("How many health expenses were there in July 2026?",
     "SELECT COUNT(*) FROM expenses WHERE category = 'health' AND date BETWEEN '2026-07-01' AND '2026-07-31'"),
    ("What was my single most expensive shopping purchase?",
     "SELECT MAX(amount) FROM expenses WHERE category = 'shopping'"),
    ("How much did I spend on entertainment between 2026-04-01 and 2026-06-30?",
     "SELECT SUM(amount) FROM expenses WHERE category = 'entertainment' AND date BETWEEN '2026-04-01' AND '2026-06-30'"),
    ("Which category did I spend the most on from January to June 2026?",
     "SELECT category FROM expenses WHERE date BETWEEN '2026-01-01' AND '2026-06-30' "
     "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1"),
    ("How much did I spend in total per category in 2026?",
     "SELECT category, SUM(amount) FROM expenses WHERE date BETWEEN '2026-01-01' AND '2026-12-31' GROUP BY category"),
    ("What were my total food expenses in August 2026 and in September 2026? One total per month.",
     "SELECT SUM(amount) FROM expenses WHERE category = 'food' AND date BETWEEN '2026-08-01' AND '2026-09-30' "
     "GROUP BY strftime('%Y-%m', date)"),
    ("What is my average total spending per month in 2026, over all categories?",
     "SELECT AVG(total) FROM (SELECT SUM(amount) AS total FROM expenses "
     "WHERE date BETWEEN '2026-01-01' AND '2026-12-31' GROUP BY strftime('%Y-%m', date))"),
]


def check_ground_truth():
    truths = []
    for question, sql in QUESTIONS:
        rows = db.run_query(sql)
        if not rows or rows[0][0] is None:
            raise ValueError(f"Ground truth is empty for: {question}")
        truths.append(rows)
    return truths


def values_equal(a, b):
    numbers = (int, float)
    if isinstance(a, numbers) and isinstance(b, numbers):
        return abs(a - b) <= 0.01
    return str(a) == str(b)


def results_match(predicted, truth):
    if not isinstance(predicted, list) or len(predicted) != len(truth):
        return False
    unused = list(predicted)
    for truth_row in truth:
        match = next((p for p in unused if all(any(values_equal(t, v) for v in p) for t in truth_row)), None)
        if match is None:
            return False
        unused.remove(match)
    return True


def md_cell(sql):
    return sql.replace("|", "\\|").replace("\n", " ")


def run_eval(limit=None, path="outputs/results.md"):
    db.create_database()
    truths = check_ground_truth()
    start = time.time()
    rows, n = [], len(QUESTIONS[:limit])
    for i, ((question, _), truth) in enumerate(zip(QUESTIONS[:limit], truths), 1):
        print(f"[{i}/{n}] {question}")
        plain = sql_agent.answer_with_sql(question, reflect=False)
        reflected = sql_agent.answer_with_sql(question, reflect=True)
        ok_plain, ok_reflect = results_match(plain["final_result"], truth), results_match(reflected["final_result"], truth)
        print(f"      without reflection: {'✅' if ok_plain else '❌'}   with reflection: {'✅' if ok_reflect else '❌'}")
        rows.append((question, ok_plain, ok_reflect, reflected["sql_v1"], reflected["sql_v2"]))

    without, with_ = sum(r[1] for r in rows), sum(r[2] for r in rows)
    lines = ["# Evaluation results: SQL component only", "",
             f"Generation model: `{sql_agent.llm.MODEL_NAME}`, reflection model: "
             f"`{sql_agent.REFLECT_MODEL}`. This evaluates only `sql_agent.answer_with_sql` "
             "(the SQL step), not the planner or the final natural-language answer.", "",
             f"**Accuracy without reflection: {without}/{n} → with reflection: {with_}/{n}**", "",
             f"Total runtime: {time.time() - start:.0f} s", "",
             "| Question | Correct without reflection | Correct with reflection | V1 SQL | V2 SQL |",
             "|---|---|---|---|---|"]
    lines += [f"| {q} | {'✅' if a else '❌'} | {'✅' if b else '❌'} | `{md_cell(v1)}` | `{md_cell(v2)}` |"
              for q, a, b, v1, v2 in rows]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWithout reflection: {without}/{n} → with reflection: {with_}/{n}. Saved {path}.")
    return without, with_, n


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate the SQL agent with and without reflection.")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N questions")
    run_eval(parser.parse_args().limit)
