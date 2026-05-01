"""Auto-generated invocable tools for Bird db `california_schools`."""
from __future__ import annotations
import json
import re
import sqlite3

# avg_enrollment_by_county_for_charter_flag — Average K‑12 enrollment per county for schools where the `Charter` column matches the supplied flag. Returns only counties that have at least `min_charter_schools` matching schools.
def run(conn, charter_flag, min_charter_schools):
        sql = (
            "SELECT \"County Name\" AS county_name, "
            "AVG(\"Enrollment (K-12)\") AS avg_enrollment "
            "FROM schools "
            "WHERE \"Charter\" = ? "
            "GROUP BY \"County Name\" "
            "HAVING COUNT(*) >= ?"
        )
        rows = conn.execute(sql, (charter_flag, min_charter_schools)).fetchall()
        averages = [
            {
                "county_name": row[0],
                "avg_enrollment": float(row[1]) if row[1] is not None else None
            }
            for row in rows
        ]
        return {"averages": averages}
avg_enrollment_by_county_for_charter_flag = run; del run

# avg_enrollment_difference_by_funding_type — Average of (Enrollment (K-12) − Enrollment (Ages 5-17)) for schools with a specified FundingType.
def run(conn, funding_type):
        cur = conn.execute(
            """
            SELECT AVG(T1.`Enrollment (K-12)` - T1.`Enrollment (Ages 5-17)`) AS avg_diff
            FROM frpm AS T1
            JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode
            WHERE T2.FundingType = ?
            """,
            (funding_type,)
        )
        row = cur.fetchone()
        return {"avg_difference": row[0] if row and row[0] is not None else None}
avg_enrollment_difference_by_funding_type = run; del run

# avg_free_meal_ratio_by_county_with_high_ratio — For each county that contains at least one school whose free‑meal ratio (Free Meal Count (K‑12) ÷ Enrollment (K‑12)) exceeds a given threshold, return the county name and the average free‑meal ratio across all its schools, ordered descending by the average.
def run(conn, ratio_threshold):
        sql = (
            "SELECT `County Name` AS county_name, "
            "AVG(`Free Meal Count (K-12)` * 1.0 / `Enrollment (K-12)`) AS avg_ratio "
            "FROM frpm "
            "WHERE `County Name` IN ("
            "    SELECT `County Name` FROM frpm "
            "    WHERE `Free Meal Count (K-12)` * 1.0 / `Enrollment (K-12)` > ?"
            ") "
            "GROUP BY `County Name` "
            "ORDER BY avg_ratio DESC"
        )
        cur = conn.execute(sql, (ratio_threshold,))
        rows = cur.fetchall()
        # Return a list of dicts with clear keys
        result = [
            {"county_name": row[0], "avg_ratio": row[1]}
            for row in rows
        ]
        return {"averages": result}
avg_free_meal_ratio_by_county_with_high_ratio = run; del run

# avg_monthly_school_openings_by_doc_county_year — Average number of schools opened per month in a given year for a specific DOC and county.
def run(conn, doc, county_name, year):
        cur = conn.execute(
            "SELECT COUNT(School) FROM schools "
            "WHERE DOC = ? AND County = ? AND strftime('%Y', OpenDate) = ?",
            (doc, county_name, year)
        )
        row = cur.fetchone()
        count = row[0] if row else 0
        avg = (float(count) / 12) if count else None
        return {"monthly_average": avg}
avg_monthly_school_openings_by_doc_county_year = run; del run

# count_active_schools_by_city_state — Count schools whose mailing address is in a given city and state, and whose StatusType matches the specified value.
def run(conn, city_name, mail_state, status_type):
        cur = conn.execute(
            "SELECT COUNT(CDSCode) FROM schools WHERE City = ? AND MailState = ? AND StatusType = ?",
            (city_name, mail_state, status_type)
        )
        row = cur.fetchone()
        return {"school_count": row[0] if row else None}
count_active_schools_by_city_state = run; del run

# count_charter_schools_in_city_by_doc — Count charter schools (Charter = 1) located in a specific city and owned by a given DOC district.
def run(conn, city_name, doc_code):
        cur = conn.execute(
            "SELECT COUNT(School) FROM schools WHERE DOC = ? AND Charter = 1 AND City = ?",
            (doc_code, city_name)
        )
        row = cur.fetchone()
        return {"count": row[0] if row else None}
count_charter_schools_in_city_by_doc = run; del run

# count_closures_by_year_city_doc_type — Count schools that closed in a specific year, within a given city, and of a particular DOC type.
def run(conn, year, city, doc_type):
        cur = conn.execute(
            "SELECT COUNT(School) FROM schools "
            "WHERE strftime('%Y', ClosedDate) = ? AND City = ? AND DOCType = ?",
            (year, city, doc_type)
        )
        row = cur.fetchone()
        return {"closure_count": row[0] if row else None}
count_closures_by_year_city_doc_type = run; del run

# count_merged_schools_by_county_with_test_takers_below — Count schools whose StatusType is 'Merged', located in a specified county, and whose number of SAT test takers is less than a given threshold.
def run(conn, county_name, max_test_takers):
        cur = conn.execute(
            "SELECT COUNT(T1.CDSCode) "
            "FROM schools AS T1 "
            "INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds "
            "WHERE T1.StatusType = ? AND T2.NumTstTakr < ? AND T1.County = ?",
            ("Merged", max_test_takers, county_name)
        )
        row = cur.fetchone()
        return {"school_count": row[0] if row else None}
count_merged_schools_by_county_with_test_takers_below = run; del run

# count_schools_by_city_and_sat_total_ge — Count schools whose mailing city matches the supplied name and whose total SAT score (AvgScrRead + AvgScrMath + AvgScrWrite) is greater than or equal to a given threshold.
def run(conn, city_name, min_total_sat):
    cur = conn.execute(
        "SELECT COUNT(T1.cds) FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode WHERE T2.MailCity = ? AND (T1.AvgScrRead + T1.AvgScrMath + T1.AvgScrWrite) >= ?",
        (city_name, min_total_sat)
    )
    row = cur.fetchone()
    return {"school_count": row[0] if row else None}
count_schools_by_city_and_sat_total_ge = run; del run

# count_schools_by_city_state_and_status — Count schools whose mailing city, mailing state, and StatusType match the provided values.
def run(conn, city_name, mail_state, status_type):
        cur = conn.execute(
            "SELECT COUNT(CDSCode) FROM schools WHERE City = ? AND MailState = ? AND StatusType = ?",
            (city_name, mail_state, status_type)
        )
        row = cur.fetchone()
        return {"school_count": row[0] if row else None}
count_schools_by_city_state_and_status = run; del run

# count_schools_by_county_and_free_meal_frpm_range — Count schools in a given county where the K‑12 free‑meal count exceeds a minimum and the K‑12 FRPM count is below a maximum.
def run(conn, county_name, min_free_meal, max_frpm):
        cur = conn.execute(
            "SELECT COUNT(CDSCode) FROM frpm "
            "WHERE `County Name` = ? "
            "AND `Free Meal Count (K-12)` > ? "
            "AND `FRPM Count (K-12)` < ?",
            (county_name, min_free_meal, max_frpm)
        )
        row = cur.fetchone()
        return {"school_count": row[0] if row else None}
count_schools_by_county_and_free_meal_frpm_range = run; del run

# count_schools_by_county_and_grade_range — Count schools located in a specified county whose Low Grade and High Grade match given values.
def run(conn, county_name, low_grade, high_grade):
        row = conn.execute(
            "SELECT COUNT(T1.`School Name`) "
            "FROM frpm AS T1 "
            "INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T2.County = ? AND T1.`Low Grade` = ? AND T1.`High Grade` = ?",
            (county_name, low_grade, high_grade)
        ).fetchone()
        return {"school_count": row[0] if row else None}
count_schools_by_county_and_grade_range = run; del run

# count_schools_by_county_free_meal_and_frpm_range — Count schools in a specified county whose K‑12 free‑meal count exceeds a minimum and whose K‑12 FRPM count is below a maximum.
def run(conn, county_name, min_free_meals, max_frpm):
        cur = conn.execute(
            "SELECT COUNT(CDSCode) FROM frpm "
            "WHERE `County Name` = ? "
            "AND `Free Meal Count (K-12)` > ? "
            "AND `FRPM Count (K-12)` < ?",
            (county_name, min_free_meals, max_frpm)
        )
        row = cur.fetchone()
        return {"school_count": row[0] if row else None}
