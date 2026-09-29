# Archive

The current analysis does not read this folder. It holds materials removed from the working folders when the canonical sources were fixed, and is used only for recovery.

| File | Content |
|---|---|
| `before_canonical_transcripts.zip` | Backup of code, configuration, documents, per-country extracts and preprocessing records from before the canonical-source change; also contains the earlier duplicate source ZIP |
| `retired_materials.zip` | Backup of former submitted PDFs, unused extraction/OCR caches, review records, one-off scripts and other retired material |
| `cleanup_manifest.json` | For each archived file: original path, SHA-256, archive ZIP and internal path, removal status |

Every archived file's SHA-256 was checked against the original before removal. Original verbatim records and files referenced by the active manifest were not archived.

To recover a file, look up its `archive` and `member` in `cleanup_manifest.json` and extract it into a separate folder. Do not bulk-restore over the current input. Old status tables and scripts in the archive reflect the paths and policies of their time.
