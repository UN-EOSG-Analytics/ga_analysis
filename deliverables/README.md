# 분석 보고서

실제 DB 분석은 시작 지시를 기다리고 있다. 2026 Day 6 자료를 받은 뒤 Codex 구독 세션이 `python -m unga_analysis analyze --execute --max-cost-usd 1`로 시작하고, 파일로 전달된 검토·분류·보고서 요청을 처리하며 재개한다. API는 임베딩만 사용하고 완료된 결과를 이 폴더에 저장한다.

- `<run-id>/UNGA81_AI_Strategic_Review.docx` 및 `.pdf`: 영어 4–6페이지 보고서.
- `<run-id>/publication_checks.json`: 페이지 수, 섹션, Word 렌더링 확인 결과.
- `<run-id>/report_page_*.png`: 최종 페이지 시각 검토용 이미지.
- `latest.json`: 최신 보고서와 근거 자료 위치.

자동 검토와 인간 검수는 구분한다. 최종 전달 전 생성된 페이지를 확인한다. 가상 자료로 만든 실행 검증 결과는 `output/workflow_validation/`에 있으며 실제 분석 보고서가 아니다.

실행 방법과 비용·재개 안내: [ANALYSIS_WORKFLOW.md](../docs/ANALYSIS_WORKFLOW.md).
