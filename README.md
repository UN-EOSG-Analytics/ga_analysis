# UNGA 영어 속기록 분석

**분석 입력:** `output/pipeline/speeches.jsonl`. 모든 연도를 같은 국가–연도·구절 구조로 읽는다. 2019년 공식 속기록과 2025·2026년 자동전사를 원문으로 확정했으며, 별도 국가별 PDF 확보를 기다리지 않는다. 2026년 마지막 날은 아직 미수집이다.

- [현재 자료 범위와 상태](output/corpus_preparation/README.md)
- [분석 방법·보고서 요구사항](ANALYSIS_PROTOCOL.md)
- [구조와 실행 흐름](ARCHITECTURE.md)
- [분석 시작부터 Word/PDF까지 실행 안내](docs/ANALYSIS_WORKFLOW.md)
- [원본 형식과 근거 위치](docs/transcript_input_contract.md)

## 실행

### OpenAI API 키

프로젝트 루트의 `.env` 파일에서 `OPENAI_API_KEY=` 뒤에 실제 키를 넣고 저장한다. `.env`는 Git에서 제외된다. 연결 확인 스크립트는 이 파일을 자동으로 읽으며, 같은 이름의 터미널 환경변수보다 `.env` 값을 우선한다.

```dotenv
OPENAI_API_KEY=여기에_실제_API_키
```

**API는 임베딩에만 사용한다.** 문맥 검토·주제 해석·분류·보고서는 구독으로 로그인한 Codex(Astra High 선택 가능 시)에서 처리하고, 군집·집계·파일 생성은 로컬 Python에서 수행한다. 현재 후보 기준 직접 API 비용은 약 $0.05이며 기본 누적 상한은 $1이다.

준비 확인: `python -m unga_analysis analyze`. 시작 지시 후 Codex가 `python -m unga_analysis analyze --execute --max-cost-usd 1`을 사용한다. Python이 검토 요청을 파일로 넘기면 Codex 세션이 읽고 답을 저장한 뒤 재개한다. 생성 API로 자동 전환하지 않는다. Day 6 제공·구독 인증·재개 절차는 [분석 워크플로우](docs/ANALYSIS_WORKFLOW.md)를 따른다.

### 데이터 준비

Python 3.11 이상, 프로젝트 루트에서:

```powershell
python -m unga_analysis status
```

현재 분석 입력은 생성되어 있다. 원문을 추가하거나 전처리 규칙을 바꾼 경우에만 다음 명령으로 다시 준비한다. PDF 추출에는 `requirements.txt`의 PyMuPDF가 필요하다.

```powershell
python -m unga_analysis prepare
```

`prepare`는 국가별 분리 → 대표본 선택 → 공통 구절 생성 → 해시·위치·본문 보존 확인 → 로컬 AI 후보 검색을 수행한다. 실패 시 오류를 남긴다. 분석에서는 `data/`를 재귀 검색하지 않고 활성 등록부와 위 JSONL만 사용한다. 검색만 갱신하려면 `python -m unga_analysis screen`을 사용한다.

## 폴더

| 경로 | 용도 |
|---|---|
| `data/unga_general_debate_verbatim_en/` | 보존하는 원본 PDF·JSON·TXT |
| `data/analysis_ready_en/` | 원본 위치를 가진 국가별 영어 발언 |
| `config/` | 활성 등록부·원문 선택 정책·지역 매핑·분석 설정 |
| `unga_analysis/` | 전처리·입력·분류 계약·집계 규칙 |
| `output/pipeline/` | 분석에 사용하는 공통 입력 |
| `output/corpus_preparation/` | 현재 자료 범위와 준비 결과 |
| `output/screening/` | 원문 위치를 가진 AI 표현·관련 개념 후보와 미검토 상태 |
| `output/analysis/` | 실행별 분석 결과·API 캐시·사용량·검토 근거 |
| `reference/` | 보고서의 제도적 배경 문서 |
| `cache/` | 현재 원문 추출 및 참고문서 캐시 |
| `archive/` | 이전 제출 PDF·캐시·수집 스크립트·감사 기록의 복구용 보관본 |
| `deliverables/` | 향후 최종 보고서 |

자동전사는 분석에 포함하지만 출처·정확성 미검토 표시를 유지한다. 정규화 DB의 AI·주제 판정은 `Pending`이며 실행 결과는 별도 분석 폴더에 저장한다. 분석 워크플로우는 구현·오프라인 검증했고 실제 코퍼스 임베딩·분류·최종 보고서는 아직 실행하지 않았다. 현재 자료 조건은 2026년 Day 6 대기다.
