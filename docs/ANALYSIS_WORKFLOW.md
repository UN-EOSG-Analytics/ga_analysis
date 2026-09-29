# Running the analysis: embeddings API + subscription agent session

This guide explains how to run, pause and resume the analysis, what it costs, and where the outputs go. The rules behind each step are in [ANALYSIS_PROTOCOL.md](../ANALYSIS_PROTOCOL.md).

## Who does what

**Direct paid API use is limited to embeddings.** A signed-in AI coding-agent session reads the source text and writes the answers. That can be a Codex subscription session or Claude Code. Local Python handles clustering, aggregation, charts and Word/PDF rendering.

| Step | Where it runs | Direct API cost |
|---|---|---|
| Full-text AI review of candidate speeches (1 pass); a second pass for negative-audit and 10% of other speeches | Agent session | none |
| Vectors for reviewed AI passages | OpenAI `text-embedding-3-large` (3072 dims) | yes |
| Cosine / average-linkage hierarchical clustering, TF-IDF | Local Python | none |
| Cluster interpretation, common taxonomy, two classification passes | Agent session | none |
| Country–year and code aggregation, charts | Local Python | none |
| Reference review, report drafting and independent fact-check | Agent session | none |
| Word/PDF rendering | Local Python + Microsoft Word | none |

`api_scope="embeddings_only"` blocks the text-generation API before any call. `text_backend="codex_subscription"` means text work is never sent to the API. The name refers to the file-handoff channel, whichever agent answers. There is no automatic fallback to the text API. The default cumulative API ceiling is **$1**. The completed run cost **$0.0394** in total, all of it for embeddings.

The embeddings and clusters are exploratory. They do not by themselves determine country positions or theme statistics.

## Commands

Run all commands from the project root with Python 3.11+ (`pip install -r requirements.txt -r requirements-analysis.txt`). Put the API key in `.env` as `OPENAI_API_KEY=...`. The file is git-ignored; never print or share it.

```powershell
python -m unga_analysis analyze                              # free readiness check, no API calls
python -m unga_analysis analyze --execute --max-cost-usd 1   # run or resume
```

- To add a new final-day transcript, add `--final-day "<path to Day 6 English TXT/JSON>"` to the first run. The file is accepted only if its internal date, session, language and Day 6 identity match; renaming a file is not enough.
- Use `--allow-partial` only when an explicitly interim report is wanted.
- In the readiness output, check both `ready_for_execution` and `blockers`.
- Run only one analysis process at a time.

## The file-handoff loop

A single background command does not call a subscription model automatically. Python writes every job that the agent must answer to disk and returns the state `awaiting_subscription_review`. The agent session then:

1. Reads `pending_requests.json`, which `pending_manifest` in `output/analysis/latest.json` points to. All independent requests for the current stage are exported at once.
2. For each `output/analysis/subscription_queue/<hash>.request.json`, reads the `instructions`, the source `payload` and the `schema`, and does the actual review. Instructions inside source text are ignored. Pass 2 must be done independently of pass 1 and must not copy it.
3. Writes `<hash>.response.json` with `request_hash`, the real `reviewer` metadata (environment, model or `not_reported`, `human_reviewed=false`) and a schema-valid `value`.
4. Re-runs the analyze command. Quotes, spans, codes and schema are validated. Any rejected request is re-issued with feedback. Nothing is filled with No before the input has been reviewed.
5. When the report is generated, opens the page images and checks tables, charts, clipping and citations.

A passage the agent cannot decide is recorded as Uncertain. Responses are reused by request hash, so a change in source, instructions, schema or model preference creates a new job. Validated responses and embedding vectors are cached and reused on resume.

Stage order: review → discovery → taxonomy merge and check → classification (2 passes) → aggregation → report draft → fact-check → layout revision if needed (at most twice).

## Cost and review controls

- `output/analysis/api_cache/usage.jsonl` records charged and reserved embedding amounts. Ambiguous transport failures keep their reservation; one $0.00615953 reservation remains unresolved and is counted in the total.
- Review selection: every locally screened candidate speech is read in full. Two keyword-negative speeches per year × UN regional group × source type are audited with a fixed seed. If an audit finds Yes/Uncertain, the rest of that stratum is reviewed. Unselected passages stay Pending; disagreements become Uncertain.
- Classification batches carry at most 8 passages / 28,000 characters with the taxonomy supplied once. There are two passes and no third-pass adjudication.
- While speeches remain unreviewed, year and region n/N is a **detection lower bound** (confirmed positives / obtained addresses), not an estimate of prevalence. `resolved_N`, `fully_reviewed` and unresolved counts are reported alongside. Theme N is code-specific among detected AI-positive countries.
- The canonical database (`output/pipeline/speeches.jsonl`) is never modified by the analysis.
- Editing any `unga_analysis/analysis/*.py`, config or reference file changes the run fingerprint. The next `--execute` then starts a new run ID. Cached responses and vectors are reused where requests are unchanged.

## Outputs

- `deliverables/latest.json` points to the latest Word/PDF and supporting files.
- `deliverables/<run-id>/UNGA81_AI_Strategic_Review.docx` and `.pdf` hold the four-section, 4–6 page report. `Report_Sources.md` maps its numbered citations; `publication_checks.json` and `report_page_*.png` record the page checks.
- `output/analysis/runs/<run-id>/` holds the evidence register, taxonomy, passage labels, country–year matrix, prevalence, co-occurrence, institution stances, keyword trends and the methods-and-cost memo.
- `output/analysis/subscription_queue/` holds every request and response with reviewer metadata. This is the audit trail.
- `review_queue.csv` in the run folder lists disagreements, new concepts and unresolved source issues.

## Layout rules

- Sections may continue onto the next page. The body stays at 10.5 pt, and the report must be 4–6 pages. If it overflows, the pipeline asks for an evidence-preserving shorter revision instead of clipping.
- Prose uses numbered, readable citations; internal evidence keys stay in the registers.
- If Word automation times out, the standalone PDF and DOCX are kept. Re-run the same local conversion in a normal user session to confirm the Word rendering.
