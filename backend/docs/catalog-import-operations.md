# 카탈로그 적재 운영 절차 (S15P31A306-295 → 317)

수집기가 만든 실행 결과 파일(JSONL)을 서버가 읽어 카탈로그에 적재하고, 품질을 확인하고, 틀린 건을 다시 처리하는 절차다. 모든 API 는 내부 API 이며 `X-Internal-Token` 헤더가 필요하다.

## 1. 적재 전에 갖춰야 할 것

| 항목 | 내용 |
| --- | --- |
| DB | `backend/src/main/resources/db/upgrade/295-catalog-import-runs.sql` 을 운영 DB 에 먼저 적용한다. 서버가 `ddl-auto=validate` 라 표가 없으면 기동하지 못한다. |
| 결과 파일 전달(S3) | 수집기와 서버는 다른 서버라 폴더를 같이 쓰지 않는다. 수집기가 `CATALOG_RUNS_STORE=s3` 로 결과 파일을 `s3://mairor-prod-media/catalog-runs/<파일>.jsonl` 에 올리고, 운영 서버(`catalog.import.source=storage`)는 그 키를 받아 캐시 폴더(`catalog.import.result-dir`, 운영 `/tmp/mairor-catalog-runs`)에서 읽는다. 받은 파일은 `catalog.import.storage-cache-ttl`(기본 5분) 동안 다시 받지 않고, 지난 파일은 다음에 받을 때 지운다. 서버 역할 `mairor-ec2-app` 은 `catalog-runs/*` 의 `GetObject`, 수집기 쪽 역할은 `GetObject`·`PutObject` 가 필요하다(올리기 전에 이미 올린 파일인지 읽어 본다). 로컬 개발(`source=local`)은 폴더에서 바로 읽는다. |
| 색 임계값 | `catalog.color.min-quality.<출처>`(`SWATCH_CHIP`, `PRODUCT_PHOTO`, `WEB_PHOTO`)와 `catalog.color.label-in-image-enabled`. 운영(`application-prod.yml`)은 눈 확인 표로 정한 값을 기본으로 둔다: `PRODUCT_PHOTO` 0.75, `SWATCH_CHIP` 0.55, 사진 속 표기 연결 켬, `WEB_PHOTO` 미설정(S15P31A306-515, 통과 55칸 중 54칸 맞음). 바꿀 때는 `CATALOG_COLOR_MIN_QUALITY_PRODUCT_PHOTO`·`CATALOG_COLOR_MIN_QUALITY_SWATCH_CHIP`·`CATALOG_COLOR_LABEL_IN_IMAGE_ENABLED` 환경변수를 쓴다(출처 이름이 맵 키라 `CATALOG_COLOR_MINQUALITY_...` 같은 일반 환경변수 이름으로는 덮이지 않는다). 개발·로컬은 기본값이 없어 사진 색이 모두 `BELOW_THRESHOLD`(서비스에는 null)다. |
| 선택 설정 | `catalog.color.label-in-image-enabled`(판독 일치율 95% 이상일 때만), `catalog.color.llm-estimate-enabled`(기준 세트로 확인한 뒤에만), `catalog.color.source-value-sites`(옵션과 색값 연결을 확인한 사이트만). |
| 사이트 허용 기록 | 사이트별 수집 허용 근거는 317 에서 사이트마다 남긴다. 약관 확인은 사용자가 한다. |

## 2. 적재

1. 수집기가 `<파일>.jsonl` 을 다 쓰고 S3 `catalog-runs/` 에 올린다. 다 올린 뒤 `<파일 앞부분>.manifest.json`(runId·건수·실패 수·sha256)을 올린다. 첫 줄은 header(`runId`, `startedAt`, `seed`, `collectorVersion`), 이후 한 줄이 상품 하나다.
2. 서버에 요청한다.

```
POST /v1/internal/catalog/import-runs/from-file
{ "resultFile": "20261108-213000-etude.jsonl", "limit": 500 }
```

3. 응답의 `finished` 가 `false` 이면 **같은 요청을 그대로 다시 보낸다.** 이미 처리한 건은 건너뛰고 이어서 처리한다. `finished=true` 가 되면 실행이 `COMPLETED` 로 끝난 것이다. 끝난 뒤 다시 보내도 아무 일도 하지 않는다.
4. `unrecorded` 가 0 이 아니면 `itemKey` 가 없는 틀린 줄이 있다는 뜻이다. 기록할 곳이 없어 처리 건 수와 통계에 들어가지 않고, 뒤의 정상 건 처리를 막지도 않는다. 수집기 쪽을 고쳐 새 파일을 만든다.
5. `unreadable` 이 0 이 아니면 중간이 깨진 줄이 있다는 뜻이다. 수집기 쪽 문제로 보고 수집 로그를 확인한다. 마지막 줄이 쓰다 만 것이면 무시한다.

`limit` 은 1~2000(기본 500)이다. 요청 하나가 너무 오래 걸리지 않게 하려는 값이다.

저장소에 닿지 못하면 `503 SERVICE_UNAVAILABLE` 이다. 잠시 뒤 같은 요청을 다시 보낸다.

### 실패한 상품을 다시 수집했을 때

