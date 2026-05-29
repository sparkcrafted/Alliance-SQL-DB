from pathlib import Path
import pandas as pd
import sqlite3
import re

# --------------------------------------------------
# 1. Set project paths
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "Data" / "Raw"
DB_DIR = PROJECT_ROOT / "Database"
DB_PATH = DB_DIR / "alliance.db"

print("Project root:", PROJECT_ROOT)
print("Raw folder:", RAW_DIR)
print("Database path:", DB_PATH)

if not DB_PATH.exists():
    raise FileNotFoundError(f"Could not find database: {DB_PATH}")

# --------------------------------------------------
# 2. Locate the admissions/enrollment workbook
# --------------------------------------------------

possible_names = [
    "High_School_Enrollment_Worksheet.xlsx",
    "High School Enrollment Worksheet.xlsx",
    "Alliance_School_Admissions_Policy.xlsx",
    "Alliance School Admissions Policy.xlsx",
]

POLICY_FILE = None

for name in possible_names:
    candidate = RAW_DIR / name
    if candidate.exists():
        POLICY_FILE = candidate
        break

if POLICY_FILE is None:
    candidates = []
    for file in RAW_DIR.glob("*.xlsx"):
        key = file.name.lower()
        if any(term in key for term in ["enrollment", "admission", "policy", "school"]):
            candidates.append(file)

    if candidates:
        POLICY_FILE = sorted(candidates)[0]
    else:
        available = sorted(file.name for file in RAW_DIR.glob("*"))
        raise FileNotFoundError(
            "Could not find an admissions/enrollment workbook.\n"
            "Files currently in Data/Raw:\n- " + "\n- ".join(available)
        )

print("Policy workbook found:", POLICY_FILE)

# --------------------------------------------------
# 3. Helpers
# --------------------------------------------------

def clean_column_name(value) -> str:
    """Clean one column name into SQL-friendly snake_case."""
    value = str(value).strip().lower()
    value = value.replace("&", "and")
    value = value.replace("/", "_")
    value = value.replace("-", "_")
    value = value.replace("%", "pct")
    value = value.replace(".", "")
    value = value.replace("(", "")
    value = value.replace(")", "")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [clean_column_name(col) for col in df.columns]
    return df


def clean_bool(value):
    """Convert Yes/No/TRUE/FALSE-style values to 1/0."""
    if pd.isna(value):
        return None

    value = str(value).strip().lower()

    if value in ["yes", "true", "1", "y"]:
        return 1
    if value in ["no", "false", "0", "n"]:
        return 0

    return None


def normalize_school_name(value):
    if pd.isna(value):
        return value
    value = str(value).strip()
    value = value.replace("Cincinatti", "Cincinnati")
    return value


def find_header_row(raw_df: pd.DataFrame) -> int:
    """
    Find the row containing the actual table headers.
    This handles workbooks with a title row above the table.
    """
    for idx, row in raw_df.iterrows():
        values = [clean_column_name(v) for v in row.tolist() if pd.notna(v)]
        row_text = " ".join(values)

        has_school = "school" in values or "school" in row_text
        has_residency = "normal_residency_area" in values or "residency" in row_text
        has_district = "can_accept_out_of_district_students" in values or "district" in row_text

        if has_school and (has_residency or has_district):
            return idx

    raise ValueError(
        "Could not detect a header row. Expected a row containing fields like "
        "School, normal_residency_area, or can_accept_out_of_district_students."
    )


def load_policy_sheet(workbook_path: Path) -> pd.DataFrame:
    """Load the best sheet from the workbook using header-row detection."""
    xls = pd.ExcelFile(workbook_path)
    print("\nWorkbook sheets found:")
    print(xls.sheet_names)

    best_df = None
    best_sheet = None
    best_score = -1
    best_header_row = None

    for sheet in xls.sheet_names:
        raw = pd.read_excel(workbook_path, sheet_name=sheet, header=None)
        raw = raw.dropna(how="all").dropna(axis=1, how="all")

        if raw.empty:
            continue

        try:
            header_row = find_header_row(raw)
        except ValueError:
            continue

        headers = raw.loc[header_row].tolist()
        data = raw.loc[header_row + 1:].copy()
        data.columns = headers
        data = data.dropna(how="all").copy()
        data = clean_column_names(data)

        score = 0
        for required_like in ["school", "normal_residency_area", "can_accept_out_of_district_students"]:
            if required_like in data.columns:
                score += 2
        score += min(len(data), 28)

        if score > best_score:
            best_score = score
            best_df = data
            best_sheet = sheet
            best_header_row = header_row

    if best_df is None:
        raise ValueError("No usable admissions/enrollment sheet found in workbook.")

    print(f"\nSelected sheet: {best_sheet}")
    print(f"Detected header row: {best_header_row + 1}")
    print("Detected columns:", best_df.columns.tolist())

    return best_df


