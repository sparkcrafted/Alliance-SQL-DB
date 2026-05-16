from pathlib import Path
import pandas as pd
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "Database" / "alliance.db"

conn = sqlite3.connect(DB_PATH)

print("Connected to:", DB_PATH)

# --------------------------------------------------
# 1. National titles by school
# --------------------------------------------------

query = """
SELECT 
    s.school,
    COUNT(fnc.title_id) AS national_titles
FROM football_national_championships AS fnc
JOIN schools AS s
    ON fnc.school_id = s.school_id
GROUP BY s.school
ORDER BY national_titles DESC;
"""

print("\nNational titles by school:")
print(pd.read_sql_query(query, conn))


# --------------------------------------------------
# 2. Conference titles by school
# --------------------------------------------------

query = """
SELECT
    s.school,
    COUNT(fcc.championship_id) AS conference_titles
FROM football_conference_championships AS fcc
JOIN schools AS s
    ON fcc.school_id = s.school_id
GROUP BY s.school
ORDER BY conference_titles DESC;
"""

print("\nConference titles by school:")
print(pd.read_sql_query(query, conn))


# --------------------------------------------------
# 3. Current coach career records
# --------------------------------------------------

query = """
SELECT
    s.school,
    fcsr.head_fb_coach,
    SUM(fcsr.wins) AS wins,
    SUM(fcsr.losses) AS losses,
    ROUND(
        CAST(SUM(fcsr.wins) AS FLOAT) /
        (SUM(fcsr.wins) + SUM(fcsr.losses)),
        3
    ) AS win_pct
FROM football_coach_season_records AS fcsr
JOIN schools AS s
    ON fcsr.school_id = s.school_id
GROUP BY s.school, fcsr.head_fb_coach
ORDER BY win_pct DESC;
"""

print("\nCurrent coach career records:")
print(pd.read_sql_query(query, conn))


# --------------------------------------------------
# 4. Best all-time head-to-head series records
# --------------------------------------------------

query = """
SELECT
    school,
    opponent_school,
    wins,
    losses,
    win_pct
FROM football_alltime_series_records_clean
WHERE wins + losses >= 5
ORDER BY win_pct DESC, wins DESC
LIMIT 25;
"""

print("\nBest all-time series records, minimum 5 games:")
print(pd.read_sql_query(query, conn))


# --------------------------------------------------
# 5. Programs with both national and conference titles
# --------------------------------------------------

query = """
SELECT
    s.school,
    COUNT(DISTINCT fnc.title_id) AS national_titles,
    COUNT(DISTINCT fcc.championship_id) AS conference_titles
FROM schools AS s
LEFT JOIN football_national_championships AS fnc
    ON s.school_id = fnc.school_id
LEFT JOIN football_conference_championships AS fcc
    ON s.school_id = fcc.school_id
GROUP BY s.school
ORDER BY national_titles DESC, conference_titles DESC;
"""

print("\nProgram title summary:")
print(pd.read_sql_query(query, conn))

conn.close()