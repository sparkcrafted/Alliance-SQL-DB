from pathlib import Path
import pandas as pd
import sqlite3
import re

# --------------------------------------------------
# 1. Set project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "Data" / "Raw"
CLEAN_DIR = PROJECT_ROOT / "Data" / "Cleaned"
DB_DIR = PROJECT_ROOT / "Database"

CLEAN_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DB_DIR / "alliance.db"

print("Project root:", PROJECT_ROOT)
print("Raw folder:", RAW_DIR)
print("Database path:", DB_PATH)

# --------------------------------------------------
# 2. Helper functions
# --------------------------------------------------

def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with SQL-friendly column names."""
    df = df.copy()
    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("-", "_", regex=False)
        .str.replace("/", "_", regex=False)
        .str.replace("%", "pct", regex=False)
        .str.replace(".", "", regex=False)
    )
    return df


def show_table_row_counts(conn: sqlite3.Connection) -> None:
    """Print all SQLite tables and their row counts."""
    tables = pd.read_sql_query(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name;
        """,
        conn
    )

    print("\nTables currently in alliance.db:")
    print(tables)

    print("\nRow counts by table:")
    for table in tables["name"]:
        count_query = f"SELECT COUNT(*) AS row_count FROM {table};"
        count = pd.read_sql_query(count_query, conn)
        print(f"{table}: {count.loc[0, 'row_count']} rows")


def validate_no_missing_ids(df: pd.DataFrame, id_col: str, label: str, display_cols=None) -> None:
    """Print missing ID checks and raise an error if missing IDs are found."""
    missing = df[df[id_col].isna()].copy()
    print(f"\n{label} missing {id_col} check:")
    if missing.empty:
        print("No missing IDs.")
    else:
        if display_cols:
            print(missing[display_cols])
        else:
            print(missing)
        raise ValueError(f"Missing {id_col} values found in {label}.")


def normalize_school_name(value: str) -> str:
    """Standardize known school-name typos before joins."""
    if pd.isna(value):
        return value
    value = str(value).strip()
    value = value.replace("Steubenville (OH))", "Steubenville (OH)")
    value = value.replace("Mount Carmel (OH)", "Mount Carmel (IL)")
    return value


def parse_opponent_token(token: str):
    """Parse a schedule token such as '@ City College (MD)', 'vs Ramsey (NJ)', or 'BYE'."""
    if pd.isna(token):
        return None, None

    token = str(token).strip()
    if token == "" or token.upper() == "BYE":
        return "BYE", None

    if token.startswith("@ "):
        return "Away", token[2:].strip()
    if token.startswith("vs "):
        return "Home", token[3:].strip()

    return "Neutral/Unknown", token


# --------------------------------------------------
# 3. List raw files
# --------------------------------------------------

print("\nRaw files found:")
for file in RAW_DIR.glob("*"):
    print("-", file.name)

# --------------------------------------------------
# 4. Load + clean Football Program Data into schools table
# --------------------------------------------------

program_file = RAW_DIR / "Football_Program_Data.csv"
programs_raw = pd.read_csv(program_file)

print("\nRaw program data preview:")
print(programs_raw.head())

print("\nRaw columns:")
print(programs_raw.columns.tolist())

programs = clean_column_names(programs_raw)

# Remove blank rows
programs = programs.dropna(how="all")
programs = programs[
    programs["school"].notna()
    & (programs["school"].astype(str).str.strip() != "")
].copy()
programs = programs.reset_index(drop=True)

# Add official Alliance school IDs
school_id_map = {
    "City College (MD)": 1001,
    "Central (PA)": 1002,
    "PG Poly (MD)": 1003,
    "Brooklyn Tech (NY)": 1004,
    "Ramsey (NJ)": 1005,
    "Phoebus (VA)": 1006,
    "Oscar Smith (VA)": 1007,
    "Canton McKinley (OH)": 1008,
    "Mount Carmel (IL)": 1009,
    "Steubenville (OH)": 1010,
    "Male (KY)": 1011,
    "East St. Louis (IL)": 1012,
    "Moeller (OH)": 1013,
    "Massillon (OH)": 1014,
}

