# UNGA General Debate AI analysis (2017–2026)

This repository analyses how Member States discuss artificial intelligence in their UN General Assembly General Debate main addresses, from UNGA72 (2017) to UNGA81 (2026). It produces the SPMU briefing **UNGA81 AI Strategic Review**.

## Latest result

Run `982ee8fb3de51100` completed on 29 September 2026.

- Report: [deliverables/982ee8fb3de51100/UNGA81_AI_Strategic_Review.pdf](deliverables/982ee8fb3de51100/UNGA81_AI_Strategic_Review.pdf) (and `.docx`). It is 5 pages with four sections: Key Facts and Figures, Themes, Role of UN, Implications. Numbered citations are resolved in [Report_Sources.md](deliverables/982ee8fb3de51100/Report_Sources.md).
- Corpus: 1,908 country–year main addresses and 50,055 passages. 2026 has 191 addresses, covering all six days.
- AI mentions in 2026: at least 131 of 191 obtained addresses (68.6%). This is a verified detection lower bound, not a prevalence estimate.
- Supporting tables and the methods memo are in [output/analysis/runs/982ee8fb3de51100/](output/analysis/runs/982ee8fb3de51100/). Start with [methodology_and_cost.md](output/analysis/runs/982ee8fb3de51100/methodology_and_cost.md), `evidence_register.csv`, `theme_taxonomy.md` and `theme_prevalence.csv`.
- Direct API cost: $0.0394 cumulative, for embeddings only.
- Reading, classification and drafting were automated AI reviews with source-quote validation. Nothing was human-reviewed (`human_reviewed=false`). Who performed each stage is recorded in [handoff_provenance.md](output/analysis/runs/982ee8fb3de51100/handoff_provenance.md).

## Dashboard

An interactive dashboard of the results is published at https://un-eosg-analytics.github.io/ga_analysis/. Its source, rules and config are in [dashboard/](dashboard/README.md); the analysis run is not modified.

## Documentation

- [ANALYSIS_PROTOCOL.md](ANALYSIS_PROTOCOL.md): analytical rules, denominators, the original brief and the required deliverables.
- [ARCHITECTURE.md](ARCHITECTURE.md): source policy, data flow and modules.
- [docs/ANALYSIS_WORKFLOW.md](docs/ANALYSIS_WORKFLOW.md): how to run or resume the analysis, the agent file-handoff loop, cost controls and outputs.
- [docs/transcript_input_contract.md](docs/transcript_input_contract.md): source formats and evidence locators.
- [output/corpus_preparation/README.md](output/corpus_preparation/README.md): corpus coverage and preparation checks.

## Quick start

Python 3.11+, from the project root:

```powershell
pip install -r requirements.txt -r requirements-analysis.txt
python -m unga_analysis status        # corpus and registry status
python -m unga_analysis analyze       # free readiness check (no API calls)
```

Rebuild the corpus only after adding sources or changing preprocessing rules. PDF extraction needs PyMuPDF from `requirements.txt`.

```powershell
python -m unga_analysis prepare       # segment, register, normalize, integrity-check, screen
python -m unga_analysis screen        # refresh local AI-term screening only
```

To run or resume the analysis, use `python -m unga_analysis analyze --execute --max-cost-usd 1` and follow [docs/ANALYSIS_WORKFLOW.md](docs/ANALYSIS_WORKFLOW.md). The OpenAI key goes in a git-ignored `.env` file as `OPENAI_API_KEY=...` and is used only for embeddings. Tests: `python -m pytest tests -q`.

## Folders

| Path | Contents |
|---|---|
| `data/unga_general_debate_verbatim_en/` | Preserved original PDF, JSON and TXT sources |
| `data/analysis_ready_en/` | Per-country English addresses with source locators |
| `config/` | Active source registry, source-selection policy, regional mapping, analysis settings |
| `unga_analysis/` | Preparation, screening, analysis and reporting code |
| `output/pipeline/` | Canonical analysis input (`speeches.jsonl`) |
| `output/corpus_preparation/` | Coverage and preparation evidence |
| `output/screening/` | Local AI-term screening candidates (not reviewed labels) |
| `output/analysis/` | Per-run results, API cache and usage ledger, handoff queue |
| `reference/` | Institutional background documents used for Role of UN |
| `cache/` | Current extraction and reference caches |
| `archive/` | Recovery-only backups of retired materials |
| `deliverables/` | Final Word/PDF reports |

Automatic transcripts (2025–2026) are included as canonical sources. They remain flagged as unofficial, and their audio accuracy has not been verified. Missing or unreviewed speeches are never counted as "no AI mention".
