"""Auto-generated invocable tools for Bird db `debit_card_specializing`."""
from __future__ import annotations
import json
import re
import sqlite3

# compute_consumption_differences — Pairwise differences between three segment averages.
def run(conn, avg_sme, avg_lam, avg_kam):
        diff_sme_lam = avg_sme - avg_lam
        diff_lam_kam = avg_lam - avg_kam
        diff_kam_sme = avg_kam - avg_sme
        return {
            "diff_sme_lam": diff_sme_lam,
            "diff_lam_kam": diff_lam_kam,
            "diff_kam_sme": diff_kam_sme
        }
compute_consumption_differences = run; del run

# count_customers_by_segment_and_currency — Count of customers belonging to a specific segment and using a specific currency.
def run(conn, segment, currency):
        row = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE Segment = ? AND Currency = ?",
            (segment, currency)
        ).fetchone()
        return {"count": row[0] if row else None}
count_customers_by_segment_and_currency = run; del run

# count_gas_stations_by_country_and_segment — Count of gas stations for a specified country and segment.
def run(conn, country, segment):
        row = conn.execute(
            "SELECT COUNT(GasStationID) FROM gasstations "
            "WHERE Country = ? COLLATE NOCASE AND Segment = ? COLLATE NOCASE",
            (country, segment)
        ).fetchone()
        return {"count": row[0] if row else None}
count_gas_stations_by_country_and_segment = run; del run

# count_transactions_by_country_date_time_range — Count transactions for a given country, optionally filtered by exact date, a time window, or a start year.
def run(conn, country, date=None, start_time=None, end_time=None, start_year=None):
        sql = ("SELECT COUNT(T1.TransactionID) "
               "FROM transactions_1k AS T1 "
               "INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID "
               "WHERE T2.Country = ? COLLATE NOCASE")
        params = [country]
    
        if date is not None:
            sql += " AND T1.Date = ?"
            params.append(date)
    
        if start_year is not None:
            # Extract year from YYYY-MM-DD string
            sql += " AND substr(T1.Date, 1, 4) >= ?"
            params.append(str(start_year))
    
        if start_time is not None and end_time is not None:
            sql += " AND T1.Time BETWEEN ? AND ?"
            params.extend([start_time, end_time])
    
        cur = conn.execute(sql, tuple(params))
        row = cur.fetchone()
        return {"count": row[0] if row else None}
count_transactions_by_country_date_time_range = run; del run

# count_transactions_by_date_time_currency — Count transactions on a given date before a specific time and paid in a given currency.
def run(conn, date, before_time, currency):
        sql = (
            "SELECT COUNT(T1.TransactionID) "
            "FROM transactions_1k AS T1 "
            "INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID "
            "WHERE T1.Date = ? "
            "AND T1.Time < ? "
            "AND T2.Currency = ? COLLATE NOCASE"
        )
        cur = conn.execute(sql, (date, before_time, currency))
        row = cur.fetchone()
        count = row[0] if row else 0
        return {"count": count}
count_transactions_by_date_time_currency = run; del run

# get_average_min_consumption_by_segment — Average consumption for the globally‑minimum‑consumption record of a given segment, currency and year.
def run(conn, segment, currency, year):
        start_date = f"{year}01"
        end_date = f"{year}12"
        # global minimum consumption across the whole table
        cur_min = conn.execute("SELECT MIN(Consumption) FROM yearmonth")
        min_consumption = cur_min.fetchone()[0]
        # sum consumption for the requested segment where consumption equals the global minimum,
        # and count all rows that satisfy the other filters (currency, date, min consumption)
        row = conn.execute(
            "SELECT SUM(CASE WHEN T1.Segment = ? THEN T2.Consumption ELSE 0 END) AS seg_sum, "
            "COUNT(*) AS cnt "
            "FROM customers T1 JOIN yearmonth T2 ON T1.CustomerID = T2.CustomerID "
            "WHERE T1.Currency = ? AND T2.Consumption = ? AND T2.Date BETWEEN ? AND ?",
            (segment, currency, min_consumption, start_date, end_date)
        ).fetchone()
        seg_sum = row[0] or 0
        cnt = row[1] or 0
        average = seg_sum / cnt if cnt != 0 else None
        return {"average": average}