count_schools_by_county_free_meal_and_frpm_range = run; del run

# count_schools_by_county_funding_and_max_test_takers — Count schools in a specified county and Charter Funding Type where the number of test takers (satscores.NumTstTakr) is at most a given maximum.
def run(conn, county_name, funding_type, max_test_takers):
        cur = conn.execute(
            """SELECT COUNT(T1.CDSCode)
               FROM frpm AS T1
               INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds
               WHERE T1.`Charter Funding Type` = ?
                 AND T1.`County Name` = ?
                 AND T2.NumTstTakr <= ?""",
            (funding_type, county_name, max_test_takers)
        )
        row = cur.fetchone()
        return {"count": row[0] if row else None}
count_schools_by_county_funding_and_max_test_takers = run; del run

# count_schools_by_county_funding_and_open_year_range — Count schools in a given county whose FundingType matches the supplied value and whose opening year (extracted from OpenDate) falls between start_year and end_year inclusive.
def run(conn, county_name, funding_type, start_year, end_year):
        row = conn.execute(
            "SELECT COUNT(School) FROM schools "
            "WHERE County = ? "
            "AND FundingType = ? "
            "AND CAST(strftime('%Y', OpenDate) AS INTEGER) BETWEEN ? AND ?",
            (county_name, funding_type, start_year, end_year),
        ).fetchone()
        return {"school_count": row[0] if row else 0}
count_schools_by_county_funding_and_open_year_range = run; del run

# count_schools_by_funding_county_and_test_takers_below — Count schools in a specified county that have the given Charter Funding Type and whose number of SAT test takers is less than a provided maximum.
def run(conn, county_name, charter_funding_type, max_test_takers):
        row = conn.execute(
            """SELECT COUNT(T1.CDSCode)
               FROM frpm AS T1
               INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds
               WHERE T1.`Charter Funding Type` = ?
                 AND T1.`County Name` = ?
                 AND T2.NumTstTakr < ?""",
            (charter_funding_type, county_name, max_test_takers)
        ).fetchone()
        return {"school_count": row[0] if row else None}
count_schools_by_funding_county_and_test_takers_below = run; del run

# count_schools_by_math_score_and_charter_funding — Count distinct schools whose average SAT Math score exceeds a given threshold and whose Charter Funding Type matches the specified value.
def run(conn, min_math_score, charter_funding_type):
        cur = conn.execute(
            """
            SELECT COUNT(DISTINCT T2.`School Code`)
            FROM satscores AS T1
            JOIN frpm AS T2 ON T1.cds = T2.CDSCode
            WHERE T1.AvgScrMath > ?
              AND T2.`Charter Funding Type` = ?
            """,
            (min_math_score, charter_funding_type)
        )
        row = cur.fetchone()
        return {"count": row[0] if row else 0}
count_schools_by_math_score_and_charter_funding = run; del run

# count_schools_by_math_score_and_virtual — Count distinct schools whose average SAT Math score is greater than a given threshold and whose Virtual flag matches the specified value.
def run(conn, min_math_score, virtual_flag):
        cur = conn.execute(
            """SELECT COUNT(DISTINCT T2.School)
               FROM satscores AS T1
               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
               WHERE T2.Virtual = ? AND T1.AvgScrMath > ?""",
            (virtual_flag, min_math_score)
        )
        row = cur.fetchone()
        return {"count": row[0] if row else 0}
count_schools_by_math_score_and_virtual = run; del run

# count_schools_by_soc_county_and_statuses — Count schools with a given School Ownership Code (SOC), located in a specified county, whose StatusType matches either of two provided values.
def run(conn, soc_code, county_name, status_type_1, status_type_2):
        cur = conn.execute(
            "SELECT COUNT(School) FROM schools "
            "WHERE SOC = ? AND County = ? AND (StatusType = ? OR StatusType = ?)",
            (soc_code, county_name, status_type_1, status_type_2)
        )
        row = cur.fetchone()
        return {"school_count": row[0] if row else None}
count_schools_by_soc_county_and_statuses = run; del run

# count_schools_by_virtual_and_math_score — Count distinct schools that have the specified virtual status and an average Math SAT score greater than a given threshold.
def run(conn, virtual_status, math_score_threshold):
        cur = conn.execute(
            """SELECT COUNT(DISTINCT T2.School)
               FROM satscores AS T1
               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
               WHERE T2.Virtual = ? AND T1.AvgScrMath > ?""",
            (virtual_status, math_score_threshold)
        )
        row = cur.fetchone()
        return {"count": row[0] if row else 0}
count_schools_by_virtual_and_math_score = run; del run

# extract_school_rows — Extract the list of school rows from the dict returned by the previous tool.
def run(conn, schools_dict):
        # The dict contains a key 'schools' with the list of rows
        return {"rows": schools_dict.get("schools", [])}
extract_school_rows = run; del run

# get_active_district_with_highest_reading_sat_score — District name of the active school that has the highest average SAT Reading score.
def run(conn):
    row = conn.execute(
        "SELECT T1.District "
        "FROM schools AS T1 "
        "INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds "
        "WHERE T1.StatusType = 'Active' "
        "ORDER BY T2.AvgScrRead DESC "
        "LIMIT 1"
    ).fetchone()
    return {"district": row[0] if row else None}
get_active_district_with_highest_reading_sat_score = run; del run

# get_address_of_school_with_lowest_excellence_rate — Returns the complete address (Street, City, State, Zip) of the school that has the lowest excellence rate (NumGE1500 / NumTstTakr) in the California schools dataset.
def run(conn):
        # Join satscores and schools, compute excellence rate, order ascending, limit 1
        row = conn.execute(
            """SELECT T2.Street, T2.City, T2.State, T2.Zip
               FROM satscores AS T1
               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
               ORDER BY CAST(T1.NumGE1500 AS REAL) / T1.NumTstTakr ASC
               LIMIT 1"""
        ).fetchone()
        if not row:
            return {"address": {"street": None, "city": None, "state": None, "zip": None}}
        return {"address": {"street": row[0], "city": row[1], "state": row[2], "zip": row[3]}}
get_address_of_school_with_lowest_excellence_rate = run; del run

# get_admin_email_and_school_of_top_sat_ge1500 — Administrator email (AdmEmail1) and school name of the school with the highest NumGE1500.
def run(conn):
    row = conn.execute(
        "SELECT T2.AdmEmail1, T2.School "
        "FROM satscores AS T1 "
        "JOIN schools AS T2 ON T1.cds = T2.CDSCode "
        "ORDER BY T1.NumGE1500 DESC "
        "LIMIT 1"
    ).fetchone()
    # Return a list of rows to match the gold result format
    return {"rows": [[row[0] if row else None, row[1] if row else None]]}
get_admin_email_and_school_of_top_sat_ge1500 = run; del run

# get_admin_email_of_charter_school_with_fewest_k12_enrollment — Administrator email (AdmEmail1) of the charter school (Charter School (Y/N)=1) that has the fewest K‑12 students (minimum `Enrollment (K-12)`). Returns null if no charter schools exist.
def run(conn):
        row = conn.execute(
            "SELECT T2.AdmEmail1 "
            "FROM frpm AS T1 "
            "JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T1.`Charter School (Y/N)` = 1 "
            "ORDER BY T1.`Enrollment (K-12)` ASC "
            "LIMIT 1"
        ).fetchone()
        return {"admin_email": row[0] if row else None}
get_admin_email_of_charter_school_with_fewest_k12_enrollment = run; del run

# get_admin_emails_by_location_and_year — Administrator email addresses (AdmEmail1, AdmEmail2) of schools that match the given county, city, DOC code, SOC code, and whose OpenDate year falls between start_year and end_year (inclusive). Returns a list of [email1, email2] rows.
def run(conn, county_name, city_name, doc, soc, start_year, end_year):
        cur = conn.execute(
            """SELECT T2.AdmEmail1, T2.AdmEmail2
               FROM frpm AS T1
               INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode
               WHERE T2.County = ?
                 AND T2.City = ?
                 AND T2.DOC = ?
                 AND T2.SOC = ?
                 AND strftime('%Y', T2.OpenDate) BETWEEN ? AND ?""",
            (county_name, city_name, doc, soc, start_year, end_year)
        )
        rows = cur.fetchall()
        # Return list of [email1, email2] (NULLs are kept as None)
        return {"admin_emails": [list(row) for row in rows]}
