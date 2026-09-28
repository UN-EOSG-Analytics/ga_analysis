# OpenAI 분석 연결과 방법

최신 실행 안내는 [ANALYSIS_WORKFLOW.md](ANALYSIS_WORKFLOW.md)이다. 이전의 “연결 코드 미구현”, “환경변수만 가능” 안내는 현재 상태에 해당하지 않는다.

## 구현된 경로

Codex 구독의 전체 연설 문맥 검토 → `.env` 키로 AI Yes 구절 임베딩 API → 로컬 cosine/average 군집 → 구독 세션의 taxonomy·분류·보고서 → 로컬 집계·Word/PDF 생성. API는 임베딩만 허용한다.

- 임베딩: `text-embedding-3-large`, 3,072차원.
- 문맥 검토·분류·taxonomy·보고서: 구독으로 로그인한 Codex, Astra High 선호(계정에서 선택 가능할 때). 실제 모델 메타데이터와 구조화 응답을 파일로 남긴다.
- 구독 연결: `unga_analysis/analysis/subscription.py`. Python이 대기 작업을 내보내면 Codex 세션이 읽고 응답하고 재개한다. 구독 인증을 API 인증으로 바꾸지 않는다.
- OpenAI 어댑터: `unga_analysis/analysis/provider.py`.
- 전체 실행: `unga_analysis/analysis/workflow.py`.
- 키: 프로젝트 루트 `.env`의 `OPENAI_API_KEY=` 뒤에 저장. 키는 Git·로그·보고서에 포함하지 않는다.

기존 canonical DB는 유지하며 분석 결과는 `output/analysis/`에 별도로 저장한다. 모델·입력·프롬프트·출처·taxonomy가 같은 경우에만 관련 캐시를 재사용한다. 지역 매핑 변경만으로 임베딩을 다시 계산하지 않는다. 이전 MiniLM 벡터와 OpenAI 벡터를 혼합하지 않는다.

## 실행과 검증의 차이

`python -m unga_analysis analyze`는 무과금 사전 점검이다. `--execute`는 시작 지시 후 로컬·구독 파일 작업과 허용된 임베딩 API를 진행한다. 기본 직접 API 누적 상한은 US$1이며 예상 청구액이 아니다. `api_scope="embeddings_only"`는 생성 API를 호출 전에 차단한다. 구독 모델은 앱에서 선택하며 Python 설정만으로 구독 세션이 자동 실행되지는 않는다.

로컬 테스트와 가짜 자료의 전체 실행, Word/PDF 렌더링을 확인했다. 무료 모델 조회로 키와 모델 접근을 확인했지만 실제 코퍼스의 유료 검토·임베딩은 아직 실행하지 않았다. 자동 두 번째 검토를 인간 검수나 사람 간 일치도로 표현하지 않는다.

## 공식 API 근거와 기록 단가

2026-09-28 공식 문서를 확인했다.

- [OpenAI 임베딩 가이드](https://developers.openai.com/api/docs/guides/embeddings): Embeddings API와 차원 설정.
- [text-embedding-3-large](https://developers.openai.com/api/docs/models/text-embedding-3-large): 입력 100만 토큰당 $0.13.
- [구독과 API 인증 구분](https://learn.chatgpt.com/docs/auth): 구독 작업은 ChatGPT 로그인 경로를 사용한다.
- [Codex 모델 선택](https://learn.chatgpt.com/docs/models): 실제 사용 가능 모델·추론 설정은 계정·앱에 따른다.

실제 비용은 응답 사용량과 기록 단가로 계산한다. 요청 전 보수적인 비용을 예약하고, 응답 사용량으로 정산한다. 연결 실패로 과금 여부가 불명확하면 예약분을 유지한다. `cost_summary.json`과 `api_cache/usage.jsonl`은 분석의 사용량 기록이며 공급자의 최종 청구서를 대체하지 않는다.
