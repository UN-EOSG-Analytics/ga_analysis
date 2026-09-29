# English country speech inputs

One JSON file per Member State and year, derived from the immutable meeting originals in `data/unga_general_debate_verbatim_en/`. Paragraphs retain PDF page/block/bounding box, original JSON pointer/audio time, or TXT line range/speaker timestamp, together with the original SHA-256 and raw extracted text.

The active manifest is `config/source_manifest.jsonl`; the adjacent `source_manifest.jsonl` is the preparation output. All selected official and user-confirmed automatic transcripts are accepted in the common `output/pipeline/speeches.jsonl` (1,908 speeches, 50,055 passages). Automatic-transcription quality remains unverified. Source acceptance is not an AI or policy classification.

This folder alone is not sufficient for source verification: also provide the original meeting files, manifests and the normalized input. Known limits: the [DB review](../../output/corpus_preparation/db_review.json) identified four foreign-language greetings/quotations in English editions, and 22 country-years have no active speech (see [missing country-years](../../output/corpus_preparation/missing_country_years.csv)). These are coverage/interpretation limits, not duplicate or hash failures. Missing speeches are not AI-negative observations.

Run `python -m unga_analysis prepare` after adding a source. See [corpus preparation](../../output/corpus_preparation/README.md), the [2026 Day 6 update](../../output/corpus_preparation/day6_2026_update/README.md) and [country-year coverage](../../output/corpus_preparation/country_year_coverage.csv). Historical submitted statements are kept only as archived comparison material.
