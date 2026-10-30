import os
import re
import sqlite3
import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import db

OUTPUT_DIR = "outputs"


def get_today():
    return datetime.date.today().isoformat()


def run_sql(query):
    cleaned = re.sub(r"--[^\n]*|/\*.*?\*/", " ", query, flags=re.DOTALL).strip().rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("run_sql rejected the query: only one statement is allowed.")
    if not re.match(r"select\b", cleaned, re.IGNORECASE):
        raise ValueError("run_sql rejected the query: only SELECT statements are allowed (read-only).")
    return db.run_query(cleaned)


def add_expense(date, category, description, amount, confirm_fn=input):
    amount = float(amount)
    if amount <= 0:
        raise ValueError(f"add_expense rejected: amount must be > 0, got {amount}.")
    if category not in db.CATEGORIES:
        raise ValueError(f"add_expense rejected: unknown category {category!r}. Allowed: {', '.join(db.CATEGORIES)}.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        raise ValueError(f"add_expense rejected: date must be YYYY-MM-DD, got {date!r}.")
    datetime.date.fromisoformat(date)

    summary = f"{date} | {category} | {description} | {amount:.2f} EUR"
    answer = confirm_fn(f"Add expense: {summary}\nConfirm? (y/n) ")
    if answer.strip().lower() != "y":
        return f"Cancelled by user: nothing was written ({summary})."
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute("INSERT INTO expenses (date, category, description, amount) VALUES (?, ?, ?, ?)",
                     (date, category, description, amount))
    return f"Added expense: {summary}."


def make_chart(query, title):
    rows = run_sql(query)
    if not rows or len(rows[0]) != 2:
        raise ValueError(f"make_chart needs rows of (label, value); got {rows[:3]}.")
    labels, values = [str(r[0]) for r in rows], [float(r[1]) for r in rows]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, re.sub(r"\W+", "_", title.lower()).strip("_") + ".png")
    plt.figure(figsize=(8, 4))
    plt.bar(labels, values)
    plt.title(title)
    plt.ylabel("EUR")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


TOOLS = {
    "get_today": {"fn": get_today, "args": {},
                  "description": "Returns today's date as YYYY-MM-DD."},
    "run_sql": {"fn": run_sql, "args": {"query": "str"},
                "description": "Runs ONE read-only SQL SELECT on the expenses table and returns the rows."},
    "add_expense": {"fn": add_expense, "args": {"date": "str", "category": "str", "description": "str", "amount": "float"},
                    "description": "Adds a new expense (date YYYY-MM-DD, category from the allowed list, "
                                   "amount in euros > 0). Asks the user to confirm first."},
    "make_chart": {"fn": make_chart, "args": {"query": "str", "title": "str"},
                   "description": "Runs a SELECT returning (label, value) rows, e.g. category and SUM(amount), "
                                  "and saves a bar chart PNG."},
}


def describe_tools():
    lines = []
    for name, tool in TOOLS.items():
        args = ", ".join(f"{a}: {t}" for a, t in tool["args"].items())
        lines.append(f"- {name}({args}): {tool['description']}")
    return "\n".join(lines)
