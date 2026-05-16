from pathlib import Path
import pandas as pd
import sqlite3

# --------------------------------------------------
# 1. Set project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "Database" / "alliance.db"
OUTPUT_DIR = PROJECT_ROOT / "Outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Database path:", DB_PATH)
print("Output folder:", OUTPUT_DIR)

# --------------------------------------------------
# 2. Helper functions
# --------------------------------------------------

def normalize_0_100(series: pd.Series) -> pd.Series:
    """Normalize a numeric pandas Series to a 0-100 scale."""
    series = pd.to_numeric(series, errors="coerce").fillna(0)
    min_val = series.min()
    max_val = series.max()

    if max_val == min_val:
        return pd.Series([50] * len(series), index=series.index)

    return ((series - min_val) / (max_val - min_val)) * 100


def ensure_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Convert selected columns to numeric, filling missing values with 0."""
    df = df.copy()
    for col in cols:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def add_missing_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Add any missing columns as 0 so the scoring model stays stable."""
    df = df.copy()
    for col in cols:
        if col not in df.columns:
            df[col] = 0
    return df


# --------------------------------------------------
# 3. Connect to database and pull base tables
# --------------------------------------------------

conn = sqlite3.connect(DB_PATH)

schools = pd.read_sql_query("SELECT * FROM schools;", conn)
print("\nSchools columns available:")
print(schools.columns.tolist())

national_titles = pd.read_sql_query(
    """
    SELECT
        school_id,
        COUNT(*) AS national_titles
    FROM football_national_championships
    GROUP BY school_id;
    """,
    conn,
)

conference_titles = pd.read_sql_query(
    """
    SELECT
        school_id,
        COUNT(*) AS conference_titles
    FROM football_conference_championships
    GROUP BY school_id;
    """,
    conn,
)

coach_records = pd.read_sql_query(
    """
    SELECT
        school_id,
        SUM(wins) AS coach_wins,
        SUM(losses) AS coach_losses,
        ROUND(
            CAST(SUM(wins) AS FLOAT) /
            NULLIF(SUM(wins) + SUM(losses), 0),
            3
        ) AS current_coach_win_pct
    FROM football_coach_season_records
    GROUP BY school_id;
    """,
    conn,
)

head_to_head = pd.read_sql_query(
    """
    SELECT
        school_id,
        COUNT(CASE WHEN win_pct > 0.500 THEN 1 END) AS winning_series_count,
        ROUND(AVG(win_pct), 3) AS avg_head_to_head_win_pct
    FROM football_alltime_series_records_clean
    GROUP BY school_id;
    """,
    conn,
)

conn.close()

# --------------------------------------------------
# 4. Merge component data
# --------------------------------------------------

power = schools.merge(national_titles, on="school_id", how="left")
power = power.merge(conference_titles, on="school_id", how="left")
power = power.merge(coach_records, on="school_id", how="left")
power = power.merge(head_to_head, on="school_id", how="left")

# Keep model stable even when some source columns are not present in schools
required_model_cols = [
    "national_titles",
    "conference_titles",
    "coach_wins",
    "coach_losses",
    "current_coach_win_pct",
    "winning_series_count",
    "avg_head_to_head_win_pct",
    "fb_head_coach_salary",
    "total_fb_expenses",
    "ath_dept_budget",
    "media_total_minutes_watched",
    "social_media_total_annual_impressions",
    "alltime_wins",
]

power = add_missing_columns(power, required_model_cols)
power = ensure_numeric(power, required_model_cols)

print("\nRaw Program Power Index input data:")
print(power.head())

# --------------------------------------------------
# 5. Create component scores
# --------------------------------------------------

# History components
power["national_title_score"] = normalize_0_100(power["national_titles"])
power["conference_title_score"] = normalize_0_100(power["conference_titles"])
power["alltime_wins_score"] = normalize_0_100(power["alltime_wins"])

power["history_score"] = (
    0.45 * power["national_title_score"] +
    0.35 * power["conference_title_score"] +
    0.20 * power["alltime_wins_score"]
)

