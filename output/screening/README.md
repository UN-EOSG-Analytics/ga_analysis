# AI 후보 검색

`python -m unga_analysis screen`으로 재생성한다. 원문을 추가한 뒤 `prepare`를 실행하면 후보 검색도 갱신한다. 외부 API와 임베딩은 사용하지 않는다.

| 파일 | 용도 |
|---|---|
| `ai_candidates.jsonl` | 검색어 적중, 주변 문맥, 원문 구절·위치, 출처 해시, 검토 필요 표시 |
| `speech_screening.jsonl` | 모든 국가–연도 발언의 검색 상태. 미적중도 Pending |
| `summary.json` | 검색 설정과 입력·등록부·코드 해시, 후보 수 |

검색어는 `config/ai_search_terms.json`에 있다. 명시적 AI 표현, 관련 개념, 문맥 확인이 필요한 약어, 간접 표현을 구분한다. `Super Intelligence`는 검색 대상 AI 관련 표현이며 모든 문맥에서 `Artificial Intelligence`와 같은 의미라고 가정하지 않는다. 일반적인 `intelligence`, `said` 안의 `ai`, `as I`는 AI/ASI 약어로 처리하지 않는다.

같은 구절에 여러 검색어가 적중할 수 있다. **적중 수는 국가 수·AI 언급 확정 수가 아니다.** 분석에서는 근거를 검토하고 국가–연도별로 한 번만 집계한다. `source_review_notes`도 후보에 전달되므로 PDF와 전사가 다른 부분의 검토 표시를 함께 읽는다.

유한한 검색어 목록만으로 모든 우회 표현·전사 오류의 누락을 보장할 수는 없다. 후보 문맥 검토와 미적중 발언의 누락 점검을 수행한 뒤 최종 AI/주제 판정을 확정한다. 현재 원문 및 AI·주제 레이블은 변경하지 않았다.
