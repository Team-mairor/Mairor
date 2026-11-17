// 가이드 조회(GET /v1/guides/{guideId}) 모의 응답. BE GuideQueryService와 같은 규칙으로 만든다.
// 목표 색·대표 이미지는 실제 1차 응답처럼 항상 null이다.
import type { GuideDto, GuideStepDto, Makeup } from "@/features/guide";

import {
  MOCK_GUIDE_AREA_URL,
  MOCK_GUIDE_STEPS,
  MOCK_VIDEO_ID,
  type MockGuideStep,
} from "./mock-guide";

/** 샘플 영상(AI 샘플 local_01)의 가이드. 단계·설명은 목업, 영역은 같은 영상의 영역 픽스처 */
export const MOCK_GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
/**
 * 9가지 화장 종류를 한 단계씩 담은 가이드. 샘플 영상에 없는 눈썹까지 표시를 확인한다.
 * 마스카라 단계는 AI 설명이 없는 단계라 동작이 비고, 화면은 요약으로 대신 보여 준다
 */
export const MOCK_ALL_PARTS_GUIDE_ID = "a0000000-0000-4000-8000-000000000002";
/** 세션이 없을 때처럼 401(로그인 필요)로 답하는 가이드 */
export const MOCK_LOGIN_REQUIRED_GUIDE_ID = "a0000000-0000-4000-8000-000000000003";

const MATCH_CATEGORY: Partial<Record<Makeup, string>> = {
  foundation: "BASE",
  eyeshadow: "EYE",
  eyeliner: "EYE",
  mascara: "EYE",
  brow: "BROW",
  blush: "CHEEK",
  highlight: "CHEEK",
  contour: "CHEEK",
  lip: "LIP",
};

function toStep(s: MockGuideStep, subSteps: GuideStepDto["subSteps"]): GuideStepDto {
  const guide = s.type === "GUIDE";
  const name = [s.product?.brand, s.product?.name].filter(Boolean).join(" ") || null;
  const shade = s.product?.shade ?? null;
  return {
    stepId: s.stepId,
    order: s.order,
    type: s.type,
    part: s.makeup,
    partLabel: s.part,
    summary: s.summary,
    actions: s.actions,
    doneWhen: s.doneWhen,
    tools: s.tool ? [s.tool] : [],
    referenceProduct:
      name || shade
        ? {
            productId: null,
            shadeId: null,
            name,
            shadeName: shade,
            matchStatus: "UNMATCHED",
            verification: "UNKNOWN",
            sources: [],
            videoConfirmed: true,
          }
        : null,
    targetColor: null,
    videoRange: s.videoRange,
    matchCategory: guide ? (MATCH_CATEGORY[s.makeup] ?? null) : null,
    subSteps,
  };
}

function toGuide(guideId: string, steps: GuideStepDto[], meshVersion: string | null): GuideDto {
  return {
    guideId,
    guideVersion: 1,
    videoId: "b0000000-0000-4000-8000-000000000001",
    youtubeVideoId: MOCK_VIDEO_ID,
    title: "모의 가이드",
    channelTitle: "모의 채널",
    thumbnailUrl: null,
    meshVersion,
    referenceImageUrl: null,
    stepCount: steps.filter((s) => s.type === "GUIDE").length,
    steps,
  };
}

const ALL_PARTS: { makeup: Makeup; part: string }[] = [
  { makeup: "foundation", part: "베이스" },
  { makeup: "brow", part: "눈썹" },
  { makeup: "eyeshadow", part: "아이섀도" },
  { makeup: "eyeliner", part: "아이라인" },
  { makeup: "mascara", part: "마스카라" },
  { makeup: "contour", part: "쉐딩" },
  { makeup: "highlight", part: "하이라이터" },
  { makeup: "blush", part: "블러셔" },
  { makeup: "lip", part: "립" },
];

/** guideId의 모의 가이드. 모르는 ID면 null(서버의 404) */
export async function mockGuide(guideId: string): Promise<GuideDto | null> {
  if (guideId === MOCK_GUIDE_ID) {
    // 영역 픽스처는 커서 번들에 넣지 않고 요청할 때 읽는다
    const area = await fetch(MOCK_GUIDE_AREA_URL).then((r) => r.json());
    const subStepsOf = (stepId: string) =>
      area.steps.find((s: { stepId: string }) => s.stepId === stepId)?.subSteps ?? [];
    return toGuide(
      guideId,
      MOCK_GUIDE_STEPS.map((s) => toStep(s, subStepsOf(s.stepId))),
      area.meshVersion,
    );
  }
  if (guideId === MOCK_ALL_PARTS_GUIDE_ID) {
    const steps = ALL_PARTS.map(({ makeup, part }, i) =>
      toStep(
        {
          stepId: `p${i + 1}`,
          order: i + 1,
          type: "GUIDE",
          makeup,
          part,
          summary: `${part} 제품을 기본 위치에 발라 줍니다.`,
          tool: null,
          actions:
            makeup === "mascara" ? [] : [{ text: `${part} 기본 위치를 따라 발라요`, tip: null }],
          doneWhen: null,
          product: null,
          videoRange: { startSeconds: i * 10, endSeconds: i * 10 + 10 },
        },
        [
          {
            subStepId: `p${i + 1}-1`,
            order: 1,
            status: "template",
            reasons: ["notAnalyzed"],
            templateId: makeup,
            guideSets: [],
          },
        ],
      ),
    );
    return toGuide(guideId, steps, "v1");
  }
  return null;
}
