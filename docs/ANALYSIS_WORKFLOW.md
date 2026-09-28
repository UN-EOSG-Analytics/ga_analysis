# 분석 실행 워크플로우

## 현재 상태

**실행 전 결함 수정 완료. 실제 DB 분석은 아직 실행하지 않았다.** 기존 47개 테스트가 놓친 분모·문자 인용·응답 잘림·요청 크기·비용 추정 문제를 재현하고 수정했으며, 현재 테스트 67개가 통과했다. 보호 대상 2,009개 파일은 전후 SHA256이 같다. 이번 검증에서는 실제 OpenAI 클라이언트와 유료 호출을 사용하지 않았다. 앞선 모델 메타데이터 접근 및 Word/PDF 렌더링 기록은 유료 추론 검증과 구분한다.

최신 기계 판독 결과: `output/workflow_readiness.json`. 결함별 재현·수정 근거: [WORKFLOW_DEFECT_AUDIT.md](WORKFLOW_DEFECT_AUDIT.md) 및 `output/workflow_defect_audit/`. 이전 가상 보고서와 Word 렌더링 기록은 `output/workflow_validation/`에 있으며 실제 분석 결과가 아니다.

## 사용자가 할 일

1. `.env`의 `OPENAI_API_KEY`를 저장한다. 현재 환경에서는 확인되었다.
2. 2026년 Day 6 영문 전사 TXT 또는 JSON을 제공한다.
3. “분석 시작해서 리포트 줘”라고 요청한다.

그 뒤에는 문맥 검토·taxonomy 작성·분류 파일을 사용자가 수동으로 채울 필요 없이 아래 실행 경로가 처리한다. 불확실한 내용은 검토 대기표와 보고서 한계에 남기며, 확인하지 않은 내용을 확정하지 않는다.

## 명령

유료 호출 없이 준비 상태만 확인:

```powershell
python -m unga_analysis analyze
```

Day 6가 기존 원문 폴더에 들어 있으면:

```powershell
python -m unga_analysis analyze --execute --max-cost-usd 50
```

다른 위치에 받은 파일도 한 번에 반영할 수 있다:

```powershell
python -m unga_analysis analyze --execute --max-cost-usd 50 --final-day "C:\경로\2026_day6_en.txt"
```

`--execute`는 API 실행 승인이다. 기본 누적 비용 상한은 **US$50**이며 자동으로 올리지 않는다. 기존 약 $27 추정은 전체 검토 두 번만 포함하고 요청 구성 비용도 빠져 있어 폐기했다. 현재 DB의 실제 검토 요청은 **4,370회**, payload·지시·schema 합계 **63,493,527자**이다. 고유 스크리닝 후보 **666구절**을 분류 대상의 대용값으로 쓰며(매칭 1,349건과 다름), 실제 AI 판정 수는 실행 후에 알 수 있다.

출력·추론 합계가 요청당 900/2,000/3,000토큰인 시나리오의 **전체 단계** 추정은 각각 **$40.95–41.38 / $69.34–69.85 / $95.14–95.73**이다. 상세 단계별 표는 결함 검증 문서와 `output/workflow_defect_audit/cost_scenarios.csv`에 있다. 4자/토큰, 주제 12개·taxonomy 12,000자 등의 가정은 `config/analysis.toml`의 `[cost_estimation]`에 있다. 입력 크기는 단계별로 실측과 가정을 구분하며, 요약 대상 로컬 참고자료도 읽어서 계산한다. 분류 재시도·잘림으로 인한 분할·추가 통합·3,000토큰 초과 출력은 범위에 포함하지 않아 **보장 상한이 아니다**. 단가는 기존 설정에 기록된 값을 사용했으며 이번 작업에서 재조회하지 않았다.

## 소액 시범 실행 — 사용자 승인 후에만

아래 명령은 절차 안내이며 이번 검증에서 실행하지 않았다. 예산을 승인한 뒤 문맥 검토부터 소액으로 측정할 수 있다.

```powershell
python -m unga_analysis review --execute --allow-partial --max-cost-usd 3
```

상한에서 멈추어도 요청 캐시는 보존된다. 상한은 워크스페이스 **누적** 기준이라 이미 사용한 금액에 $3를 추가하는 옵션이 아니다. 실제 응답당 비용은 다음처럼 확인한다.

```powershell
$usage = Get-Content output/analysis/api_cache/usage.jsonl | ConvertFrom-Json
$usage | Where-Object state -eq 'settled' | Group-Object stage | ForEach-Object {
    $cost = $_.Group | Measure-Object actual_cost_usd -Sum -Average
    [pscustomobject]@{ stage = $_.Name; requests = $_.Count; total_usd = $cost.Sum; mean_usd = $cost.Average }
}
$usage | Measure-Object charged_or_reserved_usd -Sum
```

실제 정산과 미확정 예약을 분리해서 본다. 초기 연도 위주의 review 시범 결과만으로 AI 언급이 많은 연설·분류·보고서 비용까지 확정하지 않는다. 사용자가 전체 상한을 정한 뒤 같은 명령을 새 상한으로 재개한다. 세 번째 조정 판정은 추가하지 않았으며 불일치는 Uncertain을 유지한다.

Day 6 없이 실행하면 전체 연도 보고서를 만들기 전에 차단한다. 사용자가 부분 집계를 원할 때만 `--allow-partial`을 추가한다. 6일분이 정상적으로 분리·입력되면 수집 조건은 충족된 것으로 처리하되, 모든 회원국의 참가 명단 대조 완료를 주장하지 않는다.

