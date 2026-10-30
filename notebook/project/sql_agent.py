import logging
import os
import sys

import db
import llm
import tools

log = logging.getLogger(__name__)
REFLECT_MODEL = os.environ.get("REFLECT_MODEL", llm.MODEL_NAME)
SYSTEM = "You are an expert SQLite analyst. Reply with only a JSON object, no other text."


def ask_for_json(prompt, required_keys, model_name=llm.MODEL_NAME):
    reply = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                     model_name=model_name)
    data = llm.extract_json(reply)
    for key in required_keys:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"Model JSON is missing a non-empty string {key!r}: {data}")
    return data


def execute(sql):
    try:
        return tools.run_sql(sql)
    except Exception as e:
        log.warning("SQL failed: %s | %s", sql, e)
        return f"ERROR: {e}"


def generate_sql(question):
    prompt = (f"Database schema:\n{db.get_schema()}\n\nToday is {tools.get_today()}.\n"
              "Write ONE SQLite SELECT query that answers the question. Dates are TEXT like '2026-03-15'. "
              "Example filters: March 2026 is strftime('%Y-%m', date) = '2026-03', the year 2026 is "
              "strftime('%Y', date) = '2026'. Add a date or category "
              "filter ONLY if the question mentions it. 'How much spent' and 'most expensive category' "
              "mean SUM(amount), 'how many' means COUNT(*), 'average' means AVG(amount).\n"
              f"Question: {question}\n"
              'Reply as JSON: {"sql": "SELECT ..."}')
    try:
        return ask_for_json(prompt, ["sql"])["sql"]
    except ValueError as e:
        log.warning("V1 generation failed: %s", e)
        return ""


def reflect_sql(question, sql, result):
    shown = result if isinstance(result, str) else f"{result[:10]}" + (" ..." if len(result) > 10 else "")
    if result in ([], [(None,)]):
        shown += "  <- EMPTY: no rows matched, the filters are probably wrong"
    prompt = (f"Database schema:\n{db.get_schema()}\n\nToday is {tools.get_today()}.\n"
              f"Question: {question}\nSQL: {sql}\nActual result of running it: {shown}\n\n"
              "Check: 1) date and category filters match the question, 2) the right aggregation "
              "(SUM, AVG, COUNT, MAX, GROUP BY), 3) the result is plausible (no error, not empty, "
              "not negative), 4) the result really answers the question, 5) there is no date or "
              "category filter that the question does not mention.\n"
              "Give short feedback and the corrected SQL (or the same SQL if it is correct).\n"
              'Reply as JSON: {"feedback": "...", "sql": "SELECT ..."}')
    try:
        data = ask_for_json(prompt, ["feedback", "sql"], model_name=REFLECT_MODEL)
        return data["feedback"], data["sql"]
    except ValueError as e:
        log.warning("Reflection failed: %s", e)
        return f"ERROR: reflection output unusable ({e}); kept V1.", sql


def answer_with_sql(question, reflect=True):
    sql_v1 = generate_sql(question)
    result_v1 = execute(sql_v1)
    if not reflect:
        return {"sql_v1": sql_v1, "result_v1": result_v1, "feedback": None,
                "sql_v2": sql_v1, "result_v2": result_v1, "final_result": result_v1}
    feedback, sql_v2 = reflect_sql(question, sql_v1, result_v1)
    result_v2 = execute(sql_v2)
    return {"sql_v1": sql_v1, "result_v1": result_v1, "feedback": feedback,
            "sql_v2": sql_v2, "result_v2": result_v2, "final_result": result_v2}


def print_trace(out):
    for key in ["sql_v1", "result_v1", "feedback", "sql_v2", "result_v2"]:
        print(f"{key:>10}: {out[key]}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    print_trace(answer_with_sql(" ".join(sys.argv[1:]) or "total spent on food in September 2026"))
