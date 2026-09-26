# 지침 기준 정리 결과

구식 실행 코드·보고서·통계·군집 결과 등 160개 파일을 삭제했다. 이전 재현 ZIP과 복제된 코드도 삭제했다. 남은 활성 Python 코드는 `unga_analysis/`, `scripts/build_un_groups.py`, `tests/`다.

**남은 삭제 1건:** `deliverables/UNGA_AI_Strategic_Report.docx`는 다른 프로그램에서 사용 중이어서 삭제하지 못했다. 사용자에게 Word/미리보기를 닫아 달라고 요청했다. 문서를 강제 종료하거나 저장되지 않은 편집 내용을 버리지 않았다. 파일이 닫히면 현재 삭제 계획의 해시와 대조한 뒤 제거해야 한다. 현재 지침을 적용한 최종 보고서로 사용하면 안 된다.

초기 폴더 단위 재귀 삭제 계획은 자동 승인 검토에서 재사용 캐시 등 삭제 범위가 넓다는 이유로 거부됐다. 해당 계획은 `removal_plan.json`에 rejected/superseded로 표시했다. 이후 원문·추출·OCR·검토 기록·테스트·도구 자산을 보존하는 파일 단위 계획으로 범위를 줄여 실행했다. 실행 결과는 `removal_results.json`에 기록했다.

보존·검증 사항:

- `data/` 원본 PDF 1,797개와 `reference/` 문서 3개를 보존했다.
- 추출·OCR·원문 검토 근거는 `cache/`에 분리했고 1,329개 캐시 등록 항목의 파일 해시를 검증했다.
- 국가·연도 source ID는 유지했다. manifest의 추출 캐시 경로를 갱신하고 옛 AI/주제 판정 필드를 제거해 현재 분류를 Pending으로 명시했다.
- EN이 있는 비영어 대표본 10건의 보류 상태와 2019·2026 자료 대기를 유지했다.
- 옛 결과표 import/regroup 명령을 제거했다. 현재 taxonomy는 빈 pending 상태이며 기존 검토 기록을 자동 확정 분류로 취급하지 않는다.
- 테스트 20개, 현재 Python 문법 검사, manifest의 모든 원본 파일 경로와 추출 캐시 해시 검증을 통과했다.
- API 호출, 임베딩, 재분류, 통계·보고서 생성은 실행하지 않았다.

`preserved_cache_manifest.json`은 분리한 자료의 원래 경로·보존 경로·해시를, `retained_moves.json`은 원래 자료 묶음의 이동을, `narrowed_removal_plan.json`은 실제 삭제 대상 파일을 기록한다. 활성 코드가 `cache/retained_inputs/`의 이전 판정이나 외부 2026 자료를 자동 수입하는 경로는 없다.
