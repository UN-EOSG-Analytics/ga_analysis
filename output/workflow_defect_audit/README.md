# 실행 전 결함 검증 근거

기준: `4cf6ad8`. 실제 OpenAI 클라이언트·유료 API·`--execute` CLI 없이 검증했다. 가짜 client의 비용 정산 수치는 실제 청구가 아니다.

- `reproduction_before.json`: 수정 전에 재현한 다섯 항목의 출력.
- `discovery_after.json`: 수정 후 동일 900구절 입력의 merge/audit 크기.
- `cost_scenarios.json`, `.csv`: 실제 로컬 입력과 명시한 가정에 따른 단계별 비용. 실측 청구액·보장 상한이 아니다.
- `protected_before.json`, `protected_after.json`: 보호 대상 파일별 SHA256.
- `integrity.json`: 보호 대상 2,009개 파일의 추가·삭제·변경이 없음을 확인한 결과.
- `tests.txt`, `validation.json`: 전체 67개 테스트와 검증 대상 코드 해시.

수정 위치·테스트 이름·한계·사용자 결정 사항은 [WORKFLOW_DEFECT_AUDIT.md](../../docs/WORKFLOW_DEFECT_AUDIT.md)에 정리했다. 이번 검증 결과를 실제 국가별 AI 분석 결과로 사용하지 않는다.
