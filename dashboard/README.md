# UNGA AI dashboard

`UNGA_AI_Dashboard.html` is a single self-contained file (no internet connection needed) for exploring AI references in General Debate statements from 2017 to 2026. Open it in any browser, or online at https://un-eosg-analytics.github.io/ga_analysis/.

The online copy is published by `.github/workflows/dashboard-pages.yml` whenever a rebuilt `UNGA_AI_Dashboard.html` is pushed to `main`. The workflow publishes the committed file as is and does not rebuild it.

It is built from analysis run `982ee8fb3de51100`. The run folder is only read and is never changed. All rules that apply to the dashboard alone are kept in `config/`.

```powershell
python dashboard/build_dashboard.py            # rebuild after editing config/ or template.html
python dashboard/build_dashboard.py --run-id <run-id>
```

Each build prints the headline figures so they can be checked: for 2026, 132/191 AI references, 25/29 in WEOG, and 10 / 7 / 2 supporters of the Dialogue / Panel / Fund. The build stops if a config row points to evidence that is not in the run, or if a Dialogue, Panel or Fund reference in the run has no decision.

## Dashboard rules

| Topic | Rule | File |
|---|---|---|
| AI reference | Statements with no AI keyword hit (1,303, never selected for review) count as **No**. Seven statements the review left Uncertain are settled by hand: three that name artificial intelligence in a list count as Yes, and four that mention only machines, robots or algorithms count as No. | `config/ai_status_overrides.csv` |
| Regions | The United States is counted in Western European and other States. | `build_dashboard.py` |
| Themes | The 26 taxonomy codes are grouped into six themes plus Other. A theme is Yes if any of its codes is Yes, No if all are No, and blank otherwise. Blank themes are left out of that theme's denominator. | `config/theme_groups.json` |
| Small numbers | Below 20 statements, counts are shown instead of percentages. | `template.html` |
| UN mechanisms | Every run reference to the Global Dialogue, the Scientific Panel or the proposed Fund has a position: Support, Request, Reservation, Mention or Excluded (not about the UN mechanism). A commitment is flagged on top of the position. Support means the statement names or clearly refers to the mechanism and supports, welcomes or commits to it. | `config/un_mechanism_positions.csv` |
| Requests to the UN | Explicit requests to the UN from the run, with one exclusion and two additions. | `config/un_requests.csv` |
| Institutional models and other venues | Curated from the run's evidence, each with its source quote. | `config/institutional_models.csv`, `config/other_venues.csv` |
| Implications | Recommendations from the UNGA81 AI Strategic Review, linked to the matching views. Fixed to 2026, all groups. | `config/implications.json` |

## Differences from the analysis run and the brief

- 2026 AI references: 132 of 191 (the run reports at least 131). Uruguay's passing mention of artificial intelligence is counted.
- Scientific Panel supporters: Germany is not counted, because its statement never names the Panel. Saint Kitts and Nevis and Mauritius are counted.
- Global Dialogue supporters: Turkmenistan is not counted, because it proposes its own expert dialogue in Ashgabat. Saint Kitts and Nevis is counted.
- UN mechanism counts include statements the run left uncertain, once they have been checked against the full quote. The run's `institution_stance_counts.csv` counts only rows the two coding passes agreed on.

To change the theme groups later, edit `config/theme_groups.json` and rebuild. Every code must be assigned to exactly one group.