# Competitive components
power["coach_score"] = normalize_0_100(power["current_coach_win_pct"])
power["h2h_score"] = normalize_0_100(power["avg_head_to_head_win_pct"])
power["winning_series_score"] = normalize_0_100(power["winning_series_count"])

power["competitive_score"] = (
    0.45 * power["coach_score"] +
    0.35 * power["h2h_score"] +
    0.20 * power["winning_series_score"]
)

# Resource / brand components based on columns available in Football_Program_Data.csv
power["salary_score"] = normalize_0_100(power["fb_head_coach_salary"])
power["football_expense_score"] = normalize_0_100(power["total_fb_expenses"])
power["ath_dept_budget_score"] = normalize_0_100(power["ath_dept_budget"])
power["media_score"] = normalize_0_100(power["media_total_minutes_watched"])
power["social_score"] = normalize_0_100(power["social_media_total_annual_impressions"])

power["resource_score"] = (
    0.30 * power["salary_score"] +
    0.25 * power["football_expense_score"] +
    0.20 * power["ath_dept_budget_score"] +
    0.15 * power["media_score"] +
    0.10 * power["social_score"]
)

# --------------------------------------------------
# 6. Final Program Power Index
# --------------------------------------------------

power["program_power_index"] = (
    0.40 * power["history_score"] +
    0.35 * power["competitive_score"] +
    0.25 * power["resource_score"]
).round(1)

# --------------------------------------------------
# 7. Assign program archetypes
# --------------------------------------------------

def assign_archetype(row):
    history = row["history_score"]
    competitive = row["competitive_score"]
    resources = row["resource_score"]
    power_index = row["program_power_index"]

    # Elite across history/current performance
    if power_index >= 80 and history >= 70 and competitive >= 70:
        return "Dynasty Engine"

    # Historic brand power, even if current performance is uneven
    if history >= 70 and competitive < 70:
        return "Legacy Power"

    # Wins above its resource base
    if competitive >= 70 and resources < 50:
        return "Culture Power"

    # Strong overall program, not quite dynasty/legacy level
    if power_index >= 60 and competitive >= 60:
        return "Established Contender"

    # Big resources/market/profile, weaker competitive return
    if resources >= 60 and competitive < 60:
        return "Resource-Backed Underachiever"

    # Lower history but current performance is improving/solid
    if history < 45 and competitive >= 55:
        return "Rising Program"

    # Some strength, but uneven profile across history/resources/competition
    if power_index >= 40:
        return "Volatile Talent Program"

    # Low current index; likely needs rebuilding or deeper development
    return "Development / Rebuild Program"


power["program_archetype"] = power.apply(assign_archetype, axis=1)

# --------------------------------------------------
# 8. Final table
# --------------------------------------------------

final_cols = [
    "school_id",
    "school",
    "fb_head_coach",
    "national_titles",
    "conference_titles",
    "alltime_wins",
    "coach_wins",
    "coach_losses",
    "current_coach_win_pct",
    "winning_series_count",
    "avg_head_to_head_win_pct",
    "fb_head_coach_salary",
    "total_fb_expenses",
    "ath_dept_budget",
    "media_total_minutes_watched",
    "social_media_total_annual_impressions",
    "history_score",
    "competitive_score",
    "resource_score",
    "program_power_index",
    "program_archetype",
]

# Keep only columns that exist in the current database output
final_cols = [col for col in final_cols if col in power.columns]

power_final = power[final_cols].copy()

# Round score columns for readability
score_cols = ["history_score", "competitive_score", "resource_score", "program_power_index"]
for col in score_cols:
    if col in power_final.columns:
        power_final[col] = power_final[col].round(1)

power_final = power_final.sort_values(
    by="program_power_index",
    ascending=False
).reset_index(drop=True)

power_final.insert(0, "power_rank", range(1, len(power_final) + 1))

print("\nAlliance Program Power Index:")
print(power_final)

# --------------------------------------------------
# 9. Export outputs
# --------------------------------------------------

output_file = OUTPUT_DIR / "alliance_program_power_index.csv"
power_final.to_csv(output_file, index=False)

print(f"\nProgram Power Index exported to: {output_file}")
