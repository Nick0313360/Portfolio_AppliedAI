import argparse
import json
import logging

import db
import llm
import sql_agent
import tools

log = logging.getLogger("agent")
MAX_STEPS = 5
PLANNER_ARGS = {**{name: t["args"] for name, t in tools.TOOLS.items()}, "ask_sql_agent": {"question": "str"}}

PLANNER_PROMPT = """You plan which tools to call for a user's expense request.
Tools:
{tools}
- ask_sql_agent(question: str): Answers a question about the expense data (totals, averages,
  counts, most expensive, comparisons). Best choice for any question about spending.

Today is {today}. Categories: {categories}.
Reply with only JSON: {{"steps": [{{"tool": "...", "args": {{...}}, "why": "..."}}]}} (1 to {max_steps} steps).
Examples:
Request: How much did I spend on health in May 2026?
{{"steps": [{{"tool": "ask_sql_agent", "args": {{"question": "How much did I spend on health in May 2026?"}}, "why": "data question"}}]}}
Request: Add a 30 euro taxi on 2026-05-03
{{"steps": [{{"tool": "add_expense", "args": {{"date": "2026-05-03", "category": "transport", "description": "taxi", "amount": 30}}, "why": "user wants to add an expense"}}]}}
Request: Chart my spending per month
{{"steps": [{{"tool": "make_chart", "args": {{"query": "SELECT strftime('%m', date), SUM(amount) FROM expenses GROUP BY 1", "title": "Spending per month"}}, "why": "user wants a chart"}}]}}

Request: {request}"""


def make_plan(request, llm_fn=llm.chat):
    prompt = PLANNER_PROMPT.format(tools=tools.describe_tools(), today=tools.get_today(),
                                   categories=", ".join(db.CATEGORIES), max_steps=MAX_STEPS, request=request)
    return llm.extract_json(llm_fn([{"role": "user", "content": prompt}], max_new_tokens=250))


def validate_plan(plan):
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list) or not steps:
        raise ValueError("plan must contain a non-empty list 'steps'")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"plan has {len(steps)} steps, maximum is {MAX_STEPS}")
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("tool") not in PLANNER_ARGS:
            raise ValueError(f"step {i}: unknown tool {step.get('tool') if isinstance(step, dict) else step!r}")
        args = step.get("args")
        if not isinstance(args, dict):
            raise ValueError(f"step {i}: 'args' must be an object")
        missing = [a for a in PLANNER_ARGS[step["tool"]] if a not in args]
        if missing:
            raise ValueError(f"step {i} ({step['tool']}): missing args {missing}")
    return steps


def run_step(step, confirm_fn):
    args = {a: step["args"][a] for a in PLANNER_ARGS[step["tool"]]}
    if step["tool"] == "ask_sql_agent":
        out = sql_agent.answer_with_sql(args["question"])
        return {"sql": out["sql_v2"], "result": out["final_result"]}
    if step["tool"] == "add_expense":
        return tools.add_expense(**args, confirm_fn=confirm_fn)
    return tools.TOOLS[step["tool"]]["fn"](**args)


def handle(request, trace=False, llm_fn=llm.chat, confirm_fn=input):
    try:
        steps = validate_plan(make_plan(request, llm_fn))
    except Exception as e:
        log.error("Planning failed: %s", e)
        return f"⚠️ Planning failed, nothing was executed: {e}"
    if trace:
        print("PLAN:", json.dumps(steps, indent=2))

    results = []
    for i, step in enumerate(steps, 1):
        if trace:
            print(f"STEP {i}: {step['tool']}({step['args']})")
        try:
            result = run_step(step, confirm_fn)
        except Exception as e:
            log.error("Step %d (%s) failed: %s", i, step["tool"], e)
            return f"⚠️ Step {i} failed: {e}"
        if trace:
            print(f"RESULT {i}: {result}")
        results.append({"tool": step["tool"], "result": str(result)[:1000]})

    try:
        answer = llm_fn([{"role": "user", "content":
                          f"Request: {request}\nTool results: {json.dumps(results)}\n"
                          "Write a short, friendly answer based ONLY on these results. Amounts are in euros. "
                          "If an action was cancelled, say clearly that nothing was saved."}],
                        max_new_tokens=150)
    except Exception as e:
        log.error("Answer generation failed: %s", e)
        return f"⚠️ Could not write the answer ({e}). Raw results: {results}"
    return answer.strip() or f"⚠️ The model returned an empty answer. Raw results: {results}"


def main():
    parser = argparse.ArgumentParser(description="Local expense agent")
    parser.add_argument("request", nargs="*", help="request to run once (omit for interactive mode)")
    parser.add_argument("--trace", action="store_true", help="print plan, tool calls and results")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if args.request:
        print(handle(" ".join(args.request), trace=args.trace))
        return
    print("Expense agent. Type 'quit' to stop.")
    while (request := input("\nYou: ").strip()) not in ("", "quit", "exit"):
        print("Agent:", handle(request, trace=args.trace))


if __name__ == "__main__":
    main()
