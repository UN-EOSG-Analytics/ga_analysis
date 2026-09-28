# 전사·PDF 공통 입력 계약

## 확정 원문

2019년을 포함한 2017–2024년은 공식 영어 PV 회의록, 2025·2026년은 영어 자동전사를 원문으로 사용한다. 사용자가 자동전사를 분석 원문으로 확정했으므로 국가별 제출 PDF는 필수 조건이 아니다. 출처 종류와 정확성 검토 상태는 별도 필드로 남긴다.

회의 파일은 `data/unga_general_debate_verbatim_en/`에 원본 그대로 보존한다. `python -m unga_analysis prepare`가 국가별 발언을 `data/analysis_ready_en/YYYY/YYYY_ISO3.json`으로 분리한 뒤 `output/pipeline/speeches.jsonl`로 정규화한다.

## 원본 형식별 처리

| 원본 | 분리 기준 | 보존하는 근거 위치 |
|---|---|---|
| 공식 PV PDF | 발언자·의장 소개·부록, 열 순서 | `pdf_page`, `pdf_block`, `bbox` |
| UN ASR JSON | `/transcript/data`의 발언자 소속과 문단 | `json_pointer`, `start`, `end`, `statement_start` |
| UN ASR TXT | `국가 · 직함 · 이름 [시각]:` 표제와 빈 줄 | `line_start`, `line_end`, `speaker_line`, `statement_timestamp` |

TXT 날짜·언어·표제 구조를 확인하고, 국가는 명시된 소속명을 공식 코드에 연결한다. 답변권과 의장·옵서버 발언은 제외한다. 인식하지 못한 표제·국가나 서로 다른 원문 충돌은 예외로 남긴다. 2025년 마지막 날의 교황청 발언 및 폐회사 뒤 답변권은 주요 회원국 연설에 포함하지 않는다.

TXT 시각은 발언자 표제의 시각이다. 해당 문단의 정확한 음성 구간이나 PDF 페이지 번호를 만들어 넣지 않는다. 원본 JSON의 시간 단위도 그대로 보존한다.

## 공통 연설과 구절

분석에서는 국가 대표의 주요 일반토의 발언을 해당 국가의 대표 입장으로 처리한다. 직급별 분류·비교·가중치를 적용하지 않으며, 이름과 원문 소개는 출처 확인에만 사용한다. 직함이나 이름이 없는 전사 표제도 국가와 주요 발언 범위를 확인할 수 있으면 처리한다.

- 기본 키: `speech_id=YEAR_ISO3`. 한 국가–연도에는 하나의 `accepted` 대표본만 허용한다.
- `source_type`: `official_transcript` 또는 `automatic_transcript`.
- 자동전사 원문 선택: `source_acceptance=user_confirmed_primary`.
- 자동전사 정확성: `text_accuracy=unverified_automatic_transcription`. 이는 원문 선택을 취소하거나 분석 입력에서 제외하는 상태가 아니다.
- 원본 추적: `origin_file`, `origin_sha256`; 국가별 추출본 추적: `path`, `sha256`.
- 모든 구절은 원본 위치와 추출 문단 번호(`extracted_block`), 그 문단 안의 문자 범위(`char_start`, `char_end`, 0부터 시작·끝 제외)를 가진다.
- 구절은 최대 350단어·3,000문자로 나눈다. 가능하면 문장 끝에서 자르고, 중복 문맥을 삽입하거나 내용을 교정하지 않는다. 문자 범위는 추출 블록의 `text`를 기준으로 한다.
- AI 판정, 텍스트 검토, 주제 분류는 `Pending`으로 시작한다. 원문 확정은 분석 판정 완료가 아니다.

JSONL 구절의 `source_file/source_sha256`은 국가별 추출본을, `locator.origin_file/origin_sha256`은 회의 원본을 가리킨다. 보고서 근거에는 원본 위치를 사용한다. 후속 임베딩·분류는 `passage_id`를 참조하고 모든 연도에 같은 처리 규칙을 적용한다.

## 추가 자료 반영

2026년 마지막 날을 받으면 기존 전사 폴더에 `UNGA2026_day6_EN_ASR.txt` 또는 같은 이름의 `.json`으로 보존하고 `prepare`를 실행한다. 수집 완료 여부를 확인한 뒤 `config/analysis.toml`의 `partial_years`를 갱신한다. 기존 원본을 다른 내용으로 조용히 덮어쓰지 않는다.

일반 단일 연설 TXT/DOCX/JSON/JSONL 입력 어댑터도 유지하지만, 전체 회의 파일을 한 국가로 등록해서는 안 된다. 지원하지 않는 구조는 전용 분리 규칙을 먼저 추가한다. 빈 문서·잘못된 위치·혼합 발언·해시 불일치는 오류로 처리하며 미언급으로 집계하지 않는다.