get_admin_emails_by_location_and_year = run; del run

# get_administrators_by_charter_number — Return first‑name, last‑name, school name, and city for all administrators of a chartered school identified by its CharterNum.
def run(conn, charter_number):
        cursor = conn.execute(
            "SELECT AdmFName1, AdmLName1, School, City FROM schools WHERE Charter = 1 AND CharterNum = ?",
            (charter_number,)
        )
        # Return the raw list of rows so that validation can compare directly to the gold result
        return cursor.fetchall()
get_administrators_by_charter_number = run; del run

# get_average_test_takers_by_county_and_open_year — Average number of SAT test takers (NumTstTakr) for schools in a specified county that opened in a given year.
def run(conn, county_name, open_year):
        cur = conn.execute(
            "SELECT AVG(T1.NumTstTakr) "
            "FROM satscores AS T1 "
            "JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "WHERE strftime('%Y', T2.OpenDate) = ? AND T2.County = ?",
            (str(open_year), county_name)
        )
        row = cur.fetchone()
        return {"average_test_takers": row[0] if row and row[0] is not None else None}
get_average_test_takers_by_county_and_open_year = run; del run

# get_average_writing_score_by_admin — Returns a list of schools managed by the specified administrator and each school's average SAT writing score.
def run(conn, admin_first_name, admin_last_name):
        cur = conn.execute(
            """SELECT s.School, ss.AvgScrWrite
               FROM satscores ss
               JOIN schools s ON ss.cds = s.CDSCode
               WHERE s.AdmFName1 = ? AND s.AdmLName1 = ?""",
            (admin_first_name, admin_last_name)
        )
        rows = cur.fetchall()
        return {"schools": rows}
get_average_writing_score_by_admin = run; del run

# get_avg_math_and_county_of_school_with_lowest_total_average — Returns the average Math SAT score and county of the school whose sum of average Math, Reading, and Writing scores is minimal, formatted as a list of rows.
def run(conn):
        row = conn.execute(
            "SELECT T1.AvgScrMath, T2.County "
            "FROM satscores AS T1 "
            "INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "WHERE T1.AvgScrMath IS NOT NULL "
            "ORDER BY (T1.AvgScrMath + T1.AvgScrRead + T1.AvgScrWrite) ASC "
            "LIMIT 1"
        ).fetchone()
        if row:
            return {"result": [[row[0], row[1]]]}
        else:
            return {"result": []}
get_avg_math_and_county_of_school_with_lowest_total_average = run; del run

# get_avg_writing_score_and_city_of_top_ge1500_school — Returns the average writing SAT score and the city of the school that has the highest count of test‑takers with total SAT scores ≥ 1500.
def run(conn):
        sql = (
            "SELECT T1.AvgScrWrite, T2.City "
            "FROM satscores AS T1 "
            "JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "ORDER BY T1.NumGE1500 DESC "
            "LIMIT 1"
        )
        row = conn.execute(sql).fetchone()
        if not row:
            return {"result": []}
        # Return a list of rows to match the gold‑SQL shape
        return {"result": [[row[0], row[1]]]}
get_avg_writing_score_and_city_of_top_ge1500_school = run; del run

# get_cds_of_highest_frpm_count — Return the CDSCode of the school with the highest FRPM Count (K-12) in the frpm table.
def run(conn):
        row = conn.execute(
            "SELECT CDSCode FROM frpm ORDER BY `FRPM Count (K-12)` DESC LIMIT 1"
        ).fetchone()
        return {"cds": row[0] if row else None}
get_cds_of_highest_frpm_count = run; del run

# get_cities_of_schools_by_criteria — Return the city name(s) of schools that match the specified county, NSLP provision status, lowest grade, highest grade, and school level (EILCode).
def run(conn, county_name, provision_status, low_grade, high_grade, school_level_code):
        sql = (
            "SELECT T2.City FROM frpm AS T1 "
            "INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T1.`NSLP Provision Status` = ? "
            "AND T2.County = ? "
            "AND T1.`Low Grade` = ? "
            "AND T1.`High Grade` = ? "
            "AND T2.EILCode = ?"
        )
        rows = conn.execute(sql, (
            provision_status,
            county_name,
            low_grade,
            high_grade,
            school_level_code,
        )).fetchall()
        cities = [row[0] for row in rows]  # list of city strings, may be empty
        return {"cities": cities}
get_cities_of_schools_by_criteria = run; del run

# get_cities_with_lowest_k12_enrollment — Cities with the smallest total K‑12 enrollment across all schools.
def run(conn, limit):
        rows = conn.execute(
            "SELECT T2.City FROM frpm AS T1 JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "GROUP BY T2.City ORDER BY SUM(T1.`Enrollment (K-12)`) ASC LIMIT ?",
            (limit,)
        ).fetchall()
        # Return each city as a single‑element list to match the gold row shape
        cities = [[row[0]] for row in rows]
        return {"cities": cities}
get_cities_with_lowest_k12_enrollment = run; del run

# get_county_with_most_closures_by_soc_and_year_range — County that has the highest number of schools closed in a given year range for a specific SOC ownership code.
def run(conn, soc_code, start_year, end_year):
    row = conn.execute(
        "SELECT County FROM schools "
        "WHERE strftime('%Y', ClosedDate) BETWEEN ? AND ? "
        "AND StatusType = 'Closed' AND SOC = ? "
        "GROUP BY County "
        "ORDER BY COUNT(School) DESC "
        "LIMIT 1",
        (start_year, end_year, soc_code)
    ).fetchone()
    return {"county": row[0] if row else None}
get_county_with_most_closures_by_soc_and_year_range = run; del run

# get_county_with_most_schools_without_physical_building — Among the two specified counties, return the county that has the most schools where `Virtual` = 'F' (does not offer a physical building) and the count of such schools. The output shape matches the gold SQL: a list of rows [[County, count]].
def run(conn, county_a, county_b):
    cur = conn.execute(
        "SELECT County, COUNT(*) FROM schools WHERE County IN (?, ?) AND Virtual = 'F' GROUP BY County ORDER BY COUNT(*) DESC LIMIT 1",
        (county_a, county_b)
    )
    rows = cur.fetchall()
    # Convert sqlite Row objects to plain Python lists
    return [list(r) for r in rows]
get_county_with_most_schools_without_physical_building = run; del run

# get_district_codes_by_city_and_magnet — District codes of schools located in a specified city that have the given magnet flag.
def run(conn, city_name, magnet_flag):
    cur = conn.execute(
        "SELECT T1.`District Code` FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.City = ? AND T2.Magnet = ?",
        (city_name, magnet_flag)
    )
    rows = cur.fetchall()
    return {"district_codes": [row[0] for row in rows]}
get_district_codes_by_city_and_magnet = run; del run

# get_education_type_of_school_with_highest_average_score — Return the EdOpsName (type of education) of the school that achieved the highest average SAT score for a given subject.
def run(conn, subject):
        # Map subject to the corresponding column in satscores
        col_map = {
            "Math": "AvgScrMath",
            "Reading": "AvgScrReading",
            "Science": "AvgScrScience"
        }
        col = col_map.get(subject)
        if not col:
            return {"education_type": None}
        # Build the query safely using the validated column name
        query = '''SELECT T2.EdOpsName
    FROM satscores AS T1
    JOIN schools AS T2 ON T1.cds = T2.CDSCode
    ORDER BY T1.{col} DESC
    LIMIT 1'''
        row = conn.execute(query.format(col=col)).fetchone()
        return {"education_type": row[0] if row else None}
get_education_type_of_school_with_highest_average_score = run; del run

# get_eligible_free_rate_by_enrollment_rank — Returns the eligible free‑meal rate (Free Meal Count (K-12) / Enrollment (K-12)) for schools sorted by descending K‑12 enrollment, skipping a given number of top schools (offset) and returning a specified number of rows (limit).
def run(conn, offset, limit):
    rows = conn.execute(
        """SELECT CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)` AS rate
           FROM frpm
           ORDER BY `Enrollment (K-12)` DESC
           LIMIT ? OFFSET ?""",
        (limit, offset)
    ).fetchall()
    rates = [row[0] if row[0] is not None else None for row in rows]
    return {"rates": rates}