programs["school"] = programs["school"].apply(normalize_school_name)
programs["school_id"] = programs["school"].map(school_id_map)
validate_no_missing_ids(programs, "school_id", "schools", ["school"])
programs["school_id"] = programs["school_id"].astype(int)

# Move school_id to first column
cols = ["school_id"] + [col for col in programs.columns if col != "school_id"]
programs = programs[cols]

# --------------------------------------------------
# Apply known salary corrections before saving schools table
# --------------------------------------------------
# These corrections are applied to the clean programs dataframe before it is
# written to SQLite. That way the schools table is built correctly every time.

salary_corrections = {
    "Jordan Lynch": 255000,
    "Chris Wolfe": 225000,
}

programs["fb_head_coach_salary"] = pd.to_numeric(
    programs["fb_head_coach_salary"],
    errors="coerce"
)

for coach, salary in salary_corrections.items():
    programs.loc[
        programs["fb_head_coach"] == coach,
        "fb_head_coach_salary"
    ] = salary

print("\nCleaned schools preview:")
print(programs.head())

# School lookup used throughout transformations
school_lookup = programs[["school_id", "school"]].copy()

# --------------------------------------------------
# 5. Open SQLite connection and save schools table
# --------------------------------------------------

conn = sqlite3.connect(DB_PATH)

programs.to_sql("schools", conn, if_exists="replace", index=False)

school_id_check = pd.read_sql_query(
    """
    SELECT school_id, school, fb_head_coach
    FROM schools
    ORDER BY school_id;
    """,
    conn
)

print("\nSchool ID validation:")
print(school_id_check)

# --------------------------------------------------
# 6. Validate known salary corrections
# --------------------------------------------------

salary_updates_check = pd.read_sql_query(
    """
    SELECT school, fb_head_coach, fb_head_coach_salary
    FROM schools
    WHERE fb_head_coach IN ('Jordan Lynch', 'Chris Wolfe')
    ORDER BY fb_head_coach;
    """,
    conn
)

print("\nSalary correction validation:")
print(salary_updates_check)

# --------------------------------------------------
# 7. Query: Head football coach salaries
# --------------------------------------------------

coach_salaries = pd.read_sql_query(
    """
    SELECT school, fb_head_coach, fb_head_coach_salary
    FROM schools
    WHERE fb_head_coach IS NOT NULL
      AND fb_head_coach_salary IS NOT NULL
      AND TRIM(fb_head_coach) <> ''
    ORDER BY fb_head_coach_salary DESC;
    """,
    conn
)

print("\nHead football coach salaries:")
print(coach_salaries)

# --------------------------------------------------
# 8. Load + transform Football National Championships
# --------------------------------------------------

national_titles_file = RAW_DIR / "Football_National_Championships.csv"
national_titles_raw = pd.read_csv(national_titles_file)
national_titles = clean_column_names(national_titles_raw)

print("\nRaw national championships preview:")
print(national_titles_raw.head())

print("\nCleaned national championships columns:")
print(national_titles.columns.tolist())

national_titles["school"] = national_titles["school"].apply(normalize_school_name)

# Expected starting format: school | total | years
national_titles_tidy = (
    national_titles
    .assign(years=national_titles["years"].astype(str).str.split(","))
    .explode("years")
)

national_titles_tidy["championship_year"] = (
    national_titles_tidy["years"]
    .astype(str)
    .str.strip()
)

# Remove blank/non-year values, then convert to int
national_titles_tidy = national_titles_tidy[
    national_titles_tidy["championship_year"].str.match(r"^\d{4}$", na=False)
].copy()

