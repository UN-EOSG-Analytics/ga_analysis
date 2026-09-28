# Current reusable caches

- `verbatim_blocks/`: source-hash-keyed, column-aware extraction from official PDF meeting records. Used by `python -m unga_analysis prepare`.
- `reference/`: extraction of the background documents in `reference/`.
- Normalized input extraction is cached separately in `output/pipeline/cache/text/`.

Historical statement extraction/OCR, retained external inputs and earlier country-level review notes are recoverable through `archive/cleanup_manifest.json`. They are not read by the current analysis input workflow.
