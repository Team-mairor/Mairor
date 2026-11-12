# catalog-import 공유 형식

수집기(AI 서버의 화장품 수집기, S15P31A306-293)가 만들고 적재 API(BE, S15P31A306-294·295)가 받는 **수집 상품 한 건(`CollectedProduct`)** 의 형식이다. 수집기와 적재 쪽이 같은 계약을 쓰도록 이 폴더의 샘플과 JSON Schema 로 맞춘다.

## `CollectedProduct`

수집기는 상품 하나마다 JSON 하나를 만든다. 서비스에 필요한 값만 담고, 근거·원본은 아래 '실행 결과 파일'에만 남긴다. 상품명·호수명은 사이트에 적힌 **원문 그대로** 보내고 정리는 적재 쪽이 한다.

| 필드 | 뜻 | 필수 |
| --- | --- | --- |
| `contractVersion` | 계약 판. 지금 `1`. 모르는 판은 적재 쪽이 그 건만 `INVALID` 로 처리한다 | ✅ |
| `itemKey` | 결과 파일 안 줄 위치 | ✅ |
| `source` | 상품·호수를 얻은 사이트. `OFFICIAL:<도메인>`(브랜드 공식 홈) 또는 `WEB:<도메인>` | ✅ |
| `sourceProductId` | 그 사이트의 상품 번호 | ✅ |
| `sourceUrl` | 상품 상세 URL | ✅ |
| `sourceLanguage` | 사이트 언어 (`ko`·`ja`·`en`·`de` 등) | ✅ |
| `collectedAt` | 수집 시각 (ISO-8601, 시간대 포함) | ✅ |
| `brand`·`name` | 사이트의 브랜드·상품명 원문 | ✅ |
| `sourceCategoryPath`·`categoryHint`·`typeHint` | 사이트 카테고리 경로와 추정 카테고리·소분류(힌트). 확정은 적재 쪽 | 힌트 |
| `imageUrl` | 대표 이미지 | |
| `saleStatus` | `ON_SALE`·`SOLD_OUT`·`MISSING` | |
| `shades[]` | 호수 목록. 호수 없는 상품은 빈 목록 | |
| `warnings[]` | 수집 경고 코드(문자열 목록). 알려진 코드: `SHADE_COLOR_NAMES_NOT_FOUND`(칸 이름을 찾지 못함). **모르는 코드는 적재가 기록만 하고 무시한다.** 새 코드는 이 표에 추가한다 | |

호수(`shades[]`):

| 필드 | 뜻 |
| --- | --- |
| `sourceOptionId` | 사이트의 옵션 값 (없으면 호수명). 옵션 원문을 합치지 않고 그대로 보낸다 |
| `name`·`sortOrder` | 호수 표시명(원문)·사이트 순서 |
| `slotOrderBasis` | 칸 순서 근거: `GRID`(수집기가 정한 방향의 행→열 순서) · `UNKNOWN`. 칸이 있으면 필수 |
| `variantHints` | 같은 호수를 합칠지 판단하는 구분 정보 `{volume, composition, formulation, optionAttributes, listPrice}`. 값은 사이트에 적힌 원문이고, 사이트에 그 구분 정보가 없으면 그 필드는 `null`. **객체 자체가 없으면 '수집하지 않음'이라 '충돌 없음'으로 보지 않고 자동 병합을 하지 않는다** |
| `colorStatus` | `EXTRACTED`(칸 색 하나 이상) · `NOT_FOUND`(근거 이미지·값 없음) · `FAILED`(다운로드·추출 오류). `FAILED` 는 기존 색을 지우지 않는다 |
| `colors[]` | 색 칸 0..N |

색 칸(`colors[]`):

