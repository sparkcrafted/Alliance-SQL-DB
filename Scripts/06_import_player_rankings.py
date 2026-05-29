from pathlib import Path
import pandas as pd
import sqlite3

# --------------------------------------------------
# 1. Set project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "Data" / "Raw"
DB_DIR = PROJECT_ROOT / "Database"
OUTPUT_DIR = PROJECT_ROOT / "Outputs"

DB_PATH = DB_DIR / "alliance.db"
PLAYER_WORKBOOK = RAW_DIR / "Processed_Player_Rankings.xlsx"

print("Project root:", PROJECT_ROOT)
print("Player workbook:", PLAYER_WORKBOOK)
print("Database path:", DB_PATH)

if not PLAYER_WORKBOOK.exists():
    raise FileNotFoundError(f"Could not find workbook: {PLAYER_WORKBOOK}")

if not DB_PATH.exists():
    raise FileNotFoundError(f"Could not find database: {DB_PATH}")

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
        .str.replace("(", "", regex=False)
        .str.replace(")", "", regex=False)
    )
    return df


def show_table_count(conn: sqlite3.Connection, table_name: str) -> None:
    """Print row count for one SQLite table."""
    count = pd.read_sql_query(
        f"SELECT COUNT(*) AS row_count FROM {table_name};",
        conn
    )
    print(f"{table_name}: {count.loc[0, 'row_count']} rows")


def print_query(conn: sqlite3.Connection, label: str, query: str) -> pd.DataFrame:
    """Run a SQL query, print the result, and return it."""
    print(f"\n{label}:")
    result = pd.read_sql_query(query, conn)
    print(result)
    return result


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    """Return column names for a SQLite table."""
    info = pd.read_sql_query(f"PRAGMA table_info({table_name});", conn)
    return info["name"].tolist()


def select_existing_columns(conn: sqlite3.Connection, table_name: str, preferred_cols: list[str]) -> list[str]:
    """Return preferred columns that actually exist in a table."""
    existing_cols = get_table_columns(conn, table_name)
    return [col for col in preferred_cols if col in existing_cols]


# --------------------------------------------------
# 3. Load workbook sheets
# --------------------------------------------------

sheets_to_tables = {
    "ranking_sources": "ranking_sources",
    "players": "players",
    "player_rankings": "player_rankings",
    "player_source_consensus": "player_source_consensus",
    "data_quality_flags": "player_data_quality_flags",
    "state_summary": "player_state_summary",
    "position_summary": "player_position_summary",
}

excel_file = pd.ExcelFile(PLAYER_WORKBOOK)

print("\nWorkbook sheets found:")
print(excel_file.sheet_names)

missing_sheets = [
    sheet for sheet in sheets_to_tables
    if sheet not in excel_file.sheet_names
]

if missing_sheets:
    raise ValueError(f"Missing expected sheets: {missing_sheets}")

# --------------------------------------------------
# 4. Import workbook sheets into SQLite
# --------------------------------------------------

conn = sqlite3.connect(DB_PATH)

for sheet_name, table_name in sheets_to_tables.items():
    df = pd.read_excel(PLAYER_WORKBOOK, sheet_name=sheet_name)

    # Clean names and remove blank rows
    df = clean_column_names(df)
    df = df.dropna(how="all").copy()

    # Write to SQLite
    df.to_sql(table_name, conn, if_exists="replace", index=False)

    print(f"\nImported sheet '{sheet_name}' as table '{table_name}'")
    print("Columns:", df.columns.tolist())
    show_table_count(conn, table_name)

# --------------------------------------------------
# 5. Basic validation queries
# --------------------------------------------------

print("\nValidation: player tables loaded")

basic_validation_queries = {
    "Unique players": """
        SELECT COUNT(*) AS unique_players
        FROM players;
    """,
    "Ranking records": """
        SELECT COUNT(*) AS ranking_records
        FROM player_rankings;
    """,
    "Ranking sources": """
        SELECT COUNT(*) AS ranking_sources
        FROM ranking_sources;
    """,
    "Consensus records": """
        SELECT COUNT(*) AS consensus_records
        FROM player_source_consensus;
    """,
}

for label, query in basic_validation_queries.items():
    print_query(conn, label, query)

# --------------------------------------------------
# 6. Inspect table schemas
# --------------------------------------------------

