# 동료 검토용 공유 안내

## analysis_ready_en만 공유해도 되는가?

**텍스트·JSON 구조·중복 검토는 가능하지만, 원본 대조에는 부족하다.** 이 폴더는 국가별 추출본이다. 원본 파일, PDF 페이지, JSON pointer, TXT 줄 범위와 발언 경계가 정확한지 확인하려면 실제 회의 원본을 함께 제공해야 한다.

프로젝트 기준 상대 경로를 유지해 다음을 함께 공유한다.

| 경로 | 용도 |
|---|---|
| `data/analysis_ready_en/` | 국가별 추출 본문과 출처 위치 |
| `data/unga_general_debate_verbatim_en/` | 실제 PDF·JSON·TXT 원본 |
| `config/` | 활성 등록부·국가 목록·원문 정책·귀속 보정 근거 |
| `output/corpus_preparation/` | 범위·언어 예외·대조표·점검 결과 |
| `output/pipeline/` | 실제 분석 입력 `speeches.jsonl`과 추출 캐시 |
| `unga_analysis/` | 전처리·입력·점검 코드 |
| `ANALYSIS_PROTOCOL.md`, `ARCHITECTURE.md`, `pyproject.toml` | 분석 범위·방법과 의존성 정의 |

과거 비영어 제출 PDF 자체와 번역을 비교하거나 이전 언어 목록을 독립적으로 재계산하려면, `archive/cleanup_manifest.json`에서 해당 파일의 보관 위치를 찾아 추가로 공유한다. 현재 영어 속기록의 원본 대조에는 모든 옛 보관본이 필요하지 않다. 이번 작업에서 자료를 외부로 전송하지 않았다.

## 동료에게 확인을 요청할 항목

2025년 제출 PDF 재대조 결과는 [PDF 검토표](pdf_2025_review.md)에 있다. 이 대조까지 재현하려면 `pdf_2025_comparison.csv`에 기록된 ZIP 보관본도 공유한다. `2025_VCT`의 PDF 추가 AI 문단은 실제 낭독 여부를 별도로 확인해야 한다.

1. 국가–연도당 회원국 주요 발언 한 건인지, 의장·사무총장·옵서버·답변권이 섞이지 않았는지 확인한다.
2. 발언 시작·끝, 문단 순서, 해시와 위치를 실제 원본과 비교한다.
3. 2019·2025·2026년은 전사를 확정 원문으로 사용한다. 자동전사 표시는 유지하고 발언자 직급별 분석은 하지 않는다.
4. `legacy_language_gap_resolution.csv`의 과거 영어 부재 건이 영어 속기록으로 연결되는지 확인한다.
5. `language_exception_review.json`의 비영어 구절 네 곳, 추가 언어 예외, ASR 표현을 검토한다.
6. `missing_country_years.csv`의 42건을 실제 미발언과 미확보로 구분한다. 2026년 마지막 날은 미수집이다.
7. `speeches.jsonl`의 구절을 다시 이었을 때 국가별 본문이 보존되는지 확인한다. AI·주제 판정은 현재 모두 Pending이다.

## 실행

Python 3.11 이상과 PyMuPDF가 필요하다. 프로젝트 루트에서:

```powershell
python -m unga_analysis status
python -m unga_analysis.preparation.audit
python -m unga_analysis.preparation.review
```

검토 명령은 원본·분석 입력을 읽고 `output/corpus_preparation/`의 점검 결과를 갱신한다. API 키나 모델 호출이 필요하지 않다. 검토만 할 때 데이터를 재생성하는 `prepare`는 실행할 필요가 없다.

보관본 없이 `review`를 실행하면 과거 언어 목록 재대조는 `archive_not_supplied`로 기록되며 기존 연결표는 덮어쓰지 않는다. 수동 언어 검토 기록은 자동 점검 결과와 함께 읽는다.

## 메인 Python 파일

| 역할 | 파일 |
|---|---|
| `python -m unga_analysis` 진입점 | `unga_analysis/__main__.py` |
| 명령 연결 | `unga_analysis/cli.py` |
| `prepare` 전체 흐름 | `unga_analysis/preparation/publish.py`의 `prepare()` |
| 국가별 발언 분리 | `unga_analysis/preparation/segment.py` |
| 공통 분석 입력 정규화 | `unga_analysis/pipeline.py` |
| 원본·입력 점검 | `unga_analysis/preparation/audit.py`, `review.py` |

로컬 AI 후보 검색은 `unga_analysis/screening.py`에 있다. 전체 분석 메인은 `unga_analysis/analysis/workflow.py`이며 `python -m unga_analysis analyze --execute --max-cost-usd 50`으로 문맥 검토부터 Word/PDF까지 실행한다. 실제 코퍼스 분석은 아직 실행 전이다. 동료가 분석 실행까지 검토하려면 `docs/ANALYSIS_WORKFLOW.md`, `requirements-analysis.txt`, `tests/`도 함께 제공한다. `.env`는 공유하지 않는다.
