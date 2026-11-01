# 얼굴 추적·카메라·오버레이 모듈 사용법

카메라·얼굴 추적(`features/face`), 화장 레이어(`features/overlay`), 튜토리얼 가이드(`features/guide`)를 화면에서 쓰는 방법과 기기별 측정 결과, 아직 확인하지 못한 것을 적는다. 실행 방법, 확인 화면, 합성·가이드 표현 규칙, API 클라이언트는 [README](../README.md)에 있다.

## 카메라·얼굴 추적

`(live)` 레이아웃의 `CameraProvider`가 카메라와 추적을 한 번만 켠다. 로딩(얼굴 등록) → 미리보기 → 제품 체크 → 튜토리얼은 다시 초기화하지 않고 이어 쓰고, 이 묶음을 떠나면 끈다.

```tsx
// (live)/layout.tsx
<CameraProvider autoStart={false} errorView="none">{children}</CameraProvider>

// (camera)/layout.tsx: 들어오면 켜고, 이미 켜져 있으면 그대로 쓴다
<StartCamera />
```

- `autoStart`: 기본 `true`. 로딩 화면은 얼굴 등록을 시작할 때 `start()`를 직접 부르므로 `false`로 둔다
- `errorView`: `replace`면 오류 시 자식 대신 오류 화면을 보여 준다(확인 화면용). `none`이면 화면이 `error`를 직접 보여 준다(앱 화면)
- 카메라는 640×480(4:3)으로 받아 자르지 않고 전부 보여 준다(`containTransform`)
- 프레임을 받는 곳(`useFaceFrame`)이 하나도 없으면 추적만 쉬고 카메라와 모델은 그대로 둔다

| `useCamera()`               | 내용                                                                              |
| --------------------------- | --------------------------------------------------------------------------------- |
| `status`, `error`           | `idle` · `starting` · `ready` · `error`, 오류 종류는 `CameraError.kind`           |
| `start()`, `stop()`         | 겹쳐 불러도 카메라는 한 번만 연다. 시작 중에 `stop()`하면 늦게 열린 카메라를 끈다 |
| `viewTransform`             | 원본 프레임 → 화면 좌표 변환. 영상 크기를 알기 전에는 `null`                      |
| `showVideo`, `setShowVideo` | 하프미러 앞에서는 영상을 숨기고 가이드만 그린다                                   |
| `setCoverPanel(el)`         | 화면 아래를 덮는 패널. 패널 뒤 부위는 화면 밖으로 판정한다                        |
| `videoRef`                  | 얼굴 등록 사진처럼 영상 프레임이 필요할 때                                        |

`useFaceFrame((frame, stats) => …)`은 프레임마다 불린다. 리렌더 없이 캔버스에 그릴 때 쓰고, 화면 상태가 필요하면 바뀔 때만 `setState`한다.

### FaceFrame

| 필드               | 내용                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `trackingState`    | `tracking` · `degraded`(불안정, 숨김) · `hold`(짧게 놓침, 직전 결과 복사) · `lost`. 처음 찾기 전에는 frame이 `null` |
| `landmarks`        | 정규화 좌표 0~1, 반전 전 원본 프레임 기준, 좌우는 사용자 신체 기준                                                  |
| `iod`              | 두 홍채 중심 거리(픽셀). 부위 크기·선 두께는 IOD = 1 기준                                                           |
| `pose`             | yaw·pitch·roll(라디안). 사용자 왼쪽으로 돌리면 yaw +, 위를 보면 pitch +                                             |
| `eyes`             | 눈 뜬 정도(0~1), 깜빡임                                                                                             |
| `regions`          | 부위별 중심·너비·높이·각도                                                                                          |
| `regionVisibility` | 부위별 화면 안 비율(`inFrameRatio`, 하단 패널 뒤는 밖), 카메라를 향하는지(`facing`)                                 |

- 화면 좌표: `toScreen(point, frame.imageSize, viewTransform)`. 거울 반전은 여기서 한 번만 한다
- `stats`: FPS와 구간별 처리 시간(`formatTiming`으로 표시), 근접 입력 축소 배율

### 숨김과 안내

| 판정           | 기준                                                                                |
| -------------- | ----------------------------------------------------------------------------------- |
| 추적 유지      | 핵심 부위(양쪽 눈·입술) 중 2개 이상이 화면 안에 정면으로 보일 때. 아니면 `degraded` |
| 고개 돌림      | yaw 0.6rad(약 35°) 초과면 그 부위는 `facing: false`                                 |
| 부위가 화면 안 | `inFrameRatio` 0.9 이상. 한번 밖으로 본 부위는 0.03 더 들어와야 다시 보임           |
| 너무 멂        | 얼굴 폭 / 영상 폭 0.4 미만. 숨기지 않고 측정만 막는다                               |