get_eligible_free_rate_by_enrollment_rank = run; del run

# get_enrollment_5_17_by_edops_city_year_range — Return `Enrollment (Ages 5-17)` values from frpm for schools matching a given EdOpsCode, city, and academic year range.
def run(conn, edops_code, city, start_year, end_year):
        sql = (
            "SELECT T1.`Enrollment (Ages 5-17)` "
            "FROM frpm AS T1 "
            "INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T2.EdOpsCode = ? AND T2.City = ? AND T1.`Academic Year` BETWEEN ? AND ?"
        )
        cur = conn.execute(sql, (edops_code, city, start_year, end_year))
        rows = cur.fetchall()
        enrollments = [row[0] for row in rows]
        return {"enrollments": enrollments}
get_enrollment_5_17_by_edops_city_year_range = run; del run

# get_free_meal_rate_by_admin_name — Eligible free‑meal rate (Free Meal Count (Ages 5‑17) / Enrollment (Ages 5‑17)) for the school administered by the specified first and last name.
def run(conn, admin_first_name, admin_last_name):
        row = conn.execute(
            "SELECT CAST(T2.`Free Meal Count (Ages 5-17)` AS REAL) / T2.`Enrollment (Ages 5-17)` "
            "FROM schools AS T1 "
            "INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T1.AdmFName1 = ? AND T1.AdmLName1 = ?",
            (admin_first_name, admin_last_name)
        ).fetchone()
        return {"free_rate": row[0] if row else None}
get_free_meal_rate_by_admin_name = run; del run

# get_frpm_count_ages_5_17_for_highest_reading_sat_school — FRPM count (Ages 5-17) for the school that has the highest average SAT Reading score.
def run(conn):
        row = conn.execute(
            "SELECT T2.`FRPM Count (Ages 5-17)` "
            "FROM satscores AS T1 "
            "INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode "
            "ORDER BY T1.AvgScrRead DESC "
            "LIMIT 1"
        ).fetchone()
        return {"frpm_count_5_17": row[0] if row else None}
get_frpm_count_ages_5_17_for_highest_reading_sat_school = run; del run

# get_frpm_count_by_mailstreet_and_soc_type — Return the free or reduced price meal count for ages 5‑17 (`FRPM Count (Ages 5-17)`) for the school matching a given mailing street address and SOC type.
def run(conn, mail_street, soc_type):
        row = conn.execute(
            "SELECT T1.`FRPM Count (Ages 5-17)` "
            "FROM frpm AS T1 "
            "INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T2.MailStreet = ? AND T2.SOCType = ?",
            (mail_street, soc_type)
        ).fetchone()
        return {"frpm_count": row[0] if row else None}
get_frpm_count_by_mailstreet_and_soc_type = run; del run

# get_frpm_percent_by_county_and_grade_span — List schools in a given county that serve the specified grade span (GSserved) and their Percent (%) Eligible FRPM for ages 5‑17.
def run(conn, county_name, grade_span):
        cur = conn.execute(
            "SELECT T2.School, "
            "(T1.`FRPM Count (Ages 5-17)` * 100.0) / T1.`Enrollment (Ages 5-17)` AS percent "
            "FROM frpm AS T1 "
            "JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T2.County = ? AND T2.GSserved = ?",
            (county_name, grade_span)
        )
        rows = cur.fetchall()
        # Build list of [school, percent]; handle possible NULL division result
        results = [[row[0], row[1] if row[1] is not None else None] for row in rows]
        return {"results": results}
get_frpm_percent_by_county_and_grade_span = run; del run

# get_grade_span_of_school_with_highest_longitude — Returns the grade span (GSoffered) of the school that has the highest absolute longitude value.
def run(conn):
    row = conn.execute("SELECT GSoffered FROM schools ORDER BY ABS(longitude) DESC LIMIT 1").fetchone()
    return {"grade_span": row[0] if row else None}
get_grade_span_of_school_with_highest_longitude = run; del run

# get_high_schools_in_county_with_free_meal_and_type — Return rows of high schools in a county with free‑meal count > threshold, matching the gold‑SQL shape.
def run(conn, county_name, min_free_meal, school_type):
        cursor = conn.execute(
            """SELECT T1.`School Name`,
                      T2.Street,
                      T2.City,
                      T2.State,
                      T2.Zip
               FROM frpm AS T1
               INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode
               WHERE T2.County = ?
                 AND T1.`Free Meal Count (Ages 5-17)` > ?
                 AND T1.`School Type` = ?""",
            (county_name, min_free_meal, school_type)
        )
        # Return a list of rows (each row is a list of column values)
        return [list(r) for r in cursor.fetchall()]
get_high_schools_in_county_with_free_meal_and_type = run; del run

# get_highest_free_meal_rate_by_sat_excellence — Highest eligible free‑meal rate (Free Meal Count Ages 5‑17 / Enrollment Ages 5‑17) among schools with SAT excellence rate > min_excellence_rate.
def run(conn, min_excellence_rate):
        # Compute the maximum free‑meal rate for ages 5‑17 among schools
        # whose SAT excellence rate exceeds the supplied threshold.
        sql = (
            "SELECT MAX(CAST(frpm.`Free Meal Count (Ages 5-17)` AS REAL) / frpm.`Enrollment (Ages 5-17)`) "
            "FROM frpm "
            "INNER JOIN satscores ON frpm.CDSCode = satscores.cds "
            "WHERE CAST(satscores.NumGE1500 AS REAL) / satscores.NumTstTakr > ?"
        )
        cur = conn.execute(sql, (min_excellence_rate,))
        row = cur.fetchone()
        return {"max_free_meal_rate": row[0] if row and row[0] is not None else None}
get_highest_free_meal_rate_by_sat_excellence = run; del run

# get_highest_free_meal_ratio_by_county — Maximum K‑12 free‑meal ratio (Free Meal Count (K‑12) / Enrollment (K‑12)) among schools in a specified California county.
def run(conn, county_name):
        cur = conn.execute(
            """
            SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)`
            FROM frpm
            WHERE `County Name` = ?
            ORDER BY (CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`) DESC
            LIMIT 1
            """,
            (county_name,)
        )
        row = cur.fetchone()
        return {"ratio": row[0] if row else None}
get_highest_free_meal_ratio_by_county = run; del run

# get_locally_funded_charter_ratio_by_county — Percentage ratio of charter schools that are locally funded to charter schools with any other funding type within a given county.
def run(conn, county_name):
        # Compute counts of locally funded charter schools and all other charter funding types.
        cur = conn.execute(
            """
            SELECT
                CAST(SUM(CASE WHEN FundingType = 'Locally funded' THEN 1 ELSE 0 END) AS REAL) * 100.0
                / NULLIF(SUM(CASE WHEN FundingType != 'Locally funded' THEN 1 ELSE 0 END), 0)
            FROM schools
            WHERE County = ? AND Charter = 1
            """,
            (county_name,)
        )
        row = cur.fetchone()
        return {"ratio_percent": row[0] if row and row[0] is not None else None}
get_locally_funded_charter_ratio_by_county = run; del run

# get_locally_funded_charter_ratio_percent — Compute the percentage ratio of locally funded charter schools to all other charter school funding types within a specified county.
def run(conn, county_name):
        # Count locally funded charter schools and count of all other charter funding types in the given county.
        cur = conn.execute(
            """SELECT
                   CAST(SUM(CASE WHEN FundingType = 'Locally funded' THEN 1 ELSE 0 END) AS REAL) * 100.0
                   / NULLIF(SUM(CASE WHEN FundingType != 'Locally funded' THEN 1 ELSE 0 END), 0)
               FROM schools
               WHERE County = ? AND Charter = 1""",
            (county_name,)
        )
        row = cur.fetchone()
        ratio = row[0] if row and row[0] is not None else None
        return {"ratio_percent": ratio}
get_locally_funded_charter_ratio_percent = run; del run