get_average_min_consumption_by_segment = run; del run

# get_average_monthly_consumption_by_segment_and_year — Average monthly consumption (total consumption divided by 12) for customers belonging to a specific segment in a given year.
def run(conn, segment, year):
    row = conn.execute(
        "SELECT AVG(T2.Consumption) / 12 "
        "FROM customers AS T1 "
        "JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID "
        "WHERE SUBSTR(T2.Date, 1, 4) = ? "
        "AND T1.Segment = ? COLLATE NOCASE",
        (str(year), segment)
    ).fetchone()
    return {"average_monthly_consumption": row[0] if row else None}
get_average_monthly_consumption_by_segment_and_year = run; del run

# get_average_transaction_amount_by_month — Average transaction amount for a specified year and month in the transactions_1k table.
def run(conn, year, month):
        pattern = f"{year:04d}-{month:02d}%"
        cur = conn.execute(
            "SELECT AVG(Amount) FROM transactions_1k WHERE Date LIKE ?",
            (pattern,)
        )
        row = cur.fetchone()
        # Return a list of rows to match the gold‑SQL format
        return {"rows": [[row[0] if row else None]]}
get_average_transaction_amount_by_month = run; del run

# get_average_transaction_price_by_currency — Average transaction price (Price column) for all transactions made by customers using a specified currency.
def run(conn, currency):
        # Join the three tables exactly as the gold SQL does.
        # Use COLLATE NOCASE for case‑insensitive matching of the currency string.
        cur = conn.execute(
            '''
            SELECT AVG(T1.Price)
            FROM transactions_1k AS T1
            INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID
            INNER JOIN customers AS T3 ON T1.CustomerID = T3.CustomerID
            WHERE T3.Currency = ? COLLATE NOCASE
            ''',
            (currency,)
        )
        row = cur.fetchone()
        return {"average_price": row[0] if row and row[0] is not None else None}
get_average_transaction_price_by_currency = run; del run

# get_consumption_by_date_price_and_month — For customers who paid a specific price on a given transaction date, return their consumption in a specified year‑month.
def run(conn, transaction_date, price, target_month):
        cur = conn.execute(
            "SELECT T1.CustomerID, T2.Date, T2.Consumption "
            "FROM transactions_1k AS T1 "
            "INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID "
            "WHERE T1.Date = ? AND T1.Price = ? AND T2.Date = ?",
            (transaction_date, price, target_month)
        )
        rows = cur.fetchall()
        records = [
            {"customer_id": r[0], "date": r[1], "consumption": r[2]}
            for r in rows
        ]
        return {"records": records}
get_consumption_by_date_price_and_month = run; del run

# get_consumption_difference_between_customers — Compute the numeric difference in total gas consumption between two customers for a specific year‑month (YYYYMM).
def run(conn, date, customer_a, customer_b):
        row = conn.execute(
            "SELECT "
            "SUM(IIF(CustomerID = ?, Consumption, 0)) - "
            "SUM(IIF(CustomerID = ?, Consumption, 0)) "
            "FROM yearmonth WHERE Date = ?",
            (customer_a, customer_b, date)
        ).fetchone()
        return {"difference": row[0] if row and row[0] is not None else None}
get_consumption_difference_between_customers = run; del run

# get_countries_of_gas_stations_by_transaction_date — Return distinct country codes of gas stations that have at least one transaction in the specified year‑month (YYYYMM).
def run(conn, date):
        rows = conn.execute(
            "SELECT DISTINCT T2.Country "
            "FROM transactions_1k AS T1 "
            "INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID "
            "INNER JOIN yearmonth AS T3 ON T1.CustomerID = T3.CustomerID "
            "WHERE T3.Date = ?",
            (date,)
        ).fetchall()
        countries = [r[0] for r in rows]
        return {"countries": countries}
get_countries_of_gas_stations_by_transaction_date = run; del run

