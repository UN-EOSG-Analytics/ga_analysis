# 실행 전 결함 검증·수정

기준 커밋: `4cf6ad8`. 유료 호출·실제 OpenAI 클라이언트·실행 CLI를 사용하지 않았다. 기존 DB와 원본은 읽기만 했다. 재현 출력은 `output/workflow_defect_audit/reproduction_before.json`, 보호 대상 2,009개 파일의 해시는 `protected_before.json`에 저장했다.

## 1. 주제 분모 붕괴 — 확인됨

- 재현: 가상 AI 연설 24건, 코드 20개 중 하나만 두 판정이 불일치(5%). 기존 코드는 **모든 코드의 N=0**. 실제 모델의 불일치율을 측정한 결과는 아니지만 결함은 확정적으로 재현됐다.
- 수정: 코드별 Yes OR → 1, AI 검토 완료 및 해당 코드 전체 No → 0, 나머지 NA. 주제 N·공동 언급의 두 코드 공통 N·연도별 코드 공통 패널을 따로 계산한다. 새 개념은 기존 분류를 무효화하지 않고 `review_queue.csv`에 남긴다. 보고서의 차트·분모 설명과 한국어 방법 메모도 수정했다.
- 수정 후: 불일치 코드 N=0, 나머지 19개 코드 N=24. 다른 코드의 불일치가 확정 No까지 무효화하지 않는다. 한 구절이 Uncertain이어도 다른 구절의 확정 Yes는 유지한다.
- 테스트: `test_one_disputed_code_preserves_other_code_denominators`, `test_zero_requires_only_its_code_no_and_complete_ai_review`, `test_uncovered_concept_is_queued_without_invalidating_codes`, `test_matched_panel_uses_each_codes_common_resolved_countries`.
- 프로토콜: `ANALYSIS_PROTOCOL.md`의 분모 정의를 명시적으로 변경했다. **세 번째 조정 판정은 구현·활성화하지 않았다.** 불일치는 그대로 Uncertain이며 자동 검토는 인간 검증이 아니다. 코드별 표본이 달라지는 만큼 N과 unknown을 함께 해석해야 한다.
