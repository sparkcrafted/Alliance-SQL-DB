from pathlib import Path
import pandas as pd
import sqlite3
import re

# --------------------------------------------------
# 08_build_talent_catchments.py
# --------------------------------------------------
# Purpose:
# Build the first version of the Alliance talent-access model.
#
# This script does NOT simulate commitments yet. It defines each Alliance
# school's plausible elite-player talent universe using:
#   - player rankings / consensus records
#   - school admissions policy
#   - same-state rules
#   - out-of-district flexibility
#   - cross-state relocation / regional-gravity logic
#
# Output SQLite tables:
#   - player_alliance_school_matches
#   - alliance_school_talent_access_summary
#
# Output CSV files:
#   - Outputs/player_alliance_school_matches.csv
#   - Outputs/alliance_school_talent_access_summary.csv
# --------------------------------------------------

# --------------------------------------------------
# 1. Set project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "Database" / "alliance.db"
OUTPUT_DIR = PROJECT_ROOT / "Outputs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Project root:", PROJECT_ROOT)
print("Database path:", DB_PATH)
print("Output folder:", OUTPUT_DIR)

if not DB_PATH.exists():
    raise FileNotFoundError(
        f"Could not find database at: {DB_PATH}\n"
        "Run the database build/import scripts first."
    )


# --------------------------------------------------
# 2. Helper functions
# --------------------------------------------------

