"""
N1 Data Ops Challenge - member roster standardization and summary statistics.

Combines the five raw member roster tables into a single standardized
`std_member_info` table (one row per member, restricted to members with active
eligibility at some point in the current calendar year), writes that table back
into the database, and calculates the six required summary statistics.

This script is the code equivalent of the exploration/derivation done in
notebooks/EDA.ipynb (data quality checks, format normalization, roster
combination) and notebooks/Questions.ipynb (the six required answers). See
notebooks/WALKTHROUGH.md for the full narrative walkthrough and the
assumptions behind each step.

Usage:
    python std_member_info_pipeline.py
"""

from pathlib import Path
import sqlite3

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "n1_data_ops_challenge.db"
ROSTER_TABLES = ["roster_1", "roster_2", "roster_3", "roster_4", "roster_5"]
ELIGIBILITY_YEAR = 2025  # "active eligibility this year" -> current calendar year

# Raw roster column -> standardized std_member_info column
COLUMN_RENAME = {
    "Person_Id": "member_id",
    "First_Name": "member_first_name",
    "Last_Name": "member_last_name",
    "Dob": "date_of_birth",
    "Street_Address": "main_address",
    "City": "city",
    "State": "state",
    "Zip": "zip_code",
    "payer": "payer",
    "eligibility_start_date": "eligibility_start_date",
    "eligibility_end_date": "eligibility_end_date",
}
STD_MEMBER_INFO_COLUMNS = list(COLUMN_RENAME.values())

PAYER_DISPLAY_NAMES = {"Mdcd": "Medicaid", "Madv": "Medicare Advantage"}