national_titles_tidy["championship_year"] = national_titles_tidy["championship_year"].astype(int)
national_titles_tidy = national_titles_tidy[["school", "championship_year"]].copy()
national_titles_tidy["sport"] = "Football"
national_titles_tidy["title_type"] = "National Championship"

national_titles_tidy = national_titles_tidy.merge(
    school_lookup,
    on="school",
    how="left"
)

validate_no_missing_ids(
    national_titles_tidy,
    "school_id",
    "football national championships",
    ["school", "championship_year"]
)

national_titles_tidy = national_titles_tidy[
    ["school_id", "school", "sport", "title_type", "championship_year"]
]

national_titles_tidy.insert(0, "title_id", range(1, len(national_titles_tidy) + 1))

print("\nTidy national championships preview:")
print(national_titles_tidy.head(20))

national_titles_tidy.to_sql(
    "football_national_championships",
    conn,
    if_exists="replace",
    index=False
)

national_title_counts = pd.read_sql_query(
    """
    SELECT s.school, COUNT(fnc.championship_year) AS national_titles
    FROM football_national_championships AS fnc
    JOIN schools AS s
        ON fnc.school_id = s.school_id
    GROUP BY s.school
    ORDER BY national_titles DESC;
    """,
    conn
)

print("\nNational titles by school:")
print(national_title_counts)

# --------------------------------------------------
# 9. Load remaining raw CSV tables
# --------------------------------------------------

tables_to_load = {
    "conference_championships": "Conference_Championships.csv",
    "football_alltime_series_records": "Football_AllTime_Series_Records.csv",
    "football_playoff_results": "Football_Playoff_Results.csv",
    "football_program_data_raw": "Football_Program_Data.csv",
    "head_football_coaching_record": "Head_Football_Coaching_Record.csv",
    "football_schedule_2026": "2026_Football_Schedule.csv",
}

for table_name, file_name in tables_to_load.items():
    file_path = RAW_DIR / file_name
    df_raw = pd.read_csv(file_path)
    df_clean = clean_column_names(df_raw)
    df_clean.to_sql(table_name, conn, if_exists="replace", index=False)

    print(f"\nLoaded table: {table_name}")
    print(f"Rows: {len(df_clean)}")
    print("Columns:", df_clean.columns.tolist())

# --------------------------------------------------
# 10. Transform: Conference championships into tidy relational table
# --------------------------------------------------

conference_raw = pd.read_sql_query(
    "SELECT year, football_champion FROM conference_championships;",
    conn
)

conference_tidy = conference_raw.copy()
conference_tidy["football_champion"] = conference_tidy["football_champion"].astype(str).str.strip()

conference_tidy = (
    conference_tidy
    .assign(school=conference_tidy["football_champion"].str.split("/"))
    .explode("school")
)

conference_tidy["school"] = conference_tidy["school"].apply(normalize_school_name)

conference_tidy["shared_title"] = (
    conference_tidy.groupby("year")["school"].transform("count") > 1
)
conference_tidy["sport"] = "Football"
conference_tidy["title_type"] = "Alliance Conference Championship"
conference_tidy = conference_tidy.rename(columns={"year": "season_year"})

conference_tidy = conference_tidy.merge(school_lookup, on="school", how="left")
validate_no_missing_ids(
    conference_tidy,
    "school_id",
    "football conference championships",
    ["season_year", "school", "football_champion"]
)

conference_tidy = conference_tidy[
    [
        "season_year",
        "school_id",
        "school",
        "sport",
        "title_type",
        "shared_title",
        "football_champion",
    ]
].copy()

conference_tidy.insert(0, "championship_id", range(1, len(conference_tidy) + 1))

print("\nTidy conference championships preview:")
print(conference_tidy.head(20))

conference_tidy.to_sql(
    "football_conference_championships",
    conn,
    if_exists="replace",
    index=False
)