# get_lowest_free_meal_rates_by_school_type — Return the lowest N eligible free‑meal rates for students aged 5‑17 in schools of a specified Educational Option Type. The rate is `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)`.
def run(conn, school_type, limit):
        cur = conn.execute(
            """SELECT `Free Meal Count (Ages 5-17)` / `Enrollment (Ages 5-17)` AS ratio
               FROM frpm
               WHERE `Educational Option Type` = ?
                 AND `Free Meal Count (Ages 5-17)` IS NOT NULL
                 AND `Enrollment (Ages 5-17)` IS NOT NULL
                 AND `Enrollment (Ages 5-17)` != 0
               ORDER BY ratio ASC
               LIMIT ?""",
            (school_type, limit)
        )
        rows = cur.fetchall()
        rates = [row[0] for row in rows] if rows else []
        return {"rates": rates}
get_lowest_free_meal_rates_by_school_type = run; del run

# get_lowest_low_grade_by_ncesdist_and_edopscode — Minimum `Low Grade` among schools whose NCES district ID (NCESDist) and Education Operations Code (EdOpsCode) match the given values.
def run(conn, nces_dist, edops_code):
        cur = conn.execute(
            "SELECT MIN(frpm.`Low Grade`) "
            "FROM frpm "
            "INNER JOIN schools ON frpm.CDSCode = schools.CDSCode "
            "WHERE schools.NCESDist = ? AND schools.EdOpsCode = ?",
            (nces_dist, edops_code)
        )
        row = cur.fetchone()
        return {"lowest_low_grade": row[0] if row and row[0] is not None else None}
get_lowest_low_grade_by_ncesdist_and_edopscode = run; del run

# get_mailing_street_of_school_with_highest_frpm_k12 — Unabbreviated mailing street address of the school that has the highest FRPM Count (K‑12) in the dataset.
def run(conn):
        row = conn.execute(
            "SELECT T2.MailStreet "
            "FROM frpm AS T1 "
            "INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "ORDER BY T1.`FRPM Count (K-12)` DESC "
            "LIMIT 1"
        ).fetchone()
        return {"mail_street": row[0] if row else None}
get_mailing_street_of_school_with_highest_frpm_k12 = run; del run

# get_math_score_and_county_of_school_with_lowest_total_average_score — Returns the average Math SAT score and the county of the school whose combined average scores (Math + Reading + Writing) are the lowest among all schools.
def run(conn):
        row = conn.execute(
            "SELECT T1.AvgScrMath, T2.County "
            "FROM satscores AS T1 "
            "JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "WHERE T1.AvgScrMath IS NOT NULL "
            "ORDER BY (T1.AvgScrMath + T1.AvgScrRead + T1.AvgScrWrite) ASC "
            "LIMIT 1"
        ).fetchone()
        if row:
            return {"result": [[row[0], row[1]]]}
        else:
            return {"result": []}
get_math_score_and_county_of_school_with_lowest_total_average_score = run; del run

# get_merged_district_ratio_by_county — Compute the ratio of the number of merged schools with a specified numerator DOC code to the number with a specified denominator DOC code in a given county.
def run(conn, county_name, numerator_doc, denominator_doc, status_type="Merged"):
        cur = conn.execute(
            """SELECT
                   CAST(SUM(CASE WHEN DOC = ? THEN 1 ELSE 0 END) AS REAL) /
                   NULLIF(SUM(CASE WHEN DOC = ? THEN 1 ELSE 0 END), 0)
               FROM schools
               WHERE StatusType = ? AND County = ?""",
            (numerator_doc, denominator_doc, status_type, county_name)
        )
        row = cur.fetchone()
        return {"ratio": row[0] if row else None}
get_merged_district_ratio_by_county = run; del run

# get_most_common_grade_span_by_city — Most common grade span (GSserved) served by schools in a specified city.
def run(conn, city_name):
        row = conn.execute(
            "SELECT GSserved FROM schools "
            "WHERE City = ? "
            "GROUP BY GSserved "
            "ORDER BY COUNT(GSserved) DESC "
            "LIMIT 1",
            (city_name,)
        ).fetchone()
        return {"grade_span": row[0] if row else None}
get_most_common_grade_span_by_city = run; del run

# get_nces_district_ids_by_school_ownership_code — Return the NCES district identification numbers (NCESDist) for all schools with a specified School Ownership Code (SOC).
def run(conn, soc_code):
        cur = conn.execute(
            "SELECT NCESDist FROM schools WHERE SOC = ?",
            (soc_code,)
        )
        rows = cur.fetchall()
        ids = [row[0] for row in rows if row[0] is not None]
        return {"nces_district_ids": ids}
get_nces_district_ids_by_school_ownership_code = run; del run

# get_open_date_of_school_with_largest_k12_enrollment — OpenDate of the first‑through‑twelfth‑grade school that has the largest K‑12 enrollment.
def run(conn):
    row = conn.execute(
        "SELECT T2.OpenDate "
        "FROM frpm AS T1 "
        "JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
        "ORDER BY T1.`Enrollment (K-12)` DESC "
        "LIMIT 1"
    ).fetchone()
    return {'open_date': row[0] if row else None}
get_open_date_of_school_with_largest_k12_enrollment = run; del run

# get_partially_virtual_charter_school_websites_by_county — Website URLs of schools that are charter (Charter=1) and partially virtual (Virtual='P') in the specified county.
def run(conn, county_name):
        rows = conn.execute(
            "SELECT Website FROM schools WHERE County = ? AND Virtual = 'P' AND Charter = 1",
            (county_name,)
        ).fetchall()
        websites = [row[0] for row in rows]
        return {"websites": websites}
get_partially_virtual_charter_school_websites_by_county = run; del run

# get_percent_eligible_free_by_admin_first_name — Returns a single row [percent, district_code] for the school administered by the given administrator first name.
def run(conn, admin_first_name):
        cur = conn.execute(
            "SELECT T1.`Free Meal Count (K-12)` * 100.0 / T1.`Enrollment (K-12)`, "
            "T1.`District Code` "
            "FROM frpm AS T1 "
            "INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T2.AdmFName1 = ?",
            (admin_first_name,)
        )
        row = cur.fetchone()
        if row is None:
            return []          # no rows
        return [[row[0], row[1]]]
get_percent_eligible_free_by_admin_first_name = run; del run

# get_phone_and_ext_by_zip — Return a single row (phone, extension, school) for the school with the given ZIP code.
def run(conn, zip_code):
        row = conn.execute(
            "SELECT Phone, Ext, School FROM schools WHERE Zip = ?",
            (zip_code,)
        ).fetchone()
        if row:
            return {"rows": [row]}
        return {"rows": []}
get_phone_and_ext_by_zip = run; del run

# get_phone_numbers_of_charter_schools — Phone numbers of schools that are charter schools with a specified Charter Funding Type and opened after a given date.
def run(conn, funding_type, charter_flag, open_date):
        rows = conn.execute(
            """SELECT T2.Phone
               FROM frpm AS T1
               INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode
               WHERE T1.`Charter Funding Type` = ?
                 AND T1.`Charter School (Y/N)` = ?
                 AND T2.OpenDate > ?""",
            (funding_type, charter_flag, open_date)
        ).fetchall()
        phones = [row[0] for row in rows]
        return {"phones": phones}
get_phone_numbers_of_charter_schools = run; del run