def load_rosters(con: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """Load all five raw roster tables."""
    return {name: pd.read_sql_query(f"SELECT * FROM {name};", con) for name in ROSTER_TABLES}


def normalize_roster(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize per-roster formatting quirks found during EDA.

    - roster_2 stores dates as MM/DD/YYYY instead of YYYY-MM-DD everywhere else.
    - roster_4 stores State as "CA" instead of "California" everywhere else.
    """
    df = df.copy()
    for col in ("Dob", "eligibility_start_date", "eligibility_end_date"):
        df[col] = pd.to_datetime(df[col], format="mixed").dt.strftime("%Y-%m-%d")
    df["State"] = df["State"].replace({"CA": "California"})
    return df


def combine_rosters(rosters: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Normalize and concatenate all rosters. Not deduplicated yet - roster_2/roster_5
    and roster_3/roster_4 are known to contain exact duplicate member records (confirmed
    during EDA: zero column mismatches on every overlapping Person_Id, and no Person_Id
    appears more than twice), and the duplicate count is itself a required answer, so
    deduplication happens after that count is captured (see build_std_member_info)."""
    normalized = [normalize_roster(df) for df in rosters.values()]
    combined = pd.concat(normalized, ignore_index=True)
    combined["Zip"] = combined["Zip"].astype(int)
    return combined


def filter_eligible_in_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Keep rows whose eligibility window overlaps the given calendar year at all
    (i.e. start <= year-end AND end >= year-start), not just rows eligible on one
    specific day."""
    window_start = pd.Timestamp(f"{year}-01-01")
    window_end = pd.Timestamp(f"{year}-12-31")
    start = pd.to_datetime(df["eligibility_start_date"])
    end = pd.to_datetime(df["eligibility_end_date"])
    return df[(start <= window_end) & (end >= window_start)]


def build_std_member_info(con: sqlite3.Connection) -> tuple[pd.DataFrame, int]:
    """Build the standardized, deduplicated, one-row-per-member table.

    Returns the final table plus the count of members that appeared more than
    once in the pre-dedup, eligible-this-year population (needed for Q2).
    """
    rosters = load_rosters(con)
    combined = combine_rosters(rosters)
    eligible_this_year = filter_eligible_in_year(combined, ELIGIBILITY_YEAR)

    std_member_info = eligible_this_year.rename(columns=COLUMN_RENAME)[STD_MEMBER_INFO_COLUMNS]

    duplicate_count = int(std_member_info.duplicated().sum())
    std_member_info = std_member_info.drop_duplicates().reset_index(drop=True)

    return std_member_info, duplicate_count


def answer_questions(con: sqlite3.Connection, std_member_info: pd.DataFrame, duplicate_count: int) -> dict:
    """Calculate the six required summary statistics."""
    answers = {}

    # Q1: distinct members eligible in April 2025 (interval-overlap, same logic as the
    # yearly filter above but narrowed to one month).
    window_start = pd.Timestamp("2025-04-01")
    window_end = pd.Timestamp("2025-04-30")
    start = pd.to_datetime(std_member_info["eligibility_start_date"])
    end = pd.to_datetime(std_member_info["eligibility_end_date"])
    eligible_april = std_member_info[(start <= window_end) & (end >= window_start)]
    answers["distinct_members_eligible_april_2025"] = eligible_april["member_id"].nunique()

    # Q2: members included more than once, scoped to the eligible-this-year population
    # that std_member_info represents (captured before dedup, in build_std_member_info).
    answers["members_included_more_than_once"] = duplicate_count

    # Q3: breakdown of members by payer.
    answers["payer_breakdown"] = std_member_info.groupby("payer")["member_id"].count().to_dict()

    # Q4: members living in a zip code with a food access score below 2.
    low_food_zips = pd.read_sql_query(
        "SELECT DISTINCT zcta FROM model_scores_by_zip WHERE food_access_score < 2;", con
    )["zcta"].tolist()
    low_food_members = std_member_info[std_member_info["zip_code"].isin(low_food_zips)]
    answers["members_low_food_access"] = low_food_members["member_id"].nunique()

    # Q5: average social isolation score across all members (member -> home zip -> score).
    isolation_scores = pd.read_sql_query(
        "SELECT zcta, social_isolation_score FROM model_scores_by_zip;", con
    )
    with_isolation = std_member_info.merge(
        isolation_scores, left_on="zip_code", right_on="zcta", how="left"
    )
    answers["avg_social_isolation_score"] = with_isolation["social_isolation_score"].mean()

    # Q6: members living in the zip code with the single highest Algorex SDOH composite score.
    sdoh_scores = pd.read_sql_query(
        "SELECT zcta, algorex_sdoh_composite_score AS sdoh FROM model_scores_by_zip;", con
    )
    with_sdoh = std_member_info.merge(sdoh_scores, left_on="zip_code", right_on="zcta", how="left")
    max_sdoh_members = with_sdoh[with_sdoh["sdoh"] == with_sdoh["sdoh"].max()].drop(columns="zcta")
    answers["max_sdoh_zip_members"] = max_sdoh_members

    return answers


def print_answers(answers: dict) -> None:
    print("Q1. How many distinct members were eligible in April 2025?")
    print(f"    {answers['distinct_members_eligible_april_2025']}\n")

    print("Q2. How many members were included more than once?")
    print(f"    {answers['members_included_more_than_once']}\n")

    print("Q3. What is the breakdown of members by payer?")
    for payer, count in answers["payer_breakdown"].items():
        print(f"    {PAYER_DISPLAY_NAMES.get(payer, payer)} ({payer}): {count}")
    print()

    print('Q4. How many members live in a zip code with a "Food access score" less than 2?')
    print(f"    {answers['members_low_food_access']}\n")

    print('Q5. What is the average "Social isolation score" for all members?')
    print(f"    {answers['avg_social_isolation_score']:.4f}\n")

    print('Q6. Which members live in the zip code with the highest "Algorex SDOH composite score"?')
    print(answers["max_sdoh_zip_members"].to_string(index=False))


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        std_member_info, duplicate_count = build_std_member_info(con)
        std_member_info.to_sql("std_member_info", con, if_exists="replace", index=False)
        print(f"std_member_info written to database ({len(std_member_info)} rows, 1 row per member).\n")

        answers = answer_questions(con, std_member_info, duplicate_count)
        print_answers(answers)
    finally:
        con.close()


if __name__ == "__main__":
    main()
