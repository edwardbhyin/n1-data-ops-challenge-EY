# Process Walkthrough

This document walks through everything done in `EDA.ipynb` and `Questions.ipynb` to go from
the raw SQLite database to the final `std_member_info` table and the six required answers.
It's written in two passes: a plain-language summary first, then the full technical detail.

---

## 1. Non-Technical Summary

**The task:** N1's new client handed over a database with five separate member lists
("rosters") plus a table of neighborhood health-risk scores by zip code. The job was to
combine the five rosters into one clean, trustworthy member list, then answer six questions
about that membership for the client.

**What we found before we could combine anything:** The five rosters didn't line up as
cleanly as expected.

- Two pairs of rosters turned out to substantially overlap — roster 2 and roster 5 shared
  13,775 identical member records, and roster 3 and roster 4 shared another 10,845. In other
  words, tens of thousands of members were accidentally included twice across the five files.
- The files weren't formatted consistently. One roster wrote dates as `10/01/2021` while the
  others wrote `2021-10-01`. One roster spelled out "California" while another abbreviated it
  "CA". A couple of the built-in fields (like each member's age) also didn't consistently
  match their birthdate, so we didn't rely on that field.
- On the bright side: every single member's zip code had a matching entry in the health-risk
  score table, so we could reliably attach neighborhood risk data to every member, and there
  were no missing values anywhere in any of the six tables.

**What we built:** After straightening out the formatting differences, we combined all five
rosters and narrowed the list down to members who had active coverage at some point during
2025. That produced the standardized table the client asked for, `std_member_info` — one row
per member, with a consistent set of columns (name, birthdate, address, payer, coverage
dates), saved back into the database.

**The six questions, answered:**

1. **Distinct members eligible in April 2025:** 32,576
2. **Members that had been included more than once** (the roster-overlap issue described
   above, scoped to this year's eligible population): 8,130
3. **Breakdown by payer:** 24,663 Medicaid members, 14,589 Medicare Advantage members
4. **Members living in a zip code with a Food Access score under 2** (i.e. a neighborhood
   flagged for poor grocery/food access): 3,038
5. **Average Social Isolation score across all members:** 3.07
6. **Members in the zip code with the single highest SDOH composite score** (zip 95950,
   score 8.77 — the most at-risk neighborhood in the dataset by that measure): a list of 19
   members, detailed in `Questions.ipynb`.

Everything above, including every assumption made along the way (e.g. what "eligible this
year" means, and how the roster duplicates were resolved), is documented inline in the two
notebooks so the reasoning is fully auditable.

---

## 2. Technical Walkthrough

### 2.1 `EDA.ipynb` — exploration and building `std_member_info`

**Setup.** Connected to the SQLite database via `sqlite3`, and confirmed the six tables
present: `model_scores_by_zip` and `roster_1` through `roster_5`.

**`model_scores_by_zip` exploration.** Loaded the table, checked its declared SQL types
against the types pandas inferred (they matched — `zcta` int, scores as floats), confirmed
zero nulls, and ran `.describe()` to get a feel for the score distributions. Noted `zcta` as
the likely join key, and that the table only covers California.

**Roster 1–5 exploration (one section per roster).** For each roster, checked the SQL schema,
Python dtypes, null counts, `.describe()`, and the unique values of `Gender`/`State`/`payer`.
This surfaced three concrete data-quality issues:

- **`roster_2`** stores `Dob`, `eligibility_start_date`, and `eligibility_end_date` as
  `MM/DD/YYYY` instead of the `YYYY-MM-DD` used elsewhere. This wasn't just assumed from
  convention — it was verified directly: 14,088 of 23,392 `Dob` values have a value above 12
  in the middle token, which can only be a day, proving that slot is day-of-month and the
  first slot is the month.
- **`roster_4`** uses `"CA"` for `State` instead of the `"California"` used everywhere else.
- **`roster_5`** has a different column order than the other four (cosmetic only — harmless
  once loaded into a DataFrame by column name).
- None of the roster tables declare SQL column types, so every value — including numeric-
  looking ones like `Age` and `Zip` — round-trips through SQLite as text.

**Cross-roster exploration.** Built a `Person_Id` overlap matrix across all five rosters and
found overlap in exactly two pairs: `roster_2`/`roster_5` (13,775 shared IDs) and
`roster_3`/`roster_4` (10,845 shared IDs) — zero overlap everywhere else. After normalizing
date formats and the state abbreviation so the rosters could be compared apples-to-apples, a
column-by-column comparison of every overlapping ID showed **zero mismatches on any field** —
these are exact full-row duplicates, not the same person re-enrolled with different data, and
no `Person_Id` appears more than twice anywhere. Also confirmed:

- Each roster's `eligibility_start_date` range shows the five rosters are sequential,
  roughly bi-monthly extracts from the same source system (Aug 2021 through mid-2022), which
  explains why two pairs of them overlap.
- Every `Zip` value in every roster has a matching `zcta` in `model_scores_by_zip` — a 100%
  match rate, making `Zip`/`zcta` a safe join key (once cast to matching types).
- `Age` cannot be fully reconciled against `Dob` using any single reference date (the best
  candidate, 2022-12-31, still leaves ~11% of rows mismatched), so `Age` was treated as
  unreliable and not used downstream.

**Building the combined table.** All five rosters were normalized (consistent date format,
consistent state spelling) and concatenated. Deduplication was **deliberately deferred** to
`Questions.ipynb` rather than done here, because "how many members were included more than
once" is one of the required questions, and answering it honestly requires the pre-dedup
data. The combined rosters (142,305 rows) were joined to `model_scores_by_zip` on
`Zip`/`zcta` (zero unmatched rows), then filtered down to rows whose `eligibility_start_date`
–`eligibility_end_date` window overlaps calendar year 2025 — an interval-overlap check
(`start <= 2025-12-31 AND end >= 2025-01-01`), not a single-point-in-time check, so that
someone eligible for only part of the year is still counted. That left 47,382 rows (still
containing the roster-overlap duplicates).

**`std_member_info`.** Selected and renamed the required columns
(`Person_Id → member_id`, `First_Name → member_first_name`, etc.) from that filtered set,
and wrote the result into the database with
`std_member_info.to_sql('std_member_info', con, if_exists='replace', index=False)`.

### 2.2 `Questions.ipynb` — answering the six questions

Loads `std_member_info` fresh from the database at the top, then works through the questions
in order:

- **Q1 — distinct members eligible in April 2025 (32,576):** same interval-overlap logic as
  the 2025 filter in `EDA.ipynb`, narrowed to `[2025-04-01, 2025-04-30]`, counting distinct
  `member_id`s (not raw rows, since duplicates haven't been removed yet at this point).
- **Q2 — members included more than once (8,130):** `std_member_info.duplicated().sum()` —
  counting full-row duplicates in the 2025-eligible population specifically (not the entire
  raw database), since that's the population the standardized table actually represents.
  Immediately after answering this, `std_member_info.drop_duplicates(inplace=True)` is called
  so every question from here on operates on the de-duplicated, 1-row-per-member table (down
  to 39,252 rows).
- **Q3 — breakdown by payer (24,663 Medicaid / 14,589 Medicare Advantage):**
  `groupby('payer')['member_id'].count()`, visualized with a pie chart (colors assigned by
  payer identity, not by count, so the mapping stays stable if the split changes).
- **Q4 — members in a zip with Food Access score < 2 (3,038):** queried
  `model_scores_by_zip` directly via SQL for qualifying `zcta`s, then filtered
  `std_member_info` to members whose `zip_code` is in that list.
- **Q5 — average Social Isolation score (3.07):** joined `std_member_info` to
  `model_scores_by_zip` on zip code and averaged `social_isolation_score` across all
  matched members.
- **Q6 — members in the zip with the highest Algorex SDOH composite score:** joined to
  `model_scores_by_zip`, found the maximum `algorex_sdoh_composite_score` (8.77, zip 95950),
  and filtered down to the 19 members living in that zip — listed in full in the notebook as
  `max_sdoh_members`.

### 2.3 Key assumptions

- "Active eligibility this year" is read as **calendar year 2025**, and "eligible" for a
  given window is read as an **overlap** with that window, not eligibility on one specific
  day.
- The roster-pair overlaps are treated as **accidental duplicate ingestion** of the same
  members (justified by the zero-mismatch comparison), not as two genuinely different
  enrollment records that happen to share an ID.
- `Age` is not used anywhere in the final table or the answers, since it can't be reconciled
  against `Dob`.
- Question 2's "included more than once" is scoped to the standardized, 2025-eligible
  population (`std_member_info` before dedup), not the raw combined universe of all five
  rosters — the two scopes give different numbers (8,130 vs. 24,620), and the former is what
  matches the population `std_member_info` actually represents.
