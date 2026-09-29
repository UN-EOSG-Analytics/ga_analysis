# Input contract for transcripts and PDFs

## Canonical sources

For 2017–2024 (including 2019) the source text is the official English verbatim record (PV). For 2025 and 2026 it is the English automatic speech recognition (ASR) transcript, which the project owner confirmed as the analysis source. Country-submitted PDFs are therefore not required. Source type and accuracy-review status are recorded in separate fields.

Meeting files are preserved unchanged in `data/unga_general_debate_verbatim_en/`. `python -m unga_analysis prepare` splits them into per-country speeches at `data/analysis_ready_en/YYYY/YYYY_ISO3.json` and normalizes them into `output/pipeline/speeches.jsonl`.

## Handling by source format

| Source | Segmentation basis | Preserved locator |
|---|---|---|
| Official PV PDF | Speakers, President's introductions, annexes, column order | `pdf_page`, `pdf_block`, `bbox` |
| UN ASR JSON | Speaker affiliation and paragraphs in `/transcript/data` | `json_pointer`, `start`, `end`, `statement_start` |
| UN ASR TXT | `Country · Title · Name [time]:` headings and blank lines | `line_start`, `line_end`, `speaker_line`, `statement_timestamp` |

For TXT files, the date, language and heading structure are checked, and the stated affiliation is mapped to an official country code. Rights of reply and statements by the President and observers are excluded. Unrecognized headings or countries, and conflicts between sources, are recorded as exceptions. On the last day of 2025, the Holy See statement and the rights of reply after the closing remarks are not counted as main Member State speeches.

A TXT timestamp is the time on the speaker heading. No exact audio segment or PDF page number is fabricated for a paragraph. Time units in the original JSON are kept as they are.

## Common speech and passage model

Each country delegation's main General Debate statement is treated as that country's position. There is no classification, comparison or weighting by speaker rank; names and introductions are used only for source verification. Transcript headings without a title or name are processed if the country and the extent of the main statement can be established.

- Primary key: `speech_id=YEAR_ISO3`. Only one `accepted` speech is allowed per country-year.
- `source_type`: `official_transcript` or `automatic_transcript`.
- ASR source selection: `source_acceptance=user_confirmed_primary`.
- ASR accuracy: `text_accuracy=unverified_automatic_transcription`. This flag does not revoke source selection or exclude the speech from analysis.
- Origin tracking: `origin_file`, `origin_sha256`; per-country extract tracking: `path`, `sha256`.
- Every passage carries its source location, the extracted paragraph number (`extracted_block`) and a character range within that paragraph (`char_start`, `char_end`; zero-based, end-exclusive).
- Passages are at most 350 words / 3,000 characters, split at sentence ends where possible, without inserted overlap context or text correction. Character ranges refer to the `text` of the extracted block.
- AI determination, text review and theme classification start as `Pending`. Accepting a source is not a completed analytical judgement.

In the JSONL passages, `source_file`/`source_sha256` point to the per-country extract and `locator.origin_file`/`origin_sha256` point to the meeting original. Report evidence cites the original location. Downstream embedding and classification reference `passage_id`, and the same processing rules apply to every year.

## Adding sources

A new meeting file is stored in the existing transcript folder under a year/day name (e.g. the 2026 last day is `UNGA2026_day6_EN_ASR.json`), then `prepare` is run. Once collection is confirmed complete, `partial_years` in `config/analysis.toml` is updated. An existing original must never be silently overwritten with different content.

Generic single-speech TXT/DOCX/JSON/JSONL input adapters are kept, but a whole meeting file must never be registered as one country. Unsupported structures require a dedicated segmentation rule first. Empty documents, invalid locations, mixed speakers and hash mismatches are errors and are never counted as "no mention".
