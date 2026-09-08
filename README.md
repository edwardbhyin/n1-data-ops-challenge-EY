# N1 Data Operations Challenge

Hello! My answers for the data ops challenge can be found in the following places documented below. Thanks for taking the time to go over my answers!

## Final Deliverables

### Section A - script

`/final_deliverables/std_member_info_pipeline.py` is the final Python script for Section A. Run it from anywhere (it resolves the database path relative to its own location):

```
python final_deliverables/std_member_info_pipeline.py
```

It fulfills all three parts of Section A in one run:

- **Part a** - connects to the database with `sqlite3` and reads/queries the roster and model-score tables.
- **Part b** - combines and standardizes all five rosters, restricts to members with active eligibility in the current calendar year, deduplicates to one row per member, and writes the result to the database as `std_member_info`.
- **Part c** - calculates and prints the answers to all six required questions.

### Section B - email to the project manager

`/final_deliverables/Manager_Email_n1.docx` is the drafted email explaining the process, the data issues found, and the answers to the six questions. `/final_deliverables/email_attachment.pdf` is the referenced attachment listing the 19 members from question 6.

### Section C - presentation

`/final_deliverables/N1_Data_Ops_Presentation.pptx` is the 5-slide deck covering the introduction, the data quality findings, the results, a walkthrough of the script, and the "new roster every 2 weeks" scenario.

## Where the Work Was Done (for inspection)

The script above is the finished pipeline, but the exploration and reasoning behind it live in `/notebooks/`:

- `/notebooks/EDA.ipynb` - the initial investigation: importing/querying the database, profiling `model_scores_by_zip` and each of the five rosters (types, nulls, categorical values), then the cross-roster checks that turned up the real issues to solve - inconsistent date formats and state naming, exact-duplicate records shared between `roster_2`/`roster_5` and `roster_3`/`roster_4`, and an unreliable `Age` field. Ends with the normalization/combination logic that the final script is based on.
- `/notebooks/Questions.ipynb` - answers questions 1-6 against `std_member_info`, including a payer-breakdown pie chart.
- `/notebooks/WALKTHROUGH.md` - a written walkthrough of the entire process end-to-end, in two parts: a non-technical summary (plain-language findings and answers) and a full technical walkthrough (every step taken in both notebooks, plus the assumptions behind them).

*Note: the six questions are answered under the assumption that they're scoped to the standardized, eligible-this-year population built for Part b (`std_member_info`), not the raw, un-deduplicated universe of all five rosters - see `WALKTHROUGH.md` for why.*