conference_title_counts = pd.read_sql_query(
    """
    SELECT s.school, COUNT(fcc.championship_id) AS conference_titles
    FROM football_conference_championships AS fcc
    JOIN schools AS s
        ON fcc.school_id = s.school_id
    GROUP BY s.school
    ORDER BY conference_titles DESC;
    """,
    conn
)

print("\nConference titles by school:")
print(conference_title_counts)

# --------------------------------------------------
# 11. Transform: Head football coaching records into tidy relational table
# --------------------------------------------------

coach_raw = pd.read_sql_query("SELECT * FROM head_football_coaching_record;", conn)

print("\nHead football coaching record preview:")
print(coach_raw.head(10))
print("\nHead football coaching record columns:")
print(coach_raw.columns.tolist())

coach_tidy = coach_raw.copy()
coach_tidy["school"] = coach_tidy["school"].apply(normalize_school_name)

year_cols = [col for col in coach_tidy.columns if str(col).isdigit()]

coach_tidy = coach_tidy.melt(
    id_vars=["school", "head_fb_coach", "total_seasons_at_school", "first_season"],
    value_vars=year_cols,
    var_name="season_year",
    value_name="record",
)

coach_tidy = coach_tidy[
    coach_tidy["record"].notna()
    & (coach_tidy["record"].astype(str).str.strip() != "")
].copy()

coach_tidy["record"] = coach_tidy["record"].astype(str).str.strip()
coach_tidy["season_year"] = coach_tidy["season_year"].astype(int)
coach_tidy[["wins", "losses"]] = coach_tidy["record"].str.split("-", expand=True)
coach_tidy["wins"] = coach_tidy["wins"].astype(int)
coach_tidy["losses"] = coach_tidy["losses"].astype(int)

coach_tidy = coach_tidy.merge(school_lookup, on="school", how="left")
validate_no_missing_ids(
    coach_tidy,
    "school_id",
    "football coach season records",
    ["school", "head_fb_coach", "season_year", "record"]
)

coach_tidy = coach_tidy[
    [
        "school_id",
        "school",
        "head_fb_coach",
        "season_year",
        "record",
        "wins",
        "losses",
        "total_seasons_at_school",
        "first_season",
    ]
].copy()

coach_tidy.insert(0, "coach_record_id", range(1, len(coach_tidy) + 1))

print("\nTidy coaching records preview:")
print(coach_tidy.head(20))

coach_tidy.to_sql(
    "football_coach_season_records",
    conn,
    if_exists="replace",
    index=False
)

coach_career_records = pd.read_sql_query(
    """
    SELECT
        s.school,
        fcsr.head_fb_coach,
        SUM(fcsr.wins) AS total_wins,
        SUM(fcsr.losses) AS total_losses,
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
    """,
    conn
)

print("\nCurrent coach career records:")
print(coach_career_records)

# --------------------------------------------------
# 12. Transform: Football all-time series matrix into relational table
# Source: Football_AllTime_Series_Records.csv
# --------------------------------------------------

series_raw = pd.read_sql_query("SELECT * FROM football_alltime_series_records;", conn)
series = series_raw.copy()

print("\nFootball all-time series raw columns:")
print(series.columns.tolist())

# Clean column names
series = clean_column_names(series)

print("\nFootball all-time series cleaned columns:")
print(series.columns.tolist())


def normalize_school_key(value):
    """Normalize school names/column headers for matrix parsing."""
    return (
        str(value)
        .strip()
        .lower()
        .replace(".", "")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("__", "_")
    )


# Build lookup from normalized school names to official school names/IDs
school_lookup = programs[["school_id", "school"]].copy()
school_lookup["school_key"] = school_lookup["school"].apply(normalize_school_key)
school_name_map = dict(zip(school_lookup["school_key"], school_lookup["school"]))

# First column is the row school
first_col = series.columns[0]
series = series.rename(columns={first_col: "school"})
series["school"] = series["school"].astype(str).str.strip()

