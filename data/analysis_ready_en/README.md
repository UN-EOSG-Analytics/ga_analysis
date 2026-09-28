# English country speech inputs

For independent review, see the [DB review](../../output/corpus_preparation/db_review.md) and [sharing checklist](../../output/corpus_preparation/PEER_REVIEW.md). This folder alone is insufficient for source verification: also provide the original meeting files, manifests and actual normalized input. English editions retain four identified foreign-language greetings/quotations; 42 country-year combinations have no active speech. These are explicit coverage/interpretation limits, not duplicate or hash failures.

One JSON file per Member State and year. These are derived from the immutable meeting originals. Paragraphs retain PDF page/block/bounding box, original JSON pointer/audio time, or TXT line range/speaker timestamp, together with original SHA-256 and raw extracted text.

The active manifest is `config/source_manifest.jsonl`; the adjacent manifest is the preparation output. All selected official and user-confirmed automatic transcripts are accepted in the common `output/pipeline/speeches.jsonl`. Automatic-transcription quality remains unverified. Source acceptance is not completed AI or policy classification.

Run `python -m unga_analysis prepare` after adding a source. See [current status](../../output/corpus_preparation/README.md) and [country-year coverage](../../output/corpus_preparation/country_year_coverage.csv). Unobserved speeches are not AI-negative observations. Historical submitted statements are archived comparison material.
