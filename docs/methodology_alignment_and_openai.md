# Methodology 대조와 OpenAI 임베딩 연결 안내

확인일: 2026-09-25, America/New_York. 지침·설정 갱신만 수행했다. API 연결 구현, 임베딩, 재분류, 보고서 작성은 실행하지 않았다.

## 대조 결과

제시된 Methodology의 핵심 설계는 현재 ANALYSIS_PROTOCOL.md와 일치한다. 국가–연도당 주요 연설 한 건, 회원국과 맥락 자료 분리, 검토한 연설을 분모로 하는 AI 비율, 공식 UN regional groups 고정 매핑, 임베딩을 통한 주제 탐색, 원문 검토에 따른 복수 분류, 분류 완료 AI 언급 국가를 분모로 하는 주제 비율, 방향별 조건부 공동 언급, 불확실성 표기가 동일하다. 이는 계획의 일치이며 기존 UNGA_AI_Strategic_Report가 이 방법을 모두 수행했다는 의미는 아니다.

현재 지침에는 commitments의 독립 판정 기준, 전 연도 공통 taxonomy 적용과 변경 시 과거 분류 조정, 복수 주제 비율 합계의 100% 초과 가능성, 명시적인 권고 대상(UN/SPMU/Tech Envoy/Panel/Dialogue)을 보완했다.

제시된 영문 Methodology에는 다음 표현을 추가·조정하면 자료와 사용자 지시를 더 정확히 반영한다.

1. EN 우선: “Where multiple language versions are available, only the English version is analysed; if English is unavailable, one alternative-language version is selected.” 읽히지 않는 EN과 다른 연도에 해당하는 파일은 출처 확인 단계에서 보류한다.
2. 실제 발언과 제출본 구분: 현재 모든 PDF의 실제 전달 내용을 확인한 것은 아니므로 첫 문장을 “The review analyses available texts of Member State General Debate statements, distinguishing submitted statements from as-delivered transcripts.”로 조정한다. 주요 연설 범위 자체는 유지한다.
3. 임베딩: “Context-verified AI-related passages, together with necessary adjacent context, are embedded using OpenAI text-embedding-3-large and explored through agglomerative hierarchical clustering with cosine distance and average linkage.” 전체 연설문을 임베딩하는 계획이 아니다. 모델·차원·API 사용량은 실제 실행 후 확정 기록한다.
4. 근거 위치: “Key findings and quotations are traceable to source files and PDF pages or transcript paragraphs, lines or timestamps.” transcript에 가상의 PDF 페이지를 만들지 않는다.
5. 새 표현 추세: “Annual comparisons also identify substantively important AI terms and expressions that newly recur across countries, distinguishing first observation in the available corpus from actual historical emergence.” 누락 연도는 0으로 처리하지 않는다.
6. UN 배경: “Reports and notes in the reference folder inform institutional context; they are kept separate from Member State speech evidence and endorsement counts.” 초안·최종본·채택 결정의 지위를 구분한다.

## 사용할 모델과 API 단계

공식 [임베딩 가이드](https://developers.openai.com/api/docs/guides/embeddings)는 최신 계열로 `text-embedding-3-small`과 `text-embedding-3-large`를 안내한다. 이 프로젝트에는 영어 외 언어도 남으므로, 공식 [모델 설명](https://developers.openai.com/api/docs/models/text-embedding-3-large)이 영어·비영어 작업에서 가장 높은 역량으로 소개하는 `text-embedding-3-large`를 계획 설정으로 기록했다. 공식 설명을 바탕으로 한 선택이며 이 데이터에서 별도 품질 비교를 수행한 것은 아니다. 기본 차원은 3072이다.

흐름: EN 단일 판본 선택 → 로컬 추출/OCR → 넓은 AI 키워드 검색 → 원문 문맥 확인 → AI 구절과 필요 문맥만 **OpenAI Embeddings API** → 로컬 cosine/average 계층적 군집화·TF-IDF → taxonomy → 복수 주제 분류·원문 검토 → 집계.

검색 탈락 문단의 표본 검토는 누락 점검에 사용한다. 새 표현을 발견하면 사전을 보완하되, 일반적인 디지털 발언을 모두 AI로 간주하지 않는다. 임베딩은 지지/우려 판정이나 최종 주제 분류 결과를 반환하지 않는다. 분류용 LLM API는 별도 선택·비용이며 이번 모델 선택으로 함께 실행되지 않는다.

텍스트 벡터화의 호출 위치는 `POST https://api.openai.com/v1/embeddings` / Python SDK의 `client.embeddings.create(...)`다. 아래는 향후 연결을 설명하는 예시이며 실행 명령이 아니다.

```python
from openai import OpenAI

client = OpenAI()  # OPENAI_API_KEY 환경변수 사용
response = client.embeddings.create(
    model="text-embedding-3-large",
    input=verified_ai_passages,  # 검증한 구절 문자열 목록
    dimensions=3072,
    encoding_format="float",
)
```

실제 연결 시 토큰 제한, 배치 크기, 재시도, 사용량/비용 기록, 입력 순서와 근거 ID의 연결 및 캐시를 구현해야 한다. OpenAI SDK 설치·연결 코드는 아직 만들거나 실행하지 않았다. 이전 로컬 임베딩·보고서 생성 스크립트는 제거했으므로 현재 설정만으로 자동 분석이 시작되지 않는다.

## API 키를 넣는 위치

키 발급: [OpenAI Platform API keys](https://platform.openai.com/api-keys).

Windows에서 **환경 변수 편집 → 사용자 변수 → 새로 만들기**를 열어 이름에 `OPENAI_API_KEY`, 값에 발급한 키를 넣는다. 저장 후 VS Code와 터미널을 다시 열어 새 환경변수를 상속받게 한다. [OpenAI 공식 Quickstart](https://developers.openai.com/api/docs/quickstart)에 따라 SDK가 이 환경변수를 읽는다. `ANALYSIS_PROTOCOL.md`, `analysis.toml`, Python 소스나 채팅에 키를 적을 필요는 없다.

모델·차원·환경변수 이름은 `config/analysis.toml`에 있고, 비밀 키 자체는 환경변수에만 둔다. `additional_paid_api_allowed = false`와 실행 중단 상태를 유지했다. 키 등록만으로 프로그램이 실행되거나 과금되지는 않는다. 현재 코드는 `.env` 자동 로딩을 구현하지 않았으므로 `.env`에만 적으면 된다고 안내하지 않는다.

## 캐시와 비용

MiniLM(384차원) 벡터와 OpenAI(3072차원) 벡터를 섞지 않는다. 모델·차원·구절·전처리가 같을 때만 벡터를 재사용한다. 기존 원문·추출·검토 근거는 재사용할 수 있지만 새 모델을 택하면 분석 대상 AI 구절의 OpenAI 벡터를 전 연도에 걸쳐 새로 만들어야 한다. 기존 분류도 새 taxonomy와 선택 원문에 맞는지 확인한다.

확인일의 공식 모델 페이지 일반 이용료는 입력 100만 토큰당 $0.13이다. 예를 들어 실제 선택 구절이 10만 토큰이면 벡터화 입력료는 $0.013이다. 이는 설명용 산술 예시이며 현재 선택 구절의 확정 토큰 수가 아니다. EN 선택 보류 10건과 향후 2019·2026 입력을 반영한 AI 구절 목록으로 실제 실행 전에 토큰량과 최신 요금을 확인한다. 추가 유료 호출은 없었다.
