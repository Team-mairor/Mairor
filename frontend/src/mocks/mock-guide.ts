// AI 샘플 영상(ai/samples/local_01)의 가이드 입력과 단계 설명(ai/tools/explain_runs, 서비스 모델 결과)을
// API 명세 v2 단계 모양으로 옮긴 목업. 화장 종류는 10개 값 기준인 같은 영상의 가이드 영역 샘플을 따른다.
// 단계 수·종류는 영상마다 다르고, 화면은 이 목록 길이와 순서대로 돈다.
// ponytail: API 클라이언트가 붙으면 가이드 조회 응답(Guide.steps)으로 바꾼다.
import type { Makeup } from "@/features/guide";
import type { GuideAction } from "@/features/session";

export interface MockGuideStep {
  stepId: string;
  /** 1부터 */
  order: number;
  /** EXCLUDED: 스킨케어처럼 가이드 대상이 아닌 단계. 진행 단계에서 뺀다 */
  type: "GUIDE" | "EXCLUDED";
  makeup: Makeup;
  /** 한국어 부위 이름 */
  part: string;
  /** 이 단계에서 하는 일 한 문장(영상 그대로) */
  summary: string;
  /** 쓰는 도구. 영상에서 못 찾으면 null */
  tool: string | null;
  /** 화면에 보여 줄 동작. 제품 이름은 따로 보여 주므로 넣지 않는다 */
  actions: GuideAction[];
  /** 끝내는 기준 */
  doneWhen: string | null;
  product: { brand: string | null; name: string | null; shade: string | null } | null;
  videoRange: { startSeconds: number; endSeconds: number };
}

export const MOCK_VIDEO_ID = "eFzG30avtOI";
/** 같은 영상의 가이드 영역 (scripts/generate-fixtures.mjs가 AI 샘플에서 만든다) */
export const MOCK_GUIDE_AREA_URL = "/fixtures/guide-areas/local_01.json";