player_related_tables = [
    "ranking_sources",
    "players",
    "player_rankings",
    "player_source_consensus",
    "player_data_quality_flags",
    "player_state_summary",
    "player_position_summary",
]

print("\nPlayer-related table schemas:")

for table_name in player_related_tables:
    columns = pd.read_sql_query(f"PRAGMA table_info({table_name});", conn)
    print(f"\n{table_name} columns:")
    print(columns[["name", "type"]])

# --------------------------------------------------
# 7. Flexible validation previews
# --------------------------------------------------
# These previews avoid hard-coding fields such as "position" that may not exist
# in every processed workbook version.

# Top consensus players
consensus_preferred_cols = [
    "player_id",
    "player_name",
    "position",
    "position_group",
    "primary_position",
    "high_school",
    "hometown",
    "home_state",
    "sources_count",
    "best_rank",
    "worst_rank",
    "avg_rank",
    "rank_spread",
    "consensus_score",
    "consensus_tier",
]

consensus_cols = select_existing_columns(
    conn,
    "player_source_consensus",
    consensus_preferred_cols,
)

if not consensus_cols:
    consensus_cols = ["*"]

if consensus_cols == ["*"]:
    top_consensus_query = """
        SELECT *
        FROM player_source_consensus
        ORDER BY best_rank ASC
        LIMIT 25;
    """
else:
    top_consensus_query = f"""
        SELECT {", ".join(consensus_cols)}
        FROM player_source_consensus
        ORDER BY best_rank ASC
        LIMIT 25;
    """

print_query(conn, "Top 25 consensus players", top_consensus_query)

# Top source ranking records
rankings_preferred_cols = [
    "ranking_id",
    "player_id",
    "source_id",
    "source_name",
    "player_name",
    "national_rank",
    "source_rating",
    "stars",
    "position",
    "position_group",
    "high_school",
    "home_state",
]

ranking_cols = select_existing_columns(
    conn,
    "player_rankings",
    rankings_preferred_cols,
)

if ranking_cols:
    order_col = "national_rank" if "national_rank" in ranking_cols else ranking_cols[0]
    top_rankings_query = f"""
        SELECT {", ".join(ranking_cols)}
        FROM player_rankings
        ORDER BY {order_col} ASC
        LIMIT 25;
    """
    print_query(conn, "Top 25 source ranking records", top_rankings_query)
else:
    print_query(
        conn,
        "Top 25 source ranking records",
        """
        SELECT *
        FROM player_rankings
        LIMIT 25;
        """
    )

# State summary
print_query(
    conn,
    "Player state summary",
    """
    SELECT *
    FROM player_state_summary
    LIMIT 25;
    """
)

# Position summary
print_query(
    conn,
    "Player position summary",
    """
    SELECT *
    FROM player_position_summary
    LIMIT 25;
    """
)

# Data quality flags
print_query(
    conn,
    "Sample player data quality flags",
    """
    SELECT *
    FROM player_data_quality_flags
    LIMIT 25;
    """
)

# --------------------------------------------------
# 8. Optional joined preview
# --------------------------------------------------
# This preview joins consensus back to players only when player_id exists in both.

players_cols = get_table_columns(conn, "players")
consensus_all_cols = get_table_columns(conn, "player_source_consensus")

if "player_id" in players_cols and "player_id" in consensus_all_cols:
    joined_preview_query = """
        SELECT
            c.*,
            p.player_name AS player_name_from_players
        FROM player_source_consensus AS c
        LEFT JOIN players AS p
            ON c.player_id = p.player_id
        ORDER BY c.best_rank ASC
        LIMIT 25;
    """

    print_query(conn, "Joined consensus/player preview", joined_preview_query)

# --------------------------------------------------
# 9. Confirm all player-related tables exist
# --------------------------------------------------

tables = pd.read_sql_query(
    """
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
      AND (
          name LIKE 'player_%'
          OR name = 'players'
          OR name = 'ranking_sources'
      )
    ORDER BY name;
    """,
    conn
)

print("\nPlayer-related tables now in alliance.db:")
print(tables)

# --------------------------------------------------
# 10. Final row-count audit
# --------------------------------------------------

print("\nFinal player-table row-count audit:")

for table_name in tables["name"].tolist():
    show_table_count(conn, table_name)

conn.close()

print("\nPlayer rankings import complete.")