| 필드 | 허용 값 |
| --- | --- |
| `sortOrder` | 칸 표시 순서 (1부터) |
| `name` | 칸 이름. 모르면 `null` |
| `nameSource` | `SITE_TEXT`(사이트 글자에 적힌 이름·번호) · `IMAGE_PRINT`(사진에 인쇄된 것을 읽음) · `NONE`(이름 없음, `name` 이 `null`). **모델이나 수집기가 순서대로 센 번호는 이름이 아니다** — `sortOrder` 일 뿐이고 `name` 에 넣지 않는다. `name` 이 있으면 `NONE` 이 아니어야 한다 |
| `hex` | `#RRGGBB` 대문자. 색을 못 구했으면 칸은 두고 `null` (임의 값을 만들지 않는다) |
| `colorSource` | `SOURCE_VALUE`(사이트가 준 색값) · `SWATCH_CHIP`(컬러칩 사진) · `PRODUCT_PHOTO`(공식 홈 제품 사진) · `WEB_PHOTO`(공식 홈 밖 웹 사진) · `LLM_ESTIMATE`(모델 추정) |
| `shadeLink` | 사진↔호수 연결 근거: `OPTION_IMAGE` · `SINGLE_SHADE_PRODUCT` · `LABEL_IN_IMAGE` · `UNVERIFIED` |
| `colorQuality` | 0~1. 사진에서 얻은 색만. `SOURCE_VALUE`·`LLM_ESTIMATE` 는 `null` |
| `evidenceKey` | `<sourceProductId>/<sourceOptionId>/<칸 sortOrder>`. 수집 시점에 만들고 적재 쪽은 그대로 저장한다 (다시 만들지 않는다) |

- **수집기는 색을 써도 되는지 정하지 않는다.** `shadeLink`·`colorQuality` 같은 판정 재료만 내보내고, 자동 사용 여부는 적재 쪽이 그때의 설정으로 판정한다

## 실행 결과 파일 (근거·원본)

수집기가 한 번 실행하면 JSONL 파일 하나를 만든다. DB 에는 넣지 않고, 적재 쪽은 파일을 찾아가는 키만 저장한다.

| 항목 | 규칙 |
| --- | --- |
| 위치 | 수집기가 로컬 폴더에 쓰고 S3 `catalog-runs/<이름>` 에 올린다(평평한 이름). 다 올린 뒤 `<이름 앞부분>.manifest.json` 을 올린다. BE 는 S3 에서 받아 읽기만 한다(`catalog.import.source=storage`, 로컬 개발은 폴더에서 바로 읽는다) |
| 이름 | `<시작시각>-<실행 이름>.jsonl`. 적재 시작 API 에 **상대 이름**으로 넘긴다 |
| 첫 줄 | header `{runId, startedAt, seed, collectorVersion}` |
| 이후 한 줄 | 상품 하나 `{itemKey, collected, evidence[], raw}` |
| `evidence[]` | 칸마다 `{evidenceKey, imageUrl, imageHash, imageKind, bbox, method, methodVersion, whiteBalance, scores}` |
| 보관 | 지우지 않는다. 근거 조회·재처리가 이 파일을 읽는다 |

## 수집 작업 (`CollectJob` · `CollectJobResult`)

BE 가 수집 큐(SQS)에 작업 메시지(`CollectJob`)를 넣으면, 수집 워커가 수집 → 결과 파일 S3 업로드 → BE `from-file` 적재(`finished=true` 까지)를 마친 뒤 작업 결과(`CollectJobResult`)를 BE 내부 API 로 보낸다(S15P31A306-513). BE 는 결과를 받아 수집 요청의 상태를 바꾼다(S15P31A306-517·518).

`CollectJob`(큐 메시지 본문):

| 필드 | 뜻 | 필수 |
| --- | --- | --- |
| `contractVersion` | 지금 `1` | ✅ |
| `jobId` | BE 가 정한 작업 ID(영문·숫자·`-`, 64자까지). **같은 jobId 는 몇 번 받아도 한 번만 반영된다** | ✅ |
| `brand` | 브랜드 이름. 목록에 없는 브랜드는 워커가 공식 홈을 찾는다 | ✅ |
| `name` · `url` | 제품 이름으로 찾거나(`name`), 상품 상세 주소로 다시 수집한다(`url`). **둘 중 하나만** 준다 | ✅ |
| `typeHint` | 소분류 코드. 주면 모델 분류를 하지 않는다 | |
| `requestedAt` | 요청 시각(시간대 포함) | ✅ |

`CollectJobResult`(BE 내부 API `POST /v1/internal/catalog/collect-jobs/{jobId}/result` 본문, `X-Internal-Token`):