export const MOCK_GUIDE_STEPS: MockGuideStep[] = [
  {
    stepId: "s1",
    order: 1,
    type: "EXCLUDED",
    makeup: "other",
    part: "스킨케어 패드",
    summary:
      "세안 후 마다가스카르 센텔라 퀵 카밍패드를 얼굴에 붙이고 머리를 말리는 동안 수분을 공급하고 피부 열감을 낮춰줍니다.",
    tool: "손",
    actions: [
      { text: "세안 후 얼굴에 패드를 붙여요", tip: null },
      {
        text: "머리 말리는 동안 붙여 두어요",
        tip: { kind: "tip", text: "화장 전에 붙이면 화장이 잘 먹어요" },
      },
      { text: "5~10분 정도 그대로 두어요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "스킨1004", name: "마다가스카르 센텔라 퀵 카밍패드", shade: null },
    videoRange: { startSeconds: 20, endSeconds: 75 },
  },
  {
    stepId: "s2",
    order: 2,
    type: "EXCLUDED",
    makeup: "other",
    part: "스킨케어 토너",
    summary: "헤브블루 살몬 케어링 센텔라 토너를 손으로 흡토하여 피부에 흡수시켜줍니다.",
    tool: "손",
    actions: [{ text: "토너를 피부에 흡수시켜요", tip: null }],
    doneWhen: "토너가 90% 정도 흡수되면 다음으로 넘어가요",
    product: { brand: "헤브블루", name: "살몬 케어링 센텔라 토너", shade: null },
    videoRange: { startSeconds: 75, endSeconds: 90 },
  },
  {
    stepId: "s3",
    order: 3,
    type: "EXCLUDED",
    makeup: "other",
    part: "스킨케어 앰플",
    summary: "엘라쥬 리얼 히알루로닉 블루 100 앰플을 두 번 정도 레이어링하여 피부에 발라줍니다.",
    tool: "손",
    actions: [
      {
        text: "손으로 앰플을 피부에 발라요",
        tip: { kind: "tip", text: "수분이 부족하면 기름이 더 나와요" },
      },
      { text: "앰플을 두 번 정도 겹쳐 발라요", tip: null },
    ],
    doneWhen: "수분이 꽉 채워지면 다음으로 넘어가요",
    product: { brand: "엘라쥬", name: "리얼 히알루로닉 블루 100 앰플", shade: null },
    videoRange: { startSeconds: 90, endSeconds: 158 },
  },
  {
    stepId: "s4",
    order: 4,
    type: "EXCLUDED",
    makeup: "other",
    part: "선 앰플",
    summary:
      "프롬리 비건 이지 에프 시카 워터 선앰플을 얼굴에 얇게 코팅하듯이 바르고 퍼프로 두드려 흡수시켜줍니다.",
    tool: "손",
    actions: [
      {
        text: "얼굴에 얇게 코팅하듯 발라요",
        tip: { kind: "tip", text: "모공 사이사이에 넣는 느낌으로요" },
      },
      {
        text: "코 옆과 눈두덩이, 눈 밑을 꼼꼼히 발라요",
        tip: { kind: "tip", text: "잘 뭉치는 부위예요" },
      },
      { text: "퍼프로 두드려 흡수시켜요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "프롬리", name: "비건 이지 에프 시카 워터 선앰플", shade: null },
    videoRange: { startSeconds: 158, endSeconds: 202 },
  },
  {
    stepId: "s5",
    order: 5,
    type: "GUIDE",
    makeup: "foundation",
    part: "파운데이션",
    summary:
      "바닐라코 커버리셔스 파워 핏 파운데이션 19 라이트를 스패출러로 얹고 퍼프로 톡톡 두드려 발라줍니다.",
    tool: "스패출러",
    actions: [
      { text: "스패출러로 파운데이션을 얹어요", tip: null },
      { text: "퍼프로 톡톡 두드려 발라요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "바닐라코", name: "커버리셔스 파워 핏 파운데이션", shade: "19 라이트" },
    videoRange: { startSeconds: 202, endSeconds: 221 },
  },
  {
    stepId: "s6",
    order: 6,
    type: "EXCLUDED",
    makeup: "other",
    part: "컨실러",
    summary: "마루빌츠 캐머플라지 크림 컨실러 19호를 퍼프에 묻혀 눈가를 밝혀줍니다.",
    tool: "퍼프",
    actions: [
      {
        text: "눈가에 발라 밝혀요",
        tip: { kind: "tip", text: "섀도우 올리기 전에 바르면 좋아요" },
      },
    ],
    doneWhen: null,
    product: { brand: "마루빌츠", name: "캐머플라지 크림 컨실러", shade: "19호" },
    videoRange: { startSeconds: 221, endSeconds: 242 },
  },
  {
    stepId: "s7",
    order: 7,
    type: "GUIDE",
    makeup: "blush",
    part: "크림 블러셔",
    summary: "하밍 젤리 에어 치크 02 베리피치를 퍼프로 중앙 위주로 발라줍니다.",
    tool: "퍼프",
    actions: [
      { text: "중앙 위주로 발라요", tip: { kind: "tip", text: "진하게 발라도 파우더로 연해져요" } },
    ],
    doneWhen: null,
    product: { brand: "하밍", name: "젤리 에어 치크", shade: "02 베리피치" },
    videoRange: { startSeconds: 242, endSeconds: 267 },
  },
  {
    stepId: "s8",
    order: 8,
    type: "EXCLUDED",
    makeup: "other",
    part: "파우더",
    summary: "루나 프로 포토 피니셔 02 파우더를 퍼프로 얼굴에 발라줍니다.",
    tool: "퍼프",
    actions: [{ text: "퍼프로 파우더를 얼굴에 발라요", tip: null }],
    doneWhen: null,
    product: { brand: "루나", name: "프로 포토 피니셔", shade: "02" },
    videoRange: { startSeconds: 267, endSeconds: 276 },
  },
  {
    stepId: "s9",
    order: 9,
    type: "GUIDE",
    makeup: "blush",
    part: "파우더 블러셔",
    summary:
      "컬러그램 틴토리 솜 블러셔 04 베리베일을 블러셔 브러시로 크림 블러셔 위에 레이어링 해줍니다.",
    tool: "블러셔 브러시",
    actions: [{ text: "브러시로 크림 블러셔 위에 겹쳐 발라요", tip: null }],
    doneWhen: "색이 자연스럽게 섞이면 끝나요",
    product: { brand: "컬러그램", name: "틴토리 솜 블러셔", shade: "04 베리베일" },
    videoRange: { startSeconds: 276, endSeconds: 287 },
  },
  {
    stepId: "s10",
    order: 10,
    type: "GUIDE",
    makeup: "eyeshadow",
    part: "눈두덩이 베이스 섀도우",
    summary:
      "웨이크메이크 소프트 블러링 아이팔레트 03 선셋블러링의 베이스 색상으로 눈두덩이와 애교살에 베이스 섀도우를 깔아줍니다.",
    tool: "아이섀도우 브러시",
    actions: [
      { text: "눈두덩이에 베이스 색을 깔아요", tip: null },
      { text: "애교살에도 같은 색을 발라요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "웨이크메이크", name: "소프트 블러링 아이팔레트", shade: "03 선셋블러링" },
    videoRange: { startSeconds: 287, endSeconds: 319 },
  },
  {
    stepId: "s11",
    order: 11,
    type: "GUIDE",
    makeup: "eyeliner",
    part: "언더 아이라인",
    summary:
      "웨이크메이크 소프트 블러링 아이팔레트 03 선셋블러링의 가장 진한 브라운 색상으로 눈 점막에서 살짝 띄워 언더 아이라인을 일자로 빼고 경계가 똑 떨어지지 않게 퍼뜨려줍니다.",
    tool: "아이섀도우 브러시",
    actions: [
      {
        text: "눈 점막에서 살짝 띄워 일자로 그려요",
        tip: { kind: "tip", text: "점막에서 띄우면 눈이 더 커 보여요" },
      },
      { text: "경계가 똑 떨어지지 않게 퍼뜨려요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "웨이크메이크", name: "소프트 블러링 아이팔레트", shade: "03 선셋블러링" },
    videoRange: { startSeconds: 319, endSeconds: 359 },
  },
  {
    stepId: "s12",
    order: 12,
    type: "GUIDE",
    makeup: "eyeliner",
    part: "점막 아이라인",
    summary:
      "캔메이크 크리미 터치 라이너 15 카푸치노 핑크로 눈 점막에서 살짝 0.1mm 띄워 아이라인을 그리고 뒷트임 부분은 조금 더 잡아줍니다.",
    tool: "아이라이너 펜슬",
    actions: [
      {
        text: "점막에서 살짝 0.1mm 띄워 그려요",
        tip: { kind: "tip", text: "띄우면 눈이 더 커 보여요" },
      },
      { text: "뒷트임 부분은 조금 더 잡아요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "캔메이크", name: "크리미 터치 라이너", shade: "15 카푸치노 핑크" },
    videoRange: { startSeconds: 359, endSeconds: 398 },
  },
  {
    stepId: "s13",
    order: 13,
    type: "GUIDE",
    makeup: "eyeshadow",
    part: "애교살 하이라이트",
    summary:
      "투쿨포스쿨 워터프루프 슬림 라이너 도화살몬 밀크 색상으로 눈 점막 바로 밑에 선을 살짝 그려 깔끔하고 뽀용한 애교살을 만들어줍니다.",
    tool: "아이라이너 펜슬",
    actions: [
      { text: "눈 점막 바로 밑에 선을 살짝 그려요", tip: null },
      { text: "선은 하나만 살살 그려요", tip: null },
    ],
    doneWhen: "깔끔하고 뽀용한 애교살이 되면 끝나요",
    product: { brand: "투쿨포스쿨", name: "워터프루프 슬림 라이너", shade: "도화살몬 밀크" },
    videoRange: { startSeconds: 398, endSeconds: 420 },
  },
  {
    stepId: "s14",
    order: 14,
    type: "GUIDE",
    makeup: "mascara",
    part: "마스카라",
    summary: "롬앤 한올 픽스 마스카라 롱 헤이즐을 속눈썹에 바르고 핀셋으로 속눈썹을 정리해줍니다.",
    tool: "마스카라 브러시",
    actions: [
      { text: "속눈썹에 발라요", tip: null },
      { text: "핀셋으로 속눈썹을 정리해요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "롬앤", name: "한올 픽스 마스카라 롱 헤이즐", shade: null },
    videoRange: { startSeconds: 420, endSeconds: 429 },
  },
  {
    stepId: "s15",
    order: 15,
    type: "GUIDE",
    makeup: "contour",
    part: "코 쉐딩",
    summary: "페리페라 브이 쉐딩 03 그레이쉬 쿨로 코 쉐딩을 넣어줍니다.",
    tool: "쉐딩 브러시",
    actions: [
      { text: "코끝 모양을 살짝 잡아요", tip: null },
      { text: "약간 좁게 안쪽으로 들어와요", tip: null },
      { text: "코끝을 살짝 커팅해요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "페리페라", name: "브이 쉐딩", shade: "03 그레이쉬 쿨" },
    videoRange: { startSeconds: 429, endSeconds: 452 },
  },
  {
    stepId: "s16",
    order: 16,
    type: "GUIDE",
    makeup: "highlight",
    part: "하이라이터",
    summary:
      "데이지크 멀티 섀도우 01 코튼키스의 하이라이터 색상을 코끝, 콧대, 눈 앞머리에 발라줍니다.",
    tool: "손가락",
    actions: [
      { text: "하이라이터를 손가락으로 찍어요", tip: null },
      { text: "코끝, 콧대, 눈 앞머리에 발라요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "데이지크", name: "멀티 섀도우", shade: "01 코튼키스" },
    videoRange: { startSeconds: 452, endSeconds: 465 },
  },
  {
    stepId: "s17",
    order: 17,
    type: "GUIDE",
    makeup: "lip",
    part: "립 라인 커버",
    summary: "투쿨포스쿨 워터프루프 슬림 라이너 도화살몬 밀크 색상으로 립 라인을 커버해줍니다.",
    tool: "립 라이너 펜슬",
    actions: [{ text: "입술 라인을 따라 그려요", tip: null }],
    doneWhen: null,
    product: { brand: "투쿨포스쿨", name: "워터프루프 슬림 라이너", shade: "도화살몬 밀크" },
    videoRange: { startSeconds: 465, endSeconds: 479 },
  },
  {
    stepId: "s18",
    order: 18,
    type: "GUIDE",
    makeup: "lip",
    part: "베이스 립 틴트",
    summary: "잉가 벨벳 쥬 틴트 애프리콧 슈를 입술에 베이스로 발라줍니다.",
    tool: "어플리케이터",
    actions: [
      { text: "입술에 베이스로 발라요", tip: null },
      { text: "입술 주름을 잘 메워요", tip: null },
    ],
    doneWhen: null,
    product: { brand: "잉가", name: "벨벳 쥬 틴트", shade: "애프리콧 슈" },
    videoRange: { startSeconds: 479, endSeconds: 499 },
  },
  {
    stepId: "s19",
    order: 19,
    type: "GUIDE",
    makeup: "lip",
    part: "메인 립 글로스",
    summary: "웸 3D 볼류밍 글로스 스카치 70%를 메인 립으로 발라줍니다.",
    tool: "어플리케이터",
    actions: [{ text: "글로스를 입술에 발라요", tip: null }],
    doneWhen: null,
    product: { brand: "웸", name: "3D 볼류밍 글로스", shade: "스카치 70%" },
    videoRange: { startSeconds: 499, endSeconds: 515 },
  },
];
