# Canonical English General Debate originals

These immutable meeting files are the original sources selected by the user. No country-statement PDF counterpart is required for 2019, 2025 or 2026.

- `UNGA72_2017/` through `UNGA79_2024/`: 103 official English PV PDFs, including the 2019 records. 101 contain eligible General Debate material. The 2021 Durban anniversary records PV.5 and PV.8 are retained but excluded.
- `automatic_transcripts_unofficial/`: 2025 days 1-5 and 2026 days 1-5 as JSON; 2025 day 6 as the user-supplied TXT. The 2026 final day remains missing.
- `manifest.json` and the ASR manifest preserve retrieval history. Current analytical eligibility and file hashes are in [meeting_inventory.csv](../../output/corpus_preparation/meeting_inventory.csv).

Automatic transcripts are accepted primary inputs under the user's source policy. Their unofficial ASR identity and unverified text accuracy remain explicit; acceptance does not certify wording or completed analytical review.

Run `python -m unga_analysis prepare` from the project root to segment and normalize. Use `config/source_manifest.jsonl` and `output/pipeline/speeches.jsonl` for analysis, rather than recursively treating every raw meeting as a country speech. See [current coverage](../../output/corpus_preparation/README.md).
