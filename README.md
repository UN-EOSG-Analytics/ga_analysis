# UNGA AI analysis

현재 상태: **2019·2026 사용자 자료 대기 / 분석 실행 중단 / 지침에 맞춘 입력 구조만 활성화**.

- 구조와 결정사항: [ARCHITECTURE.md](ARCHITECTURE.md)
- transcript 입력 계약: [docs/transcript_input_contract.md](docs/transcript_input_contract.md)
- 설정: [config/analysis.toml](config/analysis.toml)
- 공식 국가–그룹 매핑: [config/un_regional_groups.csv](config/un_regional_groups.csv)
- Methodology 대조와 OpenAI API 키 위치: [docs/methodology_alignment_and_openai.md](docs/methodology_alignment_and_openai.md). 다음 임베딩은 AI 구절과 필요 문맥만 OpenAI `text-embedding-3-large`로 처리하는 계획이며 API 연결·실행은 아직 하지 않았다.

Python 3.11 이상에서 프로젝트 루트 기준:

```powershell
python -m unga_analysis status
python -m unittest discover -s tests -v
```

현재 입력 계층은 표준 라이브러리로 실행한다. 신규 PDF 추출에만 `PyMuPDF`가 필요하며, 기존 PDF는 검증된 텍스트 캐시를 사용한다. 현재 구조 작업은 유료 서비스나 모델 API를 호출하지 않는다.

## 다른 컴퓨터에서 이어서 작업하기

저장소에는 원문 PDF(`data/`), 참고문서(`reference/`), 추출·OCR·검토 캐시(`cache/`), OCR 언어 데이터(`models/tessdata/`)가 모두 들어 있다. `.gitattributes`가 줄바꿈 변환을 막으므로 캐시 해시 검증이 그대로 통과한다. 원래 PC의 `.deps/`(Windows 전용 설치 패키지)와 사용하지 않는 MiniLM 모델은 올리지 않았다.

```powershell
git clone <repository-url> ga_analysis
cd ga_analysis
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests # 22개 테스트 통과 확인
python -m unga_analysis status
```

- OpenAI 임베딩을 실행할 때: `pip install openai`, 그리고 새 PC에 환경변수 `OPENAI_API_KEY`를 설정한다(키는 저장소에 넣지 않는다). 방법은 [docs/methodology_alignment_and_openai.md](docs/methodology_alignment_and_openai.md) 참조.
- 새 PDF에 OCR이 필요할 때만 Tesseract 프로그램을 따로 설치하고 `models/tessdata/`를 언어 데이터로 사용한다.
- 현재 진행 상태와 남은 작업은 [ANALYSIS_PROTOCOL.md](ANALYSIS_PROTOCOL.md)의 Scope and status, [output/cleanup/STATUS.md](output/cleanup/STATUS.md)에 있다.

실제 transcript를 받은 뒤 작성한 manifest를 등록:

```powershell
python -m unga_analysis register path/to/new_sources.jsonl
# config/analysis.toml에서 출처 확인을 마친 연도의 awaiting 상태를 갱신
python -m unga_analysis ingest --year 2026
```

`ingest`는 **텍스트 정규화만** 수행한다. 정책 분류가 완료됐다고 표시하지 않는다. 특정 기존 PDF 하나의 캐시 재사용 점검은 `python -m unga_analysis ingest --source-id legacy_pdf_2025_CRI`처럼 실행할 수 있다.

원본 `data/`와 `reference/`는 그대로다. 재사용 추출·OCR·검토 근거는 `cache/`에 두고 현재 manifest와 새 taxonomy를 확인한 뒤 사용한다. 옛 보고서 생성·로컬 임베딩·외부 2026 분석·기존 결과표 수입 코드는 제거했다. 정리 기록은 `output/cleanup/`에 있다.

현재 구현 범위는 입력 등록·정규화, EN 우선 규칙, UN regional groups 매핑, 근거와 분류 검증이다. OpenAI 호출·의미 탐색·최종 통계와 보고서는 아직 구현/실행되지 않았다. `config/theme_taxonomy.json`은 검토 전 빈 상태이며, 이전 코드북을 확정 주제로 사용하지 않는다.
