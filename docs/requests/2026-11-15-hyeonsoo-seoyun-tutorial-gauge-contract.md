# 튜토리얼 게이지에 AI 게이지 기준(`gauge`) 쓰기와 게이지 계산 · 단계 끝 평가 형식

- 작성: 김현수 (AI)
- 받는 사람: 한서윤 (FE)
- 날짜: 2026-11-15
- 기한: 급하지 않습니다. 지금은 형식만 맞춰 두면 되고, 숫자와 시험 데이터는 이후 AI 작업에서 채워 알려 드립니다
- 관련 Jira: [S15P31A306-437](https://ssafy.atlassian.net/browse/S15P31A306-437), 스토리 [S15P31A306-196 GUIDE-013](https://ssafy.atlassian.net/browse/S15P31A306-196)

## 요청 배경

지금 튜토리얼 진하기 게이지(`app/(live)/(camera)/tutorial/page.tsx`)는 `mocks/mock-data.ts`의 `BY_MAKEUP` 목표값(`target`)까지 저절로 차오르는 연출입니다. 이제 가이드 조회 응답의 `steps[].subSteps[].gauge`에 레퍼런스 영상에서 잰 기준이 옵니다. BE는 받은 그대로 넘기므로 BE 쪽 변경은 없습니다.

형식 설명은 [shared/guide-area 「게이지 기준」](../../shared/guide-area/README.md#게이지-기준-gauge)에 있습니다.

## 1. 샘플값 대신 `gauge` 읽기

`features/guide/types.ts`의 `AreaSubStep`에 선택 칸이 하나 늘어납니다. 이미 저장된 가이드에는 이 칸이 없습니다.

```ts
export interface AreaSubStep {
  // …지금 칸 그대로
  gauge?: GaugeReference | null;
}

export interface GaugeReference {
  color: { hex: string; lab: [number, number, number] } | null;
  effect: { delta: [number, number, number]; size: number; direction: "darker" | "lighter" | "same" } | null;
  strength: number | null;
  reason: "noArea" | "noMaps" | "tooFewCells" | "colorSpread" | "sidesDisagree" | "notDarker" | null;
}
```

| `gauge` | 화면 |
| --- | --- |
| 없음 · `null` · `reason`이 있음 | 이 단계는 레퍼런스 기준이 없어 **게이지를 숨김**. 카메라가 못 잴 때의 회색 「잴 수 없어요」(`canMeasure` · `reason`)와는 다른 경우 |
| 값이 있음 | 레퍼런스 위치선을 그림 |

- **막대 값은 「내 화장 효과 크기 ÷ `gauge.effect.size`」 비율로 그려 주세요.** 1이면 레퍼런스만큼입니다. 제안: 위치선을 막대 50에 두고 막대 = 비율 × 50(100에서 멈춤).
- **내가 잰 화장 효과의 방향이 `gauge.effect.direction`과 반대면 비율을 내지 않습니다.** 레퍼런스는 어두워졌는데(`darker`) 사용자는 밝아졌거나(`lighter`), 그 반대인 경우입니다. 이때는 막대 대신 「잴 수 없어요」처럼 둡니다. 방향 판단 기준(밝기 ±1)은 `gauge.effect.direction`과 같습니다.
- `strength`는 부위끼리 얼마나 진한지 견주는 값이라 막대에 그대로 쓰지 않습니다. 시연 영상에서 섀도는 10.7~19.7, 아이라인은 57.4~70.2라, 그대로 쓰면 섀도는 늘 「연해요」 근처에 머뭅니다.
- 색 샘플(`BY_MAKEUP`의 `color`)은 `gauge.color.hex`로 바꾸면 됩니다.
- 한 단계에 하위 단계가 여럿이면(아이섀도 윗눈두덩 · 눈 밑) 기준도 하위 단계마다 따로 있습니다. **화면에 지금 보이는 하위 단계(제목 옆 「영역 1/3」)의 `gauge`를 써 주세요.** 그 값이 없으면 같은 단계의 다른 하위 단계 값을 빌리지 말고 그 하위 단계 동안 게이지를 숨겨 주세요. 지금 FE README의 「게이지는 단계마다 한 번」은 이 규칙으로 바꿔야 합니다.
- 연해요 · 비슷해요 · 진해요 경계(지금 데모 값 45 · 62)는 실기기 웹캠 시험 뒤 숫자를 알려 드립니다.
- 시연 영상(RBm4rzufBV0) 기준으로 값이 있는 하위 단계는 섀도 4 · 아이라인 2 · 립 2입니다. 아이라인 `step_28` 두 개는 어두워지지 않아 `notDarker`로 오고, 블러셔 · 눈썹 · 쉐딩 · 하이라이트 · 베이스는 기본 영역이라 게이지가 숨겨집니다.

## 2. 브라우저 게이지 계산의 입력 · 출력 (형식 초안)

계산식과 숫자는 측정 작업에서 파이썬 기준 구현과 입력 · 기대값 JSON으로 드립니다. 지금은 주고받을 모양만 맞춰 두려는 것입니다.

| 입력 | 어디서 |
| --- | --- |
| 레퍼런스 기준 | 지금 하위 단계의 `gauge` |
| 재는 영역 | 지금 하위 단계의 `guideSets`(얼굴 주소 → 얼굴 지도 칸) |
| 맨얼굴 기준 | 튜토리얼 시작 때 같은 얼굴 지도 칸의 색 |
| 지금 프레임 | 카메라 프레임을 같은 얼굴 지도로 편 칸 색 |

```ts
interface GaugeReading {
  ratio: number | null;       // 내 화장 효과 크기 ÷ gauge.effect.size. 1이면 레퍼런스만큼
  hue: number | null;         // 레퍼런스보다 색 계열이 돈 각도(도). +는 노란 쪽, −는 분홍 · 보라 쪽
  chroma: number | null;      // 레퍼런스보다 선명한 정도(Lab 채도 차이). +는 더 선명
  canMeasure: boolean;        // live-state의 canMeasure와 같은 뜻
  reason: string | null;      // 못 잰 이유. live-state의 reason에 측정 불가 이유를 더하는 방식
}
```

사용자 카메라에서 잰 값은 브라우저 안에서만 쓰고, AI · BE로 보내거나 저장하지 않습니다.

## 3. 단계 끝 AI 평가 결과 (형식 초안)

한 단계를 마쳤을 때 단계 시작 사진과 끝 사진을 견줘 한 번 계산합니다. 숫자 기준과 안내 문장 표는 평가 작업에서 드립니다.

```ts
interface StepEvaluation {
  subStepId: string;
  coverage: number | null; // 가이드 영역 칸 중 바른 칸 비율 0~1
  overflow: number | null; // 영역 둘레 칸 중 바른 칸 비율 0~1
  sides: Record<"up" | "down" | "inner" | "outer", { coverage: number | null; overflow: number | null }>;
  ratio: number | null;    // 진하기 비율(위와 같은 뜻). 단계 중 조명이 바뀌면 null
  messages: { key: string; part: string | null; side: "up" | "down" | "inner" | "outer" | null }[];
  reason: string | null;   // 평가하지 못한 이유(가림 · 조명 바뀜 · 고개 각도 · 비교 사진 없음)
}
```

- `messages`의 `key`는 「조금 더 발라 주세요」 · 「레퍼런스보다 진해요」 · 「레퍼런스보다 연해요」 · 「눈꼬리 쪽이 영역을 넘었어요」 같은 안내 문장의 키입니다. 합격 · 점수 · 「잘했어요 / 실패」 같은 판정 표현은 쓰지 않습니다.
- 평가 결과와 문장은 기록에 남기지 않습니다.

## 확인 부탁

- [ ] 1번 타입과 화면 처리(기준 없으면 숨김, 막대는 비율)로 진행해도 되는지
- [ ] 2 · 3번 형식에서 FE 쪽에 더 필요한 칸이 있는지
