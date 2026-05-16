# Alliance SQL Database Project

This project builds a local SQLite database for the fictional Alliance high school football conference. The goal is to convert raw CSV files into clean, relational database tables that support repeatable analysis, program evaluation, historical research, and future league expansion planning.

The project combines Python, pandas, SQLite, and Jupyter notebooks to create a lightweight data pipeline from raw files to query-ready outputs.

## Project Purpose

The Alliance worldbuild includes schools, coaches, schedules, championships, head-to-head records, program resources, and media metrics. Keeping those files as separate spreadsheets quickly becomes difficult to manage.

This project turns those files into a structured local database that can answer questions such as:

- Which programs have the strongest historical profiles?
- Which schools dominate head-to-head series?
- Which coaches have the best records?
- Which programs have the strongest resource base?
- What does a typical Alliance school look like?
- How could future expansion candidates be evaluated?

## Tools Used

- Python
- pandas
- SQLite
- Jupyter Notebook
- Positron
- Git/GitHub

## Project Structure

```text
Alliance-SQL-DB/
│
├── Data/
│   ├── Raw/
│   └── Cleaned/
│
├── Database/
│   └── alliance.db
│
├── Notebooks/
│   └── 04_alliance_school_profile_eda.ipynb
│
├── Outputs/
│   ├── alliance_current_school_profile.csv
│   ├── alliance_program_power_index.csv
│   ├── alliance_school_profile_benchmarks.csv
│   └── expansion_candidate_template.csv
│
├── Scripts/
│   ├── 01_build_database_enhanced.py
│   ├── 02_analysis_queries.py
│   └── 03_program_power_index.py
│
├── README.md
└── requirements.txt
