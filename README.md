# Ladder · Retirement, priced by the bond market

The yield curve is a price list for retirement. Every year of future income has a price today,
and the U.S. Treasury sets it every afternoon. Ladder is a six-step guide that reads that price
list and turns it into a plan: what bonds pay, what a year of income costs, your goals, the
essentials you can lock with a TIPS ladder, how the plan held up in every start year since
1928, and the moves that close each gap.

**Live site:** https://ladder.astrodata.us

Built by [Astrodata](https://astrodata.us). The same document also runs as an Omni app; this
repository is the static build of it, plus the market data it reads.

## The data is real and refreshed every trading day

| File | What | Source |
|---|---|---|
| `data/ladder_curves_monthly.csv` | Month-end Treasury curves, nominal since 1990 and real (TIPS) since 2003, 1 month to 30 years. The latest month is the latest close. | U.S. Treasury daily par yield curve rates; FRED H.15 as fallback |
| `data/ladder_curves_keydates.csv` | The full curves on three dates the app compares: the latest close, one year earlier, and the 10-year TIPS low. | Same |
| `data/ladder_market_monthly.csv` | Fed funds, 5- and 10-year breakeven inflation, investment-grade and high-yield spreads, month-end since 1990. | FRED: DFF, T5YIE, T10YIE, BAMLC0A0CM, BAMLH0A0HYM2 |
| `data/ladder_returns_annual.csv` | Annual S&P 500, 3-month bill and 10-year Treasury returns and CPI inflation, 1928 onward. | Aswath Damodaran, NYU Stern |
| `data/ladder_facts.csv` | The figures the guide quotes (latest close, record comparisons, CPI). | Derived from the above |
| `data/ladder_data.json` | All of the above in the shape the page embeds. | Derived |

A GitHub Action (`.github/workflows/refresh.yml`) runs after each weekday close. It pulls the
newest curves, refuses to publish unless they are newer than what is here, checks that no
history went missing, then rewrites the CSVs and both pages and commits. The household in the
app starts from rounded U.S. averages (Federal Reserve, Vanguard, Census, SSA, BLS); nobody's
real finances are in it, and nothing a visitor types leaves the page.

## Files

| Path | What |
|---|---|
| `index.html` | The app, self-contained: fonts and data embedded, no network requests. |
| `ladder-omni-app.html` | The same app built for Omni. It reads the five `ladder_*` saved queries in its workbook and falls back to the embedded copy when they do not answer. |
| `refresh/` | The nightly refresh: `refresh.py` (pull), `to_csvs.py` (tables), `render.py` and `templates/` (pages). Standard library only. |

## Omni

Each saved query reads one CSV from this repository, so the Omni app is current as soon as the
Action commits:

```sql
SELECT * FROM read_csv_auto('https://raw.githubusercontent.com/astrodataus/ladder/main/data/ladder_curves_monthly.csv')
```

| Saved query | Rows |
|---|---|
| `ladder_curves_monthly` | about 730 |
| `ladder_curves_keydates` | 6 |
| `ladder_market_monthly` | about 440 |
| `ladder_returns_annual` | about 100 |
| `ladder_facts` | about 25 |

An educational model, not investment advice.
