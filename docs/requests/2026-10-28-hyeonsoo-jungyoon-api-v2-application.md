# API 명세 v2 도포 정보 대응 확인 요청

- 작성: 김현수
- 받는 사람: 김정윤
- 날짜: 2026-10-28
- 기한: 2026-10-30 (S15P31A306-224 「전체 메이크업 부위 영역 저장 및 단계별 데이터 구성」 마감 10-31 하루 전)
- 관련 Jira: S15P31A306-216
- 규격 전체: [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd) 「좌표 · 좌우」 · 「상태」

## 요청 배경

AI는 단계마다 바를 영역을 FE 얼굴 구조 스키마의 얼굴 주소(`MeshAnchor`: 삼각형 번호 + 비율)와 부위 이름(`RegionName`)으로 만듭니다 (ADR-011). FE의 레이어·가이드·기본 가이드 코드도 이 방식입니다.

API 명세 v2(`docs/references/api-spec.md`, 10-27 사본)의 `GuideStep.application`은 다른 방식입니다.

| 칸 | API 명세 v2 | AI 영역 데이터 |
| --- | --- | --- |
| 좌표 | `coordinateSystem: face_template_v1` (반전 전 정면 표준 얼굴 0~1) + `region.polygon` | `guideSets[].guides[]`의 `polygon.outline` = `MeshAnchor[]` |
| 좌우 | `side`: `LEFT` · `RIGHT` · `BOTH` · `CENTER` | 부위 이름(`leftEye` · `rightEye` 등) |
| 기본 영역 | `region.templateId` + `isFallback: true` | `status: template` + `templateId` |
| 영역 없음 | `type: EXCLUDED` 또는 `application: null` | `status: notApplicable` · `failed` |

`face_template_v1`을 정의한 파일은 아직 없고, `application` 칸을 쓰는 코드도 BE·FE·AI 어디에도 아직 없습니다. 이 데이터가 BE를 거쳐 FE로 갈 때 어떻게 맞출지 확인을 부탁드립니다.

## 요청 내용

### 1. 좌표계

- [ ] 아래 중 하나로 정해 주세요
  - `face_template_v1`을 공유 UV 평면(`shared/face-mesh/uv.v1.json`, 왼쪽 위가 (0,0))으로 정의. FE 기본 가이드 코드에 UV 평면의 점을 얼굴 주소로 바꾸는 함수가 있어 서로 바꿀 수 있습니다
  - `application.region`에 AI 영역 데이터(얼굴 주소)를 그대로 싣기

### 2. 좌우 (`side`)

AI 영역 데이터의 부위 이름으로 아래처럼 계산할 수 있습니다.

| 하위 단계의 부위별 묶음 | `side` |
| --- | --- |
| 짝 부위의 왼쪽·오른쪽이 둘 다 있음 (`leftEye`+`rightEye`, `leftBrow`+`rightBrow`, `leftCheek`+`rightCheek`) | `BOTH` |
| 짝 부위의 왼쪽만 | `LEFT` |
| 짝 부위의 오른쪽만 | `RIGHT` |
| 가운데 부위만 (`lipsOuter` · `lipsInner` · `faceOval`) | `CENTER` |
| 짝 부위와 가운데 부위가 섞임 (예: 하이라이트) | 정하지 않음 |

- [ ] 짝 부위와 가운데 부위가 섞인 경우의 `side`를 정해 주세요
- [ ] API 명세 v2의 `BOTH`는 왼쪽만 저장하고 오른쪽을 대칭으로 만듭니다. AI 데이터는 양쪽을 따로 담습니다. `BOTH`일 때 양쪽 영역을 그대로 실을 수 있는지 확인해 주세요

### 3. 상태

| AI `status` | 뜻 | API 명세 v2 (제안) |
| --- | --- | --- |
| `extracted` | 레퍼런스에서 영역을 찾음 | `type: GUIDE`, `application.region.polygon`, `isFallback: false` |
| `template` | 못 찾아 기본 영역을 씀 | `type: GUIDE`, `application.region.templateId`, `isFallback: true` |
| `notApplicable` | 영역이 없는 단계 (`makeup: other`) | `type: EXCLUDED`? |
| `failed` | 못 찾았고 기본 영역도 쓰지 않음 | `type: GUIDE`, `application: null` |

- [ ] `notApplicable`(스킨케어 같은 `other` 단계)이 API 명세 v2의 `EXCLUDED`(진행률에서 빠지는 단계)와 같은 뜻인지 확인해 주세요

## 예시

```json
{ "stepId": "s17", "order": 17, "makeup": "lip",
  "subSteps": [
    { "subStepId": "s17-1", "order": 1, "status": "extracted", "reasons": [], "templateId": null,
      "guideSets": [
        { "region": "lipsOuter", "source": "extracted", "exclude": ["lipsInner"],
          "guides": [{ "type": "polygon", "outline": [{ "triangle": 37, "bary": [0.21, 0.52, 0.27] }] }] }
      ] }
  ] }
```

- `s17` 립: 가운데 부위(`lipsOuter`)만 있어 `side`는 `CENTER`, 기본 영역이 아니라 `isFallback: false`입니다
- 삼각형 번호·비율은 예시입니다. 19단계 전체 예시는 FE 요청 문서에 있습니다: [2026-10-28-hyeonsoo-seoyun-guide-region-format.md](2026-10-28-hyeonsoo-seoyun-guide-region-format.md)