# Remove blank rows and total rows
series = series[
    series["school"].notna()
    & (series["school"].astype(str).str.strip() != "")
    & (~series["school"].astype(str).str.upper().isin(["TOTAL", "NAN"]))
].copy()

# Each opponent appears as a 3-column group:
# opponent school header | wins | losses | win_pct
records = []
cols = list(series.columns)
i = 1  # start after row-school column

while i < len(cols):
    opponent_col = cols[i]
    opponent_key = normalize_school_key(opponent_col)
    opponent_school = school_name_map.get(opponent_key)

    # Skip unnamed/non-school columns until we find a school header
    if opponent_school is None:
        i += 1
        continue

    if i + 2 >= len(cols):
        break

    win_col = cols[i]
    loss_col = cols[i + 1]
    pct_col = cols[i + 2]

    temp = series[["school", win_col, loss_col, pct_col]].copy()
    temp = temp.rename(
        columns={
            win_col: "wins",
            loss_col: "losses",
            pct_col: "win_pct",
        }
    )

    temp["opponent_school"] = opponent_school
    records.append(temp)

    i += 3

if not records:
    raise ValueError(
        "No opponent school groups were detected in Football_AllTime_Series_Records.csv. "
        f"Available columns are: {cols}"
    )

series_tidy = pd.concat(records, ignore_index=True)

# Clean values
series_tidy["school"] = series_tidy["school"].astype(str).str.strip().apply(normalize_school_name)
series_tidy["opponent_school"] = (
    series_tidy["opponent_school"]
    .astype(str)
    .str.strip()
    .apply(normalize_school_name)
)

series_tidy["wins"] = pd.to_numeric(series_tidy["wins"], errors="coerce")
series_tidy["losses"] = pd.to_numeric(series_tidy["losses"], errors="coerce")
series_tidy["win_pct"] = pd.to_numeric(series_tidy["win_pct"], errors="coerce")

# Keep only real series records
series_tidy = series_tidy[
    series_tidy["wins"].notna()
    & series_tidy["losses"].notna()
].copy()

series_tidy["wins"] = series_tidy["wins"].astype(int)
series_tidy["losses"] = series_tidy["losses"].astype(int)

# Join school_id and opponent_school_id
base_lookup = programs[["school_id", "school"]].copy()

series_tidy = series_tidy.merge(
    base_lookup,
    on="school",
    how="left"
)

opponent_lookup = base_lookup.rename(
    columns={
        "school_id": "opponent_school_id",
        "school": "opponent_school",
    }
)

series_tidy = series_tidy.merge(
    opponent_lookup,
    on="opponent_school",
    how="left"
)

validate_no_missing_ids(
    series_tidy,
    "school_id",
    "football all-time series row schools",
    ["school"]
)

validate_no_missing_ids(
    series_tidy,
    "opponent_school_id",
    "football all-time series opponent schools",
    ["opponent_school"]
)

# Remove self-matchups using IDs, which is safer than text matching
series_tidy = series_tidy[
    series_tidy["school_id"] != series_tidy["opponent_school_id"]
].copy()

# Final table shape: neutral league-wide fields, not City-specific fields
series_tidy = series_tidy[
    [
        "school_id",
        "school",
        "opponent_school_id",
        "opponent_school",
        "wins",
        "losses",
        "win_pct",
    ]
].copy()

series_tidy.insert(
    0,
    "series_record_id",
    range(1, len(series_tidy) + 1)
)

print("\nFootball all-time series records preview:")
print(series_tidy.head(25))

series_tidy.to_sql(
    "football_alltime_series_records_clean",
    conn,
    if_exists="replace",
    index=False
)

print("\nfootball_alltime_series_records_clean table created.")

# --------------------------------------------------
# Query: Best all-time series records
# --------------------------------------------------

series_query = """
SELECT
    school,
    opponent_school,
    wins,
    losses,
    win_pct
FROM football_alltime_series_records_clean
ORDER BY win_pct DESC, wins DESC
LIMIT 20;
"""