def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    result = pd.read_sql_query(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?;
        """,
        conn,
        params=(table_name,),
    )
    return not result.empty


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    info = pd.read_sql_query(f"PRAGMA table_info({table_name});", conn)
    return info["name"].tolist()


def read_table(conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    if not table_exists(conn, table_name):
        raise ValueError(f"Required table missing from alliance.db: {table_name}")
    return pd.read_sql_query(f"SELECT * FROM {table_name};", conn)


def clean_text(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value if value != "" else None


def normalize_key(value):
    """Lowercase alphanumeric key for fuzzy equality checks."""
    if pd.isna(value):
        return ""
    value = str(value).lower().strip()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def extract_state_from_school(school_name):
    """Extract two-letter state abbreviation from names like City College (MD)."""
    if pd.isna(school_name):
        return None
    match = re.search(r"\(([A-Z]{2})\)", str(school_name))
    return match.group(1) if match else None


def first_existing_column(df: pd.DataFrame, candidates: list[str]):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def to_numeric_safe(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def clean_bool_to_int(value):
    if pd.isna(value):
        return 0
    value = str(value).strip().lower()
    if value in ["1", "true", "yes", "y"]:
        return 1
    if value in ["0", "false", "no", "n"]:
        return 0
    return 0


def rank_tier_from_best_rank(best_rank):
    if pd.isna(best_rank):
        return "Unranked/Unknown"
    try:
        rank = float(best_rank)
    except Exception:
        return "Unranked/Unknown"

    if rank <= 25:
        return "Top 25"
    if rank <= 50:
        return "Top 50"
    if rank <= 100:
        return "Top 100"
    if rank <= 150:
        return "Top 150"
    if rank <= 300:
        return "Top 300"
    return "Ranked Outside Top 300"


def talent_quality_score_from_rank(best_rank):
    """Simple rank-based talent score, intentionally transparent."""
    tier = rank_tier_from_best_rank(best_rank)
    score_map = {
        "Top 25": 100,
        "Top 50": 90,
        "Top 100": 80,
        "Top 150": 70,
        "Top 300": 60,
        "Ranked Outside Top 300": 40,
        "Unranked/Unknown": 25,
    }
    return score_map.get(tier, 25)


# Regional visibility map for cross-state gravity.
# This does NOT create normal eligibility. It only flags nearby/adjacent-state talent
# that may be visible to a program but would require relocation or another legal path.
REGIONAL_STATE_MAP = {
    "MD": ["DC", "VA", "PA", "DE", "WV"],
    "DC": ["MD", "VA"],
    "VA": ["MD", "DC", "WV", "NC"],
    "PA": ["NJ", "DE", "MD", "NY", "OH", "WV"],
    "NJ": ["NY", "PA", "DE", "CT"],
    "NY": ["NJ", "PA", "CT"],
    "WV": ["OH", "PA", "MD", "VA", "KY"],
    "OH": ["PA", "WV", "KY", "IN", "MI"],
    "MI": ["OH", "IN", "IL", "WI"],
    "IL": ["MO", "IN", "WI", "IA", "KY", "MI"],
    "IN": ["IL", "OH", "KY", "MI"],
    "KY": ["OH", "IN", "IL", "WV", "TN", "MO"],
    "DE": ["PA", "MD", "NJ"],
}


def is_regional_state(school_state, player_state):
    if pd.isna(school_state) or pd.isna(player_state):
        return 0
    return int(str(player_state).upper() in REGIONAL_STATE_MAP.get(str(school_state).upper(), []))


def classify_match(row):
    """Create eligibility and gravity logic for one player-school pairing."""
    same_state = row["same_state"] == 1
    regional_state = row["regional_state"] == 1
    direct_school_match = row["direct_school_match"] == 1
    can_ood = row["can_accept_out_of_district_students"] == 1
    cross_state_allowed = row["can_cross_state_boundary"] == 1
    scope = str(row.get("out_of_district_scope", "") or "").lower()

    # Direct school match is highest-confidence access.
    if direct_school_match:
        return pd.Series({
            "eligibility_tier": "Direct Alliance School Match",
            "match_type": "Direct school match",
            "eligibility_score": 100,
            "regional_gravity_score": 100,
            "normal_catchment_flag": 1,
            "requires_relocation": 0,
            "cross_state_blocked": 0,
        })

    # Same-state logic.
    if same_state:
        if can_ood:
            if "statewide" in scope:
                tier = "Approved Out-of-District: Statewide"
                score = 90
            elif scope not in ["", "n/a", "na", "none"]:
                tier = "Approved Out-of-District: Defined Scope"
                score = 80
            else:
                tier = "Out-of-District Allowed: Scope Needs Review"
                score = 70

            return pd.Series({
                "eligibility_tier": tier,
                "match_type": "Same-state approved access",
                "eligibility_score": score,
                "regional_gravity_score": score,
                "normal_catchment_flag": 1,
                "requires_relocation": 0,
                "cross_state_blocked": 0,
            })

        # Same state, but no out-of-district pathway. We can see the talent,
        # but cannot confirm normal eligibility without county/city/district location.
        return pd.Series({
            "eligibility_tier": "Same-State Visibility / Residency Not Verified",
            "match_type": "Same-state visibility only",
            "eligibility_score": 35,
            "regional_gravity_score": 35,
            "normal_catchment_flag": 0,
            "requires_relocation": 1,
            "cross_state_blocked": 0,
        })

    # Cross-state logic.
    if not same_state:
        if cross_state_allowed:
            return pd.Series({
                "eligibility_tier": "Cross-State Allowed by Policy",
                "match_type": "Cross-state policy access",
                "eligibility_score": 60,
                "regional_gravity_score": 60,
                "normal_catchment_flag": 1,
                "requires_relocation": 0,
                "cross_state_blocked": 0,
            })

        if regional_state:
            return pd.Series({
                "eligibility_tier": "Cross-State Relocation Candidate",
                "match_type": "Regional visibility only",
                "eligibility_score": 10,
                "regional_gravity_score": 20,
                "normal_catchment_flag": 0,
                "requires_relocation": 1,
                "cross_state_blocked": 1,
            })

    return pd.Series({
        "eligibility_tier": "Outside Talent Universe",
        "match_type": "No plausible current access",
        "eligibility_score": 0,
        "regional_gravity_score": 0,
        "normal_catchment_flag": 0,
        "requires_relocation": 1,
        "cross_state_blocked": 1,
    })


# --------------------------------------------------
# 3. Connect to SQLite and verify required tables
# --------------------------------------------------

conn = sqlite3.connect(DB_PATH)

required_tables = [
    "players",
    "player_source_consensus",
    "alliance_school_admissions_policy",
]

print("\nChecking required tables...")
for table in required_tables:
    if not table_exists(conn, table):
        existing = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name;",
            conn,
        )
        print("\nExisting tables:")
        print(existing)
        raise ValueError(
            f"Required table missing: {table}. "
            "Run the player rankings and admissions policy import scripts first."
        )
    print(f"Found table: {table}")

players = read_table(conn, "players")
consensus = read_table(conn, "player_source_consensus")
policy = read_table(conn, "alliance_school_admissions_policy")

print("\nLoaded source tables:")
print("players:", players.shape)
print("player_source_consensus:", consensus.shape)
print("alliance_school_admissions_policy:", policy.shape)

print("\nplayers columns:")
print(players.columns.tolist())

print("\nplayer_source_consensus columns:")
print(consensus.columns.tolist())

print("\nalliance_school_admissions_policy columns:")
print(policy.columns.tolist())


# --------------------------------------------------
# 4. Standardize player/consensus data
# --------------------------------------------------

# Ensure player_id exists in both core tables.
if "player_id" not in players.columns:
    raise ValueError("players table must contain player_id.")

if "player_id" not in consensus.columns:
    raise ValueError("player_source_consensus table must contain player_id.")

# Merge consensus with players so we get the richest available player profile.
player_base = consensus.merge(
    players,
    on="player_id",
    how="left",
    suffixes=("_consensus", "_players"),
)

# Resolve common columns from either consensus or players.
player_name_col = first_existing_column(
    player_base,
    ["player_name_consensus", "player_name", "name_consensus", "name", "player_name_players", "name_players"],
)
position_col = first_existing_column(
    player_base,
    ["position_group_consensus", "position_group", "position_consensus", "position", "pos", "position_players"],
)
high_school_col = first_existing_column(
    player_base,
    ["high_school_consensus", "high_school", "school_consensus", "high_school_players", "school_players"],
)
home_state_col = first_existing_column(
    player_base,
    ["home_state_consensus", "home_state", "hometown_state", "state_consensus", "state", "home_state_players", "state_players"],
)
best_rank_col = first_existing_column(
    player_base,
    ["best_rank", "best_national_rank", "national_rank", "rank"],
)
avg_rank_col = first_existing_column(
    player_base,
    ["avg_rank", "average_rank", "mean_rank"],
)
sources_count_col = first_existing_column(
    player_base,
    ["sources_count", "source_count", "ranking_sources_count"],
)
consensus_tier_col = first_existing_column(
    player_base,
    ["consensus_tier", "rank_tier", "tier"],
)
consensus_score_col = first_existing_column(
    player_base,
    ["consensus_score", "talent_score", "rating_score"],
)

standard_players = pd.DataFrame()
standard_players["player_id"] = player_base["player_id"]
standard_players["player_name"] = player_base[player_name_col].apply(clean_text) if player_name_col else None
standard_players["position_group"] = player_base[position_col].apply(clean_text) if position_col else None
standard_players["high_school"] = player_base[high_school_col].apply(clean_text) if high_school_col else None
standard_players["home_state"] = player_base[home_state_col].apply(clean_text) if home_state_col else None
standard_players["best_rank"] = to_numeric_safe(player_base[best_rank_col]) if best_rank_col else pd.NA
standard_players["avg_rank"] = to_numeric_safe(player_base[avg_rank_col]) if avg_rank_col else pd.NA
standard_players["sources_count"] = to_numeric_safe(player_base[sources_count_col]) if sources_count_col else pd.NA
standard_players["consensus_tier"] = player_base[consensus_tier_col].apply(clean_text) if consensus_tier_col else None
standard_players["consensus_score"] = to_numeric_safe(player_base[consensus_score_col]) if consensus_score_col else pd.NA

# Clean state text.
standard_players["home_state"] = standard_players["home_state"].astype(str).str.strip().str.upper()
standard_players.loc[standard_players["home_state"].isin(["", "NAN", "NONE"]), "home_state"] = pd.NA

# Derived player variables.
standard_players["rank_tier"] = standard_players["best_rank"].apply(rank_tier_from_best_rank)
standard_players["talent_quality_score"] = standard_players["best_rank"].apply(talent_quality_score_from_rank)
standard_players["is_top_25"] = (standard_players["best_rank"] <= 25).astype(int)
standard_players["is_top_50"] = (standard_players["best_rank"] <= 50).astype(int)
standard_players["is_top_100"] = (standard_players["best_rank"] <= 100).astype(int)
standard_players["is_top_300"] = (standard_players["best_rank"] <= 300).astype(int)
standard_players["player_key"] = standard_players["player_name"].apply(normalize_key)
standard_players["high_school_key"] = standard_players["high_school"].apply(normalize_key)

# Remove duplicate player_id rows if the source accidentally duplicated after merge.
standard_players = standard_players.drop_duplicates(subset=["player_id"]).copy()

print("\nStandardized player profile preview:")
print(standard_players.head(10))
print("\nStandardized player rows:", len(standard_players))

missing_state_count = standard_players["home_state"].isna().sum()
print("\nPlayers missing home_state:", missing_state_count)


# --------------------------------------------------
# 5. Standardize admissions policy data
# --------------------------------------------------

required_policy_cols = [
    "school_id",
    "school",
    "normal_residency_area",
    "can_accept_out_of_district_students",
    "out_of_district_scope",
    "can_cross_state_boundary",
    "admissions_mechanism",
    "athlete_specific_or_general",
]

missing_policy_cols = [col for col in required_policy_cols if col not in policy.columns]
if missing_policy_cols:
    raise ValueError(
        f"Admissions policy table is missing required columns: {missing_policy_cols}\n"
        f"Available columns: {policy.columns.tolist()}"
    )

school_policy = policy[required_policy_cols].copy()
school_policy["school"] = school_policy["school"].astype(str).str.strip()
school_policy["school_state"] = school_policy["school"].apply(extract_state_from_school)
school_policy["school_key"] = school_policy["school"].apply(normalize_key)
school_policy["can_accept_out_of_district_students"] = school_policy[
    "can_accept_out_of_district_students"
].apply(clean_bool_to_int)
school_policy["can_cross_state_boundary"] = school_policy[
    "can_cross_state_boundary"
].apply(clean_bool_to_int)

# Derived school policy variables.
school_policy["out_of_district_allowed_flag"] = school_policy["can_accept_out_of_district_students"]
school_policy["cross_state_blocked_flag"] = school_policy["can_cross_state_boundary"].apply(lambda x: 0 if x == 1 else 1)
school_policy["admissions_policy_type"] = school_policy["can_accept_out_of_district_students"].apply(
    lambda x: "Open / Out-of-District" if x == 1 else "Residency Restricted"
)

if school_policy["school_state"].isna().any():
    print("\nWarning: Some schools are missing state abbreviations:")
    print(school_policy[school_policy["school_state"].isna()][["school"]])

print("\nStandardized admissions policy preview:")
print(school_policy.head(10))
print("\nAdmissions policy rows:", len(school_policy))


# --------------------------------------------------
# 6. Build player-school match universe
# --------------------------------------------------

# Cross join players to schools.
players_for_join = standard_players.copy()
schools_for_join = school_policy.copy()
players_for_join["_join_key"] = 1
schools_for_join["_join_key"] = 1

matches = players_for_join.merge(
    schools_for_join,
    on="_join_key",
    how="inner",
).drop(columns=["_join_key"])

matches["same_state"] = (
    matches["home_state"].astype(str).str.upper()
    == matches["school_state"].astype(str).str.upper()
).astype(int)

matches["regional_state"] = matches.apply(
    lambda row: is_regional_state(row["school_state"], row["home_state"]),
    axis=1,
)

matches["direct_school_match"] = (
    (matches["high_school_key"] != "")
    & (matches["high_school_key"] == matches["school_key"])
).astype(int)

classification = matches.apply(classify_match, axis=1)
matches = pd.concat([matches, classification], axis=1)

# Keep only useful talent-universe rows.
# This avoids storing all 28 x every-player combinations where there is no meaningful relationship.
matches = matches[
    (matches["same_state"] == 1)
    | (matches["regional_state"] == 1)
    | (matches["direct_school_match"] == 1)
].copy()

# Add overall fit score. This is NOT a commitment probability. It is a
# transparent first-pass indicator of plausible access + talent quality.
matches["school_talent_fit_score"] = (
    0.65 * matches["eligibility_score"]
    + 0.25 * matches["regional_gravity_score"]
    + 0.10 * matches["talent_quality_score"]
).round(1)

# Add final IDs and reorder fields.
matches = matches.sort_values(
    by=["school", "home_state", "best_rank", "player_name"],
    ascending=[True, True, True, True],
).reset_index(drop=True)

matches.insert(0, "match_id", range(1, len(matches) + 1))

match_cols = [
    "match_id",
    "player_id",
    "player_name",
    "position_group",
    "high_school",
    "home_state",
    "best_rank",
    "avg_rank",
    "sources_count",
    "consensus_tier",
    "rank_tier",
    "talent_quality_score",
    "is_top_25",
    "is_top_50",
    "is_top_100",
    "is_top_300",
    "school_id",
    "school",
    "school_state",
    "normal_residency_area",
    "can_accept_out_of_district_students",
    "out_of_district_scope",
    "can_cross_state_boundary",
    "admissions_mechanism",
    "athlete_specific_or_general",
    "same_state",
    "regional_state",
    "direct_school_match",
    "eligibility_tier",
    "match_type",
    "eligibility_score",
    "regional_gravity_score",
    "normal_catchment_flag",
    "requires_relocation",
    "cross_state_blocked",
    "school_talent_fit_score",
]

# Only keep columns that exist, in case optional columns were unavailable.
match_cols = [col for col in match_cols if col in matches.columns]
matches_final = matches[match_cols].copy()

print("\nPlayer-school talent universe preview:")
print(matches_final.head(25))
print("\nTalent universe rows:", len(matches_final))


# --------------------------------------------------
# 7. Build school-level talent access summary
# --------------------------------------------------

def count_condition(series):
    return int(series.sum())

summary_rows = []

for _, school_row in school_policy.sort_values("school").iterrows():
    school_id = school_row["school_id"]
    school_name = school_row["school"]
    school_matches = matches_final[matches_final["school_id"] == school_id].copy()
    strict = school_matches[school_matches["normal_catchment_flag"] == 1].copy()
    same_state_visibility = school_matches[
        (school_matches["same_state"] == 1)
        & (school_matches["normal_catchment_flag"] == 0)
    ].copy()
    regional = school_matches[
        (school_matches["regional_state"] == 1)
        & (school_matches["same_state"] == 0)
    ].copy()
    relocation = school_matches[school_matches["requires_relocation"] == 1].copy()

    position_groups = strict["position_group"].dropna().nunique() if "position_group" in strict.columns else 0

    summary_rows.append({
        "school_id": school_id,
        "school": school_name,
        "school_state": school_row["school_state"],
        "normal_residency_area": school_row["normal_residency_area"],
        "admissions_policy_type": school_row["admissions_policy_type"],
        "can_accept_out_of_district_students": school_row["can_accept_out_of_district_students"],
        "out_of_district_scope": school_row["out_of_district_scope"],
        "can_cross_state_boundary": school_row["can_cross_state_boundary"],
        "strict_access_players": len(strict),
        "strict_top_25": int(strict["is_top_25"].sum()) if not strict.empty else 0,
        "strict_top_50": int(strict["is_top_50"].sum()) if not strict.empty else 0,
        "strict_top_100": int(strict["is_top_100"].sum()) if not strict.empty else 0,
        "strict_top_300": int(strict["is_top_300"].sum()) if not strict.empty else 0,
        "same_state_visibility_players": len(same_state_visibility),
        "regional_gravity_players": len(regional),
        "regional_top_100": int(regional["is_top_100"].sum()) if not regional.empty else 0,
        "regional_top_300": int(regional["is_top_300"].sum()) if not regional.empty else 0,
        "relocation_candidate_players": len(relocation),
        "avg_talent_quality_strict": round(strict["talent_quality_score"].mean(), 2) if not strict.empty else 0,
        "avg_talent_quality_regional": round(regional["talent_quality_score"].mean(), 2) if not regional.empty else 0,
        "position_groups_strict": int(position_groups),
    })

school_summary = pd.DataFrame(summary_rows)

# Composite scores. These are first-pass and intentionally simple.
# They can be tuned later once geography/distance and program needs are added.
for col in [
    "strict_access_players",
    "strict_top_100",
    "strict_top_300",
    "regional_gravity_players",
    "regional_top_100",
    "regional_top_300",
    "avg_talent_quality_strict",
    "position_groups_strict",
]:
    school_summary[col] = pd.to_numeric(school_summary[col], errors="coerce").fillna(0)


def normalize_0_100(series: pd.Series) -> pd.Series:
    min_val = series.min()
    max_val = series.max()
    if max_val == min_val:
        return pd.Series([50] * len(series), index=series.index)
    return ((series - min_val) / (max_val - min_val)) * 100

school_summary["strict_volume_score"] = normalize_0_100(school_summary["strict_access_players"])
school_summary["strict_elite_score"] = normalize_0_100(
    2 * school_summary["strict_top_100"] + school_summary["strict_top_300"]
)
school_summary["strict_quality_score"] = normalize_0_100(school_summary["avg_talent_quality_strict"])
school_summary["strict_position_diversity_score"] = normalize_0_100(school_summary["position_groups_strict"])

school_summary["talent_access_score"] = (
    0.35 * school_summary["strict_volume_score"]
    + 0.35 * school_summary["strict_elite_score"]
    + 0.20 * school_summary["strict_quality_score"]
    + 0.10 * school_summary["strict_position_diversity_score"]
).round(1)

school_summary["regional_gravity_score"] = normalize_0_100(
    2 * school_summary["regional_top_100"]
    + school_summary["regional_top_300"]
    + 0.25 * school_summary["regional_gravity_players"]
).round(1)

school_summary = school_summary.sort_values(
    by=["talent_access_score", "strict_top_100", "strict_top_300"],
    ascending=[False, False, False],
).reset_index(drop=True)

school_summary.insert(0, "talent_access_rank", range(1, len(school_summary) + 1))

print("\nAlliance school talent access summary:")
print(school_summary)


# --------------------------------------------------
# 8. Save outputs to SQLite and CSV
# --------------------------------------------------

matches_final.to_sql(
    "player_alliance_school_matches",
    conn,
    if_exists="replace",
    index=False,
)

school_summary.to_sql(
    "alliance_school_talent_access_summary",
    conn,
    if_exists="replace",
    index=False,
)

matches_output = OUTPUT_DIR / "player_alliance_school_matches.csv"
summary_output = OUTPUT_DIR / "alliance_school_talent_access_summary.csv"

matches_final.to_csv(matches_output, index=False)
school_summary.to_csv(summary_output, index=False)

print("\nSaved SQLite tables:")
print("- player_alliance_school_matches")
print("- alliance_school_talent_access_summary")

print("\nSaved CSV outputs:")
print("-", matches_output)
print("-", summary_output)


# --------------------------------------------------
# 9. Validation queries
# --------------------------------------------------

validation_queries = {
    "Player-school matches": """
        SELECT COUNT(*) AS match_rows
        FROM player_alliance_school_matches;
    """,
    "Talent access summary rows": """
        SELECT COUNT(*) AS school_rows
        FROM alliance_school_talent_access_summary;
    """,
    "Top talent access schools": """
        SELECT
            talent_access_rank,
            school,
            school_state,
            admissions_policy_type,
            strict_access_players,
            strict_top_100,
            strict_top_300,
            regional_gravity_players,
            talent_access_score,
            regional_gravity_score
        FROM alliance_school_talent_access_summary
        ORDER BY talent_access_rank
        LIMIT 15;
    """,
    "Eligibility tier distribution": """
        SELECT
            eligibility_tier,
            COUNT(*) AS matches
        FROM player_alliance_school_matches
        GROUP BY eligibility_tier
        ORDER BY matches DESC;
    """,
}

for label, query in validation_queries.items():
    print(f"\n{label}:")
    print(pd.read_sql_query(query, conn))

conn.close()

print("\nTalent catchment build complete.")

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(r"C:\Users\Warren Jones\OneDrive\Desktop\Alliance-SQL-DB\Database\alliance.db")

conn = sqlite3.connect(DB_PATH)

columns = pd.read_sql_query(
    "PRAGMA table_info(alliance_school_talent_access_summary);",
    conn
)

print(columns[["name", "type"]])

conn.close()

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(r"C:\Users\Warren Jones\OneDrive\Desktop\Alliance-SQL-DB\Database\alliance.db")

conn = sqlite3.connect(DB_PATH)

query = """
SELECT *
FROM alliance_school_talent_access_summary
LIMIT 10;
"""

result = pd.read_sql_query(query, conn)
print(result)

conn.close()

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(r"C:\Users\Warren Jones\OneDrive\Desktop\Alliance-SQL-DB\Database\alliance.db")

conn = sqlite3.connect(DB_PATH)

query = """
SELECT *
FROM alliance_school_talent_access_summary;
"""

summary = pd.read_sql_query(query, conn)

print(summary.columns.tolist())
print(summary.head(20))

conn.close()