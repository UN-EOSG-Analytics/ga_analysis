# Transcript 입력 계약

실제 2026 파일 형식은 아직 정해지지 않았다. 원본을 이 형식으로 강제 변환하도록 사용자에게 요구하지 않는다. 파일을 받은 뒤 기존 adapter를 선택하거나 adapter 하나를 추가한다. 분류·집계 코드는 바꾸지 않는다.

## 파일 등록

`config/source_manifest.jsonl`의 한 행은 국가–연도 연설의 **한 버전**이다. 기본 키는 `speech_id=YEAR_ISO3`, 버전 키는 `source_id`다. 국가·연도·주요 일반토의 연설 여부를 파일명으로 추측하지 않고 등록 정보와 내용으로 확인한다.

필수 필드와 타입은 `schemas/source_manifest.schema.json` 및 실행 검증 코드 `unga_analysis/contracts.py`가 정의한다. 발언자, 정확한 직급, 일자를 확인하지 못하면 null/unknown으로 남긴다. `head_unspecified`는 기존 정상급 판정만 있고 국가원수/정부수반 구분은 아직 확인되지 않았다는 의미다.

기본 예시 구조는 다음과 같다. 아래는 형식 예시이며 실제 연설·국가 입장 데이터가 아니다.

```json
{
  "source_id": "2026_ISO_version1",
  "speech_id": "2026_ISO",
  "country_iso3": "ISO",
  "year": 2026,
  "path": "data/incoming/2026/supplied_file.txt",
  "format": "txt",
  "source_type": "official_transcript",
  "speech_kind": "main_general_debate",
  "entity_type": "member_state",
  "status": "pending",
  "representative": false,
  "speech_date": null,
  "speaker_name": null,
  "speaker_rank": "unknown",
  "language": "en"
}
```

`ISO`는 예시 자리표시자다. 실제 등록 때 공식 국가 코드를 사용한다. 공식 transcript 여부도 실제 제공 문서에 따라 확인하며 자동전사라면 `automatic_transcript`로 등록한다. 등록 명령은 파일 존재와 해시를 확인한다. accepted/representative 상태 변경은 원문과 버전 확인 후 수행한다. 같은 국가–연도에 accepted 대표본이 둘이면 실패한다.

## 수용 형식과 위치 정보

| 원본 | Adapter가 읽는 구조 | 근거 위치 |
|---|---|---|
| PDF | 기존 페이지 텍스트 캐시 우선, 신규 자료만 로컬 추출 | 실제 PDF 페이지와 추출/OCR 방식 |
| TXT | 빈 줄로 구분된 문단, UTF-8 기본 | 원본 줄 시작·끝 |
| DOCX | 문서 본문의 문단 | 문단 번호; PDF 페이지를 만들지 않음 |
| JSON | `text`, `paragraphs`, `segments` 중 명시된 구조 | 원본 문단 번호와 제공된 start/end/timestamp |
| JSONL | 한 줄당 text/문단 객체 | 선택 범위 내 문단 번호; 명시된 기록 범위와 원본 파일 |

JSON의 원문이 더 깊은 위치에 있으면 `selector.json_pointer`로 특정 연설 블록을 지정한다. 예: `/transcript/data/12`. JSONL의 일부 기록을 사용할 때는 1부터 시작하는 `record_start`와 `record_end`를 지정한다. 실제 미지원 구조는 오류로 남기며 전사 형식을 임의로 추정하지 않는다.

JSON 문단은 문자열 또는 `{ "text": "...", "start": "00:12:01", "end": "00:12:11" }` 형태를 지원한다. `sentences` 아래 text가 있는 블록도 지원한다. 시간 단위는 원본 그대로 보존한다. 회의 전체 transcript는 발언자별 범위를 먼저 등록해야 하며, 서로 다른 country 또는 `right_of_reply`/진행 발언이 섞이면 주요 연설로 처리하지 않는다. 이름만 있는 발언자 구분 등 실제 파일의 다른 구조는 파일 수령 후 별도 매핑한다.

DOCX 표 안에만 전사가 있거나 이미지형 DOCX인 경우 현재 adapter 범위를 벗어난다. 이런 입력은 확인 후 확장하며, 누락 텍스트를 AI 미언급으로 처리하지 않는다.

## 공통 출력

각 정규화 연설에는 출처 종류, 원본 해시, 발언자 메타데이터, UN regional group 및 `passages`가 붙는다. Passage는 text, locator, source_file, source_sha256을 보존한다. 추출만 마친 문단의 AI/주제 판정은 `Pending`이다.

다음 단계의 청크는 이 passage의 ID와 문자 범위를 참조한다. 최종 주제 분류는 모든 코드에 대해 Yes/No/Uncertain/Pending을 명시하고, Yes에는 원문 근거가 필요하다. 분류 전·불확실 값을 No로 자동 치환하지 않는다. PDF와 transcript는 이후 동일한 Discover → Classify → Aggregate 경로로 들어간다.
