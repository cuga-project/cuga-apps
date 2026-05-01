"""Auto-generated MCP server exposing invocable tools for Bird db `debit_card_specializing`.

Run:
    python mcp_server.py            # binds 0.0.0.0:8765 by default

Configuration:
    SQLITE_PATH   path to debit_card_specializing.sqlite (required)
    MCP_PORT      port to bind (default 8765)
"""
from __future__ import annotations
import json, os, sqlite3, sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_SQLITE = os.environ.get("SQLITE_PATH")
if not _SQLITE or not Path(_SQLITE).exists():
    print("set SQLITE_PATH to the sqlite database", file=sys.stderr)
    sys.exit(1)


def _conn():
    return sqlite3.connect(f"file:{_SQLITE}?mode=ro", uri=True,
                           check_same_thread=False)


def _ok(data): return json.dumps({"ok": True, "data": data}, default=str)
def _err(msg): return json.dumps({"ok": False, "error": str(msg)})


mcp = FastMCP("invocable-apis-debit_card_specializing")


@mcp.tool()
def compute_consumption_differences(avg_sme, avg_lam, avg_kam) -> str:
    """Pairwise differences between three segment averages."""
    try:
        _ns = {}
        exec(compile("def run(conn, avg_sme, avg_lam, avg_kam):\n        diff_sme_lam = avg_sme - avg_lam\n        diff_lam_kam = avg_lam - avg_kam\n        diff_kam_sme = avg_kam - avg_sme\n        return {\n            \"diff_sme_lam\": diff_sme_lam,\n            \"diff_lam_kam\": diff_lam_kam,\n            \"diff_kam_sme\": diff_kam_sme\n        }\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, avg_sme=avg_sme, avg_lam=avg_lam, avg_kam=avg_kam)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_customers_by_segment_and_currency(segment, currency) -> str:
    """Count of customers belonging to a specific segment and using a specific currency."""
    try:
        _ns = {}
        exec(compile("def run(conn, segment, currency):\n        row = conn.execute(\n            \"SELECT COUNT(*) FROM customers WHERE Segment = ? AND Currency = ?\",\n            (segment, currency)\n        ).fetchone()\n        return {\"count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment, currency=currency)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_gas_stations_by_country_and_segment(country, segment) -> str:
    """Count of gas stations for a specified country and segment."""
    try:
        _ns = {}
        exec(compile("def run(conn, country, segment):\n        row = conn.execute(\n            \"SELECT COUNT(GasStationID) FROM gasstations \"\n            \"WHERE Country = ? COLLATE NOCASE AND Segment = ? COLLATE NOCASE\",\n            (country, segment)\n        ).fetchone()\n        return {\"count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, country=country, segment=segment)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_transactions_by_country_date_time_range(country, date, start_time, end_time, start_year) -> str:
    """Count transactions for a given country, optionally filtered by exact date, a time window, or a start year."""
    try:
        _ns = {}
        exec(compile("def run(conn, country, date=None, start_time=None, end_time=None, start_year=None):\n        sql = (\"SELECT COUNT(T1.TransactionID) \"\n               \"FROM transactions_1k AS T1 \"\n               \"INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID \"\n               \"WHERE T2.Country = ? COLLATE NOCASE\")\n        params = [country]\n    \n        if date is not None:\n            sql += \" AND T1.Date = ?\"\n            params.append(date)\n    \n        if start_year is not None:\n            # Extract year from YYYY-MM-DD string\n            sql += \" AND substr(T1.Date, 1, 4) >= ?\"\n            params.append(str(start_year))\n    \n        if start_time is not None and end_time is not None:\n            sql += \" AND T1.Time BETWEEN ? AND ?\"\n            params.extend([start_time, end_time])\n    \n        cur = conn.execute(sql, tuple(params))\n        row = cur.fetchone()\n        return {\"count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, country=country, date=date, start_time=start_time, end_time=end_time, start_year=start_year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_transactions_by_date_time_currency(date, before_time, currency) -> str:
    """Count transactions on a given date before a specific time and paid in a given currency."""
    try:
        _ns = {}
        exec(compile("def run(conn, date, before_time, currency):\n        sql = (\n            \"SELECT COUNT(T1.TransactionID) \"\n            \"FROM transactions_1k AS T1 \"\n            \"INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID \"\n            \"WHERE T1.Date = ? \"\n            \"AND T1.Time < ? \"\n            \"AND T2.Currency = ? COLLATE NOCASE\"\n        )\n        cur = conn.execute(sql, (date, before_time, currency))\n        row = cur.fetchone()\n        count = row[0] if row else 0\n        return {\"count\": count}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, date=date, before_time=before_time, currency=currency)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_average_min_consumption_by_segment(segment, currency, year) -> str:
    """Average consumption for the globally‑minimum‑consumption record of a given segment, currency and year."""
    try:
        _ns = {}
        exec(compile("def run(conn, segment, currency, year):\n        start_date = f\"{year}01\"\n        end_date = f\"{year}12\"\n        # global minimum consumption across the whole table\n        cur_min = conn.execute(\"SELECT MIN(Consumption) FROM yearmonth\")\n        min_consumption = cur_min.fetchone()[0]\n        # sum consumption for the requested segment where consumption equals the global minimum,\n        # and count all rows that satisfy the other filters (currency, date, min consumption)\n        row = conn.execute(\n            \"SELECT SUM(CASE WHEN T1.Segment = ? THEN T2.Consumption ELSE 0 END) AS seg_sum, \"\n            \"COUNT(*) AS cnt \"\n            \"FROM customers T1 JOIN yearmonth T2 ON T1.CustomerID = T2.CustomerID \"\n            \"WHERE T1.Currency = ? AND T2.Consumption = ? AND T2.Date BETWEEN ? AND ?\",\n            (segment, currency, min_consumption, start_date, end_date)\n        ).fetchone()\n        seg_sum = row[0] or 0\n        cnt = row[1] or 0\n        average = seg_sum / cnt if cnt != 0 else None\n        return {\"average\": average}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment, currency=currency, year=year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_average_monthly_consumption_by_segment_and_year(segment, year) -> str:
    """Average monthly consumption (total consumption divided by 12) for customers belonging to a specific segment in a given year."""
    try:
        _ns = {}
        exec(compile("def run(conn, segment, year):\n    row = conn.execute(\n        \"SELECT AVG(T2.Consumption) / 12 \"\n        \"FROM customers AS T1 \"\n        \"JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID \"\n        \"WHERE SUBSTR(T2.Date, 1, 4) = ? \"\n        \"AND T1.Segment = ? COLLATE NOCASE\",\n        (str(year), segment)\n    ).fetchone()\n    return {\"average_monthly_consumption\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment, year=year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_average_transaction_amount_by_month(year, month) -> str:
    """Average transaction amount for a specified year and month in the transactions_1k table."""
    try:
        _ns = {}
        exec(compile("def run(conn, year, month):\n        pattern = f\"{year:04d}-{month:02d}%\"\n        cur = conn.execute(\n            \"SELECT AVG(Amount) FROM transactions_1k WHERE Date LIKE ?\",\n            (pattern,)\n        )\n        row = cur.fetchone()\n        # Return a list of rows to match the gold\u2011SQL format\n        return {\"rows\": [[row[0] if row else None]]}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, year=year, month=month)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_average_transaction_price_by_currency(currency) -> str:
    """Average transaction price (Price column) for all transactions made by customers using a specified currency."""
    try:
        _ns = {}
        exec(compile("def run(conn, currency):\n        # Join the three tables exactly as the gold SQL does.\n        # Use COLLATE NOCASE for case\u2011insensitive matching of the currency string.\n        cur = conn.execute(\n            '''\n            SELECT AVG(T1.Price)\n            FROM transactions_1k AS T1\n            INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID\n            INNER JOIN customers AS T3 ON T1.CustomerID = T3.CustomerID\n            WHERE T3.Currency = ? COLLATE NOCASE\n            ''',\n            (currency,)\n        )\n        row = cur.fetchone()\n        return {\"average_price\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, currency=currency)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_consumption_by_date_price_and_month(transaction_date, price, target_month) -> str:
    """For customers who paid a specific price on a given transaction date, return their consumption in a specified year‑month."""
    try:
        _ns = {}
        exec(compile("def run(conn, transaction_date, price, target_month):\n        cur = conn.execute(\n            \"SELECT T1.CustomerID, T2.Date, T2.Consumption \"\n            \"FROM transactions_1k AS T1 \"\n            \"INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID \"\n            \"WHERE T1.Date = ? AND T1.Price = ? AND T2.Date = ?\",\n            (transaction_date, price, target_month)\n        )\n        rows = cur.fetchall()\n        records = [\n            {\"customer_id\": r[0], \"date\": r[1], \"consumption\": r[2]}\n            for r in rows\n        ]\n        return {\"records\": records}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, transaction_date=transaction_date, price=price, target_month=target_month)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_consumption_difference_between_customers(date, customer_a, customer_b) -> str:
    """Compute the numeric difference in total gas consumption between two customers for a specific year‑month (YYYYMM)."""
    try:
        _ns = {}
        exec(compile("def run(conn, date, customer_a, customer_b):\n        row = conn.execute(\n            \"SELECT \"\n            \"SUM(IIF(CustomerID = ?, Consumption, 0)) - \"\n            \"SUM(IIF(CustomerID = ?, Consumption, 0)) \"\n            \"FROM yearmonth WHERE Date = ?\",\n            (customer_a, customer_b, date)\n        ).fetchone()\n        return {\"difference\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, date=date, customer_a=customer_a, customer_b=customer_b)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_countries_of_gas_stations_by_transaction_date(date) -> str:
    """Return distinct country codes of gas stations that have at least one transaction in the specified year‑month (YYYYMM)."""
    try:
        _ns = {}
        exec(compile("def run(conn, date):\n        rows = conn.execute(\n            \"SELECT DISTINCT T2.Country \"\n            \"FROM transactions_1k AS T1 \"\n            \"INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID \"\n            \"INNER JOIN yearmonth AS T3 ON T1.CustomerID = T3.CustomerID \"\n            \"WHERE T3.Date = ?\",\n            (date,)\n        ).fetchall()\n        countries = [r[0] for r in rows]\n        return {\"countries\": countries}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, date=date)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_country_by_transaction(card_id, date) -> str:
    """Return the ISO country code of the gas station for a transaction identified by CardID or by exact transaction Date."""
    try:
        _ns = {}
        exec(compile("def run(conn, card_id=None, date=None):\n    if card_id is not None:\n        sql = \"SELECT T2.Country FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID WHERE T1.CardID = ?\"\n        params = (card_id,)\n    elif date is not None:\n        sql = \"SELECT T2.Country FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID WHERE T1.Date = ?\"\n        params = (date,)\n    else:\n        return {\"country\": None}\n    row = conn.execute(sql, params).fetchone()\n    return {\"country\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, card_id=card_id, date=date)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_country_of_gas_station(product_id, date, price) -> str:
    """Return the ISO country code of the gas station that sold the most expensive unit matching the supplied criteria (either a specific product_id, or a specific date and price)."""
    try:
        _ns = {}
        exec(compile("def run(conn, product_id=None, date=None, price=None):\n        # Build the base query and parameters list\n        base_sql = (\n            \"SELECT T2.Country \"\n            \"FROM transactions_1k AS T1 \"\n            \"JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID \"\n        )\n        where_clauses = []\n        params = []\n    \n        # Priority: product_id filter if supplied\n        if product_id is not None:\n            where_clauses.append(\"T1.ProductID = ?\")\n            params.append(product_id)\n        else:\n            # If product_id not given, require both date and price\n            if date is not None and price is not None:\n                where_clauses.append(\"T1.Date = ?\")\n                where_clauses.append(\"T1.Price = ?\")\n                params.extend([date, price])\n            else:\n                # No usable filter \u2013 return empty result\n                return {\"country\": None}\n    \n        sql = base_sql + \"WHERE \" + \" AND \".join(where_clauses) + \" ORDER BY T1.Price DESC LIMIT 1\"\n        row = conn.execute(sql, tuple(params)).fetchone()\n        return {\"country\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, product_id=product_id, date=date, price=price)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_country_with_most_gas_stations_by_segment(segment) -> str:
    """Return the country that has the most gas stations for a specified segment, and the total number of stations of that segment across all countries."""
    try:
        _ns = {}
        exec(compile("def run(conn, segment):\n        # total count of the segment (global)\n        total_row = conn.execute(\n            \"SELECT COUNT(GasStationID) FROM gasstations WHERE Segment = ? COLLATE NOCASE\",\n            (segment,)\n        ).fetchone()\n        total_count = total_row[0] if total_row else None\n    \n        # country with the highest count for the segment\n        country_row = conn.execute(\n            \"SELECT Country FROM gasstations WHERE Segment = ? COLLATE NOCASE \"\n            \"GROUP BY Country ORDER BY COUNT(GasStationID) DESC LIMIT 1\",\n            (segment,)\n        ).fetchone()\n        top_country = country_row[0] if country_row else None\n    \n        return {\"country\": top_country, \"count\": total_count}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_currency_by_date_and_consumption(date, consumption) -> str:
    """Currency used by the customer who spent a specific amount in a given year‑month."""
    try:
        _ns = {}
        exec(compile("def run(conn, date, consumption):\n    row = conn.execute(\n        \"SELECT T2.Currency \"\n        \"FROM yearmonth AS T1 \"\n        \"INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID \"\n        \"WHERE T1.Date = ? COLLATE NOCASE AND T1.Consumption = ?\",\n        (date, consumption)\n    ).fetchone()\n    return {\"currency\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, date=date, consumption=consumption)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_currency_by_datetime(date, time) -> str:
    """Return distinct currency codes used by customers for transactions on a given date and time."""
    try:
        _ns = {}
        exec(compile("def run(conn, date, time):\n        rows = conn.execute(\n            \"\"\"SELECT DISTINCT T3.Currency\n               FROM transactions_1k AS T1\n               INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID\n               INNER JOIN customers AS T3 ON T1.CustomerID = T3.CustomerID\n               WHERE T1.Date = ? COLLATE NOCASE\n                 AND T1.Time = ? COLLATE NOCASE\"\"\",\n            (date, time)\n        ).fetchall()\n        return {\"currencies\": [r[0] for r in rows]}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, date=date, time=time)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_customer_by_segment_and_month(segment, date, order) -> str:
    """Return the CustomerID for a given month (YYYYMM), optionally limited to a segment, ordered by total consumption."""
    try:
        _ns = {}
        exec(compile("def run(conn, date, order, segment=None):\n        # Build the base query and parameters\n        sql = (\n            \"SELECT T1.CustomerID \"\n            \"FROM customers AS T1 \"\n            \"INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID \"\n            \"WHERE T2.Date = ?\"\n        )\n        params = [date]\n    \n        # Optional segment filter\n        if segment is not None:\n            sql += \" AND T1.Segment = ? COLLATE NOCASE\"\n            params.append(segment)\n    \n        # Ordering (ASC for least, DESC for most)\n        direction = \"ASC\" if order == \"asc\" else \"DESC\"\n        sql += f\" GROUP BY T1.CustomerID ORDER BY SUM(T2.Consumption) {direction} LIMIT 1\"\n    \n        row = conn.execute(sql, tuple(params)).fetchone()\n        return {\"customer_id\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment, date=date, order=order)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_distinct_transaction_times_by_chain(chain_id) -> str:
    """Return all distinct transaction times (HH:MM:SS) for transactions that occurred at gas stations belonging to a specified chain."""
    try:
        _ns = {}
        exec(compile("def run(conn, chain_id):\n        rows = conn.execute(\n            \"SELECT DISTINCT T1.Time \"\n            \"FROM transactions_1k AS T1 \"\n            \"INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID \"\n            \"WHERE T2.ChainID = ?\",\n            (chain_id,)\n        ).fetchall()\n        times = sorted([r[0] for r in rows]) if rows else []\n        return {\"times\": times}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, chain_id=chain_id)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_earliest_customer_segment() -> str:
    """Return the Segment of the customer associated with the earliest transaction."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\n        \"SELECT T2.Segment \"\n        \"FROM transactions_1k AS T1 \"\n        \"INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID \"\n        \"ORDER BY T1.Date ASC \"\n        \"LIMIT 1\"\n    ).fetchone()\n    return {\"segment\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_gas_station_with_highest_revenue() -> str:
    """Return the GasStationID of the gas station that generated the highest total revenue (sum of `Price`) in the `transactions_1k` table."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\n        \"SELECT GasStationID FROM transactions_1k \"\n        \"GROUP BY GasStationID \"\n        \"ORDER BY SUM(Price) DESC \"\n        \"LIMIT 1\"\n    ).fetchone()\n    return {\"gas_station_id\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_highest_monthly_consumption_by_year(year) -> str:
    """Maximum total gas consumption for any month within a specified year."""
    try:
        _ns = {}
        exec(compile("def run(conn, year):\n        cur = conn.execute(\n            \"SELECT SUM(Consumption) AS total \"\n            \"FROM yearmonth \"\n            \"WHERE SUBSTR(Date, 1, 4) = ? \"\n            \"GROUP BY SUBSTR(Date, 5, 2) \"\n            \"ORDER BY total DESC \"\n            \"LIMIT 1\",\n            (str(year),)\n        )\n        row = cur.fetchone()\n        return {\"max_monthly_consumption\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, year=year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_peak_consumption_month_by_segment_and_year(segment, year) -> str:
    """Return the two‑digit month (MM) with the highest total gas consumption for customers of a specific segment in a given year."""
    try:
        _ns = {}
        exec(compile("def run(conn, segment, year):\n        # Find month (MM) with max total consumption for the given segment and year\n        row = conn.execute(\n            \"SELECT SUBSTR(T2.Date, 5, 2) AS month \"\n            \"FROM customers AS T1 \"\n            \"JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID \"\n            \"WHERE SUBSTR(T2.Date, 1, 4) = ? \"\n            \"  AND T1.Segment = ? COLLATE NOCASE \"\n            \"GROUP BY month \"\n            \"ORDER BY SUM(T2.Consumption) DESC \"\n            \"LIMIT 1\",\n            (str(year), segment)\n        ).fetchone()\n        return {\"peak_month\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment, year=year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_percentage_increases_by_segment_between_years(start_year, end_year) -> str:
    """Compute the percentage increase in total consumption between start_year and end_year for each segment (SME, LAM, KAM). Percentage = (consumption_end - consumption_start) * 100 / consumption_start."""
    try:
        _ns = {}
        exec(compile("def run(conn, start_year, end_year):\n        start_pat = f\"{start_year}%\"\n        end_pat   = f\"{end_year}%\"\n        sql = \"\"\"\n            SELECT\n                (SUM(CASE WHEN T1.Segment = 'SME' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END) -\n                 SUM(CASE WHEN T1.Segment = 'SME' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END)) *\n                100.0 /\n                NULLIF(SUM(CASE WHEN T1.Segment = 'SME' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END), 0) AS percent_sme,\n                (SUM(CASE WHEN T1.Segment = 'LAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END) -\n                 SUM(CASE WHEN T1.Segment = 'LAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END)) *\n                100.0 /\n                NULLIF(SUM(CASE WHEN T1.Segment = 'LAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END), 0) AS percent_lam,\n                (SUM(CASE WHEN T1.Segment = 'KAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END) -\n                 SUM(CASE WHEN T1.Segment = 'KAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END)) *\n                100.0 /\n                NULLIF(SUM(CASE WHEN T1.Segment = 'KAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END), 0) AS percent_kam\n            FROM customers T1\n            JOIN yearmonth T2 ON T1.CustomerID = T2.CustomerID\n        \"\"\"\n        params = (\n            end_pat, start_pat, start_pat,   # SME\n            end_pat, start_pat, start_pat,   # LAM\n            end_pat, start_pat, start_pat    # KAM\n        )\n        cur = conn.execute(sql, params)\n        row = cur.fetchone()\n        return {\n            \"percent_sme\": row[0] if row and row[0] is not None else None,\n            \"percent_lam\": row[1] if row and row[1] is not None else None,\n            \"percent_kam\": row[2] if row and row[2] is not None else None,\n        }\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, start_year=start_year, end_year=end_year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_product_descriptions_by_country(country) -> str:
    """List distinct product descriptions for transactions that occurred at gas stations in the specified country."""
    try:
        _ns = {}
        exec(compile("def run(conn, country):\n        cur = conn.execute(\n            \"SELECT DISTINCT p.Description \"\n            \"FROM transactions_1k AS t \"\n            \"JOIN gasstations AS g ON t.GasStationID = g.GasStationID \"\n            \"JOIN products AS p ON t.ProductID = p.ProductID \"\n            \"WHERE g.Country = ? COLLATE NOCASE\",\n            (country,)\n        )\n        rows = cur.fetchall()\n        return {\"descriptions\": [r[0] for r in rows]}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, country=country)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_product_id_by_datetime(date, time) -> str:
    """Retrieve the ProductID of the transaction that occurred on a specific date and time."""
    try:
        _ns = {}
        exec(compile("def run(conn, date, time):\n        cur = conn.execute(\n            \"SELECT T1.ProductID \"\n            \"FROM transactions_1k AS T1 \"\n            \"INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID \"\n            \"WHERE T1.Date = ? AND T1.Time = ? \"\n            \"LIMIT 1\",\n            (date, time)\n        )\n        row = cur.fetchone()\n        return {\"product_id\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, date=date, time=time)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_segment_percentage_by_country(country, segment) -> str:
    """Percentage of gas stations belonging to a specified segment within a given country. Calculated as (count of rows where Country and Segment match) * 100 / total rows for the country."""
    try:
        _ns = {}
        exec(compile("def run(conn, country, segment):\n        # Total stations in the country\n        total_row = conn.execute(\n            \"SELECT COUNT(*) FROM gasstations WHERE `Country` = ? COLLATE NOCASE\",\n            (country,)\n        ).fetchone()\n        total = total_row[0] if total_row else 0\n    \n        # Stations matching both country and segment\n        seg_row = conn.execute(\n            \"SELECT COUNT(*) FROM gasstations WHERE `Country` = ? COLLATE NOCASE AND `Segment` = ? COLLATE NOCASE\",\n            (country, segment)\n        ).fetchone()\n        seg_count = seg_row[0] if seg_row else 0\n    \n        if total == 0:\n            return {\"percentage\": None}\n        percentage = (seg_count / total) * 100.0\n        return {\"percentage\": percentage}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, country=country, segment=segment)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_segment_with_min_consumption(year_month) -> str:
    """Return the Segment of the customer with the smallest total gas consumption. If `year_month` is provided, the calculation is limited to that month; otherwise it uses all months."""
    try:
        _ns = {}
        exec(compile("def run(conn, year_month=None):\n        # Build the base query: sum consumption per customer\n        sql = (\n            \"SELECT T1.CustomerID, T1.Segment, SUM(T2.Consumption) AS total_cons \"\n            \"FROM customers AS T1 \"\n            \"INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID \"\n        )\n        params = []\n        if year_month is not None:\n            sql += \"WHERE T2.Date = ? \"\n            params.append(year_month)\n        sql += \"GROUP BY T1.CustomerID ORDER BY total_cons ASC LIMIT 1\"\n        row = conn.execute(sql, tuple(params)).fetchone()\n        return {\"segment\": row[1] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, year_month=year_month)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_customer_by_currency_and_year(currency, year) -> str:
    """Return the CustomerID of the customer who consumed the most gas in a specified year while paying with a given currency."""
    try:
        _ns = {}
        exec(compile("def run(conn, currency, year):\n        # Build start and end dates in YYYYMM format\n        start_date = year * 100 + 1   # e.g., 201101\n        end_date = year * 100 + 12    # e.g., 201112\n        row = conn.execute(\n            \"\"\"SELECT T1.CustomerID\n               FROM customers AS T1\n               INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID\n               WHERE T1.Currency = ? COLLATE NOCASE\n                 AND T2.Date BETWEEN ? AND ?\n               GROUP BY T1.CustomerID\n               ORDER BY SUM(T2.Consumption) DESC\n               LIMIT 1\"\"\",\n            (currency, start_date, end_date)\n        ).fetchone()\n        return {\"customer_id\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, currency=currency, year=year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_customer_by_date(date) -> str:
    """Return the CustomerID of the customer who paid the highest total Price on a specific transaction date."""
    try:
        _ns = {}
        exec(compile("def run(conn, date):\n        row = conn.execute(\n            \"SELECT CustomerID FROM transactions_1k \"\n            \"WHERE Date = ? COLLATE NOCASE \"\n            \"GROUP BY CustomerID \"\n            \"ORDER BY SUM(Price) DESC \"\n            \"LIMIT 1\",\n            (date,)\n        ).fetchone()\n        return {\"customer_id\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, date=date)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_customer_by_segment_currency_and_month(segment, currency, year_month) -> str:
    """Return the CustomerID of the customer in a specified segment who used a given currency and had the highest total consumption in a specific year‑month."""
    try:
        _ns = {}
        exec(compile("def run(conn, segment, currency, year_month):\n    row = conn.execute(\n        \"\"\"\n        SELECT T1.CustomerID\n        FROM customers AS T1\n        INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID\n        WHERE T1.Segment = ? COLLATE NOCASE\n          AND T1.Currency = ? COLLATE NOCASE\n          AND T2.Date = ?\n        GROUP BY T1.CustomerID\n        ORDER BY SUM(T2.Consumption) DESC\n        LIMIT 1\n        \"\"\",\n        (segment, currency, year_month)\n    ).fetchone()\n    return {\"customer_id\": row[0] if row else None}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment, currency=currency, year_month=year_month)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_product_descriptions(limit) -> str:
    """Return the full product descriptions of the top‑selling products, ordered by transaction amount descending."""
    try:
        _ns = {}
        exec(compile("def run(conn, limit):\n        rows = conn.execute(\n            \"SELECT T2.Description \"\n            \"FROM transactions_1k AS T1 \"\n            \"INNER JOIN products AS T2 ON T1.ProductID = T2.ProductID \"\n            \"ORDER BY T1.Amount DESC \"\n            \"LIMIT ?\",\n            (limit,)\n        ).fetchall()\n        descriptions = [r[0] for r in rows] if rows else []\n        return {\"descriptions\": descriptions}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_total_consumption_by_customer_and_date_range(customer_id, start_date, end_date) -> str:
    """Total gas consumption for a specific customer between a start and end year‑month (inclusive)."""
    try:
        _ns = {}
        exec(compile("def run(conn, customer_id, start_date, end_date):\n        cur = conn.execute(\n            \"SELECT SUM(Consumption) FROM yearmonth \"\n            \"WHERE CustomerID = ? AND Date BETWEEN ? AND ?\",\n            (customer_id, start_date, end_date)\n        )\n        row = cur.fetchone()\n        return {\"total_consumption\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, customer_id=customer_id, start_date=start_date, end_date=end_date)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_total_consumption_by_segment_and_month(segment, year_month) -> str:
    """Total gas consumption for all customers of a given segment in a specific year‑month."""
    try:
        _ns = {}
        exec(compile("def run(conn, segment, year_month):\n    cur = conn.execute(\n        \"SELECT SUM(T2.Consumption) \"\n        \"FROM customers AS T1 \"\n        \"INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID \"\n        \"WHERE T2.Date = ? AND T1.Segment = ? COLLATE NOCASE\",\n        (year_month, segment)\n    )\n    row = cur.fetchone()\n    return {\"total_consumption\": row[0] if row and row[0] is not None else None}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, segment=segment, year_month=year_month)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_year_with_max_gas_consumption_by_currency(currency) -> str:
    """Return the four‑digit year (YYYY) that recorded the highest total gas consumption for a specified currency."""
    try:
        _ns = {}
        exec(compile("def run(conn, currency):\n        sql = (\n            \"SELECT SUBSTRING(T2.Date, 1, 4) AS yr, SUM(T2.Consumption) AS total \"\n            \"FROM customers AS T1 \"\n            \"JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID \"\n            \"WHERE T1.Currency = ? COLLATE NOCASE \"\n            \"GROUP BY yr \"\n            \"ORDER BY total DESC \"\n            \"LIMIT 1\"\n        )\n        cur = conn.execute(sql, (currency,))\n        row = cur.fetchone()\n        return {\"year\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, currency=currency)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def subtract_counts(count_a, count_b) -> str:
    """Subtract count_b from count_a and return the numeric difference."""
    try:
        _ns = {}
        exec(compile("def run(conn, count_a, count_b):\n        return {\"difference\": count_a - count_b}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, count_a=count_a, count_b=count_b)
        return _ok(out)
    except Exception as _e:
        return _err(_e)


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8765"))
    mcp.settings.transport_security.enable_dns_rebinding_protection = False
    mcp.run(transport="streamable-http")