series_results = pd.read_sql_query(series_query, conn)

print("\nBest all-time series records:")
print(series_results)

# --------------------------------------------------
# 13. Transform: 2026 football schedule into game-level table
# --------------------------------------------------

schedule_raw = pd.read_sql_query("SELECT * FROM football_schedule_2026;", conn)
schedule = schedule_raw.copy()
schedule["team"] = schedule["team"].apply(normalize_school_name)

week_cols = [col for col in schedule.columns if re.fullmatch(r"w\d+", str(col))]

schedule_long = schedule.melt(
    id_vars=["team"],
    value_vars=week_cols,
    var_name="week",
    value_name="opponent_token",
)

schedule_long["week_number"] = schedule_long["week"].str.extract(r"(\d+)").astype(int)
schedule_long[["site", "opponent"]] = schedule_long["opponent_token"].apply(
    lambda token: pd.Series(parse_opponent_token(token))
)
schedule_long["opponent"] = schedule_long["opponent"].apply(normalize_school_name)

schedule_long = schedule_long[
    schedule_long["site"].notna()
    & (schedule_long["site"] != "BYE")
    & schedule_long["opponent"].notna()
].copy()

schedule_long = schedule_long.merge(
    school_lookup.rename(columns={"school": "team", "school_id": "team_school_id"}),
    on="team",
    how="left",
)
validate_no_missing_ids(schedule_long, "team_school_id", "2026 schedule teams", ["team"])

schedule_long = schedule_long.merge(
    school_lookup.rename(columns={"school": "opponent", "school_id": "opponent_school_id"}),
    on="opponent",
    how="left",
)

# Nonconference opponents are expected to be outside the Alliance; keep their ID null but label them.
schedule_long["opponent_is_alliance"] = schedule_long["opponent_school_id"].notna()
schedule_long["conference_game"] = schedule_long["opponent_is_alliance"]

schedule_long = schedule_long[
    [
        "team_school_id",
        "team",
        "week_number",
        "site",
        "opponent_school_id",
        "opponent",
        "opponent_is_alliance",
        "conference_game",
        "opponent_token",
    ]
].copy()
schedule_long.insert(0, "schedule_entry_id", range(1, len(schedule_long) + 1))

print("\n2026 football schedule entries preview:")
print(schedule_long.head(25))

schedule_long.to_sql(
    "football_schedule_2026_game_entries",
    conn,
    if_exists="replace",
    index=False
)

# --------------------------------------------------
# 14. Final validation queries and audit
# --------------------------------------------------

school_id_summary = pd.read_sql_query(
    """
    SELECT
        COUNT(*) AS total_schools,
        MIN(school_id) AS min_school_id,
        MAX(school_id) AS max_school_id,
        COUNT(DISTINCT school_id) AS unique_school_ids
    FROM schools;
    """,
    conn
)

print("\nSchool ID summary:")
print(school_id_summary)

show_table_row_counts(conn)

# Validate complete directed all-time series matrix
series_total_check = pd.read_sql_query(
    """
    SELECT COUNT(*) AS total_series_records
    FROM football_alltime_series_records_clean;
    """,
    conn
)

print("\nTotal all-time series records:")
print(series_total_check)

missing_series_pairs = pd.read_sql_query(
    """
    SELECT
        s1.school AS school,
        s2.school AS expected_opponent
    FROM schools AS s1
    CROSS JOIN schools AS s2
    LEFT JOIN football_alltime_series_records_clean AS r
        ON r.school_id = s1.school_id
       AND r.opponent_school_id = s2.school_id
    WHERE s1.school_id <> s2.school_id
      AND r.series_record_id IS NULL
    ORDER BY s1.school, s2.school;
    """,
    conn
)

print("\nMissing all-time series pairings:")
print(missing_series_pairs)
print("\nMissing pair count:", len(missing_series_pairs))

conn.close()

print("\nDatabase build complete.")
