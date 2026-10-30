import argparse
import sys

RESULTS = []


def check(name, condition):
    passed = bool(condition)
    RESULTS.append((name, passed))
    print(f"{'PASS' if passed else 'FAIL'}  {name}")
    return passed


def test_step_1():
    import db

    check("create_database() inserts 300 rows", db.create_database() == 300)
    check("table has exactly 300 rows", db.run_query("SELECT COUNT(*) FROM expenses") == [(300,)])
    check("all amounts > 0", db.run_query("SELECT COUNT(*) FROM expenses WHERE amount <= 0") == [(0,)])
    cats = {c for (c,) in db.run_query("SELECT DISTINCT category FROM expenses")}
    check("all categories allowed", cats <= set(db.CATEGORIES))
    check("dates within 2026-01-01..2026-10-28", db.run_query(
        "SELECT MIN(date) >= '2026-01-01' AND MAX(date) <= '2026-10-28' FROM expenses") == [(1,)])
    total_1 = db.run_query("SELECT SUM(amount) FROM expenses")
    db.create_database()
    check("same seed gives same SUM(amount)", db.run_query("SELECT SUM(amount) FROM expenses") == total_1)
    rent = db.run_query("SELECT substr(date, 1, 7), COUNT(*), MIN(amount), MAX(amount) "
                        "FROM expenses WHERE category = 'rent' GROUP BY 1")
    check("rent once per month (10 months), same amount",
          len(rent) == 10 and all(n == 1 and lo == hi == db.RENT_AMOUNT for _, n, lo, hi in rent))
    schema = db.get_schema()
    check("schema names every column", all(c in schema for c in ["id", "date", "category", "description", "amount"]))


def test_step_2():
    import llm

    check("extract_json: JSON inside chatter", llm.extract_json('Sure! {"a": 1} hope that helps') == {"a": 1})
    check("extract_json: fenced block",
          llm.extract_json('```json\n{"sql": "SELECT 1"}\n```') == {"sql": "SELECT 1"})
    try:
        llm.extract_json("no json here")
        check("extract_json: raises ValueError on no JSON", False)
    except ValueError as e:
        check("extract_json: raises ValueError on no JSON", "No JSON" in str(e))

    reply = llm.chat([{"role": "user", "content": 'Reply with only the JSON {"ok": true}'}], max_new_tokens=20)
    print(f"      raw model output: {reply!r}")
    try:
        check("chat() output parses as JSON", isinstance(llm.extract_json(reply), dict))
    except ValueError as e:
        check(f"chat() output parses as JSON ({e})", False)
    llm.chat([{"role": "user", "content": "Say hi"}], max_new_tokens=5)
    check("model loaded only once for two chat() calls", llm.LOAD_COUNT == 1)


def raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception as e:
        return str(e)
    return None


def test_step_3():
    import os
    import re
    import db
    import tools

    db.create_database()
    check("get_today() is YYYY-MM-DD", re.fullmatch(r"\d{4}-\d{2}-\d{2}", tools.get_today()))
    check("run_sql SELECT works", tools.run_sql("SELECT COUNT(*) FROM expenses") == [(300,)])
    for bad in ["DELETE FROM expenses", "DROP TABLE expenses", "SELECT 1; DROP TABLE expenses",
                "UPDATE expenses SET amount = 0", "/* hi */ delete from expenses", "-- x\nDROP TABLE expenses"]:
        check(f"run_sql rejects {bad!r}", raises(tools.run_sql, bad))
    check("table still has 300 rows", db.run_query("SELECT COUNT(*) FROM expenses") == [(300,)])

    expense = {"date": "2026-10-28", "category": "food", "description": "lunch", "amount": 12.5}
    msg = tools.add_expense(**expense, confirm_fn=lambda _: "n")
    check("add_expense 'n' → cancelled, nothing written",
          "Cancelled" in msg and db.run_query("SELECT COUNT(*) FROM expenses") == [(300,)])
    tools.add_expense(**expense, confirm_fn=lambda _: "y")
    check("add_expense 'y' → 301 rows", db.run_query("SELECT COUNT(*) FROM expenses") == [(301,)])
    db.create_database()
    check("add_expense rejects amount -5", raises(tools.add_expense, **{**expense, "amount": -5}, confirm_fn=lambda _: "y"))
    check("add_expense rejects category 'crypto'",
          raises(tools.add_expense, **{**expense, "category": "crypto"}, confirm_fn=lambda _: "y"))

    path = tools.make_chart("SELECT category, SUM(amount) FROM expenses GROUP BY category", "Smoke test chart")
    check(f"make_chart creates {path}", path.startswith("outputs") and os.path.exists(path))
    desc = tools.describe_tools()
    print(desc)
    check("describe_tools mentions all tools and args",
          all(n in desc for n in tools.TOOLS) and all(a in desc for t in tools.TOOLS.values() for a in t["args"]))