## 자동으로 수행하는 단계

| 단계 | 수행 내용 |
|---|---|
| `review` | 전체 연설의 모든 구절을 두 번 자동 문맥 검토. 검색 미적중도 포함. 정확한 인용·검토 범위 확인, 불일치는 Uncertain |
| `discover` | AI Yes 구절·필요 문맥만 OpenAI 임베딩. 평균 중심화·cosine/average 계층적 군집과 여러 절단 비교. 대표·경계 구절을 읽어 공통 taxonomy 생성·재검토. 군집 구조가 끝내 부적합하면 전체 구절을 나누어 원문 검토 |
| `classify` | 구절별 모든 주제 판정, UN 메커니즘·입장·기능·기여 약속·표현 추출. 독립된 두 호출의 불일치는 불확실로 보존 |
| `aggregate` | 국가–연도·코드별 OR 집계. 주제 N은 AI 양성 국가 중 해당 코드가 1/0으로 확정된 국가 수이며, 공동 언급 N은 두 코드가 모두 확정된 국가 수. 연도 비교의 공통 국가도 코드별 산정. 미검토·불일치는 NA, 새 개념은 검토 대기표에 기록 |
| `report` | 참고자료 전체 추출·요약, 공식 UN 페이지 재조회, 근거 기반 초안과 재검토, 동일 내용의 영어 Word/PDF 생성 |

각 단계 이름도 CLI 명령으로 쓸 수 있다. 예: `python -m unga_analysis discover --execute --max-cost-usd 50`은 앞 단계를 거쳐 discovery까지 실행한다. 중간 API 요청·벡터는 캐시되므로 같은 명령으로 재개할 수 있다.

`config/theme_taxonomy.json`은 실행 전에는 비어 있어도 정상이다. `discover`가 실제 데이터에서 생성하고 원문 검토 근거와 버전을 저장한다. 미리 정한 주제를 임의로 채우지 않는다.

taxonomy 통합·재검토에는 제안의 예시에 인용된 구절 원문만 전달한다. JSON payload는 `discovery.taxonomy_payload_max_chars`(기본 120,000자)로 제한하며, 큰 제안 묶음은 여러 번 나누어 통합한다. 단일 제안도 너무 크거나 통합이 수렴하지 않으면 원문을 임의 삭제하지 않고 중단 사유를 남긴다.

## 비용·재개·출처

- OpenAI Embeddings: `text-embedding-3-large`, 3,072차원. 문맥·분류·보고서: `gpt-5.4-mini`.
- 입력·프롬프트·모델·schema가 같으면 응답 캐시를, 원문 해시·텍스트·모델·차원이 같으면 벡터 캐시를 재사용한다.
- 토큰 한도로 잘리거나 거부된 응답도 캐시한다. 전체 텍스트 검토 묶음을 절반씩 나누되 한 구절에서도 실패하면 미검토 Uncertain으로 남긴다. 재실행 시 같은 실패 요청을 다시 결제하지 않는다. 실제 원문 인용이 없는 API 실패를 분석 근거로 표시하지 않는다.
- `output/analysis/api_cache/usage.jsonl`은 토큰·기록 단가·비용 예약/정산 원장이다. 비용 상한은 워크스페이스 누적 기준이며 중단 후 재개해도 초기화하지 않는다. 실제 청구서와는 다를 수 있다.
- 불명확한 네트워크 실패는 최악의 예약 비용을 남겨 중복 지출을 보수적으로 계산한다. 키·인증 오류의 원문 응답은 출력하지 않는다.
- 동시 실행 잠금과 구절별 캐시가 있다. 한 실행 실패로 원문이나 이전 결과를 삭제하지 않는다.
- 정규화 DB는 읽기 전용으로 사용한다. 새 Day 6가 있을 때에만 기존 `prepare`로 추가 입력을 생성한다.

## 결과 위치

- `deliverables/latest.json`: 최신 Word/PDF와 근거 폴더 경로.
- `deliverables/<run-id>/UNGA81_AI_Strategic_Review.docx`, `.pdf`: 영어 4–6페이지, 정확히 네 섹션.
- `output/analysis/runs/<run-id>/`: 검토 결과, taxonomy, 근거 등록부, 구절별 분류, 국가–연도 행렬, 연도·지역·주제·공동 언급·기관별 입장·표현 추세, 출처 목록, 한국어 방법/비용 메모.
- `review_queue.csv`: 판정 불일치, 미분류 개념, 2025 VCT 원고/전사 차이 등 미해결 사항.
- `publication_checks.json`: PDF 페이지·섹션·Word 렌더링 검증 여부.

## 검증 수준

두 호출은 **자동 재검토**이며 사람 간 일치도나 인간 검수 완료가 아니다. 근거 인용은 원문과 일치해야 하며, 통계는 코드로 계산한다. 음성 검증·실제 참가 명단 완전 대조·미해결 VCT 낭독 여부를 완료했다고 표시하지 않는다. 최종 실행의 의미적 결과와 모델 품질은 실제 분석 후 평가해야 한다.

현재 검증은 오프라인 구조/전체 실행과 무료 모델 접근 확인이다. 계정 잔액·실시간 한도·네트워크 상태 때문에 실제 API 실행이 실패할 가능성까지 없앨 수는 없다. 그런 경우 원인을 표시하고 완료된 작업부터 재개한다.
