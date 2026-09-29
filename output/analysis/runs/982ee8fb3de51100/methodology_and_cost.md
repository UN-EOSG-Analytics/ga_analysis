# Methods and cost



The analysis uses the country–year as the unit and does not modify the transcript database. Reviewers read the full context of every speech with a search candidate, plus a sample of search-negative speeches stratified by year, region and source. Each selected speech is reviewed automatically once; the negative-audit sample and a fixed hash-selected 10% are reviewed twice. If a sample finds Yes/Uncertain, review expands to that stratum. The actual selection, pass counts and expansions are recorded in review_selection.json. Unreviewed passages stay Pending; disagreements become Uncertain.

While unreviewed speeches remain, the year/region n/N is a lower bound: confirmed AI-positive countries over obtained country speeches. It is not an estimate of the population mention rate and does not treat unreviewed text as No. resolved_N and fully_reviewed are reported separately. Because of search/sampling bias and different review coverage by year, changes in rates are not asserted as policy shifts. Theme shares are computed within detected and reviewed AI-positive speeches and are not generalised to undetected AI remarks.

Execution path for context review, classification and report: codex_subscription. On the subscription path the actual model is recorded in the reviewer metadata of each subscription_queue response. Embeddings: text-embedding-3-large, 3072 dimensions.

Embeddings are applied only to AI-Yes passages and required context. Local mean-centring, cosine distance and average linkage are used; several cut levels and representative/boundary passages per cluster are reviewed to build a common taxonomy. Cluster IDs are never used as final theme values.

Classification is multi-label per passage and aggregated per country–year and code with OR. A code is 1 if any passage is Yes; 0 if AI review is complete and every AI passage is No for that code; otherwise NA. The theme N is the number of AI-positive countries with a resolved value for that code; co-occurrence uses countries resolved on both codes as denominator. Same-country year comparisons use the per-code common sample. Unreviewed or unobtained data are never converted to 0. New concepts go to the review queue and do not block completion of existing codes. Regions use the fixed UN mapping.

Separate calls to the same model are automated re-review, not inter-human agreement. No audio verification or completed human review is claimed. Reports produced from automated review state this limitation.

Usage and cost ledger: output/analysis/api_cache/usage.jsonl. Recorded rates are applied to API-reported token usage. Ambiguous transport failures keep their cost reservation. Rates checked: 2026-09-28.

An embedding-free approach is possible but would need a separate theme-discovery procedure; earlier MiniLM results are not reused. This path links the user-specified OpenAI embeddings to source-grounded review.

Cache keys change when sources, prompts, models or the taxonomy change. Word and PDF are generated from the same content; PDF page boundaries and sections are checked. Whether the Word rendering was verified is recorded in publication_checks.json.


## Run cost

Estimated direct API cost for the current execution path: US$0.05–$0.05. On the subscription path only embeddings incur API cost; assumptions are in cost_estimate.json. This is not a guaranteed ceiling. Charged/reserved increase in this run: US$0.0000. Cumulative workspace charged/reserved: US$0.0394. Actual token usage and unresolved reservations are in cost_summary.json and usage.jsonl. These are not invoiced amounts.