def test_step_4():
    import sql_agent

    keys = {"sql_v1", "result_v1", "feedback", "sql_v2", "result_v2", "final_result"}
    q = "total spent on food in September 2026"
    out = sql_agent.answer_with_sql(q, reflect=False)
    check("reflect=False: all keys, feedback None, sql_v2 == sql_v1",
          set(out) == keys and out["feedback"] is None and out["sql_v2"] == out["sql_v1"])

    bad = sql_agent.execute("SELEKT")
    check("invalid SQL is captured as 'ERROR: ...' text", isinstance(bad, str) and bad.startswith("ERROR:"))
    feedback, fixed = sql_agent.reflect_sql("number of expenses", "SELEKT", bad)
    print(f"      error-path feedback: {feedback!r}\n      error-path V2: {fixed!r}")
    check("reflection on an error returns feedback + SQL without crashing", feedback and isinstance(fixed, str))

    for q in [q, "number of transport expenses in 2026"]:
        out = sql_agent.answer_with_sql(q, reflect=True)
        print(f"      Q: {q}")
        sql_agent.print_trace(out)
        check(f"reflect=True: all keys, non-empty feedback ({q})",
              set(out) == keys and isinstance(out["feedback"], str) and out["feedback"].strip())


def test_step_5():
    import json
    import agent
    import db

    step = {"tool": "run_sql", "args": {"query": "SELECT 1"}, "why": "test"}
    check("validate_plan rejects unknown tool", raises(agent.validate_plan, {"steps": [{"tool": "hack", "args": {}}]}))
    check("validate_plan rejects missing arg", raises(agent.validate_plan, {"steps": [{"tool": "run_sql", "args": {}}]}))
    check("validate_plan rejects 6 steps", raises(agent.validate_plan, {"steps": [step] * 6}))
    check("validate_plan rejects non-list steps", raises(agent.validate_plan, {"steps": "run_sql"}))
    check("validate_plan accepts valid 2-step plan", not raises(agent.validate_plan, {"steps": [
        {"tool": "get_today", "args": {}}, step]}))

    def fake_llm(reply):
        return lambda messages, max_new_tokens=300: reply

    out = agent.handle("hi", llm_fn=fake_llm("I am not JSON"))
    check(f"invalid planner JSON → string starting with ⚠️ ({out[:45]}...)", isinstance(out, str) and out.startswith("⚠️"))
    plan = json.dumps({"steps": [{"tool": "run_sql", "args": {"query": "DELETE FROM expenses"}}]})
    out = agent.handle("delete all", llm_fn=fake_llm(plan))
    check(f"tool exception → '⚠️ Step 1 failed' ({out[:45]}...)", out.startswith("⚠️ Step 1 failed"))
    check("write via plan still blocked (defence in depth)", db.run_query("SELECT COUNT(*) FROM expenses") == [(300,)])

    for request in ["How much did I spend on food in September 2026?", "What is my most expensive category this year?",
                    "Add a 12.50 euro lunch for today.", "Make a chart of spending per category."]:
        print(f"\n      REQUEST: {request}")
        out = agent.handle(request, trace=True, confirm_fn=lambda _: "n")
        print(f"      ANSWER: {out}")
        check(f"handle() returns a non-empty string: {request}", isinstance(out, str) and out.strip())
    check("auto-'n' confirm: still 300 rows", db.run_query("SELECT COUNT(*) FROM expenses") == [(300,)])


def test_step_6():
    import db
    import eval as ev

    db.create_database()
    check(f"eval has 10 questions", len(ev.QUESTIONS) == 10)
    truth_error = raises(ev.check_ground_truth)
    check(f"all ground-truth SQLs run and are non-empty {truth_error or ''}", truth_error is None)
    check("compare: 10.004 vs 10.0 → equal", ev.results_match([(10.004,)], [(10.0,)]))
    check("compare: different row order → equal", ev.results_match([("b", 2), ("a", 1)], [("a", 1), ("b", 2)]))
    check("compare: different values → not equal", not ev.results_match([(11.0,)], [(10.0,)]))
    check("compare: error string vs value → not equal", not ev.results_match("ERROR: no such column", [(10.0,)]))
    check("compare: None vs value → not equal", not ev.results_match([(None,)], [(10.0,)]))
    check("compare: extra label column → equal", ev.results_match([(45.47, "food")], [(45.47,)]))
    check("compare: extra rows → not equal", not ev.results_match([("rent",), ("food",)], [("rent",)]))


STEPS = {1: test_step_1, 2: test_step_2, 3: test_step_3, 4: test_step_4, 5: test_step_5, 6: test_step_6}


def main():
    parser = argparse.ArgumentParser(description="Smoke tests per build step.")
    parser.add_argument("step", type=int, help="run all checks for steps 1..step")
    args = parser.parse_args()

    for step in range(1, args.step + 1):
        if step in STEPS:
            print(f"--- Step {step} ---")
            STEPS[step]()

    failed = [name for name, passed in RESULTS if not passed]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
