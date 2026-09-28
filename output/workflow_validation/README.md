# 워크플로우 검증 자료 — 실제 분석 결과 아님

이 폴더는 가상 연설과 고정된 모형 응답으로 실행 경로를 확인한 결과다. 실제 국가의 입장·수치로 인용하지 않는다. OpenAI 유료 요청은 수행하지 않았다.

- `validation.json`: 테스트, DB 불변 해시, 무료 모델 접근 확인, Word/PDF 렌더링 근거.
- `synthetic/`: 전체 실행의 가상 입력·중간 산출물·보고서.
- `word_render_check.pdf`, `word_page_*.png`: 설치된 Microsoft Word에서 가상 DOCX를 실제 변환한 결과.
- `layout_stress/`: 본문 90단어 문단, 권고 5개, 지역 7개, 주제 8개, 제도 입장 9행, 모델 4행을 넣은 분량 점검. 공통 레이아웃 PDF와 실제 Word 출력 모두 4페이지.

현재 준비 상태는 `../workflow_readiness.json`, 실제 실행 안내는 `../../docs/ANALYSIS_WORKFLOW.md`를 참고한다. 의미 판정 품질·유료 API 추론·실제 보고서 내용의 검증은 실제 분석 실행 후 이루어진다.
