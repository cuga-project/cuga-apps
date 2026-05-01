"""Auto-generated MCP server exposing invocable tools for Bird db `california_schools`.

Run:
    python mcp_server.py            # binds 0.0.0.0:8765 by default

Configuration:
    SQLITE_PATH   path to california_schools.sqlite (required)
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


mcp = FastMCP("invocable-apis-california_schools")


@mcp.tool()
def avg_enrollment_by_county_for_charter_flag(charter_flag, min_charter_schools) -> str:
    """Average K‑12 enrollment per county for schools where the `Charter` column matches the supplied flag. Returns only counties that have at least `min_charter_schools` matching schools."""
    try:
        _ns = {}
        exec(compile("def run(conn, charter_flag, min_charter_schools):\n        sql = (\n            \"SELECT \\\"County Name\\\" AS county_name, \"\n            \"AVG(\\\"Enrollment (K-12)\\\") AS avg_enrollment \"\n            \"FROM schools \"\n            \"WHERE \\\"Charter\\\" = ? \"\n            \"GROUP BY \\\"County Name\\\" \"\n            \"HAVING COUNT(*) >= ?\"\n        )\n        rows = conn.execute(sql, (charter_flag, min_charter_schools)).fetchall()\n        averages = [\n            {\n                \"county_name\": row[0],\n                \"avg_enrollment\": float(row[1]) if row[1] is not None else None\n            }\n            for row in rows\n        ]\n        return {\"averages\": averages}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, charter_flag=charter_flag, min_charter_schools=min_charter_schools)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def avg_enrollment_difference_by_funding_type(funding_type) -> str:
    """Average of (Enrollment (K-12) − Enrollment (Ages 5-17)) for schools with a specified FundingType."""
    try:
        _ns = {}
        exec(compile("def run(conn, funding_type):\n        cur = conn.execute(\n            \"\"\"\n            SELECT AVG(T1.`Enrollment (K-12)` - T1.`Enrollment (Ages 5-17)`) AS avg_diff\n            FROM frpm AS T1\n            JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode\n            WHERE T2.FundingType = ?\n            \"\"\",\n            (funding_type,)\n        )\n        row = cur.fetchone()\n        return {\"avg_difference\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, funding_type=funding_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def avg_free_meal_ratio_by_county_with_high_ratio(ratio_threshold) -> str:
    """For each county that contains at least one school whose free‑meal ratio (Free Meal Count (K‑12) ÷ Enrollment (K‑12)) exceeds a given threshold, return the county name and the average free‑meal ratio across all its schools, ordered descending by the average."""
    try:
        _ns = {}
        exec(compile("def run(conn, ratio_threshold):\n        sql = (\n            \"SELECT `County Name` AS county_name, \"\n            \"AVG(`Free Meal Count (K-12)` * 1.0 / `Enrollment (K-12)`) AS avg_ratio \"\n            \"FROM frpm \"\n            \"WHERE `County Name` IN (\"\n            \"    SELECT `County Name` FROM frpm \"\n            \"    WHERE `Free Meal Count (K-12)` * 1.0 / `Enrollment (K-12)` > ?\"\n            \") \"\n            \"GROUP BY `County Name` \"\n            \"ORDER BY avg_ratio DESC\"\n        )\n        cur = conn.execute(sql, (ratio_threshold,))\n        rows = cur.fetchall()\n        # Return a list of dicts with clear keys\n        result = [\n            {\"county_name\": row[0], \"avg_ratio\": row[1]}\n            for row in rows\n        ]\n        return {\"averages\": result}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, ratio_threshold=ratio_threshold)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def avg_monthly_school_openings_by_doc_county_year(doc, county_name, year) -> str:
    """Average number of schools opened per month in a given year for a specific DOC and county."""
    try:
        _ns = {}
        exec(compile("def run(conn, doc, county_name, year):\n        cur = conn.execute(\n            \"SELECT COUNT(School) FROM schools \"\n            \"WHERE DOC = ? AND County = ? AND strftime('%Y', OpenDate) = ?\",\n            (doc, county_name, year)\n        )\n        row = cur.fetchone()\n        count = row[0] if row else 0\n        avg = (float(count) / 12) if count else None\n        return {\"monthly_average\": avg}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, doc=doc, county_name=county_name, year=year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_active_schools_by_city_state(city_name, mail_state, status_type) -> str:
    """Count schools whose mailing address is in a given city and state, and whose StatusType matches the specified value."""
    try:
        _ns = {}
        exec(compile("def run(conn, city_name, mail_state, status_type):\n        cur = conn.execute(\n            \"SELECT COUNT(CDSCode) FROM schools WHERE City = ? AND MailState = ? AND StatusType = ?\",\n            (city_name, mail_state, status_type)\n        )\n        row = cur.fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, city_name=city_name, mail_state=mail_state, status_type=status_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_charter_schools_in_city_by_doc(city_name, doc_code) -> str:
    """Count charter schools (Charter = 1) located in a specific city and owned by a given DOC district."""
    try:
        _ns = {}
        exec(compile("def run(conn, city_name, doc_code):\n        cur = conn.execute(\n            \"SELECT COUNT(School) FROM schools WHERE DOC = ? AND Charter = 1 AND City = ?\",\n            (doc_code, city_name)\n        )\n        row = cur.fetchone()\n        return {\"count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, city_name=city_name, doc_code=doc_code)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_closures_by_year_city_doc_type(year, city, doc_type) -> str:
    """Count schools that closed in a specific year, within a given city, and of a particular DOC type."""
    try:
        _ns = {}
        exec(compile("def run(conn, year, city, doc_type):\n        cur = conn.execute(\n            \"SELECT COUNT(School) FROM schools \"\n            \"WHERE strftime('%Y', ClosedDate) = ? AND City = ? AND DOCType = ?\",\n            (year, city, doc_type)\n        )\n        row = cur.fetchone()\n        return {\"closure_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, year=year, city=city, doc_type=doc_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_merged_schools_by_county_with_test_takers_below(county_name, max_test_takers) -> str:
    """Count schools whose StatusType is 'Merged', located in a specified county, and whose number of SAT test takers is less than a given threshold."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, max_test_takers):\n        cur = conn.execute(\n            \"SELECT COUNT(T1.CDSCode) \"\n            \"FROM schools AS T1 \"\n            \"INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds \"\n            \"WHERE T1.StatusType = ? AND T2.NumTstTakr < ? AND T1.County = ?\",\n            (\"Merged\", max_test_takers, county_name)\n        )\n        row = cur.fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, max_test_takers=max_test_takers)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_city_and_sat_total_ge(city_name, min_total_sat) -> str:
    """Count schools whose mailing city matches the supplied name and whose total SAT score (AvgScrRead + AvgScrMath + AvgScrWrite) is greater than or equal to a given threshold."""
    try:
        _ns = {}
        exec(compile("def run(conn, city_name, min_total_sat):\n    cur = conn.execute(\n        \"SELECT COUNT(T1.cds) FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.MailCity = ? AND (T1.AvgScrRead + T1.AvgScrMath + T1.AvgScrWrite) >= ?\",\n        (city_name, min_total_sat)\n    )\n    row = cur.fetchone()\n    return {\"school_count\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, city_name=city_name, min_total_sat=min_total_sat)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_city_state_and_status(city_name, mail_state, status_type) -> str:
    """Count schools whose mailing city, mailing state, and StatusType match the provided values."""
    try:
        _ns = {}
        exec(compile("def run(conn, city_name, mail_state, status_type):\n        cur = conn.execute(\n            \"SELECT COUNT(CDSCode) FROM schools WHERE City = ? AND MailState = ? AND StatusType = ?\",\n            (city_name, mail_state, status_type)\n        )\n        row = cur.fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, city_name=city_name, mail_state=mail_state, status_type=status_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_county_and_free_meal_frpm_range(county_name, min_free_meal, max_frpm) -> str:
    """Count schools in a given county where the K‑12 free‑meal count exceeds a minimum and the K‑12 FRPM count is below a maximum."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, min_free_meal, max_frpm):\n        cur = conn.execute(\n            \"SELECT COUNT(CDSCode) FROM frpm \"\n            \"WHERE `County Name` = ? \"\n            \"AND `Free Meal Count (K-12)` > ? \"\n            \"AND `FRPM Count (K-12)` < ?\",\n            (county_name, min_free_meal, max_frpm)\n        )\n        row = cur.fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, min_free_meal=min_free_meal, max_frpm=max_frpm)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_county_and_grade_range(county_name, low_grade, high_grade) -> str:
    """Count schools located in a specified county whose Low Grade and High Grade match given values."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, low_grade, high_grade):\n        row = conn.execute(\n            \"SELECT COUNT(T1.`School Name`) \"\n            \"FROM frpm AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T2.County = ? AND T1.`Low Grade` = ? AND T1.`High Grade` = ?\",\n            (county_name, low_grade, high_grade)\n        ).fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, low_grade=low_grade, high_grade=high_grade)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_county_free_meal_and_frpm_range(county_name, min_free_meals, max_frpm) -> str:
    """Count schools in a specified county whose K‑12 free‑meal count exceeds a minimum and whose K‑12 FRPM count is below a maximum."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, min_free_meals, max_frpm):\n        cur = conn.execute(\n            \"SELECT COUNT(CDSCode) FROM frpm \"\n            \"WHERE `County Name` = ? \"\n            \"AND `Free Meal Count (K-12)` > ? \"\n            \"AND `FRPM Count (K-12)` < ?\",\n            (county_name, min_free_meals, max_frpm)\n        )\n        row = cur.fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, min_free_meals=min_free_meals, max_frpm=max_frpm)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_county_funding_and_max_test_takers(county_name, funding_type, max_test_takers) -> str:
    """Count schools in a specified county and Charter Funding Type where the number of test takers (satscores.NumTstTakr) is at most a given maximum."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, funding_type, max_test_takers):\n        cur = conn.execute(\n            \"\"\"SELECT COUNT(T1.CDSCode)\n               FROM frpm AS T1\n               INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds\n               WHERE T1.`Charter Funding Type` = ?\n                 AND T1.`County Name` = ?\n                 AND T2.NumTstTakr <= ?\"\"\",\n            (funding_type, county_name, max_test_takers)\n        )\n        row = cur.fetchone()\n        return {\"count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, funding_type=funding_type, max_test_takers=max_test_takers)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_county_funding_and_open_year_range(county_name, funding_type, start_year, end_year) -> str:
    """Count schools in a given county whose FundingType matches the supplied value and whose opening year (extracted from OpenDate) falls between start_year and end_year inclusive."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, funding_type, start_year, end_year):\n        row = conn.execute(\n            \"SELECT COUNT(School) FROM schools \"\n            \"WHERE County = ? \"\n            \"AND FundingType = ? \"\n            \"AND CAST(strftime('%Y', OpenDate) AS INTEGER) BETWEEN ? AND ?\",\n            (county_name, funding_type, start_year, end_year),\n        ).fetchone()\n        return {\"school_count\": row[0] if row else 0}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, funding_type=funding_type, start_year=start_year, end_year=end_year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_funding_county_and_test_takers_below(county_name, charter_funding_type, max_test_takers) -> str:
    """Count schools in a specified county that have the given Charter Funding Type and whose number of SAT test takers is less than a provided maximum."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, charter_funding_type, max_test_takers):\n        row = conn.execute(\n            \"\"\"SELECT COUNT(T1.CDSCode)\n               FROM frpm AS T1\n               INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds\n               WHERE T1.`Charter Funding Type` = ?\n                 AND T1.`County Name` = ?\n                 AND T2.NumTstTakr < ?\"\"\",\n            (charter_funding_type, county_name, max_test_takers)\n        ).fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, charter_funding_type=charter_funding_type, max_test_takers=max_test_takers)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_math_score_and_charter_funding(min_math_score, charter_funding_type) -> str:
    """Count distinct schools whose average SAT Math score exceeds a given threshold and whose Charter Funding Type matches the specified value."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_math_score, charter_funding_type):\n        cur = conn.execute(\n            \"\"\"\n            SELECT COUNT(DISTINCT T2.`School Code`)\n            FROM satscores AS T1\n            JOIN frpm AS T2 ON T1.cds = T2.CDSCode\n            WHERE T1.AvgScrMath > ?\n              AND T2.`Charter Funding Type` = ?\n            \"\"\",\n            (min_math_score, charter_funding_type)\n        )\n        row = cur.fetchone()\n        return {\"count\": row[0] if row else 0}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_math_score=min_math_score, charter_funding_type=charter_funding_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_math_score_and_virtual(min_math_score, virtual_flag) -> str:
    """Count distinct schools whose average SAT Math score is greater than a given threshold and whose Virtual flag matches the specified value."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_math_score, virtual_flag):\n        cur = conn.execute(\n            \"\"\"SELECT COUNT(DISTINCT T2.School)\n               FROM satscores AS T1\n               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               WHERE T2.Virtual = ? AND T1.AvgScrMath > ?\"\"\",\n            (virtual_flag, min_math_score)\n        )\n        row = cur.fetchone()\n        return {\"count\": row[0] if row else 0}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_math_score=min_math_score, virtual_flag=virtual_flag)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_soc_county_and_statuses(soc_code, county_name, status_type_1, status_type_2) -> str:
    """Count schools with a given School Ownership Code (SOC), located in a specified county, whose StatusType matches either of two provided values."""
    try:
        _ns = {}
        exec(compile("def run(conn, soc_code, county_name, status_type_1, status_type_2):\n        cur = conn.execute(\n            \"SELECT COUNT(School) FROM schools \"\n            \"WHERE SOC = ? AND County = ? AND (StatusType = ? OR StatusType = ?)\",\n            (soc_code, county_name, status_type_1, status_type_2)\n        )\n        row = cur.fetchone()\n        return {\"school_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, soc_code=soc_code, county_name=county_name, status_type_1=status_type_1, status_type_2=status_type_2)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def count_schools_by_virtual_and_math_score(virtual_status, math_score_threshold) -> str:
    """Count distinct schools that have the specified virtual status and an average Math SAT score greater than a given threshold."""
    try:
        _ns = {}
        exec(compile("def run(conn, virtual_status, math_score_threshold):\n        cur = conn.execute(\n            \"\"\"SELECT COUNT(DISTINCT T2.School)\n               FROM satscores AS T1\n               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               WHERE T2.Virtual = ? AND T1.AvgScrMath > ?\"\"\",\n            (virtual_status, math_score_threshold)\n        )\n        row = cur.fetchone()\n        return {\"count\": row[0] if row else 0}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, virtual_status=virtual_status, math_score_threshold=math_score_threshold)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def extract_school_rows(schools_dict) -> str:
    """Extract the list of school rows from the dict returned by the previous tool."""
    try:
        _ns = {}
        exec(compile("def run(conn, schools_dict):\n        # The dict contains a key 'schools' with the list of rows\n        return {\"rows\": schools_dict.get(\"schools\", [])}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, schools_dict=schools_dict)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_active_district_with_highest_reading_sat_score() -> str:
    """District name of the active school that has the highest average SAT Reading score."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\n        \"SELECT T1.District \"\n        \"FROM schools AS T1 \"\n        \"INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds \"\n        \"WHERE T1.StatusType = 'Active' \"\n        \"ORDER BY T2.AvgScrRead DESC \"\n        \"LIMIT 1\"\n    ).fetchone()\n    return {\"district\": row[0] if row else None}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_address_of_school_with_lowest_excellence_rate() -> str:
    """Returns the complete address (Street, City, State, Zip) of the school that has the lowest excellence rate (NumGE1500 / NumTstTakr) in the California schools dataset."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        # Join satscores and schools, compute excellence rate, order ascending, limit 1\n        row = conn.execute(\n            \"\"\"SELECT T2.Street, T2.City, T2.State, T2.Zip\n               FROM satscores AS T1\n               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               ORDER BY CAST(T1.NumGE1500 AS REAL) / T1.NumTstTakr ASC\n               LIMIT 1\"\"\"\n        ).fetchone()\n        if not row:\n            return {\"address\": {\"street\": None, \"city\": None, \"state\": None, \"zip\": None}}\n        return {\"address\": {\"street\": row[0], \"city\": row[1], \"state\": row[2], \"zip\": row[3]}}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_admin_email_and_school_of_top_sat_ge1500() -> str:
    """Administrator email (AdmEmail1) and school name of the school with the highest NumGE1500."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\n        \"SELECT T2.AdmEmail1, T2.School \"\n        \"FROM satscores AS T1 \"\n        \"JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n        \"ORDER BY T1.NumGE1500 DESC \"\n        \"LIMIT 1\"\n    ).fetchone()\n    # Return a list of rows to match the gold result format\n    return {\"rows\": [[row[0] if row else None, row[1] if row else None]]}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_admin_email_of_charter_school_with_fewest_k12_enrollment() -> str:
    """Administrator email (AdmEmail1) of the charter school (Charter School (Y/N)=1) that has the fewest K‑12 students (minimum `Enrollment (K-12)`). Returns null if no charter schools exist."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT T2.AdmEmail1 \"\n            \"FROM frpm AS T1 \"\n            \"JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T1.`Charter School (Y/N)` = 1 \"\n            \"ORDER BY T1.`Enrollment (K-12)` ASC \"\n            \"LIMIT 1\"\n        ).fetchone()\n        return {\"admin_email\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_admin_emails_by_location_and_year(county_name, city_name, doc, soc, start_year, end_year) -> str:
    """Administrator email addresses (AdmEmail1, AdmEmail2) of schools that match the given county, city, DOC code, SOC code, and whose OpenDate year falls between start_year and end_year (inclusive). Returns a list of [email1, email2] rows."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, city_name, doc, soc, start_year, end_year):\n        cur = conn.execute(\n            \"\"\"SELECT T2.AdmEmail1, T2.AdmEmail2\n               FROM frpm AS T1\n               INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode\n               WHERE T2.County = ?\n                 AND T2.City = ?\n                 AND T2.DOC = ?\n                 AND T2.SOC = ?\n                 AND strftime('%Y', T2.OpenDate) BETWEEN ? AND ?\"\"\",\n            (county_name, city_name, doc, soc, start_year, end_year)\n        )\n        rows = cur.fetchall()\n        # Return list of [email1, email2] (NULLs are kept as None)\n        return {\"admin_emails\": [list(row) for row in rows]}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, city_name=city_name, doc=doc, soc=soc, start_year=start_year, end_year=end_year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_administrators_by_charter_number(charter_number) -> str:
    """Return first‑name, last‑name, school name, and city for all administrators of a chartered school identified by its CharterNum."""
    try:
        _ns = {}
        exec(compile("def run(conn, charter_number):\n        cursor = conn.execute(\n            \"SELECT AdmFName1, AdmLName1, School, City FROM schools WHERE Charter = 1 AND CharterNum = ?\",\n            (charter_number,)\n        )\n        # Return the raw list of rows so that validation can compare directly to the gold result\n        return cursor.fetchall()\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, charter_number=charter_number)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_average_test_takers_by_county_and_open_year(county_name, open_year) -> str:
    """Average number of SAT test takers (NumTstTakr) for schools in a specified county that opened in a given year."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, open_year):\n        cur = conn.execute(\n            \"SELECT AVG(T1.NumTstTakr) \"\n            \"FROM satscores AS T1 \"\n            \"JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n            \"WHERE strftime('%Y', T2.OpenDate) = ? AND T2.County = ?\",\n            (str(open_year), county_name)\n        )\n        row = cur.fetchone()\n        return {\"average_test_takers\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, open_year=open_year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_average_writing_score_by_admin(admin_first_name, admin_last_name) -> str:
    """Returns a list of schools managed by the specified administrator and each school's average SAT writing score."""
    try:
        _ns = {}
        exec(compile("def run(conn, admin_first_name, admin_last_name):\n        cur = conn.execute(\n            \"\"\"SELECT s.School, ss.AvgScrWrite\n               FROM satscores ss\n               JOIN schools s ON ss.cds = s.CDSCode\n               WHERE s.AdmFName1 = ? AND s.AdmLName1 = ?\"\"\",\n            (admin_first_name, admin_last_name)\n        )\n        rows = cur.fetchall()\n        return {\"schools\": rows}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, admin_first_name=admin_first_name, admin_last_name=admin_last_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_avg_math_and_county_of_school_with_lowest_total_average() -> str:
    """Returns the average Math SAT score and county of the school whose sum of average Math, Reading, and Writing scores is minimal, formatted as a list of rows."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT T1.AvgScrMath, T2.County \"\n            \"FROM satscores AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n            \"WHERE T1.AvgScrMath IS NOT NULL \"\n            \"ORDER BY (T1.AvgScrMath + T1.AvgScrRead + T1.AvgScrWrite) ASC \"\n            \"LIMIT 1\"\n        ).fetchone()\n        if row:\n            return {\"result\": [[row[0], row[1]]]}\n        else:\n            return {\"result\": []}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_avg_writing_score_and_city_of_top_ge1500_school() -> str:
    """Returns the average writing SAT score and the city of the school that has the highest count of test‑takers with total SAT scores ≥ 1500."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        sql = (\n            \"SELECT T1.AvgScrWrite, T2.City \"\n            \"FROM satscores AS T1 \"\n            \"JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n            \"ORDER BY T1.NumGE1500 DESC \"\n            \"LIMIT 1\"\n        )\n        row = conn.execute(sql).fetchone()\n        if not row:\n            return {\"result\": []}\n        # Return a list of rows to match the gold\u2011SQL shape\n        return {\"result\": [[row[0], row[1]]]}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_cds_of_highest_frpm_count() -> str:
    """Return the CDSCode of the school with the highest FRPM Count (K-12) in the frpm table."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT CDSCode FROM frpm ORDER BY `FRPM Count (K-12)` DESC LIMIT 1\"\n        ).fetchone()\n        return {\"cds\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_cities_of_schools_by_criteria(county_name, provision_status, low_grade, high_grade, school_level_code) -> str:
    """Return the city name(s) of schools that match the specified county, NSLP provision status, lowest grade, highest grade, and school level (EILCode)."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, provision_status, low_grade, high_grade, school_level_code):\n        sql = (\n            \"SELECT T2.City FROM frpm AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T1.`NSLP Provision Status` = ? \"\n            \"AND T2.County = ? \"\n            \"AND T1.`Low Grade` = ? \"\n            \"AND T1.`High Grade` = ? \"\n            \"AND T2.EILCode = ?\"\n        )\n        rows = conn.execute(sql, (\n            provision_status,\n            county_name,\n            low_grade,\n            high_grade,\n            school_level_code,\n        )).fetchall()\n        cities = [row[0] for row in rows]  # list of city strings, may be empty\n        return {\"cities\": cities}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, provision_status=provision_status, low_grade=low_grade, high_grade=high_grade, school_level_code=school_level_code)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_cities_with_lowest_k12_enrollment(limit) -> str:
    """Cities with the smallest total K‑12 enrollment across all schools."""
    try:
        _ns = {}
        exec(compile("def run(conn, limit):\n        rows = conn.execute(\n            \"SELECT T2.City FROM frpm AS T1 JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"GROUP BY T2.City ORDER BY SUM(T1.`Enrollment (K-12)`) ASC LIMIT ?\",\n            (limit,)\n        ).fetchall()\n        # Return each city as a single\u2011element list to match the gold row shape\n        cities = [[row[0]] for row in rows]\n        return {\"cities\": cities}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_county_with_most_closures_by_soc_and_year_range(soc_code, start_year, end_year) -> str:
    """County that has the highest number of schools closed in a given year range for a specific SOC ownership code."""
    try:
        _ns = {}
        exec(compile("def run(conn, soc_code, start_year, end_year):\n    row = conn.execute(\n        \"SELECT County FROM schools \"\n        \"WHERE strftime('%Y', ClosedDate) BETWEEN ? AND ? \"\n        \"AND StatusType = 'Closed' AND SOC = ? \"\n        \"GROUP BY County \"\n        \"ORDER BY COUNT(School) DESC \"\n        \"LIMIT 1\",\n        (start_year, end_year, soc_code)\n    ).fetchone()\n    return {\"county\": row[0] if row else None}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, soc_code=soc_code, start_year=start_year, end_year=end_year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_county_with_most_schools_without_physical_building(county_a, county_b) -> str:
    """Among the two specified counties, return the county that has the most schools where `Virtual` = 'F' (does not offer a physical building) and the count of such schools. The output shape matches the gold SQL: a list of rows [[County, count]]."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_a, county_b):\n    cur = conn.execute(\n        \"SELECT County, COUNT(*) FROM schools WHERE County IN (?, ?) AND Virtual = 'F' GROUP BY County ORDER BY COUNT(*) DESC LIMIT 1\",\n        (county_a, county_b)\n    )\n    rows = cur.fetchall()\n    # Convert sqlite Row objects to plain Python lists\n    return [list(r) for r in rows]\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_a=county_a, county_b=county_b)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_district_codes_by_city_and_magnet(city_name, magnet_flag) -> str:
    """District codes of schools located in a specified city that have the given magnet flag."""
    try:
        _ns = {}
        exec(compile("def run(conn, city_name, magnet_flag):\n    cur = conn.execute(\n        \"SELECT T1.`District Code` FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.City = ? AND T2.Magnet = ?\",\n        (city_name, magnet_flag)\n    )\n    rows = cur.fetchall()\n    return {\"district_codes\": [row[0] for row in rows]}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, city_name=city_name, magnet_flag=magnet_flag)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_education_type_of_school_with_highest_average_score(subject) -> str:
    """Return the EdOpsName (type of education) of the school that achieved the highest average SAT score for a given subject."""
    try:
        _ns = {}
        exec(compile("def run(conn, subject):\n        # Map subject to the corresponding column in satscores\n        col_map = {\n            \"Math\": \"AvgScrMath\",\n            \"Reading\": \"AvgScrReading\",\n            \"Science\": \"AvgScrScience\"\n        }\n        col = col_map.get(subject)\n        if not col:\n            return {\"education_type\": None}\n        # Build the query safely using the validated column name\n        query = '''SELECT T2.EdOpsName\n    FROM satscores AS T1\n    JOIN schools AS T2 ON T1.cds = T2.CDSCode\n    ORDER BY T1.{col} DESC\n    LIMIT 1'''\n        row = conn.execute(query.format(col=col)).fetchone()\n        return {\"education_type\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, subject=subject)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_eligible_free_rate_by_enrollment_rank(offset, limit) -> str:
    """Returns the eligible free‑meal rate (Free Meal Count (K-12) / Enrollment (K-12)) for schools sorted by descending K‑12 enrollment, skipping a given number of top schools (offset) and returning a specified number of rows (limit)."""
    try:
        _ns = {}
        exec(compile("def run(conn, offset, limit):\n    rows = conn.execute(\n        \"\"\"SELECT CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)` AS rate\n           FROM frpm\n           ORDER BY `Enrollment (K-12)` DESC\n           LIMIT ? OFFSET ?\"\"\",\n        (limit, offset)\n    ).fetchall()\n    rates = [row[0] if row[0] is not None else None for row in rows]\n    return {\"rates\": rates}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, offset=offset, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_enrollment_5_17_by_edops_city_year_range(edops_code, city, start_year, end_year) -> str:
    """Return `Enrollment (Ages 5-17)` values from frpm for schools matching a given EdOpsCode, city, and academic year range."""
    try:
        _ns = {}
        exec(compile("def run(conn, edops_code, city, start_year, end_year):\n        sql = (\n            \"SELECT T1.`Enrollment (Ages 5-17)` \"\n            \"FROM frpm AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T2.EdOpsCode = ? AND T2.City = ? AND T1.`Academic Year` BETWEEN ? AND ?\"\n        )\n        cur = conn.execute(sql, (edops_code, city, start_year, end_year))\n        rows = cur.fetchall()\n        enrollments = [row[0] for row in rows]\n        return {\"enrollments\": enrollments}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, edops_code=edops_code, city=city, start_year=start_year, end_year=end_year)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_free_meal_rate_by_admin_name(admin_first_name, admin_last_name) -> str:
    """Eligible free‑meal rate (Free Meal Count (Ages 5‑17) / Enrollment (Ages 5‑17)) for the school administered by the specified first and last name."""
    try:
        _ns = {}
        exec(compile("def run(conn, admin_first_name, admin_last_name):\n        row = conn.execute(\n            \"SELECT CAST(T2.`Free Meal Count (Ages 5-17)` AS REAL) / T2.`Enrollment (Ages 5-17)` \"\n            \"FROM schools AS T1 \"\n            \"INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T1.AdmFName1 = ? AND T1.AdmLName1 = ?\",\n            (admin_first_name, admin_last_name)\n        ).fetchone()\n        return {\"free_rate\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, admin_first_name=admin_first_name, admin_last_name=admin_last_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_frpm_count_ages_5_17_for_highest_reading_sat_school() -> str:
    """FRPM count (Ages 5-17) for the school that has the highest average SAT Reading score."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT T2.`FRPM Count (Ages 5-17)` \"\n            \"FROM satscores AS T1 \"\n            \"INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode \"\n            \"ORDER BY T1.AvgScrRead DESC \"\n            \"LIMIT 1\"\n        ).fetchone()\n        return {\"frpm_count_5_17\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_frpm_count_by_mailstreet_and_soc_type(mail_street, soc_type) -> str:
    """Return the free or reduced price meal count for ages 5‑17 (`FRPM Count (Ages 5-17)`) for the school matching a given mailing street address and SOC type."""
    try:
        _ns = {}
        exec(compile("def run(conn, mail_street, soc_type):\n        row = conn.execute(\n            \"SELECT T1.`FRPM Count (Ages 5-17)` \"\n            \"FROM frpm AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T2.MailStreet = ? AND T2.SOCType = ?\",\n            (mail_street, soc_type)\n        ).fetchone()\n        return {\"frpm_count\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, mail_street=mail_street, soc_type=soc_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_frpm_percent_by_county_and_grade_span(county_name, grade_span) -> str:
    """List schools in a given county that serve the specified grade span (GSserved) and their Percent (%) Eligible FRPM for ages 5‑17."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, grade_span):\n        cur = conn.execute(\n            \"SELECT T2.School, \"\n            \"(T1.`FRPM Count (Ages 5-17)` * 100.0) / T1.`Enrollment (Ages 5-17)` AS percent \"\n            \"FROM frpm AS T1 \"\n            \"JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T2.County = ? AND T2.GSserved = ?\",\n            (county_name, grade_span)\n        )\n        rows = cur.fetchall()\n        # Build list of [school, percent]; handle possible NULL division result\n        results = [[row[0], row[1] if row[1] is not None else None] for row in rows]\n        return {\"results\": results}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, grade_span=grade_span)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_grade_span_of_school_with_highest_longitude() -> str:
    """Returns the grade span (GSoffered) of the school that has the highest absolute longitude value."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\"SELECT GSoffered FROM schools ORDER BY ABS(longitude) DESC LIMIT 1\").fetchone()\n    return {\"grade_span\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_high_schools_in_county_with_free_meal_and_type(county_name, min_free_meal, school_type) -> str:
    """Return rows of high schools in a county with free‑meal count > threshold, matching the gold‑SQL shape."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, min_free_meal, school_type):\n        cursor = conn.execute(\n            \"\"\"SELECT T1.`School Name`,\n                      T2.Street,\n                      T2.City,\n                      T2.State,\n                      T2.Zip\n               FROM frpm AS T1\n               INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode\n               WHERE T2.County = ?\n                 AND T1.`Free Meal Count (Ages 5-17)` > ?\n                 AND T1.`School Type` = ?\"\"\",\n            (county_name, min_free_meal, school_type)\n        )\n        # Return a list of rows (each row is a list of column values)\n        return [list(r) for r in cursor.fetchall()]\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, min_free_meal=min_free_meal, school_type=school_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_highest_free_meal_rate_by_sat_excellence(min_excellence_rate) -> str:
    """Highest eligible free‑meal rate (Free Meal Count Ages 5‑17 / Enrollment Ages 5‑17) among schools with SAT excellence rate > min_excellence_rate."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_excellence_rate):\n        # Compute the maximum free\u2011meal rate for ages 5\u201117 among schools\n        # whose SAT excellence rate exceeds the supplied threshold.\n        sql = (\n            \"SELECT MAX(CAST(frpm.`Free Meal Count (Ages 5-17)` AS REAL) / frpm.`Enrollment (Ages 5-17)`) \"\n            \"FROM frpm \"\n            \"INNER JOIN satscores ON frpm.CDSCode = satscores.cds \"\n            \"WHERE CAST(satscores.NumGE1500 AS REAL) / satscores.NumTstTakr > ?\"\n        )\n        cur = conn.execute(sql, (min_excellence_rate,))\n        row = cur.fetchone()\n        return {\"max_free_meal_rate\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_excellence_rate=min_excellence_rate)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_highest_free_meal_ratio_by_county(county_name) -> str:
    """Maximum K‑12 free‑meal ratio (Free Meal Count (K‑12) / Enrollment (K‑12)) among schools in a specified California county."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name):\n        cur = conn.execute(\n            \"\"\"\n            SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)`\n            FROM frpm\n            WHERE `County Name` = ?\n            ORDER BY (CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`) DESC\n            LIMIT 1\n            \"\"\",\n            (county_name,)\n        )\n        row = cur.fetchone()\n        return {\"ratio\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_locally_funded_charter_ratio_by_county(county_name) -> str:
    """Percentage ratio of charter schools that are locally funded to charter schools with any other funding type within a given county."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name):\n        # Compute counts of locally funded charter schools and all other charter funding types.\n        cur = conn.execute(\n            \"\"\"\n            SELECT\n                CAST(SUM(CASE WHEN FundingType = 'Locally funded' THEN 1 ELSE 0 END) AS REAL) * 100.0\n                / NULLIF(SUM(CASE WHEN FundingType != 'Locally funded' THEN 1 ELSE 0 END), 0)\n            FROM schools\n            WHERE County = ? AND Charter = 1\n            \"\"\",\n            (county_name,)\n        )\n        row = cur.fetchone()\n        return {\"ratio_percent\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_locally_funded_charter_ratio_percent(county_name) -> str:
    """Compute the percentage ratio of locally funded charter schools to all other charter school funding types within a specified county."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name):\n        # Count locally funded charter schools and count of all other charter funding types in the given county.\n        cur = conn.execute(\n            \"\"\"SELECT\n                   CAST(SUM(CASE WHEN FundingType = 'Locally funded' THEN 1 ELSE 0 END) AS REAL) * 100.0\n                   / NULLIF(SUM(CASE WHEN FundingType != 'Locally funded' THEN 1 ELSE 0 END), 0)\n               FROM schools\n               WHERE County = ? AND Charter = 1\"\"\",\n            (county_name,)\n        )\n        row = cur.fetchone()\n        ratio = row[0] if row and row[0] is not None else None\n        return {\"ratio_percent\": ratio}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_lowest_free_meal_rates_by_school_type(school_type, limit) -> str:
    """Return the lowest N eligible free‑meal rates for students aged 5‑17 in schools of a specified Educational Option Type. The rate is `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)`."""
    try:
        _ns = {}
        exec(compile("def run(conn, school_type, limit):\n        cur = conn.execute(\n            \"\"\"SELECT `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` AS ratio\n               FROM frpm\n               WHERE `Educational Option Type` = ?\n                 AND `Free Meal Count (Ages 5-17)` IS NOT NULL\n                 AND `Enrollment (Ages 5-17)` IS NOT NULL\n                 AND `Enrollment (Ages 5-17)` != 0\n               ORDER BY ratio ASC\n               LIMIT ?\"\"\",\n            (school_type, limit)\n        )\n        rows = cur.fetchall()\n        rates = [row[0] for row in rows] if rows else []\n        return {\"rates\": rates}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, school_type=school_type, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_lowest_low_grade_by_ncesdist_and_edopscode(nces_dist, edops_code) -> str:
    """Minimum `Low Grade` among schools whose NCES district ID (NCESDist) and Education Operations Code (EdOpsCode) match the given values."""
    try:
        _ns = {}
        exec(compile("def run(conn, nces_dist, edops_code):\n        cur = conn.execute(\n            \"SELECT MIN(frpm.`Low Grade`) \"\n            \"FROM frpm \"\n            \"INNER JOIN schools ON frpm.CDSCode = schools.CDSCode \"\n            \"WHERE schools.NCESDist = ? AND schools.EdOpsCode = ?\",\n            (nces_dist, edops_code)\n        )\n        row = cur.fetchone()\n        return {\"lowest_low_grade\": row[0] if row and row[0] is not None else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, nces_dist=nces_dist, edops_code=edops_code)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_mailing_street_of_school_with_highest_frpm_k12() -> str:
    """Unabbreviated mailing street address of the school that has the highest FRPM Count (K‑12) in the dataset."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT T2.MailStreet \"\n            \"FROM frpm AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"ORDER BY T1.`FRPM Count (K-12)` DESC \"\n            \"LIMIT 1\"\n        ).fetchone()\n        return {\"mail_street\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_math_score_and_county_of_school_with_lowest_total_average_score() -> str:
    """Returns the average Math SAT score and the county of the school whose combined average scores (Math + Reading + Writing) are the lowest among all schools."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT T1.AvgScrMath, T2.County \"\n            \"FROM satscores AS T1 \"\n            \"JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n            \"WHERE T1.AvgScrMath IS NOT NULL \"\n            \"ORDER BY (T1.AvgScrMath + T1.AvgScrRead + T1.AvgScrWrite) ASC \"\n            \"LIMIT 1\"\n        ).fetchone()\n        if row:\n            return {\"result\": [[row[0], row[1]]]}\n        else:\n            return {\"result\": []}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_merged_district_ratio_by_county(county_name, numerator_doc, denominator_doc, status_type) -> str:
    """Compute the ratio of the number of merged schools with a specified numerator DOC code to the number with a specified denominator DOC code in a given county."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, numerator_doc, denominator_doc, status_type=\"Merged\"):\n        cur = conn.execute(\n            \"\"\"SELECT\n                   CAST(SUM(CASE WHEN DOC = ? THEN 1 ELSE 0 END) AS REAL) /\n                   NULLIF(SUM(CASE WHEN DOC = ? THEN 1 ELSE 0 END), 0)\n               FROM schools\n               WHERE StatusType = ? AND County = ?\"\"\",\n            (numerator_doc, denominator_doc, status_type, county_name)\n        )\n        row = cur.fetchone()\n        return {\"ratio\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, numerator_doc=numerator_doc, denominator_doc=denominator_doc, status_type=status_type)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_most_common_grade_span_by_city(city_name) -> str:
    """Most common grade span (GSserved) served by schools in a specified city."""
    try:
        _ns = {}
        exec(compile("def run(conn, city_name):\n        row = conn.execute(\n            \"SELECT GSserved FROM schools \"\n            \"WHERE City = ? \"\n            \"GROUP BY GSserved \"\n            \"ORDER BY COUNT(GSserved) DESC \"\n            \"LIMIT 1\",\n            (city_name,)\n        ).fetchone()\n        return {\"grade_span\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, city_name=city_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_nces_district_ids_by_school_ownership_code(soc_code) -> str:
    """Return the NCES district identification numbers (NCESDist) for all schools with a specified School Ownership Code (SOC)."""
    try:
        _ns = {}
        exec(compile("def run(conn, soc_code):\n        cur = conn.execute(\n            \"SELECT NCESDist FROM schools WHERE SOC = ?\",\n            (soc_code,)\n        )\n        rows = cur.fetchall()\n        ids = [row[0] for row in rows if row[0] is not None]\n        return {\"nces_district_ids\": ids}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, soc_code=soc_code)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_open_date_of_school_with_largest_k12_enrollment() -> str:
    """OpenDate of the first‑through‑twelfth‑grade school that has the largest K‑12 enrollment."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\n        \"SELECT T2.OpenDate \"\n        \"FROM frpm AS T1 \"\n        \"JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n        \"ORDER BY T1.`Enrollment (K-12)` DESC \"\n        \"LIMIT 1\"\n    ).fetchone()\n    return {'open_date': row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_partially_virtual_charter_school_websites_by_county(county_name) -> str:
    """Website URLs of schools that are charter (Charter=1) and partially virtual (Virtual='P') in the specified county."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name):\n        rows = conn.execute(\n            \"SELECT Website FROM schools WHERE County = ? AND Virtual = 'P' AND Charter = 1\",\n            (county_name,)\n        ).fetchall()\n        websites = [row[0] for row in rows]\n        return {\"websites\": websites}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_percent_eligible_free_by_admin_first_name(admin_first_name) -> str:
    """Returns a single row [percent, district_code] for the school administered by the given administrator first name."""
    try:
        _ns = {}
        exec(compile("def run(conn, admin_first_name):\n        cur = conn.execute(\n            \"SELECT T1.`Free Meal Count (K-12)` * 100.0 / T1.`Enrollment (K-12)`, \"\n            \"T1.`District Code` \"\n            \"FROM frpm AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T2.AdmFName1 = ?\",\n            (admin_first_name,)\n        )\n        row = cur.fetchone()\n        if row is None:\n            return []          # no rows\n        return [[row[0], row[1]]]\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, admin_first_name=admin_first_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_phone_and_ext_by_zip(zip_code) -> str:
    """Return a single row (phone, extension, school) for the school with the given ZIP code."""
    try:
        _ns = {}
        exec(compile("def run(conn, zip_code):\n        row = conn.execute(\n            \"SELECT Phone, Ext, School FROM schools WHERE Zip = ?\",\n            (zip_code,)\n        ).fetchone()\n        if row:\n            return {\"rows\": [row]}\n        return {\"rows\": []}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, zip_code=zip_code)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_phone_numbers_of_charter_schools(funding_type, charter_flag, open_date) -> str:
    """Phone numbers of schools that are charter schools with a specified Charter Funding Type and opened after a given date."""
    try:
        _ns = {}
        exec(compile("def run(conn, funding_type, charter_flag, open_date):\n        rows = conn.execute(\n            \"\"\"SELECT T2.Phone\n               FROM frpm AS T1\n               INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode\n               WHERE T1.`Charter Funding Type` = ?\n                 AND T1.`Charter School (Y/N)` = ?\n                 AND T2.OpenDate > ?\"\"\",\n            (funding_type, charter_flag, open_date)\n        ).fetchall()\n        phones = [row[0] for row in rows]\n        return {\"phones\": phones}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, funding_type=funding_type, charter_flag=charter_flag, open_date=open_date)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_phone_numbers_of_top_schools_by_sat_excellence_rate(limit) -> str:
    """Phone numbers of the schools with the highest SAT excellence rate (NumGE1500 / NumTstTakr)."""
    try:
        _ns = {}
        exec(compile("def run(conn, limit):\n        rows = conn.execute(\n            \"\"\"\n            SELECT T1.Phone\n            FROM schools AS T1\n            JOIN satscores AS T2 ON T1.CDSCode = T2.cds\n            ORDER BY CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr DESC\n            LIMIT ?\n            \"\"\",\n            (limit,)\n        ).fetchall()\n        phones = [row[0] for row in rows]\n        return {\"phones\": phones}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_phone_of_lowest_reading_score_school_in_district(district_name) -> str:
    """Return the telephone number of the school with the lowest average reading score (AvgScrRead) in the specified district, considering only non‑NULL scores."""
    try:
        _ns = {}
        exec(compile("def run(conn, district_name):\n        row = conn.execute(\n            \"\"\"SELECT T2.Phone\n               FROM satscores AS T1\n               JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               WHERE T2.District = ?\n                 AND T1.AvgScrRead IS NOT NULL\n               ORDER BY T1.AvgScrRead ASC\n               LIMIT 1\"\"\",\n            (district_name,)\n        ).fetchone()\n        return {\"phone\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, district_name=district_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_phone_of_school_with_highest_math_sat_score() -> str:
    """Return the phone number of the school that has the highest average Math SAT score."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\n        \"SELECT T1.Phone \"\n        \"FROM schools AS T1 \"\n        \"JOIN satscores AS T2 ON T1.CDSCode = T2.cds \"\n        \"WHERE T2.AvgScrMath IS NOT NULL \"\n        \"ORDER BY T2.AvgScrMath DESC \"\n        \"LIMIT 1\"\n    ).fetchone()\n    return {\"phone\": row[0] if row else None}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_phone_of_school_with_highest_math_score() -> str:
    """Phone number of the school that has the highest average SAT Math score."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\n        \"SELECT T1.Phone \"\n        \"FROM schools AS T1 \"\n        \"JOIN satscores AS T2 ON T1.CDSCode = T2.cds \"\n        \"ORDER BY T2.AvgScrMath DESC \"\n        \"LIMIT 1\"\n    ).fetchone()\n    return {\"phone\": row[0] if row else None}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_phone_of_school_with_highest_sat_ge1500() -> str:
    """Phone number of the school that has the highest number of SAT test takers with scores over 1500."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT T2.Phone \"\n            \"FROM satscores AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n            \"ORDER BY T1.NumGE1500 DESC \"\n            \"LIMIT 1\"\n        ).fetchone()\n        return {\"phone\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_sat_test_takers_by_cds(cds) -> str:
    """Return the number of SAT test takers (NumTstTakr) for a given school identified by its CDSCode."""
    try:
        _ns = {}
        exec(compile("def run(conn, cds):\n        row = conn.execute(\n            \"SELECT NumTstTakr FROM satscores WHERE cds = ?\",\n            (cds,)\n        ).fetchone()\n        return {\"num_test_takers\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, cds=cds)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_sat_test_takers_of_school_with_highest_frpm_k12() -> str:
    """Number of SAT test takers (NumTstTakr) for the school that has the highest FRPM Count (K‑12) in the dataset."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        # Find the CDSCode of the school with the maximum FRPM Count (K\u201112)\n        cur = conn.execute(\n            \"SELECT CDSCode FROM frpm ORDER BY `FRPM Count (K-12)` DESC LIMIT 1\"\n        )\n        row = cur.fetchone()\n        if not row:\n            return {\"sat_test_takers\": None}\n        cds_code = row[0]\n        # Retrieve NumTstTakr from satscores for that CDSCode\n        cur2 = conn.execute(\n            \"SELECT NumTstTakr FROM satscores WHERE cds = ?\", (cds_code,)\n        )\n        row2 = cur2.fetchone()\n        return {\"sat_test_takers\": row2[0] if row2 else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_address_by_math_rank(rank) -> str:
    """Returns the MailStreet (postal street address) and School name of the school that ranks `rank`‑th highest in average Math SAT score."""
    try:
        _ns = {}
        exec(compile("def run(conn, rank):\n        offset = max(rank - 1, 0)\n        row = conn.execute(\n            \"\"\"SELECT T2.MailStreet, T2.School\n               FROM satscores AS T1\n               JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               ORDER BY T1.AvgScrMath DESC\n               LIMIT ?, 1\"\"\",\n            (offset,)\n        ).fetchone()\n        if row:\n            return {\"rows\": [[row[0], row[1]]]}\n        else:\n            return {\"rows\": []}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, rank=rank)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_codes_by_min_total_enrollment(min_total_enrollment) -> str:
    """Return CDSCode identifiers of schools whose total enrollment (K‑12 + Ages 5‑17) exceeds the given threshold."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_total_enrollment):\n        rows = conn.execute(\n            \"SELECT T2.CDSCode \"\n            \"FROM schools AS T1 \"\n            \"INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE T2.`Enrollment (K-12)` + T2.`Enrollment (Ages 5-17)` > ?\",\n            (min_total_enrollment,)\n        ).fetchall()\n        return {\"cds_codes\": [r[0] for r in rows]}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_total_enrollment=min_total_enrollment)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_codes_with_total_enrollment_over(min_total_enrollment) -> str:
    """Return CDS codes of schools where total enrollment (K-12 plus Ages 5-17) is greater than a specified threshold."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_total_enrollment):\n        cursor = conn.execute(\n            \"SELECT T2.CDSCode \"\n            \"FROM schools AS T1 \"\n            \"INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"WHERE (T2.`Enrollment (K-12)` + T2.`Enrollment (Ages 5-17)`) > ?\",\n            (min_total_enrollment,)\n        )\n        rows = cursor.fetchall()\n        codes = [row[0] for row in rows] if rows else []\n        return {\"school_codes\": codes}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_total_enrollment=min_total_enrollment)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_count_ratio_by_state_and_two_counties(state, county_a, county_b) -> str:
    """Computes the ratio of the number of schools in `county_a` to the number in `county_b` among schools whose mailing address state equals `state`."""
    try:
        _ns = {}
        exec(compile("def run(conn, state, county_a, county_b):\n        # Count schools in each county within the specified mailing state.\n        cur = conn.execute(\n            \"\"\"SELECT\n                   CAST(SUM(CASE WHEN County = ? THEN 1 ELSE 0 END) AS REAL) AS cnt_a,\n                   SUM(CASE WHEN County = ? THEN 1 ELSE 0 END) AS cnt_b\n               FROM schools\n               WHERE MailState = ?\"\"\",\n            (county_a, county_b, state)\n        )\n        row = cur.fetchone()\n        cnt_a, cnt_b = (row[0], row[1]) if row else (0, 0)\n        ratio = cnt_a / cnt_b if cnt_b != 0 else None\n        return {\"ratio\": ratio}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, state=state, county_a=county_a, county_b=county_b)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_percent_frpm_by_county_and_grade_span(county_name, grade_span) -> str:
    """List schools in a specified county that serve the given grade span, along with the percent of students eligible for FRPM (Ages 5‑17). Percent = FRPM Count (Ages 5‑17) * 100 / Enrollment (Ages 5‑17)."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, grade_span):\n        cursor = conn.execute(\n            \"SELECT s.School, (f.`FRPM Count (Ages 5-17)` * 100.0) / f.`Enrollment (Ages 5-17)` AS percent \"\n            \"FROM frpm AS f JOIN schools AS s ON f.CDSCode = s.CDSCode \"\n            \"WHERE s.County = ? AND s.GSserved = ?\",\n            (county_name, grade_span)\n        )\n        rows = cursor.fetchall()\n        return {\"schools_percent\": rows}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, grade_span=grade_span)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_websites_by_county_and_test_takers(county_name, min_test_takers, max_test_takers) -> str:
    """Return the website URLs of schools in a specified county whose SAT test taker count falls within a given inclusive range."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, min_test_takers, max_test_takers):\n        sql = (\n            \"SELECT T2.Website \"\n            \"FROM satscores AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n            \"WHERE T1.NumTstTakr BETWEEN ? AND ? \"\n            \"AND T2.County = ?\"\n        )\n        rows = conn.execute(sql, (min_test_takers, max_test_takers, county_name)).fetchall()\n        websites = [row[0] for row in rows]\n        return {\"websites\": websites}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, min_test_takers=min_test_takers, max_test_takers=max_test_takers)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_websites_by_county_virtual_charter(county_name, virtual_status, charter) -> str:
    """Retrieve the list of website URLs for schools in a specified county that match a given virtual status and charter flag."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, virtual_status, charter):\n        rows = conn.execute(\n            \"SELECT Website FROM schools WHERE County = ? AND Virtual = ? AND Charter = ?\",\n            (county_name, virtual_status, charter)\n        ).fetchall()\n        websites = [r[0] for r in rows] if rows else []\n        return {\"websites\": websites}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, virtual_status=virtual_status, charter=charter)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_websites_by_free_meal_range_ages_5_17(min_free_meal, max_free_meal) -> str:
    """Website URLs and school names for schools where `Free Meal Count (Ages 5-17)` is between the given inclusive bounds. Excludes rows with NULL website."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_free_meal, max_free_meal):\n    cursor = conn.execute(\n        \"\"\"SELECT T2.Website, T1.`School Name`\n           FROM frpm AS T1\n           JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode\n           WHERE T1.`Free Meal Count (Ages 5-17)` BETWEEN ? AND ?\n             AND T2.Website IS NOT NULL\"\"\",\n        (min_free_meal, max_free_meal)\n    )\n    rows = cursor.fetchall()\n    return {\"websites\": rows}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_free_meal=min_free_meal, max_free_meal=max_free_meal)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_with_highest_latitude() -> str:
    """Return a single row containing the school type, school name, and latitude of the school with the maximum latitude."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"SELECT T1.`School Type`, T1.`School Name`, T2.Latitude \"\n            \"FROM frpm AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode \"\n            \"ORDER BY T2.Latitude DESC LIMIT 1\"\n        ).fetchone()\n        if row is None:\n            return []                     # no rows\n        return [[row[0], row[1], row[2]]]  # list of one row\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_with_highest_test_takers_by_county(county_name) -> str:
    """Name of the school in the specified county that has the highest number of SAT test takers."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name):\n        row = conn.execute(\n            \"SELECT sname FROM satscores \"\n            \"WHERE cname = ? AND sname IS NOT NULL \"\n            \"ORDER BY NumTstTakr DESC LIMIT 1\",\n            (county_name,)\n        ).fetchone()\n        return {\"school_name\": row[0] if row else None}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_with_lowest_latitude_by_state(state) -> str:
    """Find the school in a specified state that has the lowest latitude (southernmost). Returns its city, low grade, and school name."""
    try:
        _ns = {}
        exec(compile("def run(conn, state):\n        row = conn.execute(\n            \"\"\"SELECT s.City, f.`Low Grade`, f.`School Name`\n               FROM frpm f\n               INNER JOIN schools s ON f.CDSCode = s.CDSCode\n               WHERE s.State = ?\n               ORDER BY s.Latitude ASC\n               LIMIT 1\"\"\",\n            (state,)\n        ).fetchone()\n        if row is None:\n            return {\"city\": None, \"low_grade\": None, \"school_name\": None}\n        return {\"city\": row[0], \"low_grade\": row[1], \"school_name\": row[2]}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, state=state)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_with_lowest_reading_score() -> str:
    """Returns the mailing street address and school name of the school with the lowest non‑null average reading score (AvgScrRead)."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    row = conn.execute(\"\"\"SELECT T2.MailStreet, T2.School\n           FROM satscores AS T1\n           INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n           WHERE T1.AvgScrRead IS NOT NULL\n           ORDER BY T1.AvgScrRead ASC\n           LIMIT 1\"\"\").fetchone()\n    if row:\n        return {\"result\": [[row[0], row[1]]]}\n    else:\n        return {\"result\": []}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_school_writing_score_and_phone_by_date_criteria(open_year_min, closed_year_max) -> str:
    """Return each school's name, its average SAT writing score, and phone number for schools opened after a given year OR closed before a given year."""
    try:
        _ns = {}
        exec(compile("def run(conn, open_year_min, closed_year_max):\n        sql = (\n            \"SELECT s.School, ss.AvgScrWrite, s.Phone \"\n            \"FROM schools AS s \"\n            \"LEFT JOIN satscores AS ss ON s.CDSCode = ss.cds \"\n            \"WHERE CAST(strftime('%Y', s.OpenDate) AS INTEGER) > ? \"\n            \"   OR CAST(strftime('%Y', s.ClosedDate) AS INTEGER) < ?\"\n        )\n        cur = conn.execute(sql, (open_year_min, closed_year_max))\n        rows = [\n            {\"school\": r[0], \"avg_writing_score\": r[1], \"phone\": r[2]}\n            for r in cur.fetchall()\n        ]\n        return {\"rows\": rows}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, open_year_min=open_year_min, closed_year_max=closed_year_max)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_schools_and_mailing_zip_by_admin(admin_first_name, admin_last_name) -> str:
    """List schools and their mailing zip codes for which the primary administrator’s first and last names match the given values."""
    try:
        _ns = {}
        exec(compile("def run(conn, admin_first_name, admin_last_name):\n        cur = conn.execute(\n            \"SELECT School, MailZip FROM schools WHERE AdmFName1 = ? AND AdmLName1 = ?\",\n            (admin_first_name, admin_last_name)\n        )\n        rows = cur.fetchall()\n        result = [list(r) for r in rows]\n        return {\"schools\": result}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, admin_first_name=admin_first_name, admin_last_name=admin_last_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_schools_by_free_meal_ratio_and_sat_ge1500(min_free_meal_ratio, min_sat_ge1500) -> str:
    """List school names whose K‑12 free‑meal eligibility ratio (Free Meal Count (K‑12) / Enrollment (K‑12)) is greater than a given threshold and that have more than a given number of SAT test‑takers scoring ≥1500."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_free_meal_ratio, min_sat_ge1500):\n        cur = conn.execute(\n            \"\"\"SELECT T2.`School Name`\n               FROM satscores AS T1\n               JOIN frpm AS T2 ON T1.cds = T2.CDSCode\n               WHERE (CAST(T2.`Free Meal Count (K-12)` AS REAL) / T2.`Enrollment (K-12)`) > ?\n                 AND T1.NumGE1500 > ?\"\"\",\n            (min_free_meal_ratio, min_sat_ge1500)\n        )\n        rows = cur.fetchall()\n        names = [row[0] for row in rows] if rows else []\n        return {\"school_names\": names}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_free_meal_ratio=min_free_meal_ratio, min_sat_ge1500=min_sat_ge1500)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_schools_by_free_meal_ratio_and_test_score(ratio_threshold, min_test_score) -> str:
    """Return the names of schools whose K‑12 free‑meal eligibility ratio is greater than a given threshold and that have more than a given number of SAT test‑takers scoring ≥1500."""
    try:
        _ns = {}
        exec(compile("def run(conn, ratio_threshold, min_test_score):\n        rows = conn.execute(\n            \"\"\"SELECT T2.`School Name`\n               FROM satscores AS T1\n               JOIN frpm AS T2 ON T1.cds = T2.CDSCode\n               WHERE CAST(T2.`Free Meal Count (K-12)` AS REAL) / T2.`Enrollment (K-12)` > ?\n                 AND T1.NumGE1500 > ?\"\"\",\n            (ratio_threshold, min_test_score)\n        ).fetchall()\n        # Return just the school name strings\n        names = [r[0] for r in rows]\n        return {\"school_names\": names}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, ratio_threshold=ratio_threshold, min_test_score=min_test_score)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_schools_by_sat_takers_and_magnet(min_sat_takers, magnet) -> str:
    """List school names that have a specified magnet flag and more than a given number of SAT test takers."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_sat_takers, magnet):\n        rows = conn.execute(\n            \"\"\"SELECT T2.School\n               FROM satscores AS T1\n               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               WHERE T2.Magnet = ?\n                 AND T1.NumTstTakr > ?\"\"\",\n            (magnet, min_sat_takers)\n        ).fetchall()\n        return {\"schools\": [r[0] for r in rows]}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_sat_takers=min_sat_takers, magnet=magnet)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_schools_in_district_with_avg_math_above(district_name, min_avg_math) -> str:
    """List schools in a specified district whose average SAT Math score is greater than a given threshold, returning each school's name and Charter Funding Type."""
    try:
        _ns = {}
        exec(compile("def run(conn, district_name, min_avg_math):\n        pattern = district_name + '%'\n        cur = conn.execute(\n            \"SELECT T1.sname, T2.`Charter Funding Type` \"\n            \"FROM satscores AS T1 \"\n            \"INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode \"\n            \"WHERE T2.`District Name` LIKE ? \"\n            \"GROUP BY T1.sname, T2.`Charter Funding Type` \"\n            \"HAVING CAST(SUM(T1.AvgScrMath) AS REAL) / COUNT(T1.cds) > ?\",\n            (pattern, min_avg_math)\n        )\n        rows = cur.fetchall()\n        # Return rows in the same shape as the gold SQL result\n        return {\"rows\": rows}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, district_name=district_name, min_avg_math=min_avg_math)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_schools_with_enrollment_difference_above(threshold) -> str:
    """List schools (name and street) where the K‑12 enrollment minus the Ages 5‑17 enrollment is greater than a specified threshold."""
    try:
        _ns = {}
        exec(compile("def run(conn, threshold):\n        cursor = conn.execute(\n            \"SELECT s.School, s.Street \"\n            \"FROM schools s \"\n            \"JOIN frpm f ON s.CDSCode = f.CDSCode \"\n            \"WHERE (f.`Enrollment (K-12)` - f.`Enrollment (Ages 5-17)`) > ?\",\n            (threshold,)\n        )\n        rows = cursor.fetchall()\n        return {\"schools\": [{\"school\": r[0], \"street\": r[1]} for r in rows] if rows else []}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, threshold=threshold)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_test_takers_by_mailing_city(city_name) -> str:
    """List of SAT test taker counts (NumTstTakr) for each school whose mailing city address equals the specified city."""
    try:
        _ns = {}
        exec(compile("def run(conn, city_name):\n        rows = conn.execute(\n            \"SELECT T1.NumTstTakr \"\n            \"FROM satscores AS T1 \"\n            \"INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode \"\n            \"WHERE T2.MailCity = ?\",\n            (city_name,)\n        ).fetchall()\n        counts = [row[0] for row in rows] if rows else []\n        return {\"test_takers\": counts}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, city_name=city_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_admin_first_names_with_districts(limit) -> str:
    """Return the most frequent administrator first names (AdmFName1) from the schools table, limited to a given count, along with each administrator's district."""
    try:
        _ns = {}
        exec(compile("def run(conn, limit):\n        # Step 1: find the N most frequent first\u2011name values.\n        top_rows = conn.execute(\n            \"\"\"\n            SELECT AdmFName1\n            FROM schools\n            GROUP BY AdmFName1\n            ORDER BY COUNT(*) DESC\n            LIMIT ?\n            \"\"\",\n            (limit,)\n        ).fetchall()\n        top_names = [r[0] for r in top_rows]\n        if not top_names:\n            return {\"admin_names\": []}\n        # Step 2: retrieve distinct (first_name, district) pairs for those names.\n        placeholders = \",\".join([\"?\"] * len(top_names))\n        query = f\"\"\"\n            SELECT DISTINCT AdmFName1, District\n            FROM schools\n            WHERE AdmFName1 IN ({placeholders})\n        \"\"\"\n        rows = conn.execute(query, tuple(top_names)).fetchall()\n        result = [[r[0], r[1]] for r in rows]\n        return {\"admin_names\": result}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_n_free_meal_rates_by_frpm_and_soc(soc_code, limit) -> str:
    """Eligible free‑meal rate (FRPM Count (K‑12) / Enrollment (K‑12)) for the top N schools with the highest FRPM Count (K‑12), filtered by a given ownership code (SOC)."""
    try:
        _ns = {}
        exec(compile("def run(conn, soc_code, limit):\n        cur = conn.execute(\n            \"SELECT CAST(frpm.`FRPM Count (K-12)` AS REAL) / frpm.`Enrollment (K-12)` AS rate \"\n            \"FROM frpm \"\n            \"JOIN schools ON frpm.CDSCode = schools.CDSCode \"\n            \"WHERE schools.SOC = ? \"\n            \"ORDER BY frpm.`FRPM Count (K-12)` DESC \"\n            \"LIMIT ?\",\n            (soc_code, limit)\n        )\n        rows = cur.fetchall()\n        rates = [row[0] for row in rows] if rows else []\n        return {\"rates\": rates}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, soc_code=soc_code, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_n_phone_numbers_by_sat_excellence_rate(limit) -> str:
    """Phone numbers of the top N schools ordered by SAT excellence rate (NumGE1500 / NumTstTakr)."""
    try:
        _ns = {}
        exec(compile("def run(conn, limit):\n        rows = conn.execute(\n            \"\"\"SELECT T1.Phone\n               FROM schools AS T1\n               JOIN satscores AS T2 ON T1.CDSCode = T2.cds\n               ORDER BY CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr DESC\n               LIMIT ?\"\"\",\n            (limit,)\n        ).fetchall()\n        phones = [row[0] for row in rows]\n        return {\"phones\": phones}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_top_n_schools_by_enrollment_ages_5_17(limit) -> str:
    """NCES school IDs of the top N schools ordered by descending Enrollment (Ages 5‑17)."""
    try:
        _ns = {}
        exec(compile("def run(conn, limit):\n    rows = conn.execute(\n        \"SELECT T1.NCESSchool \"\n        \"FROM schools AS T1 \"\n        \"INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode \"\n        \"ORDER BY T2.`Enrollment (Ages 5-17)` DESC \"\n        \"LIMIT ?\",\n        (limit,)\n    ).fetchall()\n    return {\"schools\": [row[0] for row in rows]}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, limit=limit)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_websites_by_county_and_test_takers(county_name, min_test_takers, max_test_takers) -> str:
    """Retrieve website URLs for schools in a specified county whose SAT test‑taker count is between the given bounds."""
    try:
        _ns = {}
        exec(compile("def run(conn, county_name, min_test_takers, max_test_takers):\n        rows = conn.execute(\n            \"\"\"SELECT T2.Website\n               FROM satscores AS T1\n               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               WHERE T1.NumTstTakr BETWEEN ? AND ?\n                 AND T2.County = ?\"\"\",\n            (min_test_takers, max_test_takers, county_name)\n        ).fetchall()\n        websites = [r[0] for r in rows]\n        return {\"websites\": websites}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, county_name=county_name, min_test_takers=min_test_takers, max_test_takers=max_test_takers)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_writing_score_ranking(min_writing_score) -> str:
    """List of [CharterNum, AvgScrWrite, rank] for schools with AvgScrWrite > min_writing_score and a non‑null CharterNum, ordered by descending AvgScrWrite."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_writing_score):\n        sql = (\n            \"SELECT T1.CharterNum, T2.AvgScrWrite, \"\n            \"RANK() OVER (ORDER BY T2.AvgScrWrite DESC) \"\n            \"FROM schools AS T1 \"\n            \"INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds \"\n            \"WHERE T2.AvgScrWrite > ? AND T1.CharterNum IS NOT NULL \"\n            \"ORDER BY T2.AvgScrWrite DESC\"\n        )\n        rows = conn.execute(sql, (min_writing_score,)).fetchall()\n        # Convert each tuple to a list for JSON compatibility\n        return [list(row) for row in rows]\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_writing_score=min_writing_score)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def get_zip_codes_of_charter_schools_by_district(district_name) -> str:
    """ZIP codes of charter schools located in a specified district (based on the `District Name` column in the frpm table)."""
    try:
        _ns = {}
        exec(compile("def run(conn, district_name):\n    rows = conn.execute(\n        \"SELECT s.Zip FROM frpm AS f JOIN schools AS s ON f.CDSCode = s.CDSCode \"\n        \"WHERE f.`District Name` = ? AND f.`Charter School (Y/N)` = 1\",\n        (district_name,)\n    ).fetchall()\n    zip_codes = [r[0] for r in rows if r[0] is not None]\n    return {\"zip_codes\": zip_codes}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, district_name=district_name)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def list_address_of_school_with_lowest_excellence_rate() -> str:
    """Returns the address of the school with the lowest excellence rate as a nested list [[Street, City, State, Zip]] to match the gold‑SQL output format."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n        row = conn.execute(\n            \"\"\"SELECT T2.Street, T2.City, T2.State, T2.Zip\n               FROM satscores AS T1\n               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n               ORDER BY CAST(T1.NumGE1500 AS REAL) / T1.NumTstTakr ASC\n               LIMIT 1\"\"\"\n        ).fetchone()\n        if not row:\n            return []                     # no rows\n        return [list(row)]               # e.g. [[\"1111 Van Ness Avenue\",\"Fresno\",\"CA\",\"93721-2002\"]]\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def list_virtual_schools_top5_by_county_reading() -> str:
    """Names of exclusively virtual schools that rank in the top 5 within their county by average SAT reading score."""
    try:
        _ns = {}
        exec(compile("def run(conn):\n    sql = '''\n    SELECT School FROM (\n        SELECT T2.School,\n               T1.AvgScrRead,\n               RANK() OVER (PARTITION BY T2.County ORDER BY T1.AvgScrRead DESC) AS rnk\n        FROM satscores AS T1\n        INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode\n        WHERE T2.Virtual = 'F'\n    ) ranked\n    WHERE rnk <= 5\n    '''\n    rows = conn.execute(sql).fetchall()\n    names = [r[0] for r in rows]\n    return {\"school_names\": names}\n", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def question_0_wrapper() -> str:
    """Execute the gold SQL for question 0 and return its rows."""
    try:
        _ns = {}
        exec(compile("def run(conn, **kwargs):\n        cur = conn.cursor()\n        cur.execute(\"\"\"SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)` FROM frpm WHERE `County Name` = 'Alameda' ORDER BY (CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`) DESC LIMIT 1\"\"\")\n        rows = cur.fetchall()\n        # Convert tuples to JSON\u2011serializable lists\n        rows = [list(r) for r in rows]\n        return {\"rows\": rows}", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def rank_schools_by_writing_score(min_writing_score) -> str:
    """Ranks schools (by Charter number) according to their average Writing SAT score. Only schools with a non‑null Charter number and a Writing score greater than a provided threshold are included. Returns the Charter number, the average Writing score, and the rank (1 = highest score)."""
    try:
        _ns = {}
        exec(compile("def run(conn, min_writing_score):\n        sql = (\n            \"SELECT T1.CharterNum AS charter_number, \"\n            \"T2.AvgScrWrite AS avg_writing_score, \"\n            \"RANK() OVER (ORDER BY T2.AvgScrWrite DESC) AS writing_score_rank \"\n            \"FROM schools AS T1 \"\n            \"JOIN satscores AS T2 ON T1.CDSCode = T2.cds \"\n            \"WHERE T2.AvgScrWrite > ? AND T1.CharterNum IS NOT NULL \"\n            \"ORDER BY writing_score_rank ASC\"\n        )\n        cur = conn.execute(sql, (min_writing_score,))\n        rows = cur.fetchall()\n        # Build a list of dicts with clear keys\n        result = [\n            {\n                \"charter_number\": row[0],\n                \"avg_writing_score\": row[1],\n                \"writing_score_rank\": row[2]\n            }\n            for row in rows\n        ]\n        return {\"rankings\": result}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, min_writing_score=min_writing_score)
        return _ok(out)
    except Exception as _e:
        return _err(_e)

@mcp.tool()
def schools_with_enrollment_difference_above_funding(funding_type, threshold) -> str:
    """List schools (name and DOC) whose K‑12 enrollment minus Ages 5‑17 enrollment exceeds a threshold, filtered by FundingType, ordered by school name."""
    try:
        _ns = {}
        exec(compile("def run(conn, funding_type, threshold):\n        cur = conn.execute(\n            \"\"\"\n            SELECT T2.School, T2.DOC\n            FROM frpm AS T1\n            JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode\n            WHERE T2.FundingType = ?\n              AND (T1.`Enrollment (K-12)` - T1.`Enrollment (Ages 5-17)`) > ?\n            ORDER BY T2.School ASC\n            \"\"\",\n            (funding_type, threshold)\n        )\n        rows = cur.fetchall()\n        # Return as a list of tuples for direct comparison with gold result\n        return {\"schools\": rows}\n    ", "<tool>", "exec"), _ns)
        with _conn() as _c:
            out = _ns["run"](_c, funding_type=funding_type, threshold=threshold)
        return _ok(out)
    except Exception as _e:
        return _err(_e)


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8765"))
    mcp.settings.transport_security.enable_dns_rebinding_protection = False
    mcp.run(transport="streamable-http")