# get_country_by_transaction — Return the ISO country code of the gas station for a transaction identified by CardID or by exact transaction Date.
def run(conn, card_id=None, date=None):
    if card_id is not None:
        sql = "SELECT T2.Country FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID WHERE T1.CardID = ?"
        params = (card_id,)
    elif date is not None:
        sql = "SELECT T2.Country FROM transactions_1k AS T1 INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID WHERE T1.Date = ?"
        params = (date,)
    else:
        return {"country": None}
    row = conn.execute(sql, params).fetchone()
    return {"country": row[0] if row else None}
get_country_by_transaction = run; del run

# get_country_of_gas_station — Return the ISO country code of the gas station that sold the most expensive unit matching the supplied criteria (either a specific product_id, or a specific date and price).
def run(conn, product_id=None, date=None, price=None):
        # Build the base query and parameters list
        base_sql = (
            "SELECT T2.Country "
            "FROM transactions_1k AS T1 "
            "JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID "
        )
        where_clauses = []
        params = []
    
        # Priority: product_id filter if supplied
        if product_id is not None:
            where_clauses.append("T1.ProductID = ?")
            params.append(product_id)
        else:
            # If product_id not given, require both date and price
            if date is not None and price is not None:
                where_clauses.append("T1.Date = ?")
                where_clauses.append("T1.Price = ?")
                params.extend([date, price])
            else:
                # No usable filter – return empty result
                return {"country": None}
    
        sql = base_sql + "WHERE " + " AND ".join(where_clauses) + " ORDER BY T1.Price DESC LIMIT 1"
        row = conn.execute(sql, tuple(params)).fetchone()
        return {"country": row[0] if row else None}
get_country_of_gas_station = run; del run

# get_country_with_most_gas_stations_by_segment — Return the country that has the most gas stations for a specified segment, and the total number of stations of that segment across all countries.
def run(conn, segment):
        # total count of the segment (global)
        total_row = conn.execute(
            "SELECT COUNT(GasStationID) FROM gasstations WHERE Segment = ? COLLATE NOCASE",
            (segment,)
        ).fetchone()
        total_count = total_row[0] if total_row else None
    
        # country with the highest count for the segment
        country_row = conn.execute(
            "SELECT Country FROM gasstations WHERE Segment = ? COLLATE NOCASE "
            "GROUP BY Country ORDER BY COUNT(GasStationID) DESC LIMIT 1",
            (segment,)
        ).fetchone()
        top_country = country_row[0] if country_row else None
    
        return {"country": top_country, "count": total_count}
get_country_with_most_gas_stations_by_segment = run; del run

# get_currency_by_date_and_consumption — Currency used by the customer who spent a specific amount in a given year‑month.
def run(conn, date, consumption):
    row = conn.execute(
        "SELECT T2.Currency "
        "FROM yearmonth AS T1 "
        "INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID "
        "WHERE T1.Date = ? COLLATE NOCASE AND T1.Consumption = ?",
        (date, consumption)
    ).fetchone()
    return {"currency": row[0] if row else None}
get_currency_by_date_and_consumption = run; del run

# get_currency_by_datetime — Return distinct currency codes used by customers for transactions on a given date and time.
def run(conn, date, time):
        rows = conn.execute(
            """SELECT DISTINCT T3.Currency
               FROM transactions_1k AS T1
               INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID
               INNER JOIN customers AS T3 ON T1.CustomerID = T3.CustomerID
               WHERE T1.Date = ? COLLATE NOCASE
                 AND T1.Time = ? COLLATE NOCASE""",
            (date, time)
        ).fetchall()
        return {"currencies": [r[0] for r in rows]}
get_currency_by_datetime = run; del run

# get_customer_by_segment_and_month — Return the CustomerID for a given month (YYYYMM), optionally limited to a segment, ordered by total consumption.
def run(conn, date, order, segment=None):
        # Build the base query and parameters
        sql = (
            "SELECT T1.CustomerID "
            "FROM customers AS T1 "
            "INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID "
            "WHERE T2.Date = ?"
        )
        params = [date]
    
        # Optional segment filter
        if segment is not None:
            sql += " AND T1.Segment = ? COLLATE NOCASE"
            params.append(segment)
    
        # Ordering (ASC for least, DESC for most)
        direction = "ASC" if order == "asc" else "DESC"
        sql += f" GROUP BY T1.CustomerID ORDER BY SUM(T2.Consumption) {direction} LIMIT 1"
    
        row = conn.execute(sql, tuple(params)).fetchone()
        return {"customer_id": row[0] if row else None}
