# 실행 전 결함 검증·수정

기준 커밋: `4cf6ad8`. 유료 호출·실제 OpenAI 클라이언트·실행 CLI를 사용하지 않았다. 기존 DB와 원본은 읽기만 했다. 재현 출력은 `output/workflow_defect_audit/reproduction_before.json`, 보호 대상 2,009개 파일의 해시는 `protected_before.json`에 저장했다.

## 1. 주제 분모 붕괴 — 확인됨

- 재현: 가상 AI 연설 24건, 코드 20개 중 하나만 두 판정이 불일치(5%). 기존 코드는 **모든 코드의 N=0**. 실제 모델의 불일치율을 측정한 결과는 아니지만 결함은 확정적으로 재현됐다.
- 수정: 코드별 Yes OR → 1, AI 검토 완료 및 해당 코드 전체 No → 0, 나머지 NA. 주제 N·공동 언급의 두 코드 공통 N·연도별 코드 공통 패널을 따로 계산한다. 새 개념은 기존 분류를 무효화하지 않고 `review_queue.csv`에 남긴다. 보고서의 차트·분모 설명과 한국어 방법 메모도 수정했다.
- 수정 후: 불일치 코드 N=0, 나머지 19개 코드 N=24. 다른 코드의 불일치가 확정 No까지 무효화하지 않는다. 한 구절이 Uncertain이어도 다른 구절의 확정 Yes는 유지한다.
- 테스트: `test_one_disputed_code_preserves_other_code_denominators`, `test_zero_requires_only_its_code_no_and_complete_ai_review`, `test_uncovered_concept_is_queued_without_invalidating_codes`, `test_matched_panel_uses_each_codes_common_resolved_countries`.
- 프로토콜: `ANALYSIS_PROTOCOL.md`의 분모 정의를 명시적으로 변경했다. **세 번째 조정 판정은 구현·활성화하지 않았다.** 불일치는 그대로 Uncertain이며 자동 검토는 인간 검증이 아니다. 코드별 표본이 달라지는 만큼 N과 unknown을 함께 해석해야 한다.

## 2. 인용 부호 차이 — 확인됨

- 재현: `quote_in("Secretary-General's", "the Secretary‑General’s report")`는 기존 코드에서 False였다.
- 수정: 비교할 때만 NFKC·따옴표·하이픈/대시·공백을 정규화한다. 원문과 저장된 인용은 그대로 둔다. 대소문자 변경·단어 생략·재배열·의역·불연속 인용은 허용하지 않는다.
- 테스트: `test_typographic_variants_match_without_changing_inputs`, `test_nfkc_dashes_and_whitespace_are_comparison_only`, `test_normalization_does_not_allow_paraphrases_or_discontinuous_quotes`.
- 한계: 정확 일치는 이제 명시된 문자 정규화 후의 연속 일치이다. 내용이 다른 인용은 여전히 검증 실패하며 이를 근거로 No를 채우지 않는다.

## 3. 잘린 응답의 반복 과금 — 확인됨

- 재현: 가짜 client가 `max_output_tokens` incomplete를 반환하도록 했다. 같은 `json` 요청 두 번과 같은 `review_speech` 두 번 모두 ValueError, 총 4회 요청·모의 정산 $0.1083. 실제 비용은 발생하지 않았다.
- 수정: 잘림·거부 결과도 요청 해시로 캐시하고 정산은 한 번만 한다. 텍스트 검토 묶음은 문맥을 유지하며 재귀적으로 이등분한다. 한 구절에서도 잘리거나 거부되면 인용을 꾸미지 않고 미검토 Uncertain으로 남긴다. 분류 단계의 구절별 잘림·거부도 Uncertain이며 키워드 검토 완료로 오인하지 않는다. 모르는 실패 이유·네트워크 오류·예산 초과는 숨기지 않는다.
- 테스트: `test_incomplete_request_is_cached_and_charged_once_across_resume`, `test_truncation_splits_with_context_and_resume_reuses_all_requests`, `test_single_passage_truncation_or_refusal_is_uncertain_not_no`, `test_unclassified_refusal_does_not_become_empty_keyword_negative`, `test_unknown_incomplete_reason_stops_without_inventing_verdict`.
- 한계: 실패도 비용이 발생할 수 있다. 캐시된 실패는 같은 요청으로 재결제하지 않으며 모델·설정·입력이 바뀌면 새 요청이 된다. fallback Uncertain은 분석 근거 인용이 아니라 API 검토 실패 기록이다. `all_passages_attempted`와 `all_passages_reviewed`를 구분한다.

## 4. taxonomy 통합 요청 폭증 — 확인됨

- 재현: 1,500자 구절 900개·사용 불가능한 군집 구조에서 merge **1,450,105자**, audit **1,384,173자**, 각각 원문 900개가 들어갔다.
- 수정: 각 제안이 실제 인용한 passage_id의 원문만 보내고 해당 요청에 보낸 원문만으로 검증한다. `discovery.taxonomy_payload_max_chars=120000`을 추가했다. 초과하면 제안을 나눠 통합하고 다시 통합한다. audit도 필요한 원문만 포함하며 분할 가능하다. 재시도의 검증 피드백까지 문자 상한을 검사한다.
- 수정 후 같은 입력: merge **119,537자 / 6,669자 / 6,665자**, audit **3,400자**. 참조 원문은 각각 36/2/2/1개였다. 전체 900개에 대한 앞단 원문 검토는 유지한다.
- 테스트: `test_900_passage_fallback_bounds_merge_and_audit_to_cited_sources`, `test_uncited_source_is_rejected_even_if_present_in_original_corpus`, `test_single_oversize_proposal_stops_before_any_request`, `test_nonshrinking_merge_cannot_loop_forever`.
- 한계: 단일 제안 하나가 상한을 넘거나 통합이 수렴하지 않으면 근거를 잘라내지 않고 설명과 함께 중단한다. 상한은 JSON payload 문자 수이며 시스템 지시·schema·출력 토큰은 별도다. 군집은 최종 주제 판정으로 사용하지 않는다.
