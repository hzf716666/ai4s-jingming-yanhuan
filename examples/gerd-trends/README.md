# R&D trends — an economics example project

Real OECD R&D expenditure data, small enough to analyze in seconds, rich
enough for a genuine end-to-end economic analysis: trend quantification,
cross-country comparison, a publication-quality figure, and a report with
every number traced to code.

## Data

`data/msti_gerd_multicountry.csv` — **OECD Main Science and Technology
Indicators (MSTI)**, Gross Domestic Expenditure on R&D (GERD).

- Four countries: China, Germany, Japan, United States; annual observations
  2019–2024 (168 rows).
- Four measures per country-year in the `UNIT_MEASURE` column:
  `Percentage of GDP`, `US dollars per person, PPP converted`,
  `US dollars, PPP converted` (totals, `value_scale` = 1000000, i.e. millions),
  and `National currency` (current prices).
- Note the `OBS_STATUS` column: some United States post-2021 observations carry
  `Time series break, Definition differs` — treat those as a level break, not
  a true growth rate.
- Source: OECD SDMX data flow `OECD.STI.STP,DSD_MSTI@DF_MSTI`, retrieved
  2026-09-02 through the app's OECD connector (`@cyanheads/oecd-mcp-server`).
  Cite as: OECD, Main Science and Technology Indicators (MSTI), GERD
  (dataset DSD_MSTI@DF_MSTI), retrieved 2026-09-02.

## Suggested workflow

1. Pivot the long CSV into country × year panels for each unit measure.
2. Quantify change in R&D intensity (% of GDP) and per-capita spending over
   2019–2024, and compare levels and growth across the four countries.
3. Save a figure comparing R&D intensity by country and write a short report —
  every number from code output, with the dataset source cited.