get_customer_by_segment_and_month = run; del run

# get_distinct_transaction_times_by_chain — Return all distinct transaction times (HH:MM:SS) for transactions that occurred at gas stations belonging to a specified chain.
def run(conn, chain_id):
        rows = conn.execute(
            "SELECT DISTINCT T1.Time "
            "FROM transactions_1k AS T1 "
            "INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID "
            "WHERE T2.ChainID = ?",
            (chain_id,)
        ).fetchall()
        times = sorted([r[0] for r in rows]) if rows else []
        return {"times": times}
get_distinct_transaction_times_by_chain = run; del run

# get_earliest_customer_segment — Return the Segment of the customer associated with the earliest transaction.
def run(conn):
    row = conn.execute(
        "SELECT T2.Segment "
        "FROM transactions_1k AS T1 "
        "INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID "
        "ORDER BY T1.Date ASC "
        "LIMIT 1"
    ).fetchone()
    return {"segment": row[0] if row else None}
get_earliest_customer_segment = run; del run

# get_gas_station_with_highest_revenue — Return the GasStationID of the gas station that generated the highest total revenue (sum of `Price`) in the `transactions_1k` table.
def run(conn):
    row = conn.execute(
        "SELECT GasStationID FROM transactions_1k "
        "GROUP BY GasStationID "
        "ORDER BY SUM(Price) DESC "
        "LIMIT 1"
    ).fetchone()
    return {"gas_station_id": row[0] if row else None}
get_gas_station_with_highest_revenue = run; del run

# get_highest_monthly_consumption_by_year — Maximum total gas consumption for any month within a specified year.
def run(conn, year):
        cur = conn.execute(
            "SELECT SUM(Consumption) AS total "
            "FROM yearmonth "
            "WHERE SUBSTR(Date, 1, 4) = ? "
            "GROUP BY SUBSTR(Date, 5, 2) "
            "ORDER BY total DESC "
            "LIMIT 1",
            (str(year),)
        )
        row = cur.fetchone()
        return {"max_monthly_consumption": row[0] if row else None}
get_highest_monthly_consumption_by_year = run; del run

# get_peak_consumption_month_by_segment_and_year — Return the two‑digit month (MM) with the highest total gas consumption for customers of a specific segment in a given year.
def run(conn, segment, year):
        # Find month (MM) with max total consumption for the given segment and year
        row = conn.execute(
            "SELECT SUBSTR(T2.Date, 5, 2) AS month "
            "FROM customers AS T1 "
            "JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID "
            "WHERE SUBSTR(T2.Date, 1, 4) = ? "
            "  AND T1.Segment = ? COLLATE NOCASE "
            "GROUP BY month "
            "ORDER BY SUM(T2.Consumption) DESC "
            "LIMIT 1",
            (str(year), segment)
        ).fetchone()
        return {"peak_month": row[0] if row else None}
get_peak_consumption_month_by_segment_and_year = run; del run

# get_percentage_increases_by_segment_between_years — Compute the percentage increase in total consumption between start_year and end_year for each segment (SME, LAM, KAM). Percentage = (consumption_end - consumption_start) * 100 / consumption_start.
def run(conn, start_year, end_year):
        start_pat = f"{start_year}%"
        end_pat   = f"{end_year}%"
        sql = """
            SELECT
                (SUM(CASE WHEN T1.Segment = 'SME' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END) -
                 SUM(CASE WHEN T1.Segment = 'SME' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END)) *
                100.0 /
                NULLIF(SUM(CASE WHEN T1.Segment = 'SME' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END), 0) AS percent_sme,
                (SUM(CASE WHEN T1.Segment = 'LAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END) -
                 SUM(CASE WHEN T1.Segment = 'LAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END)) *
                100.0 /
                NULLIF(SUM(CASE WHEN T1.Segment = 'LAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END), 0) AS percent_lam,
                (SUM(CASE WHEN T1.Segment = 'KAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END) -
                 SUM(CASE WHEN T1.Segment = 'KAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END)) *
                100.0 /
                NULLIF(SUM(CASE WHEN T1.Segment = 'KAM' AND T2.Date LIKE ? THEN T2.Consumption ELSE 0 END), 0) AS percent_kam
            FROM customers T1
            JOIN yearmonth T2 ON T1.CustomerID = T2.CustomerID
        """
        params = (
            end_pat, start_pat, start_pat,   # SME
            end_pat, start_pat, start_pat,   # LAM
            end_pat, start_pat, start_pat    # KAM
        )
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return {
            "percent_sme": row[0] if row and row[0] is not None else None,
            "percent_lam": row[1] if row and row[1] is not None else None,
            "percent_kam": row[2] if row and row[2] is not None else None,
        }
