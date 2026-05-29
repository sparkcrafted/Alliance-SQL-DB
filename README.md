![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![pandas](https://img.shields.io/badge/pandas-Data%20Cleaning-purple)
![SQLite](https://img.shields.io/badge/SQLite-Relational%20Database-lightgrey)
![Jupyter](https://img.shields.io/badge/Jupyter-EDA-orange)
![Data Modeling](https://img.shields.io/badge/Data%20Modeling-SQL%20Schema-teal)
![ETL](https://img.shields.io/badge/ETL-CSV%20%2B%20Excel-green)
![Talent Analytics](https://img.shields.io/badge/Talent%20Analytics-In%20Development-yellow)
![License](https://img.shields.io/badge/License-MIT-blue)
# Alliance SQL Database Project

This project builds a local SQLite database for the fictional Alliance high school football conference. The goal is to convert raw CSV and Excel files into clean, relational database tables that support repeatable analysis, program evaluation, historical research, talent access modeling, and future league expansion planning.

The project combines Python, pandas, SQLite, and Jupyter notebooks to create a lightweight data pipeline from raw files to query-ready outputs.

## Project Purpose

The Alliance worldbuild includes schools, coaches, schedules, championships, head-to-head records, program resources, media metrics, national player rankings, admissions policy rules, and talent catchment logic. Keeping those files as separate spreadsheets quickly becomes difficult to manage.

This project turns those files into a structured local database that can answer questions such as:

* Which programs have the strongest historical profiles?
* Which schools dominate head-to-head series?
* Which coaches have the best records?
* Which programs have the strongest resource base?
* What does a typical Alliance school look like?
* How could future expansion candidates be evaluated?
* Which Alliance schools have access to the strongest football talent markets?
* How do admissions rules shape a school’s realistic talent universe?
* Which schools may be talent-rich, talent-limited, or underperforming their available talent base?

## Tools Used

* Python
* pandas
* SQLite
* Jupyter Notebook
* Positron
* Git/GitHub

## Project Structure

```text
Alliance-SQL-DB/
│
├── Data/
│   ├── Raw/
│   │   ├── 2026_Football_Schedule.csv
│   │   ├── Conference_Championships.csv
│   │   ├── Football_AllTime_Series_Records.csv
│   │   ├── Football_National_Championships.csv
│   │   ├── Football_Playoff_Results.csv
│   │   ├── Football_Program_Data.csv
│   │   ├── Head_Football_Coaching_Record.csv
│   │   ├── High_School_Enrollment_Worksheet.xlsx
│   │   └── Processed_Player_Rankings.xlsx
│   │
│   └── Cleaned/
│
├── Database/
│   └── alliance.db
│
├── Notebooks/
│   ├── 04_alliance_school_profile_eda.ipynb
│   └── 05_alliance_governance_vote_model.ipynb
│
├── Outputs/
│   ├── alliance_current_school_profile.csv
│   ├── alliance_program_power_index.csv
│   ├── alliance_school_profile_benchmarks.csv
│   ├── alliance_school_talent_access_summary.csv
│   ├── alliance_talent_access_ranking.csv
│   ├── expansion_candidate_template.csv
│   ├── player_alliance_school_matches.csv
│   └── top_players_by_alliance_school_access.csv
│
├── Scripts/
│   ├── 01_build_database_enhanced.py
│   ├── 02_analysis_queries.py
│   ├── 03_program_power_index.py
│   ├── 06_import_player_rankings.py
│   ├── 07_import_admissions_policy.py
│   ├── 08_build_talent_catchments.py
│   └── 09_analyze_talent_access.py
│
├── README.md
└── requirements.txt
```

## Key Scripts

### `01_build_database_enhanced.py`

Builds the core SQLite database from raw CSV files.

This script:

* loads raw football data
* cleans column names
* assigns official school IDs
* converts wide tables into tidy relational tables
* builds the main `schools` table
* creates cleaned championship, coaching, schedule, and all-time series tables
* validates row counts and missing joins

Key database tables include:

* `schools`
* `football_national_championships`
* `football_conference_championships`
* `football_coach_season_records`
* `football_alltime_series_records_clean`
* `football_schedule_2026_game_entries`

### `02_analysis_queries.py`

Runs core SQL queries against the database.

Example outputs include:

* national titles by school
* conference titles by school
* current coach career records
* best all-time head-to-head series
* program title summaries

### `03_program_power_index.py`

Creates the Alliance Program Power Index.

The index combines multiple dimensions of program strength:

* historical success
* national championships
* conference championships
* current coach performance
* all-time head-to-head strength
* resource and media indicators

The script exports:

```text
Outputs/alliance_program_power_index.csv
```

### `06_import_player_rankings.py`

Imports the processed national player rankings workbook into SQLite.

This script loads:

* `ranking_sources`
* `players`
* `player_rankings`
* `player_source_consensus`
* `player_data_quality_flags`
* `player_state_summary`
* `player_position_summary`

The player rankings layer supports future talent-access and recruiting simulation work.

### `07_import_admissions_policy.py`

Imports the expanded Alliance admissions and enrollment policy workbook.

This script creates:

```text
alliance_school_admissions_policy
```

This table captures school-level eligibility rules, including:

* normal residency area
* out-of-district admissions access
* out-of-district scope
* state boundary restrictions
* admissions mechanism
* whether the provision is general or athlete-specific

This table is important because Alliance schools are public schools, so geography and admissions policy shape each program’s realistic talent universe.

### `08_build_talent_catchments.py`

Builds the player-to-school talent catchment model.

This script joins player rankings with Alliance school admissions rules to create:

```text
player_alliance_school_matches
alliance_school_talent_access_summary
```

The goal is not to say that a player automatically attends a school. Instead, the script identifies whether a ranked player is inside a school’s plausible talent universe based on state, admissions rules, residency logic, and regional visibility.

### `09_analyze_talent_access.py`

Analyzes the talent catchment outputs.

This script creates school-level outputs that help evaluate:

* which schools have access to top-ranked players
* which schools have stronger strict talent access
* which schools have broader regional gravity
* which players appear in each school’s access universe

The script exports:

```text
Outputs/alliance_talent_access_ranking.csv
Outputs/top_players_by_alliance_school_access.csv
```

## Jupyter Notebooks

### `04_alliance_school_profile_eda.ipynb`

Explores the current profile of an Alliance school.

The notebook is designed to support future league expansion analysis. It examines:

* geography and market profile
* resources and budgets
* competitive strength
* Program Power Index results
* league-wide benchmarks
* expansion candidate template structure

The notebook exports:

```text
Outputs/alliance_school_profile_benchmarks.csv
Outputs/alliance_current_school_profile.csv
Outputs/expansion_candidate_template.csv
```

### `05_alliance_governance_vote_model.ipynb`

Explores Alliance governance voting scenarios and distribution estimates.

This notebook supports league-structure and governance modeling around expansion, alignment, and voting behavior.

## Database Design

The project uses `school_id` as the core join key across school-level tables.

Example:

```text
schools.school_id
    → football_national_championships.school_id
    → football_conference_championships.school_id
    → football_coach_season_records.school_id
    → football_alltime_series_records_clean.school_id
    → football_schedule_2026_game_entries.school_id
    → alliance_school_admissions_policy.school_id
    → player_alliance_school_matches.school_id
```

For player data, the project uses `player_id` as the core player-level key.

Example:

```text
players.player_id
    → player_rankings.player_id
    → player_source_consensus.player_id
    → player_alliance_school_matches.player_id
```

This allows the project to move beyond separate spreadsheet analysis and into repeatable relational querying.

## Talent Access Model

The project now includes an early-stage talent access model that connects national player rankings to Alliance schools.

The model separates:

```text
Talent access = who is plausibly in a school’s geographic/admissions universe
Recruiting outcome = who actually enrolls or commits
```

The current project focuses on talent access, not final recruiting outcomes.

The model considers:

* player ranking quality
* player home state
* player high school
* school state
* school admissions policy
* normal residency area
* out-of-district access
* state boundary restrictions
* regional gravity
* relocation requirements

Important distinction:

```text
Normal catchment access is not the same as regional visibility.
```

A school may have regional awareness of a player, but public-school admissions rules may prevent that player from being counted as part of the school’s strict talent pool unless relocation or a legal admissions pathway exists.

## Example Analysis Questions

This database can support questions like:

```sql
SELECT
    s.school,
    COUNT(fcc.championship_id) AS conference_titles
FROM football_conference_championships AS fcc
JOIN schools AS s
    ON fcc.school_id = s.school_id
GROUP BY s.school
ORDER BY conference_titles DESC;
```

Or:

```sql
SELECT
    school,
    opponent_school,
    wins,
    losses,
    win_pct
FROM football_alltime_series_records_clean
ORDER BY win_pct DESC, wins DESC;
```

Or:

```sql
SELECT
    school,
    COUNT(*) AS accessible_players,
    SUM(is_top_100) AS top_100_players,
    MIN(best_rank) AS best_available_rank
FROM player_alliance_school_matches
WHERE normal_catchment_flag = 1
GROUP BY school
ORDER BY top_100_players DESC, best_available_rank ASC;
```

## Key Outputs

* `Database/alliance.db`
  Local SQLite database.

* `Outputs/alliance_program_power_index.csv`
  Ranked program strength model.

* `Outputs/alliance_school_profile_benchmarks.csv`
  League benchmark table for future expansion evaluation.

* `Outputs/alliance_current_school_profile.csv`
  Current Alliance school profile dataset.

* `Outputs/expansion_candidate_template.csv`
  Template for evaluating future expansion schools.

* `Outputs/player_alliance_school_matches.csv`
  Player-to-school talent universe table.

* `Outputs/alliance_school_talent_access_summary.csv`
  School-level talent access summary.

* `Outputs/alliance_talent_access_ranking.csv`
  Talent access ranking output.

* `Outputs/top_players_by_alliance_school_access.csv`
  Ranked-player access output by school.

## Skills Demonstrated

This project demonstrates:

* SQL database design
* Python data cleaning
* pandas transformations
* wide-to-long reshaping
* primary and foreign key mapping
* SQLite table creation
* validation checks
* repeatable analytical workflows
* benchmark creation
* player ranking normalization
* admissions policy modeling
* talent catchment analysis
* portfolio-ready data storytelling

## Current Status

The project currently builds a functioning local SQLite database from raw CSV and Excel files and generates reusable outputs for program analysis, league profile analysis, expansion planning, and early-stage football talent access modeling.

The talent catchment model is still in development. The current version successfully builds player-school access tables, but future iterations should refine the eligibility and geography logic before using the results for full recruiting simulation.

## Future Development

Potential next steps include:

* refining the admissions-based talent access model
* adding player and school latitude/longitude
* adding distance and drive-time calculations
* improving strict catchment versus regional gravity logic
* building a recruiting simulation model
* adding recruiting conversion scores by school
* comparing talent access to Program Power Index results
* building an expansion candidate evaluator
* adding an ERD/schema visual to the README
* creating visual dashboards
* connecting the SQLite database to Tableau or Power BI
* creating automated season simulation outputs

```
```