- `useTrackingIssue()`: 안내할 이유(`lost` · `turned` · `out-of-frame` · `far` · `null`)가 바뀔 때만 다시 그린다. 문구는 `TRACKING_ISSUE_TEXT`
- `isGuideVisible(frame, region)`: 추적이 `tracking`이고 부위가 화면 안에 정면으로 보일 때만 true
- `HoldVisibility`: `hold` 동안 직전 판정을 유지해 깜빡일 때 가이드·화장이 깜빡이지 않게 한다. 대상이 바뀌면 `reset()`

## 화장 레이어

```tsx
<MakeupOverlay layersUrl={url} hidden={hide} />
```

- `layersUrl`: AI 파트 미리보기 출력(`layers.json`). 불러오지 못하면 5초마다 다시 시도한다
- `hidden`: 레이어는 두고 그리기만 멈춘다. 다시 보일 때 새로 불러오지 않는다
- `enabled={false}`는 그리기를 끈다(성능 비교용), `showStats`는 처리 시간을 띄운다
- 화장 캔버스는 CSS 픽셀의 절반 해상도로 그린다. 그리는 픽셀이 많을수록 얼굴 검출이 느려지기 때문이다(아래 측정 결과)

## 튜토리얼 가이드

```tsx
const defaults = await loadDefaultGuideSet(); // 9개 부위 기본 가이드
const area = await loadGuideArea(url); // AI 가이드 영역 (shared/guide-area)
const step = resolveSubStep(subStep, defaults); // 하위 단계 → 그릴 단계 (상태별 처리 포함)
const inView = useStepInView(step); // 단계 부위가 잘렸는지
<GuideOverlay step={canRender ? step : null} />;
```

- `resolveSubStep`: `extracted`는 받은 영역, `template`은 `templateId`의 기본 가이드, `notApplicable` · `failed`는 `null`
- `GuideOverlay`는 지금 단계 도형만 그리고, 단계가 바뀌면 직전 숨김 판정을 버린다
- 가이드 파일(`GuideSet`)을 직접 쓸 때는 `loadGuideSet(url)`. 불러올 때 부위 이름·기준점을 확인하고 쓸 수 없는 단계·도형만 경고 후 뺀다

## 얼굴 등록

로딩 화면 모달(`features/loading`)이 `useFaceCheck(enabled)`로 조명·거리·정면·가림 4개를 실시간 판정하고, 1.5초 유지하면 `captureFace(video)`로 정면 1장을 찍는다. 사진은 `saveFacePhoto(runId, blob)`로 이번 실행에만 보관한다(업로드 API 전). 기준값과 판정 방식은 README 폴더 구조 아래 설명과 `face-register.ts`에 있다.

## 측정 결과

| 기기                                  | 결과                                                                                                                                |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 갤럭시탭 S6 Lite (목표 기기, 640×480) | 얼굴 없음 14~18 FPS(검출 50~65ms). 얼굴 있음 미리보기 5~6 FPS(검출 약 184ms), 튜토리얼 약 8 FPS. 피부 분할은 느려서 자동으로 꺼진다 |
| 갤럭시 S24 울트라 (크롬)              | 해상도가 높을수록 FPS가 떨어져 640×480·1280×720 권장. 노출 고정은 현재 값 유지가 안 돼 노출 시간을 직접 지정한다                    |
| PC 웹캠                               | 1280×720 기준 FPS 30(웹캠 상한), 검출 8~12ms. 640×480으로 바꾼 뒤 다시 재지 않았다                                                  |

- 탭에서 얼굴이 잡히면 느려지는 원인은 화장 그리기의 GPU 작업이 끝날 때까지 검출 결과 읽기(`readPixels`)가 기다리는 것이다(메인 스레드의 42%). 검출은 화장 없음 100ms → 립 1개 167ms → 6개 184~238ms. 카메라 입력·입력 크기·피부 분할·CPU 추론은 원인이 아니었다
- 화장 캔버스를 절반 해상도로 바꿔 검출 221 → 184ms, FPS 4~5 → 5~6
- 측정은 `/debug/preview?stats`, `/debug/face`의 구간별 시간으로 한다

## 아직 확인하지 못한 것

- 갤럭시탭에서 화면 꺼짐·앱 전환 뒤 가이드 복귀, 얼굴 등록 후 미리보기에서 카메라를 다시 켜지 않는지 (S15P31A306-268)
- 고개를 움직일 때 가이드가 늦게 따라온다. 튜토리얼 8 FPS라 0.1~0.25초 전 위치에 그려진다 (S15P31A306-269)
- 얼굴 등록의 조명 고르기·맨얼굴 안내·업로드·조명 변화 감지 (S15P31A306-268). 손 가림과 표정은 판정하지 않는다
- 하프미러 모드의 좌표 보정은 없다. 가이드는 `Projection`으로 분리만 해 두었다
