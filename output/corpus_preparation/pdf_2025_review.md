# 2025 submitted PDFs: comparison with transcripts

## Outcome

The **218 PDFs and 1 index file** re-delivered to `data/raw/` were identical to files already in the ZIP archive. No evidence was found to add a new country speech or replace any transcript text. The comparison was extended to the last day, and the one content difference found was recorded as review metadata in the analysis input. Deletions and per-file hashes are recorded in the [cleanup log](raw_2025_cleanup.json).

| Item | Result | Handling |
|---|---:|---|
| English PDFs comparable | 121 countries / 121 PDFs | Word-sequence comparison with transcripts and AI term cross-check |
| English PDF extraction failure | Albania, 1 PDF | English on screen but stored extracted text is garbled; not treated as a content mismatch |
| Non-English Member State submissions | 87 PDFs | Not added to the English analysis text |
| Outside main Member State statements | 9 PDFs | Not added as separate country observations |
| Member States covered by this batch | 176 countries | All map to existing 2025 transcripts |
| Last-day English PDFs compared | 11 countries | Compared with the last-day transcript |
| New country speeches / transcript edits | 0 / 0 | 2025 remains at 189 speeches |
| Content difference flagged | Saint Vincent and the Grenadines, 1 | `source_review_notes` added to the analysis input |

Last-day countries compared: DPRK, Denmark, Eritrea, Malawi, Nepal, Nicaragua, Moldova, Saint Lucia, Timor-Leste, Vanuatu, Zambia. These 11 are not the whole last day; the last-day transcript contains 17 main Member State statements.

## Content difference: Saint Vincent and the Grenadines (`2025_VCT`)

Physical page 16 (printed page 15) of the submitted PDF contains a bracketed paragraph on AI regulation and the role of the General Assembly. At the corresponding point, the transcript moves from climate change to hurricane damage without this paragraph. The transcript does mention `artificial intelligence` earlier, so the country's AI mention itself is not new.

The two documents alone cannot show whether the paragraph was omitted in delivery or missed by the ASR. The prepared-only paragraph was **not imported**: it is not appended to the transcript, and the PDF is not counted as a second speech. Any theme or UN-role judgement that depends on that paragraph stays `Uncertain/Pending` unless audio or an official record confirms delivery.

- [PDF quotation and transcript location evidence](pdf_2025_review_evidence.json)
- [Persistent review notes applied on regeneration](../../config/source_review_notes.json)
- The same note is reflected in the active manifest, the extract manifest and the matching row of `output/pipeline/speeches.jsonl`. The per-country JSON, passage text, locations and hashes are unchanged.

For Cuba, Namibia and Portugal, `AI` in the PDF versus `artificial intelligence` in the transcript was checked in context and is not a missed AI mention. The Italy PDF is 2025 (80th session) material; the `2024` on its first page is the Global Peace Index year.

## Scope and reproducibility

- [Per-file comparison CSV](pdf_2025_comparison.csv): country, language, comparison status, bidirectional 5-word-sequence overlap, hashes, ZIP file and internal path.
- [Per-page extracted text and candidates](pdf_2025_comparison_detail.json), [summary JSON](pdf_2025_review_summary.json).
- [Delivered file inventory](raw_2025_inventory.json), [ZIP match and deletion log](raw_2025_cleanup.json).

Existing page extracts were reused only when the source PDF hash, full extraction cache hash, page count and per-page source hashes all matched. The cache is `cache/extraction/selected_pages.jsonl` inside `archive/retired_materials.zip` (SHA-256 `044e7133e52ce2cdfd6b79f9f62ebc7eac43248047fd30faa2cb7f0d0b148bb7`). Original files are kept at the ZIP paths listed in the comparison table.

Word-sequence overlap is computed on text normalized for whitespace and case. A low ratio alone does not indicate a faulty transcript: submitted English translations and live interpretation can differ, as can prepared texts and delivered speeches. For example, the Papua New Guinea transcript is much longer than its PDF, so it was not replaced.

The AI term check used `artificial intelligence`, standalone `AI`, `machine learning`, `generative`, `deepfake(s)` and `large language model(s)`, after Unicode ligature normalization. Candidates appeared in 44 comparable English PDFs, and the corresponding transcripts also contained candidates. **This does not mean the full AI content matched.** No sentence-level semantic comparison or audio verification was done, and the unverified-ASR flag remains.