def standardize_policy_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map common messy/wrapped workbook headers to the expected schema."""
    df = df.copy()

    alias_map = {
        "school": "school",
        "normal_residency_area": "normal_residency_area",
        "residency_area": "normal_residency_area",
        "normal_residency": "normal_residency_area",
        "can_accept_out_of_district_students": "can_accept_out_of_district_students",
        "out_of_district_students": "can_accept_out_of_district_students",
        "can_accept_out_of_district": "can_accept_out_of_district_students",
        "out_of_district_scope": "out_of_district_scope",
        "scope": "out_of_district_scope",
        "state_boundary_allowed": "can_cross_state_boundary",
        "state_boundary_allow_ed": "can_cross_state_boundary",
        "state_boundary_allow": "can_cross_state_boundary",
        "can_cross_state_boundary": "can_cross_state_boundary",
        "admissions_mechanism": "admissions_mechanism",
        "admission_mechanism": "admissions_mechanism",
        "athlete_specific_or_general": "athlete_specific_or_general",
        "athlete_specific_or_ge_neral": "athlete_specific_or_general",
        "athlete_specific_or_ge\nneral": "athlete_specific_or_general",
        "athlete_specific_or_ge neral": "athlete_specific_or_general",
    }

    renamed = {}
    for col in df.columns:
        cleaned = clean_column_name(col)
        if cleaned in alias_map:
            renamed[col] = alias_map[cleaned]
        else:
            # Catch Excel-wrapped/truncated versions of athlete_specific_or_general.
            compact = cleaned.replace("_", "")
            if "athlete" in compact and "general" in compact:
                renamed[col] = "athlete_specific_or_general"
            elif "state" in compact and "boundary" in compact:
                renamed[col] = "can_cross_state_boundary"

    df = df.rename(columns=renamed)
    return df

# --------------------------------------------------
# 4. Expanded 28-school ID map
# --------------------------------------------------

school_id_map = {
    "Bergen Central (NJ)": 2001,
    "Bluefield (WV)": 2002,
    "Brooklyn Tech (NY)": 2003,
    "Canton McKinley (OH)": 2004,
    "Carmel (IN)": 2005,
    "Cass Tech (MI)": 2006,
    "Central (PA)": 2007,
    "Central-Pittsburgh (PA)": 2008,
    "City College (MD)": 2009,
    "Colerain (OH)": 2010,
    "East St. Louis (IL)": 2011,
    "King (MI)": 2012,
    "Lincoln-Way East (IL)": 2013,
    "Male (KY)": 2014,
    "Massillon (OH)": 2015,
    "Moeller (OH)": 2016,
    "Mount Carmel (IL)": 2017,
    "Muskegon (MI)": 2018,
    "Oscar Smith (VA)": 2019,
    "Palumbo (PA)": 2020,
    "PG Poly (MD)": 2021,
    "Phoebus (VA)": 2022,
    "Ramsey (NJ)": 2023,
    "Steubenville (OH)": 2024,
    "Stuyvesant (NY)": 2025,
    "University (NJ)": 2026,
    "Washington Latin (DC)": 2027,
    "Wilmington Tech (DE)": 2028,
}

expected_schools = set(school_id_map.keys())

# --------------------------------------------------
# 5. Load, standardize, and validate policy table
# --------------------------------------------------

policy = load_policy_sheet(POLICY_FILE)
policy = standardize_policy_columns(policy)

required_cols = [
    "school",
    "normal_residency_area",
    "can_accept_out_of_district_students",
    "out_of_district_scope",
    "can_cross_state_boundary",
    "admissions_mechanism",
    "athlete_specific_or_general",
]

missing_required = [col for col in required_cols if col not in policy.columns]
if missing_required:
    raise ValueError(
        f"Missing required columns after cleanup: {missing_required}\n"
        f"Available columns: {policy.columns.tolist()}\n"
        "Check workbook headers or add an alias in standardize_policy_columns()."
    )

policy = policy[required_cols].copy()
policy = policy[policy["school"].notna()].copy()
policy["school"] = policy["school"].apply(normalize_school_name)
policy = policy[policy["school"].astype(str).str.strip() != ""].copy()

# Remove any repeated header rows inside the table.
policy = policy[policy["school"].str.lower() != "school"].copy()

policy["school_id"] = policy["school"].map(school_id_map)

missing_ids = policy[policy["school_id"].isna()].copy()
if not missing_ids.empty:
    print("\nSchools that did not map to school_id:")
    print(missing_ids[["school"]].drop_duplicates())
    raise ValueError("Some schools did not map to school_id.")

policy["school_id"] = policy["school_id"].astype(int)

actual_schools = set(policy["school"].tolist())
missing_expected = sorted(expected_schools - actual_schools)
extra_schools = sorted(actual_schools - expected_schools)

print("\nExpected school count:", len(expected_schools))
print("Actual school count:", len(actual_schools))

if missing_expected:
    print("\nExpected schools missing from workbook:")
    print(missing_expected)

if extra_schools:
    print("\nUnexpected schools in workbook:")
    print(extra_schools)

if missing_expected or extra_schools:
    raise ValueError("Workbook school list does not match expected 28-school Alliance list.")

# Clean booleans.
policy["can_accept_out_of_district_students"] = policy[
    "can_accept_out_of_district_students"
].apply(clean_bool)

policy["can_cross_state_boundary"] = policy[
    "can_cross_state_boundary"
].apply(clean_bool)

bool_missing = policy[
    policy["can_accept_out_of_district_students"].isna()
    | policy["can_cross_state_boundary"].isna()
]

if not bool_missing.empty:
    print("\nRows with boolean values that could not be cleaned:")
    print(bool_missing[["school", "can_accept_out_of_district_students", "can_cross_state_boundary"]])
    raise ValueError("Some boolean values could not be cleaned.")

# --------------------------------------------------
# 6. Derived fields for catchment modeling
# --------------------------------------------------

policy.insert(0, "policy_id", range(1, len(policy) + 1))

# Move school_id behind policy_id.
cols = ["policy_id", "school_id"] + [col for col in policy.columns if col not in ["policy_id", "school_id"]]
policy = policy[cols]

policy["out_of_district_allowed_flag"] = policy["can_accept_out_of_district_students"]
policy["cross_state_blocked_flag"] = policy["can_cross_state_boundary"].apply(lambda x: 0 if x == 1 else 1)

policy["admissions_policy_type"] = policy.apply(
    lambda row: (
        "Open / Out-of-District"
        if row["can_accept_out_of_district_students"] == 1
        else "Residency Restricted"
    ),
    axis=1,
)

policy["normal_catchment_rule"] = policy.apply(
    lambda row: (
        "Normal catchment may include approved same-state out-of-district scope."
        if row["can_accept_out_of_district_students"] == 1
        else "Normal catchment generally limited to listed residency area."
    ),
    axis=1,
)

policy["eligibility_notes"] = policy.apply(
    lambda row: (
        "Cross-state students are not normally eligible unless family relocates into the legal attendance/admissions area."
        if row["can_cross_state_boundary"] == 0
        else "Cross-state access permitted by listed admissions policy."
    ),
    axis=1,
)

front_cols = [
    "policy_id",
    "school_id",
    "school",
    "normal_residency_area",
    "can_accept_out_of_district_students",
    "out_of_district_scope",
    "can_cross_state_boundary",
    "admissions_mechanism",
    "athlete_specific_or_general",
    "admissions_policy_type",
    "out_of_district_allowed_flag",
    "cross_state_blocked_flag",
    "normal_catchment_rule",
    "eligibility_notes",
]

remaining_cols = [col for col in policy.columns if col not in front_cols]
policy = policy[front_cols + remaining_cols].sort_values("school").reset_index(drop=True)

print("\nCleaned admissions policy preview:")
print(policy.head(28))

# --------------------------------------------------
# 7. Save to SQLite
# --------------------------------------------------

conn = sqlite3.connect(DB_PATH)

policy.to_sql(
    "alliance_school_admissions_policy",
    conn,
    if_exists="replace",
    index=False,
)

print("\nTable created: alliance_school_admissions_policy")

# --------------------------------------------------
# 8. Validation queries
# --------------------------------------------------

row_count = pd.read_sql_query(
    """
    SELECT COUNT(*) AS policy_rows
    FROM alliance_school_admissions_policy;
    """,
    conn,
)
print("\nPolicy row count:")
print(row_count)

policy_type_summary = pd.read_sql_query(
    """
    SELECT
        admissions_policy_type,
        COUNT(*) AS schools
    FROM alliance_school_admissions_policy
    GROUP BY admissions_policy_type
    ORDER BY schools DESC;
    """,
    conn,
)
print("\nAdmissions policy summary:")
print(policy_type_summary)

out_of_district_schools = pd.read_sql_query(
    """
    SELECT
        school,
        normal_residency_area,
        out_of_district_scope,
        admissions_mechanism
    FROM alliance_school_admissions_policy
    WHERE can_accept_out_of_district_students = 1
    ORDER BY school;
    """,
    conn,
)
print("\nSchools with out-of-district access:")
print(out_of_district_schools)

schema_check = pd.read_sql_query(
    "PRAGMA table_info(alliance_school_admissions_policy);",
    conn,
)
print("\nAdmissions policy table schema:")
print(schema_check[["name", "type"]])

conn.close()

print("\nAdmissions policy import complete.")