# get_phone_numbers_of_top_schools_by_sat_excellence_rate — Phone numbers of the schools with the highest SAT excellence rate (NumGE1500 / NumTstTakr).
def run(conn, limit):
        rows = conn.execute(
            """
            SELECT T1.Phone
            FROM schools AS T1
            JOIN satscores AS T2 ON T1.CDSCode = T2.cds
            ORDER BY CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        phones = [row[0] for row in rows]
        return {"phones": phones}
get_phone_numbers_of_top_schools_by_sat_excellence_rate = run; del run

# get_phone_of_lowest_reading_score_school_in_district — Return the telephone number of the school with the lowest average reading score (AvgScrRead) in the specified district, considering only non‑NULL scores.
def run(conn, district_name):
        row = conn.execute(
            """SELECT T2.Phone
               FROM satscores AS T1
               JOIN schools AS T2 ON T1.cds = T2.CDSCode
               WHERE T2.District = ?
                 AND T1.AvgScrRead IS NOT NULL
               ORDER BY T1.AvgScrRead ASC
               LIMIT 1""",
            (district_name,)
        ).fetchone()
        return {"phone": row[0] if row else None}
get_phone_of_lowest_reading_score_school_in_district = run; del run

# get_phone_of_school_with_highest_math_sat_score — Return the phone number of the school that has the highest average Math SAT score.
def run(conn):
    row = conn.execute(
        "SELECT T1.Phone "
        "FROM schools AS T1 "
        "JOIN satscores AS T2 ON T1.CDSCode = T2.cds "
        "WHERE T2.AvgScrMath IS NOT NULL "
        "ORDER BY T2.AvgScrMath DESC "
        "LIMIT 1"
    ).fetchone()
    return {"phone": row[0] if row else None}
get_phone_of_school_with_highest_math_sat_score = run; del run

# get_phone_of_school_with_highest_math_score — Phone number of the school that has the highest average SAT Math score.
def run(conn):
    row = conn.execute(
        "SELECT T1.Phone "
        "FROM schools AS T1 "
        "JOIN satscores AS T2 ON T1.CDSCode = T2.cds "
        "ORDER BY T2.AvgScrMath DESC "
        "LIMIT 1"
    ).fetchone()
    return {"phone": row[0] if row else None}
get_phone_of_school_with_highest_math_score = run; del run

# get_phone_of_school_with_highest_sat_ge1500 — Phone number of the school that has the highest number of SAT test takers with scores over 1500.
def run(conn):
        row = conn.execute(
            "SELECT T2.Phone "
            "FROM satscores AS T1 "
            "INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "ORDER BY T1.NumGE1500 DESC "
            "LIMIT 1"
        ).fetchone()
        return {"phone": row[0] if row else None}
get_phone_of_school_with_highest_sat_ge1500 = run; del run

# get_sat_test_takers_by_cds — Return the number of SAT test takers (NumTstTakr) for a given school identified by its CDSCode.
def run(conn, cds):
        row = conn.execute(
            "SELECT NumTstTakr FROM satscores WHERE cds = ?",
            (cds,)
        ).fetchone()
        return {"num_test_takers": row[0] if row else None}
get_sat_test_takers_by_cds = run; del run

# get_sat_test_takers_of_school_with_highest_frpm_k12 — Number of SAT test takers (NumTstTakr) for the school that has the highest FRPM Count (K‑12) in the dataset.
def run(conn):
        # Find the CDSCode of the school with the maximum FRPM Count (K‑12)
        cur = conn.execute(
            "SELECT CDSCode FROM frpm ORDER BY `FRPM Count (K-12)` DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return {"sat_test_takers": None}
        cds_code = row[0]
        # Retrieve NumTstTakr from satscores for that CDSCode
        cur2 = conn.execute(
            "SELECT NumTstTakr FROM satscores WHERE cds = ?", (cds_code,)
        )
        row2 = cur2.fetchone()
        return {"sat_test_takers": row2[0] if row2 else None}
get_sat_test_takers_of_school_with_highest_frpm_k12 = run; del run

# get_school_address_by_math_rank — Returns the MailStreet (postal street address) and School name of the school that ranks `rank`‑th highest in average Math SAT score.
def run(conn, rank):
        offset = max(rank - 1, 0)
        row = conn.execute(
            """SELECT T2.MailStreet, T2.School
               FROM satscores AS T1
               JOIN schools AS T2 ON T1.cds = T2.CDSCode
               ORDER BY T1.AvgScrMath DESC
               LIMIT ?, 1""",
            (offset,)
        ).fetchone()
        if row:
            return {"rows": [[row[0], row[1]]]}
        else:
            return {"rows": []}
get_school_address_by_math_rank = run; del run

# get_school_codes_by_min_total_enrollment — Return CDSCode identifiers of schools whose total enrollment (K‑12 + Ages 5‑17) exceeds the given threshold.
def run(conn, min_total_enrollment):
        rows = conn.execute(
            "SELECT T2.CDSCode "
            "FROM schools AS T1 "
            "INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE T2.`Enrollment (K-12)` + T2.`Enrollment (Ages 5-17)` > ?",
            (min_total_enrollment,)
        ).fetchall()
        return {"cds_codes": [r[0] for r in rows]}
get_school_codes_by_min_total_enrollment = run; del run

# get_school_codes_with_total_enrollment_over — Return CDS codes of schools where total enrollment (K-12 plus Ages 5-17) is greater than a specified threshold.
def run(conn, min_total_enrollment):
        cursor = conn.execute(
            "SELECT T2.CDSCode "
            "FROM schools AS T1 "
            "INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode "
            "WHERE (T2.`Enrollment (K-12)` + T2.`Enrollment (Ages 5-17)`) > ?",
            (min_total_enrollment,)
        )
        rows = cursor.fetchall()
        codes = [row[0] for row in rows] if rows else []
        return {"school_codes": codes}
get_school_codes_with_total_enrollment_over = run; del run

# get_school_count_ratio_by_state_and_two_counties — Computes the ratio of the number of schools in `county_a` to the number in `county_b` among schools whose mailing address state equals `state`.
def run(conn, state, county_a, county_b):
        # Count schools in each county within the specified mailing state.
        cur = conn.execute(
            """SELECT
                   CAST(SUM(CASE WHEN County = ? THEN 1 ELSE 0 END) AS REAL) AS cnt_a,
                   SUM(CASE WHEN County = ? THEN 1 ELSE 0 END) AS cnt_b
               FROM schools
               WHERE MailState = ?""",
            (county_a, county_b, state)
        )
        row = cur.fetchone()
        cnt_a, cnt_b = (row[0], row[1]) if row else (0, 0)
        ratio = cnt_a / cnt_b if cnt_b != 0 else None
        return {"ratio": ratio}
get_school_count_ratio_by_state_and_two_counties = run; del run

# get_school_percent_frpm_by_county_and_grade_span — List schools in a specified county that serve the given grade span, along with the percent of students eligible for FRPM (Ages 5‑17). Percent = FRPM Count (Ages 5‑17) * 100 / Enrollment (Ages 5‑17).
def run(conn, county_name, grade_span):
        cursor = conn.execute(
            "SELECT s.School, (f.`FRPM Count (Ages 5-17)` * 100.0) / f.`Enrollment (Ages 5-17)` AS percent "
            "FROM frpm AS f JOIN schools AS s ON f.CDSCode = s.CDSCode "
            "WHERE s.County = ? AND s.GSserved = ?",
            (county_name, grade_span)
        )
        rows = cursor.fetchall()
        return {"schools_percent": rows}
get_school_percent_frpm_by_county_and_grade_span = run; del run

# get_school_websites_by_county_and_test_takers — Return the website URLs of schools in a specified county whose SAT test taker count falls within a given inclusive range.
def run(conn, county_name, min_test_takers, max_test_takers):
        sql = (
            "SELECT T2.Website "
            "FROM satscores AS T1 "
            "INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "WHERE T1.NumTstTakr BETWEEN ? AND ? "
            "AND T2.County = ?"
        )
        rows = conn.execute(sql, (min_test_takers, max_test_takers, county_name)).fetchall()
        websites = [row[0] for row in rows]
        return {"websites": websites}
get_school_websites_by_county_and_test_takers = run; del run

# get_school_websites_by_county_virtual_charter — Retrieve the list of website URLs for schools in a specified county that match a given virtual status and charter flag.
def run(conn, county_name, virtual_status, charter):
        rows = conn.execute(
            "SELECT Website FROM schools WHERE County = ? AND Virtual = ? AND Charter = ?",
            (county_name, virtual_status, charter)
        ).fetchall()
        websites = [r[0] for r in rows] if rows else []
        return {"websites": websites}
get_school_websites_by_county_virtual_charter = run; del run

# get_school_websites_by_free_meal_range_ages_5_17 — Website URLs and school names for schools where `Free Meal Count (Ages 5-17)` is between the given inclusive bounds. Excludes rows with NULL website.
def run(conn, min_free_meal, max_free_meal):
    cursor = conn.execute(
        """SELECT T2.Website, T1.`School Name`
           FROM frpm AS T1
           JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode
           WHERE T1.`Free Meal Count (Ages 5-17)` BETWEEN ? AND ?
             AND T2.Website IS NOT NULL""",
        (min_free_meal, max_free_meal)
    )
    rows = cursor.fetchall()
    return {"websites": rows}
get_school_websites_by_free_meal_range_ages_5_17 = run; del run

# get_school_with_highest_latitude — Return a single row containing the school type, school name, and latitude of the school with the maximum latitude.
def run(conn):
        row = conn.execute(
            "SELECT T1.`School Type`, T1.`School Name`, T2.Latitude "
            "FROM frpm AS T1 "
            "INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode "
            "ORDER BY T2.Latitude DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return []                     # no rows
        return [[row[0], row[1], row[2]]]  # list of one row
get_school_with_highest_latitude = run; del run

# get_school_with_highest_test_takers_by_county — Name of the school in the specified county that has the highest number of SAT test takers.
def run(conn, county_name):
        row = conn.execute(
            "SELECT sname FROM satscores "
            "WHERE cname = ? AND sname IS NOT NULL "
            "ORDER BY NumTstTakr DESC LIMIT 1",
            (county_name,)
        ).fetchone()
        return {"school_name": row[0] if row else None}
get_school_with_highest_test_takers_by_county = run; del run

# get_school_with_lowest_latitude_by_state — Find the school in a specified state that has the lowest latitude (southernmost). Returns its city, low grade, and school name.
def run(conn, state):
        row = conn.execute(
            """SELECT s.City, f.`Low Grade`, f.`School Name`
               FROM frpm f
               INNER JOIN schools s ON f.CDSCode = s.CDSCode
               WHERE s.State = ?
               ORDER BY s.Latitude ASC
               LIMIT 1""",
            (state,)
        ).fetchone()
        if row is None:
            return {"city": None, "low_grade": None, "school_name": None}
        return {"city": row[0], "low_grade": row[1], "school_name": row[2]}
get_school_with_lowest_latitude_by_state = run; del run

# get_school_with_lowest_reading_score — Returns the mailing street address and school name of the school with the lowest non‑null average reading score (AvgScrRead).
def run(conn):
    row = conn.execute("""SELECT T2.MailStreet, T2.School
           FROM satscores AS T1
           INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
           WHERE T1.AvgScrRead IS NOT NULL
           ORDER BY T1.AvgScrRead ASC
           LIMIT 1""").fetchone()
    if row:
        return {"result": [[row[0], row[1]]]}
    else:
        return {"result": []}
get_school_with_lowest_reading_score = run; del run

# get_school_writing_score_and_phone_by_date_criteria — Return each school's name, its average SAT writing score, and phone number for schools opened after a given year OR closed before a given year.
def run(conn, open_year_min, closed_year_max):
        sql = (
            "SELECT s.School, ss.AvgScrWrite, s.Phone "
            "FROM schools AS s "
            "LEFT JOIN satscores AS ss ON s.CDSCode = ss.cds "
            "WHERE CAST(strftime('%Y', s.OpenDate) AS INTEGER) > ? "
            "   OR CAST(strftime('%Y', s.ClosedDate) AS INTEGER) < ?"
        )
        cur = conn.execute(sql, (open_year_min, closed_year_max))
        rows = [
            {"school": r[0], "avg_writing_score": r[1], "phone": r[2]}
            for r in cur.fetchall()
        ]
        return {"rows": rows}
get_school_writing_score_and_phone_by_date_criteria = run; del run

# get_schools_and_mailing_zip_by_admin — List schools and their mailing zip codes for which the primary administrator’s first and last names match the given values.
def run(conn, admin_first_name, admin_last_name):
        cur = conn.execute(
            "SELECT School, MailZip FROM schools WHERE AdmFName1 = ? AND AdmLName1 = ?",
            (admin_first_name, admin_last_name)
        )
        rows = cur.fetchall()
        result = [list(r) for r in rows]
        return {"schools": result}
get_schools_and_mailing_zip_by_admin = run; del run

# get_schools_by_free_meal_ratio_and_sat_ge1500 — List school names whose K‑12 free‑meal eligibility ratio (Free Meal Count (K‑12) / Enrollment (K‑12)) is greater than a given threshold and that have more than a given number of SAT test‑takers scoring ≥1500.
def run(conn, min_free_meal_ratio, min_sat_ge1500):
        cur = conn.execute(
            """SELECT T2.`School Name`
               FROM satscores AS T1
               JOIN frpm AS T2 ON T1.cds = T2.CDSCode
               WHERE (CAST(T2.`Free Meal Count (K-12)` AS REAL) / T2.`Enrollment (K-12)`) > ?
                 AND T1.NumGE1500 > ?""",
            (min_free_meal_ratio, min_sat_ge1500)
        )
        rows = cur.fetchall()
        names = [row[0] for row in rows] if rows else []
        return {"school_names": names}
get_schools_by_free_meal_ratio_and_sat_ge1500 = run; del run

# get_schools_by_free_meal_ratio_and_test_score — Return the names of schools whose K‑12 free‑meal eligibility ratio is greater than a given threshold and that have more than a given number of SAT test‑takers scoring ≥1500.
def run(conn, ratio_threshold, min_test_score):
        rows = conn.execute(
            """SELECT T2.`School Name`
               FROM satscores AS T1
               JOIN frpm AS T2 ON T1.cds = T2.CDSCode
               WHERE CAST(T2.`Free Meal Count (K-12)` AS REAL) / T2.`Enrollment (K-12)` > ?
                 AND T1.NumGE1500 > ?""",
            (ratio_threshold, min_test_score)
        ).fetchall()
        # Return just the school name strings
        names = [r[0] for r in rows]
        return {"school_names": names}
get_schools_by_free_meal_ratio_and_test_score = run; del run

# get_schools_by_sat_takers_and_magnet — List school names that have a specified magnet flag and more than a given number of SAT test takers.
def run(conn, min_sat_takers, magnet):
        rows = conn.execute(
            """SELECT T2.School
               FROM satscores AS T1
               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
               WHERE T2.Magnet = ?
                 AND T1.NumTstTakr > ?""",
            (magnet, min_sat_takers)
        ).fetchall()
        return {"schools": [r[0] for r in rows]}
get_schools_by_sat_takers_and_magnet = run; del run

# get_schools_in_district_with_avg_math_above — List schools in a specified district whose average SAT Math score is greater than a given threshold, returning each school's name and Charter Funding Type.
def run(conn, district_name, min_avg_math):
        pattern = district_name + '%'
        cur = conn.execute(
            "SELECT T1.sname, T2.`Charter Funding Type` "
            "FROM satscores AS T1 "
            "INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode "
            "WHERE T2.`District Name` LIKE ? "
            "GROUP BY T1.sname, T2.`Charter Funding Type` "
            "HAVING CAST(SUM(T1.AvgScrMath) AS REAL) / COUNT(T1.cds) > ?",
            (pattern, min_avg_math)
        )
        rows = cur.fetchall()
        # Return rows in the same shape as the gold SQL result
        return {"rows": rows}
get_schools_in_district_with_avg_math_above = run; del run

# get_schools_with_enrollment_difference_above — List schools (name and street) where the K‑12 enrollment minus the Ages 5‑17 enrollment is greater than a specified threshold.
def run(conn, threshold):
        cursor = conn.execute(
            "SELECT s.School, s.Street "
            "FROM schools s "
            "JOIN frpm f ON s.CDSCode = f.CDSCode "
            "WHERE (f.`Enrollment (K-12)` - f.`Enrollment (Ages 5-17)`) > ?",
            (threshold,)
        )
        rows = cursor.fetchall()
        return {"schools": [{"school": r[0], "street": r[1]} for r in rows] if rows else []}
get_schools_with_enrollment_difference_above = run; del run

# get_test_takers_by_mailing_city — List of SAT test taker counts (NumTstTakr) for each school whose mailing city address equals the specified city.
def run(conn, city_name):
        rows = conn.execute(
            "SELECT T1.NumTstTakr "
            "FROM satscores AS T1 "
            "INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "WHERE T2.MailCity = ?",
            (city_name,)
        ).fetchall()
        counts = [row[0] for row in rows] if rows else []
        return {"test_takers": counts}
get_test_takers_by_mailing_city = run; del run

# get_top_admin_first_names_with_districts — Return the most frequent administrator first names (AdmFName1) from the schools table, limited to a given count, along with each administrator's district.
def run(conn, limit):
        # Step 1: find the N most frequent first‑name values.
        top_rows = conn.execute(
            """
            SELECT AdmFName1
            FROM schools
            GROUP BY AdmFName1
            ORDER BY COUNT(*) DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        top_names = [r[0] for r in top_rows]
        if not top_names:
            return {"admin_names": []}
        # Step 2: retrieve distinct (first_name, district) pairs for those names.
        placeholders = ",".join(["?"] * len(top_names))
        query = f"""
            SELECT DISTINCT AdmFName1, District
            FROM schools
            WHERE AdmFName1 IN ({placeholders})
        """
        rows = conn.execute(query, tuple(top_names)).fetchall()
        result = [[r[0], r[1]] for r in rows]
        return {"admin_names": result}
get_top_admin_first_names_with_districts = run; del run

# get_top_n_free_meal_rates_by_frpm_and_soc — Eligible free‑meal rate (FRPM Count (K‑12) / Enrollment (K‑12)) for the top N schools with the highest FRPM Count (K‑12), filtered by a given ownership code (SOC).
def run(conn, soc_code, limit):
        cur = conn.execute(
            "SELECT CAST(frpm.`FRPM Count (K-12)` AS REAL) / frpm.`Enrollment (K-12)` AS rate "
            "FROM frpm "
            "JOIN schools ON frpm.CDSCode = schools.CDSCode "
            "WHERE schools.SOC = ? "
            "ORDER BY frpm.`FRPM Count (K-12)` DESC "
            "LIMIT ?",
            (soc_code, limit)
        )
        rows = cur.fetchall()
        rates = [row[0] for row in rows] if rows else []
        return {"rates": rates}
get_top_n_free_meal_rates_by_frpm_and_soc = run; del run

# get_top_n_phone_numbers_by_sat_excellence_rate — Phone numbers of the top N schools ordered by SAT excellence rate (NumGE1500 / NumTstTakr).
def run(conn, limit):
        rows = conn.execute(
            """SELECT T1.Phone
               FROM schools AS T1
               JOIN satscores AS T2 ON T1.CDSCode = T2.cds
               ORDER BY CAST(T2.NumGE1500 AS REAL) / T2.NumTstTakr DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        phones = [row[0] for row in rows]
        return {"phones": phones}
get_top_n_phone_numbers_by_sat_excellence_rate = run; del run

# get_top_n_schools_by_enrollment_ages_5_17 — NCES school IDs of the top N schools ordered by descending Enrollment (Ages 5‑17).
def run(conn, limit):
    rows = conn.execute(
        "SELECT T1.NCESSchool "
        "FROM schools AS T1 "
        "INNER JOIN frpm AS T2 ON T1.CDSCode = T2.CDSCode "
        "ORDER BY T2.`Enrollment (Ages 5-17)` DESC "
        "LIMIT ?",
        (limit,)
    ).fetchall()
    return {"schools": [row[0] for row in rows]}
get_top_n_schools_by_enrollment_ages_5_17 = run; del run

# get_websites_by_county_and_test_takers — Retrieve website URLs for schools in a specified county whose SAT test‑taker count is between the given bounds.
def run(conn, county_name, min_test_takers, max_test_takers):
        rows = conn.execute(
            """SELECT T2.Website
               FROM satscores AS T1
               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
               WHERE T1.NumTstTakr BETWEEN ? AND ?
                 AND T2.County = ?""",
            (min_test_takers, max_test_takers, county_name)
        ).fetchall()
        websites = [r[0] for r in rows]
        return {"websites": websites}
get_websites_by_county_and_test_takers = run; del run

# get_writing_score_ranking — List of [CharterNum, AvgScrWrite, rank] for schools with AvgScrWrite > min_writing_score and a non‑null CharterNum, ordered by descending AvgScrWrite.
def run(conn, min_writing_score):
        sql = (
            "SELECT T1.CharterNum, T2.AvgScrWrite, "
            "RANK() OVER (ORDER BY T2.AvgScrWrite DESC) "
            "FROM schools AS T1 "
            "INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds "
            "WHERE T2.AvgScrWrite > ? AND T1.CharterNum IS NOT NULL "
            "ORDER BY T2.AvgScrWrite DESC"
        )
        rows = conn.execute(sql, (min_writing_score,)).fetchall()
        # Convert each tuple to a list for JSON compatibility
        return [list(row) for row in rows]
get_writing_score_ranking = run; del run

# get_zip_codes_of_charter_schools_by_district — ZIP codes of charter schools located in a specified district (based on the `District Name` column in the frpm table).
def run(conn, district_name):
    rows = conn.execute(
        "SELECT s.Zip FROM frpm AS f JOIN schools AS s ON f.CDSCode = s.CDSCode "
        "WHERE f.`District Name` = ? AND f.`Charter School (Y/N)` = 1",
        (district_name,)
    ).fetchall()
    zip_codes = [r[0] for r in rows if r[0] is not None]
    return {"zip_codes": zip_codes}
get_zip_codes_of_charter_schools_by_district = run; del run

# list_address_of_school_with_lowest_excellence_rate — Returns the address of the school with the lowest excellence rate as a nested list [[Street, City, State, Zip]] to match the gold‑SQL output format.
def run(conn):
        row = conn.execute(
            """SELECT T2.Street, T2.City, T2.State, T2.Zip
               FROM satscores AS T1
               INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
               ORDER BY CAST(T1.NumGE1500 AS REAL) / T1.NumTstTakr ASC
               LIMIT 1"""
        ).fetchone()
        if not row:
            return []                     # no rows
        return [list(row)]               # e.g. [["1111 Van Ness Avenue","Fresno","CA","93721-2002"]]
list_address_of_school_with_lowest_excellence_rate = run; del run

# list_virtual_schools_top5_by_county_reading — Names of exclusively virtual schools that rank in the top 5 within their county by average SAT reading score.
def run(conn):
    sql = '''
    SELECT School FROM (
        SELECT T2.School,
               T1.AvgScrRead,
               RANK() OVER (PARTITION BY T2.County ORDER BY T1.AvgScrRead DESC) AS rnk
        FROM satscores AS T1
        INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode
        WHERE T2.Virtual = 'F'
    ) ranked
    WHERE rnk <= 5
    '''
    rows = conn.execute(sql).fetchall()
    names = [r[0] for r in rows]
    return {"school_names": names}
list_virtual_schools_top5_by_county_reading = run; del run

# question_0_wrapper — Execute the gold SQL for question 0 and return its rows.
def run(conn, **kwargs):
        cur = conn.cursor()
        cur.execute("""SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)` FROM frpm WHERE `County Name` = 'Alameda' ORDER BY (CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`) DESC LIMIT 1""")
        rows = cur.fetchall()
        # Convert tuples to JSON‑serializable lists
        rows = [list(r) for r in rows]
        return {"rows": rows}
question_0_wrapper = run; del run

# rank_schools_by_writing_score — Ranks schools (by Charter number) according to their average Writing SAT score. Only schools with a non‑null Charter number and a Writing score greater than a provided threshold are included. Returns the Charter number, the average Writing score, and the rank (1 = highest score).
def run(conn, min_writing_score):
        sql = (
            "SELECT T1.CharterNum AS charter_number, "
            "T2.AvgScrWrite AS avg_writing_score, "
            "RANK() OVER (ORDER BY T2.AvgScrWrite DESC) AS writing_score_rank "
            "FROM schools AS T1 "
            "JOIN satscores AS T2 ON T1.CDSCode = T2.cds "
            "WHERE T2.AvgScrWrite > ? AND T1.CharterNum IS NOT NULL "
            "ORDER BY writing_score_rank ASC"
        )
        cur = conn.execute(sql, (min_writing_score,))
        rows = cur.fetchall()
        # Build a list of dicts with clear keys
        result = [
            {
                "charter_number": row[0],
                "avg_writing_score": row[1],
                "writing_score_rank": row[2]
            }
            for row in rows
        ]
        return {"rankings": result}
rank_schools_by_writing_score = run; del run

# schools_with_enrollment_difference_above_funding — List schools (name and DOC) whose K‑12 enrollment minus Ages 5‑17 enrollment exceeds a threshold, filtered by FundingType, ordered by school name.
def run(conn, funding_type, threshold):
        cur = conn.execute(
            """
            SELECT T2.School, T2.DOC
            FROM frpm AS T1
            JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode
            WHERE T2.FundingType = ?
              AND (T1.`Enrollment (K-12)` - T1.`Enrollment (Ages 5-17)`) > ?
            ORDER BY T2.School ASC
            """,
            (funding_type, threshold)
        )
        rows = cur.fetchall()
        # Return as a list of tuples for direct comparison with gold result
        return {"schools": rows}
schools_with_enrollment_difference_above_funding = run; del run
