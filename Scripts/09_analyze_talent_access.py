from pathlib import Path
import pandas as pd
import sqlite3

# --------------------------------------------------
# 1. Paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "Database" / "alliance.db"
OUTPUT_DIR = PROJECT_ROOT / "Outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Database path:", DB_PATH)
print("Output folder:", OUTPUT_DIR)

conn = sqlite3.connect(DB_PATH)

# --------------------------------------------------
# 2. Inspect actual table columns
# --------------------------------------------------

for table in ["player_alliance_school_matches", "alliance_school_talent_access_summary", "player_source_consensus"]:
    print(f"\nColumns in {table}:")
    cols = pd.read_sql_query(f"PRAGMA table_info({table});", conn)
    print(cols[["name", "type"]])

# --------------------------------------------------
# 3. Load match table
# --------------------------------------------------

matches = pd.read_sql_query(
    "SELECT * FROM player_alliance_school_matches;",
    conn
)

print("\nMatch table shape:", matches.shape)
print(matches.head())

# --------------------------------------------------
# 4. Standardize key numeric columns
# --------------------------------------------------

numeric_candidates = [
    "best_rank",
    "avg_rank",
    "consensus_score",
    "eligibility_score",
    "regional_gravity_score",
]

for col in numeric_candidates:
    if col in matches.columns:
        matches[col] = pd.to_numeric(matches[col], errors="coerce")

# --------------------------------------------------
# 5. Create rank tier flags
# --------------------------------------------------

if "best_rank" not in matches.columns:
    raise ValueError("The match table does not include best_rank. We need to join player_source_consensus into the match table.")

matches["is_top_25"] = matches["best_rank"] <= 25
matches["is_top_50"] = matches["best_rank"] <= 50
matches["is_top_100"] = matches["best_rank"] <= 100
matches["is_top_300"] = matches["best_rank"] <= 300

# Strict access means real eligibility/catchment, not merely regional gravity
strict_tiers = [
    "Direct Alliance School Match",
    "Approved Out-of-District: Statewide",
    "Approved Out-of-District: Defined Scope",
    "Core Residency",
]

if "eligibility_tier" in matches.columns:
    matches["strict_access_flag"] = matches["eligibility_tier"].isin(strict_tiers)
else:
    matches["strict_access_flag"] = matches.get("eligibility_score", 0) >= 50

# Regional access includes visible/relocation candidates
matches["regional_access_flag"] = matches.get("regional_gravity_score", 0) > 0

# --------------------------------------------------
# 6. School-level talent access summary
# --------------------------------------------------

group_cols = ["school_id", "school"]

school_summary = (
    matches
    .groupby(group_cols)
    .agg(
        total_player_matches=("player_id", "count"),
        strict_player_matches=("strict_access_flag", "sum"),
        regional_player_matches=("regional_access_flag", "sum"),

        strict_top_25=("is_top_25", lambda x: int((x & matches.loc[x.index, "strict_access_flag"]).sum())),
        strict_top_50=("is_top_50", lambda x: int((x & matches.loc[x.index, "strict_access_flag"]).sum())),
        strict_top_100=("is_top_100", lambda x: int((x & matches.loc[x.index, "strict_access_flag"]).sum())),
        strict_top_300=("is_top_300", lambda x: int((x & matches.loc[x.index, "strict_access_flag"]).sum())),

        regional_top_25=("is_top_25", lambda x: int((x & matches.loc[x.index, "regional_access_flag"]).sum())),
        regional_top_50=("is_top_50", lambda x: int((x & matches.loc[x.index, "regional_access_flag"]).sum())),
        regional_top_100=("is_top_100", lambda x: int((x & matches.loc[x.index, "regional_access_flag"]).sum())),
        regional_top_300=("is_top_300", lambda x: int((x & matches.loc[x.index, "regional_access_flag"]).sum())),

        avg_best_rank=("best_rank", "mean"),
        best_available_rank=("best_rank", "min"),
    )
    .reset_index()
)

# --------------------------------------------------
# 7. Create simple talent access scores
# --------------------------------------------------

school_summary["strict_talent_score"] = (
    10 * school_summary["strict_top_25"] +
    7 * school_summary["strict_top_50"] +
    4 * school_summary["strict_top_100"] +
    1 * school_summary["strict_top_300"]
)

school_summary["regional_gravity_score"] = (
    10 * school_summary["regional_top_25"] +
    7 * school_summary["regional_top_50"] +
    4 * school_summary["regional_top_100"] +
    1 * school_summary["regional_top_300"]
)

school_summary["talent_access_gap"] = (
    school_summary["regional_gravity_score"] - school_summary["strict_talent_score"]
)

school_summary = school_summary.sort_values(
    by=["strict_talent_score", "regional_gravity_score", "strict_top_100"],
    ascending=False
).reset_index(drop=True)

school_summary.insert(0, "talent_access_rank", range(1, len(school_summary) + 1))

# --------------------------------------------------
# 8. Print helpful outputs
# --------------------------------------------------

print("\nAlliance Talent Access Ranking:")
print(
    school_summary[
        [
            "talent_access_rank",
            "school",
            "strict_talent_score",
            "regional_gravity_score",
            "strict_top_25",
            "strict_top_50",
            "strict_top_100",
            "strict_top_300",
            "regional_top_100",
            "regional_top_300",
            "best_available_rank",
        ]
    ]
)

print("\nSchools with strongest strict access to elite talent:")
print(
    school_summary[
        [
            "school",
            "strict_top_25",
            "strict_top_50",
            "strict_top_100",
            "strict_top_300",
            "strict_talent_score",
        ]
    ].head(15)
)

print("\nSchools with strongest regional gravity beyond strict access:")
print(
    school_summary[
        [
            "school",
            "strict_talent_score",
            "regional_gravity_score",
            "talent_access_gap",
            "regional_top_100",
            "regional_top_300",
        ]
    ].sort_values("talent_access_gap", ascending=False).head(15)
)

# --------------------------------------------------
# 9. Best players by school access
# --------------------------------------------------

best_players_by_school = (
    matches[
        matches["strict_access_flag"] &
        matches["is_top_100"]
    ]
    .sort_values(["school", "best_rank"])
)

print("\nTop 100 players in strict school talent universes:")
print(
    best_players_by_school[
        [
            "school",
            "player_name",
            "best_rank",
            "avg_rank",
            "consensus_tier",
            "home_state",
            "high_school",
            "eligibility_tier",
        ]
    ].head(100)
)

# --------------------------------------------------
# 10. Export outputs
# --------------------------------------------------

summary_path = OUTPUT_DIR / "alliance_talent_access_ranking.csv"
players_path = OUTPUT_DIR / "top_players_by_alliance_school_access.csv"

school_summary.to_csv(summary_path, index=False)
best_players_by_school.to_csv(players_path, index=False)

print(f"\nExported school talent ranking to: {summary_path}")
print(f"Exported top player access table to: {players_path}")

conn.close()

print("\nTalent access analysis complete.")

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(r"C:\Users\Warren Jones\OneDrive\Desktop\Alliance-SQL-DB\Database\alliance.db")

conn = sqlite3.connect(DB_PATH)

query = """
SELECT
    school,
    school_state,
    player_name,
    high_school,
    home_state,
    eligibility_tier,
    match_type,
    normal_catchment_flag,
    requires_relocation,
    cross_state_blocked,
    eligibility_score,
    regional_gravity_score
FROM player_alliance_school_matches
WHERE normal_catchment_flag = 1
  AND school_state <> home_state
ORDER BY school, home_state, player_name;
"""

bad_matches = pd.read_sql_query(query, conn)
print(bad_matches)

conn.close()