**올린 결과 파일은 바꾸지 않는다.** 서버는 실행을 `runId` 로 기억해서, 이미 `COMPLETED` 인 `runId` 의 파일은 상품이 늘어도 다시 읽지 않는다. 그래서 수집기는 이미 올린 실행을 `--resume` 으로 이어 쓰지 않고, 같은 이름에 다른 내용을 올리지도 않는다(같은 내용은 다시 올려도 된다).

1. 수집 요약이나 manifest 의 `failed` 로 실패한 상품이 있는지 본다.
2. 수집기에서 `collect … --retry-of <처음 파일>` 로 실패한 상품만 **새 파일·새 runId** 로 다시 수집한다. 끝나면 새 파일이 S3 에 올라간다.
3. 새 파일 이름으로 `from-file` 을 보낸다. 처음 파일의 적재 기록은 그대로 남는다.

## 3. 품질 확인

- `GET /v1/internal/catalog/import-runs/{id}/stats` : 이번 실행의 결과 분포(신규·갱신·모호·미분류·형식 오류·실패)와 문제 건 목록.
- `GET /v1/internal/catalog/quality` : 지금 카탈로그 전체의 색 채움 상태(현재 품질 통계).
- 실행 통계는 "이번에 한 일", 품질 통계는 "지금 상태"다. 둘을 섞어 보지 않는다.

## 4. 틀린 건 재처리

서버 쪽 일시 오류로 `FAILED` 가 된 건은 같은 파일에서 다시 처리한다. (수집기에서 실패한 상품은 위의 "실패한 상품을 다시 수집했을 때"로 새 파일을 만든다.)

```
POST /v1/internal/catalog/import-runs/from-file
{ "resultFile": "20261108-213000-etude.jsonl", "retryOf": "<이전 실행 id>" }
```

- 이전 실행에서 `FAILED`·`INVALID` 로 끝난 건만 읽어 새 실행 `<이전 runId>-retry` 로 처리한다. 이전 실행의 기록과 통계는 그대로 남는다.
- 같은 파일이어야 한다(`RETRY_FILE_MISMATCH`).
- 형식이 틀린 건(`INVALID`)은 파일이 같으면 다시 해도 같은 결과다. 수집기를 고쳐 새 파일을 만든 뒤 새 실행으로 적재한다.

## 5. 끊긴 실행

수집기가 죽거나 호출이 끊겨 하트비트가 `catalog.import.heartbeat-timeout`(기본 10분) 동안 없으면 감시기가 실행을 `ABANDONED` 로 닫는다. 닫힌 실행에 건을 더 보내면 `409 IMPORT_RUN_CLOSED` 다. 새 `runId` 의 파일로 다시 시작한다. 이미 반영된 건은 다시 보내도 중복 반영되지 않는다.

실행을 끝내는 쪽(수집기의 끝내기 요청, 끊긴 실행 정리)은 진행 중인 건이 모두 확정될 때까지 기다린 뒤 끝낸다. 그래서 `COMPLETED`·`ABANDONED` 응답 뒤에는 통계와 제품 수가 더 바뀌지 않는다.

## 재처리 범위

재처리 대상은 `FAILED`·`INVALID` 건뿐이다. 판정이 `UNCLASSIFIED`·`AMBIGUOUS` 로 나온 건을 사람이 풀어 반영하는 기능은 이번 범위에 없다.

## 6. 색의 근거 조회

```
GET /v1/internal/catalog/shade-colors/{colorId}/evidence
```

색 칸이 어떤 이미지·영역·방법·품질 점수에서 나왔는지 실행 결과 파일에서 찾아 준다. DB 에는 근거를 두지 않고 찾아갈 키(적재 건, 근거 키)만 둔다.

- 결과 파일은 S3 `catalog-runs/` 에 남겨 두고 지우지 않는다. 그래도 파일이 없으면 `fileAvailable=false` 이고 `evidence` 는 비어 있다. 그때는 같은 값을 다시 수집해서 판단한다.
- 직접 넣은 칸처럼 적재가 만들지 않은 칸은 `404 COLOR_EVIDENCE_NOT_RECORDED` 다.

## 7. 오류 코드

| 코드 | 상태 | 뜻 |
| --- | --- | --- |
| `INVALID_RESULT_FILE` | 400 | 파일 이름 규칙 위반, 폴더 밖, header 에 runId 없음 |
| `RESULT_FILE_NOT_FOUND` | 404 | 파일 없음(S3 에 올리지 않았거나 이름이 틀림) |
| `SERVICE_UNAVAILABLE` | 503 | 저장소(S3)에 닿지 못함. 잠시 뒤 다시 보낸다 |
| `VALIDATION_FAILED` | 400 | `limit` 범위 밖 등 |
| `RETRY_FILE_MISMATCH` | 400 | 재처리 대상 실행과 다른 파일 |
| `IMPORT_RUN_CLOSED` | 409 | 실패하거나 끊겨 끝난 실행에 건을 더 보냄 |
| `COLOR_NOT_FOUND` | 404 | 색 칸 없음 |
| `COLOR_EVIDENCE_NOT_RECORDED` | 404 | 적재가 만든 칸이 아님 |