get_percentage_increases_by_segment_between_years = run; del run

# get_product_descriptions_by_country — List distinct product descriptions for transactions that occurred at gas stations in the specified country.
def run(conn, country):
        cur = conn.execute(
            "SELECT DISTINCT p.Description "
            "FROM transactions_1k AS t "
            "JOIN gasstations AS g ON t.GasStationID = g.GasStationID "
            "JOIN products AS p ON t.ProductID = p.ProductID "
            "WHERE g.Country = ? COLLATE NOCASE",
            (country,)
        )
        rows = cur.fetchall()
        return {"descriptions": [r[0] for r in rows]}
get_product_descriptions_by_country = run; del run

# get_product_id_by_datetime — Retrieve the ProductID of the transaction that occurred on a specific date and time.
def run(conn, date, time):
        cur = conn.execute(
            "SELECT T1.ProductID "
            "FROM transactions_1k AS T1 "
            "INNER JOIN gasstations AS T2 ON T1.GasStationID = T2.GasStationID "
            "WHERE T1.Date = ? AND T1.Time = ? "
            "LIMIT 1",
            (date, time)
        )
        row = cur.fetchone()
        return {"product_id": row[0] if row else None}
get_product_id_by_datetime = run; del run

# get_segment_percentage_by_country — Percentage of gas stations belonging to a specified segment within a given country. Calculated as (count of rows where Country and Segment match) * 100 / total rows for the country.
def run(conn, country, segment):
        # Total stations in the country
        total_row = conn.execute(
            "SELECT COUNT(*) FROM gasstations WHERE `Country` = ? COLLATE NOCASE",
            (country,)
        ).fetchone()
        total = total_row[0] if total_row else 0
    
        # Stations matching both country and segment
        seg_row = conn.execute(
            "SELECT COUNT(*) FROM gasstations WHERE `Country` = ? COLLATE NOCASE AND `Segment` = ? COLLATE NOCASE",
            (country, segment)
        ).fetchone()
        seg_count = seg_row[0] if seg_row else 0
    
        if total == 0:
            return {"percentage": None}
        percentage = (seg_count / total) * 100.0
        return {"percentage": percentage}
get_segment_percentage_by_country = run; del run

# get_segment_with_min_consumption — Return the Segment of the customer with the smallest total gas consumption. If `year_month` is provided, the calculation is limited to that month; otherwise it uses all months.
def run(conn, year_month=None):
        # Build the base query: sum consumption per customer
        sql = (
            "SELECT T1.CustomerID, T1.Segment, SUM(T2.Consumption) AS total_cons "
            "FROM customers AS T1 "
            "INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID "
        )
        params = []
        if year_month is not None:
            sql += "WHERE T2.Date = ? "
            params.append(year_month)
        sql += "GROUP BY T1.CustomerID ORDER BY total_cons ASC LIMIT 1"
        row = conn.execute(sql, tuple(params)).fetchone()
        return {"segment": row[1] if row else None}
get_segment_with_min_consumption = run; del run

# get_top_customer_by_currency_and_year — Return the CustomerID of the customer who consumed the most gas in a specified year while paying with a given currency.
def run(conn, currency, year):
        # Build start and end dates in YYYYMM format
        start_date = year * 100 + 1   # e.g., 201101
        end_date = year * 100 + 12    # e.g., 201112
        row = conn.execute(
            """SELECT T1.CustomerID
               FROM customers AS T1
               INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID
               WHERE T1.Currency = ? COLLATE NOCASE
                 AND T2.Date BETWEEN ? AND ?
               GROUP BY T1.CustomerID
               ORDER BY SUM(T2.Consumption) DESC
               LIMIT 1""",
            (currency, start_date, end_date)
        ).fetchone()
        return {"customer_id": row[0] if row else None}
