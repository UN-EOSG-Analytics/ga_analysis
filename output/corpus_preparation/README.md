# Corpus preparation

This folder documents how the analysis input was built and checked. The full workflow is described in [ANALYSIS_WORKFLOW.md](../../docs/ANALYSIS_WORKFLOW.md). Analysis run `982ee8fb3de51100` is complete; the report is in [deliverables/982ee8fb3de51100/](../../deliverables/982ee8fb3de51100/) (`UNGA81_AI_Strategic_Review.docx` / `.pdf`).

**The corpus holds 1,908 canonical English speeches and 50,055 passages (2017–2026)** in a single analysis input. The official verbatim records (including 2019) and the 2025/2026 automatic transcripts are the confirmed canonical sources; no additional country PDFs are needed. The last day of both 2025 and 2026 is included. See the [2026 Day 6 update](day6_2026_update/README.md) for the latest additions and duplicate checks.

## Key files

Each country's main General Debate statement is analysed as that country's position. Speaker-rank classification, comparison, weighting and head-of-state counts are not used.

- Analysis input: `output/pipeline/speeches.jsonl` — 1,528 official verbatim records + 380 automatic transcripts.
- Active manifest: `config/source_manifest.jsonl`.
- Per-country extracts: `data/analysis_ready_en/YYYY/YYYY_ISO3.json`.
- [Country-year coverage](country_year_coverage.csv), [missing country-years](missing_country_years.csv), [release status](release_status.json), [input integrity](input_integrity.json).
- [DB review](db_review.json): structural, hash and duplicate checks (snapshot taken before 2026 Day 6 was added, at 1,888 speeches).
- AI keyword screening: [output/screening/](../screening/README.md).

## Coverage by year

| Year | Speeches | Source | Notes |
|---|---:|---|---|
| 2017 | 193 | Official English PV | All obtained main speeches |
| 2018 | 193 | Official English PV | All obtained main speeches |
| 2019 | 192 | Official English PV | Verbatim record used; no country-submitted PDFs needed |
| 2020 | 190 | Official English PV | All obtained main speeches |
| 2021 | 191 | Official English PV | All obtained main speeches |
| 2022 | 190 | Official English PV | All obtained main speeches |
| 2023 | 189 | Official English PV | All obtained main speeches |
| 2024 | 190 | Official English PV | All obtained main speeches |
| 2025 | 189 | English ASR JSON and TXT | All six days; 17 speeches on the last day |
| 2026 | 191 | English ASR JSON | All six days; 20 speeches on the last day |

A gap relative to 193 Member States does not necessarily mean a missing file; some states may not have spoken. The 22 country-years without input are listed in [missing_country_years.csv](missing_country_years.csv) (for 2026: Afghanistan and Myanmar). Missing or unreviewed speeches are never treated as "no AI mention". For 2025, the 189 Member States cited in the President's closing remarks match the number of main speeches extracted.

## Handling format differences

- Official PV records are segmented by page, column, speaker and annex; ASR JSON by speaker metadata; ASR TXT by speaker headings and line ranges.
- Statements by the President, the Secretary-General and observers, and rights of reply, are excluded. In 2026, an unnamed 39-word continuation of Egypt's statement was attached to the main speech.
- Source hashes and PDF page/block, JSON pointer/time, and TXT line/statement start time are carried through to every passage.
- Long transcript paragraphs are split into passages of at most 350 words / 3,000 characters. Text and order are preserved; nothing is corrected or summarized.
- Duplicate country-year speeches, changed source hashes, invalid locations, missing or reordered text and minimum-count shortfalls are blocked at preparation.
- The DB review flagged four non-English passages (foreign-language greetings/quotations in English editions); see [language_exception_review.json](language_exception_review.json).

`accepted` means the text was selected as the analysis source. Automatic transcripts keep `source_type=automatic_transcript` and an unverified-accuracy flag.

## 2025 PDF comparison

Country-submitted 2025 PDFs were compared with the transcripts; see the [2025 PDF review](pdf_2025_review.md). 121 English PDFs were linked as comparison material. For Saint Vincent and the Grenadines, an AI paragraph found only in the prepared PDF was flagged for review and **not** imported into the transcript text.

## Re-running

```powershell
python -m unga_analysis prepare
python -m unga_analysis status
```

Re-run `prepare` only after adding a new source. PDF comparison is optional evidence review, not a required preparation step.

Former submitted PDFs, duplicate copies, unused caches, old audit tables and collection/comparison scripts are kept in the [archive](../../archive/README.md). Original verbatim records and the current input remain in the working folders.
