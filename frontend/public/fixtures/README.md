# 픽스처

미리보기·추적 화면을 카메라·백엔드 없이 확인하기 위한 예시 데이터다. `npm run fixtures`로 다시 만든다 (손으로 고치지 않는다). 스크립트는 Node 22.18 이상에서 돌아가고, 낮은 버전이면 바로 알려 준다 (`.nvmrc` 기준 24). 판정 기준값은 추적기 코드(`tracking-rules.ts`, `visibility.ts`)에서 그대로 읽는다.

- 얼굴 데이터: `FaceFrame` (`src/features/face/types.ts`, `meshVersion: "v1"`)
- 레이어: `LayerSet` (`src/features/overlay/types.ts`)
- 가이드: `GuideSet` (`src/features/guide/types.ts`)
- 출처: `shared/face-mesh/`의 캐노니컬 얼굴 메시 UV를 정면 얼굴 랜드마크로 쓴 합성 데이터. 실제 사람 얼굴이 아니다
- 확인 화면: `/debug/overlay`에서 얼굴과 레이어를 골라 합성 결과를 본다 (`?face=turned-left&layers=lip-only`처럼 주소로도 고를 수 있다)

## 얼굴 (`faces/`)

| 파일 | 상태 | 예상 화면 동작 |
| --- | --- | --- |
| `front.json` | 정면, `tracking` | 화장 레이어·가이드 모두 표시 |
| `turned-left.json` | `yaw` 0.8 (왼쪽으로 돌림), 왼쪽 눈·입이 돌아가 `degraded` | 화장 레이어·가이드 모두 숨김 |
| `close-up.json` | 가까이 다가가 아랫입술·턱이 화면 밖, 립 `inFrameRatio` 0.75라 `degraded` | 화장 레이어·가이드 모두 숨김 |
| `blink-hold.json` | 눈 감음, `hold` | 직전에 보이던 경우에만 직전 위치로 유지. 확인 화면에서 처음 고르면 숨김 |
| `lost.json` | `lost` | 화장 레이어·가이드 모두 숨김 |

- `trackingState`는 추적기와 같은 규칙으로 정한다. 주요 부위(양쪽 눈·입술 바깥) 중 하나라도 화면 안 비율이 0.9 미만이거나 돌아가 있으면 `degraded`다.
- 추적이 불안정(`degraded`)하거나 놓치면(`lost`) 화장 레이어와 가이드를 모두 숨긴다 (CAMERA-004).

## 레이어 (`layers/`)

| 파일 | 내용 | 예상 화면 동작 |
| --- | --- | --- |
| `sample.json` | 파운데이션·아이섀도·아이라인(양쪽)·블러셔·립 | 배열 순서대로 겹쳐 표시 |
| `lip-only.json` | 립 하나 | 입술만 표시, 입 안쪽은 빔 |
| `empty.json` | 레이어 없음 | 영상만 표시. `/preview`에서는 "그릴 수 있는 화장 레이어가 없어요" 안내 |
| `no-color.json` | 립 `color: null` | 립은 그리지 않고 파운데이션만 표시 |
| `missing-mask.json` | 블러셔 마스크 파일 없음 | 블러셔는 경고를 남기고 빼고 립만 표시 |

- UV 마스크(`layers/masks/`)는 512 × 512, 8비트 흑백 PNG이고 색 프로필이 없다. 입·눈 안쪽은 0이다
- 볼 점 번호가 아직 후보값이라 블러셔 마스크도 임시 모양이다

## 가이드 (`guides/`)

| 파일 | 내용 | 예상 화면 동작 |
| --- | --- | --- |
| `sample.json` | 앱의 기본 가이드(9개 부위)를 파일로 내보낸 것, `source: template` | `/tutorial?guides=/fixtures/guides/sample.json`에서 단계마다 점선 영역·선·화살표 표시 |
| `empty.json` | 단계 없음 | "이 영상에는 가이드가 없어요" 안내 |

- `/debug/overlay?step=0~8`로 카메라 없이 기본 가이드를 부위별로 볼 수 있다
