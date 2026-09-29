# AI keyword screening

Regenerate with `python -m unga_analysis screen`; running `prepare` after adding sources also refreshes screening. No external API or embeddings are used.

| File | Content |
|---|---|
| `ai_candidates.jsonl` | Term hits with surrounding context, source passage and location, source hash, review-needed flag |
| `speech_screening.jsonl` | Screening status for every country-year speech (speeches without hits are listed too) |
| `summary.json` | Screening settings, input/manifest/code hashes, candidate counts |

Search terms are in `config/ai_search_terms.json`, grouped into explicit AI expressions, related concepts, abbreviations needing context checks, and indirect expressions. `Super Intelligence` is a searched AI-related expression but is not assumed to mean `Artificial Intelligence` in every context. Generic `intelligence`, `ai` inside `said`, and `as I` are not treated as AI/ASI abbreviations.

A passage may match several terms. **Hit counts are not country counts or confirmed AI mentions.** The analysis reviews the evidence and counts each country-year once. `source_review_notes` are passed through to candidates so that PDF/transcript differences are visible during review.

A finite term list cannot guarantee that every paraphrase or transcription error is caught; final AI and theme judgements rely on candidate context review plus a check of speeches without hits.