| 필드 | 뜻 |
| --- | --- |
| `status` | `COLLECTED`(수집·적재 끝) · `SEARCH_EMPTY`(이름으로 찾은 상품 없음) · `UNSUPPORTED_SOURCE`(수집할 공식 홈이 없거나 꺼졌거나 사이트 종류를 모름) · `BLOCKED`(봇 차단, 우회하지 않음) · `FAILED`(상품을 하나도 수집하지 못했거나 재시도를 다 썼음) |
| `reason` | `COLLECTED` 가 아닐 때의 사유 코드(예: `NOT_FOUND`, `SITE_DISABLED`, `HTTP_ERROR`). 모르는 코드는 기록만 한다 |
| `resultFile` · `runId` · `importRunId` | `COLLECTED` 일 때만. 결과 파일 이름, 결과 파일의 runId, BE 적재 실행 ID |
| `products[]` | 결과 파일에 쓴 상품 `{itemKey, source, sourceProductId, sourceUrl}`. `COLLECTED` 면 하나 이상 |
| `failedProducts[]` | 수집하지 못한 상품 `{url, code}` |
| `finishedAt` | 작업이 끝난 시각 |

- 이름으로 찾을 때 후보가 하나로 정해지지 않으면 후보를 최대 3개까지 수집한다. 어느 제품이 요청과 맞는지는 BE 가 정한다.
- 같은 결과가 두 번 올 수 있다(콜백 응답 유실 뒤 재시도). BE 는 jobId 로 한 번만 반영한다.
- 일시 오류는 결과를 보내지 않고 큐 재시도에 맡긴다. 재시도를 다 쓰면 `FAILED` 를 보낸다.
- JSON Schema(`collect_job.v1.schema.json` · `collect_job_result.v1.schema.json`)는 `ai/app/tasks/catalog/jobs.py` 에서 같은 도구로 만든다. `name`·`url` 중 하나, 상태와 적재 결과의 짝 같은 규칙은 모델과 BE 검증이 본다.

## 샘플

`samples/` 의 JSON 은 모두 **테스트용 예시이며 실제로 수집한 값이 아니다.** 수집기·적재 코드의 테스트가 같은 파일을 쓴다.

| 파일 | 내용 | 쓰임 |
| --- | --- | --- |
| `samples/romand_single_unverified.json` | 단색 상품. 옵션 이미지가 없어 `shadeLink=UNVERIFIED` 인 칸과, 색을 못 찾은 호수(`NOT_FOUND`)가 있다 | 적재: 연결 근거 부족 → 서비스에 색 없음 |
| `samples/romand_duo_shade.json` | 한 호수에 색이 2개(듀오)이고 이름이 없는 칸 | 칸 2개 저장, 칸 순서 규칙 |
| `samples/etude_option_image.json` | 호수마다 사진이 있어 `shadeLink=OPTION_IMAGE` | 적재: 자동 사용 판정 통과 경로 |
| `samples/romand_named_palette.json` | 칸 이름이 있는 팔레트(`nameSource` `SITE_TEXT`·`IMAGE_PRINT`)와 색을 못 구한 칸 | 칸 이름 근거 저장, 색 없는 칸 |
| `samples/invalid_incomplete_source.json` | 일부러 깨뜨린 건: `sourceProductId` 가 없고 `hex` 형식이 틀리다 | 적재: 그 건만 `INVALID` 로 기록, 나머지는 계속 |
| `samples/collect_job_search.json` · `collect_job_product.json` | 이름으로 찾는 작업, 상품 주소로 다시 수집하는 작업 | 수집 워커 입력 |
| `samples/collect_job_result_collected.json` · `collect_job_result_search_empty.json` | 수집·적재가 끝난 결과, 찾은 상품이 없는 결과 | BE 수집 요청 상태 갱신 |

JSON Schema(`collected_product.v1.schema.json`)는 수집기 모델(`ai/app/tasks/catalog/contract.py`)에서 만든다. 모델을 바꾸면 `cd ai && uv run python tools/export_catalog_schema.py` 로 파일을 다시 만든다. 수집기 테스트는 이 파일이 모델과 같은지, 샘플이 통과하는지(깨뜨린 건은 실패하는지)를 본다. 스키마는 필드 모양만 검사하고, 칸 이름과 근거의 일치·`evidenceKey` 꼴 같은 건 간 규칙은 모델과 백엔드 검증이 본다.

## 형식을 바꿀 때

- `contractVersion` 을 올리고 이 README, 샘플, 수집기·적재 코드를 같이 고친다
- 적재 쪽은 모르는 판을 건별 `INVALID` 로 처리한다