get_top_customer_by_currency_and_year = run; del run

# get_top_customer_by_date — Return the CustomerID of the customer who paid the highest total Price on a specific transaction date.
def run(conn, date):
        row = conn.execute(
            "SELECT CustomerID FROM transactions_1k "
            "WHERE Date = ? COLLATE NOCASE "
            "GROUP BY CustomerID "
            "ORDER BY SUM(Price) DESC "
            "LIMIT 1",
            (date,)
        ).fetchone()
        return {"customer_id": row[0] if row else None}
get_top_customer_by_date = run; del run

# get_top_customer_by_segment_currency_and_month — Return the CustomerID of the customer in a specified segment who used a given currency and had the highest total consumption in a specific year‑month.
def run(conn, segment, currency, year_month):
    row = conn.execute(
        """
        SELECT T1.CustomerID
        FROM customers AS T1
        INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID
        WHERE T1.Segment = ? COLLATE NOCASE
          AND T1.Currency = ? COLLATE NOCASE
          AND T2.Date = ?
        GROUP BY T1.CustomerID
        ORDER BY SUM(T2.Consumption) DESC
        LIMIT 1
        """,
        (segment, currency, year_month)
    ).fetchone()
    return {"customer_id": row[0] if row else None}
get_top_customer_by_segment_currency_and_month = run; del run

# get_top_product_descriptions — Return the full product descriptions of the top‑selling products, ordered by transaction amount descending.
def run(conn, limit):
        rows = conn.execute(
            "SELECT T2.Description "
            "FROM transactions_1k AS T1 "
            "INNER JOIN products AS T2 ON T1.ProductID = T2.ProductID "
            "ORDER BY T1.Amount DESC "
            "LIMIT ?",
            (limit,)
        ).fetchall()
        descriptions = [r[0] for r in rows] if rows else []
        return {"descriptions": descriptions}
get_top_product_descriptions = run; del run

# get_total_consumption_by_customer_and_date_range — Total gas consumption for a specific customer between a start and end year‑month (inclusive).
def run(conn, customer_id, start_date, end_date):
        cur = conn.execute(
            "SELECT SUM(Consumption) FROM yearmonth "
            "WHERE CustomerID = ? AND Date BETWEEN ? AND ?",
            (customer_id, start_date, end_date)
        )
        row = cur.fetchone()
        return {"total_consumption": row[0] if row and row[0] is not None else None}
get_total_consumption_by_customer_and_date_range = run; del run

# get_total_consumption_by_segment_and_month — Total gas consumption for all customers of a given segment in a specific year‑month.
def run(conn, segment, year_month):
    cur = conn.execute(
        "SELECT SUM(T2.Consumption) "
        "FROM customers AS T1 "
        "INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID "
        "WHERE T2.Date = ? AND T1.Segment = ? COLLATE NOCASE",
        (year_month, segment)
    )
    row = cur.fetchone()
    return {"total_consumption": row[0] if row and row[0] is not None else None}
get_total_consumption_by_segment_and_month = run; del run

# get_year_with_max_gas_consumption_by_currency — Return the four‑digit year (YYYY) that recorded the highest total gas consumption for a specified currency.
def run(conn, currency):
        sql = (
            "SELECT SUBSTRING(T2.Date, 1, 4) AS yr, SUM(T2.Consumption) AS total "
            "FROM customers AS T1 "
            "JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID "
            "WHERE T1.Currency = ? COLLATE NOCASE "
            "GROUP BY yr "
            "ORDER BY total DESC "
            "LIMIT 1"
        )
        cur = conn.execute(sql, (currency,))
        row = cur.fetchone()
        return {"year": row[0] if row else None}
get_year_with_max_gas_consumption_by_currency = run; del run

# subtract_counts — Subtract count_b from count_a and return the numeric difference.
def run(conn, count_a, count_b):
        return {"difference": count_a - count_b}
subtract_counts = run; del run
