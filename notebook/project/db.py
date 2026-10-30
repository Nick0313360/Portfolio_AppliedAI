import random
import sqlite3
from datetime import date, timedelta

DB_PATH = "expenses.db"
CATEGORIES = ["food", "transport", "rent", "entertainment", "shopping", "health", "subscriptions"]
RENT_AMOUNT = 950.0
START, END = date(2026, 1, 1), date(2026, 10, 28)

PROFILES = {
    "food": [("groceries", 15, 80), ("lunch", 8, 18), ("coffee", 2, 5), ("dinner out", 25, 60)],
    "transport": [("bus ticket", 2, 4), ("train ticket", 8, 40), ("taxi", 12, 35), ("fuel", 40, 70)],
    "entertainment": [("cinema", 9, 15), ("concert", 30, 80), ("museum", 8, 20)],
    "shopping": [("clothes", 20, 120), ("books", 10, 35), ("shoes", 50, 130)],
    "health": [("pharmacy", 5, 30), ("dentist co-pay", 40, 90), ("vitamins", 8, 25)],
    "subscriptions": [("streaming", 9, 15), ("music app", 10, 11), ("phone plan", 15, 25)],
}


def create_database(path=DB_PATH, n_rows=300, seed=42):
    rng = random.Random(seed)
    rows = []
    month = START
    while month <= END:
        rows.append((month.isoformat(), "rent", "monthly rent", RENT_AMOUNT))
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    days = (END - START).days
    while len(rows) < n_rows:
        category = rng.choice(list(PROFILES))
        description, low, high = rng.choice(PROFILES[category])
        day = START + timedelta(days=rng.randint(0, days))
        rows.append((day.isoformat(), category, description, round(rng.uniform(low, high), 2)))
    rows.sort()

    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE IF EXISTS expenses")
        conn.execute(
            "CREATE TABLE expenses (id INTEGER PRIMARY KEY, date TEXT, category TEXT, "
            "description TEXT, amount REAL)"
        )
        conn.executemany("INSERT INTO expenses (date, category, description, amount) VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def get_schema():
    return (
        "CREATE TABLE expenses (\n"
        "  id INTEGER PRIMARY KEY,\n"
        "  date TEXT,         -- format 'YYYY-MM-DD'\n"
        "  category TEXT,     -- one of: " + ", ".join(CATEGORIES) + "\n"
        "  description TEXT,\n"
        "  amount REAL        -- always positive, in euros\n"
        ")"
    )


def run_query(sql, path=DB_PATH):
    with sqlite3.connect(path) as conn:
        return conn.execute(sql).fetchall()


if __name__ == "__main__":
    print(f"Created {create_database()} rows in {DB_PATH}")
    for row in run_query("SELECT * FROM expenses LIMIT 5"):
        print(row)
    print("\nTotal per category:")
    for category, total in run_query("SELECT category, ROUND(SUM(amount), 2) FROM expenses GROUP BY category ORDER BY 2 DESC"):
        print(f"  {category:<14} {total:>9.2f}")
