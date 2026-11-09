import type { GuideActionDto } from "./guide-api";
import type { AreaSubStep, GuideArea, Makeup } from "./types";

/** 화장 종류의 한국어 이름. 부위 이름(partLabel)이 비었을 때 쓴다 */
export const MAKEUP_LABEL: Record<Makeup, string> = {
  foundation: "베이스",
  eyeshadow: "아이섀도",
  eyeliner: "아이라인",
  blush: "블러셔",
  lip: "립",
  brow: "눈썹",
  mascara: "마스카라",
  contour: "쉐딩",
  highlight: "하이라이터",
  other: "기타",
};

/** 따라 하는(GUIDE) 단계 하나 */
export interface GuideStepModel {
  stepId: string;
  order: number;
  makeup: Makeup;
  /** 화면 제목. 부위 이름이 없으면 화장 종류 이름 */
  label: string;
  summary: string | null;
  actions: GuideActionDto[];
  doneWhen: string | null;
  /** 영상에 나온 제품 이름과 호수. 둘 다 없으면 null */
  product: { name: string | null; shade: string | null } | null;
  /** 모르는 값이면 null */
  matchCategory: MatchCategory | null;
  subSteps: AreaSubStep[];
}

export const MATCH_CATEGORIES = ["BASE", "EYE", "BROW", "CHEEK", "LIP"] as const;
export type MatchCategory = (typeof MATCH_CATEGORIES)[number];

/** 화면이 쓰는 가이드. 단계는 GUIDE만 order 순으로 담는다 */
export interface GuideModel {
  guideId: string;
  guideVersion: number;
  videoId: string;
  youtubeVideoId: string | null;
  thumbnailUrl: string | null;
  title: string;
  channelTitle: string;
  /** 가이드 영역의 메시 판. 영역이 없으면 null */
  meshVersion: string | null;
  steps: GuideStepModel[];
}

/** 응답이 약속한 모양과 달라 쓸 수 없음 */
export class GuideContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GuideContractError";
  }
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown) => (typeof v === "string" && v.trim() ? v : null);
const isMakeup = (v: unknown): v is Makeup =>
  typeof v === "string" && Object.hasOwn(MAKEUP_LABEL, v);
const isMatchCategory = (v: unknown): v is MatchCategory =>
  (MATCH_CATEGORIES as readonly unknown[]).includes(v);
const AREA_STATUSES = new Set<unknown>(["extracted", "template", "notApplicable", "failed"]);

function actionsOf(v: unknown): GuideActionDto[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((a) => {
    if (!isRecord(a) || !text(a.text)) return [];
    const tip = isRecord(a.tip) && text(a.tip.text) ? a.tip : null;
    return [
      {
        text: a.text as string,
        tip: tip
          ? { kind: tip.kind === "caution" ? "caution" : "tip", text: tip.text as string }
          : null,
      },
    ];
  });
}

// 모양이 틀린 하위 단계는 그 하위 단계만 빼고, 단계의 설명은 그대로 보여 준다
function subStepsOf(stepId: string, v: unknown): AreaSubStep[] {
  if (!Array.isArray(v)) return [];
  return v.filter((sub): sub is AreaSubStep => {
    const ok = isRecord(sub) && !!text(sub.subStepId) && AREA_STATUSES.has(sub.status);
    if (!ok) console.warn(`${stepId}의 하위 단계 모양이 달라 뺍니다`, sub);
    return ok;
  });
}

function productOf(v: unknown): GuideStepModel["product"] {
  if (!isRecord(v)) return null;
  const name = text(v.name);
  const shade = text(v.shadeName);
  return name || shade ? { name, shade } : null;
}

/**
 * 가이드 조회 응답을 검사해 화면 모델로 바꾼다.
 * 요청한 가이드가 아니거나, 단계 ID·순서가 겹치거나, 알 수 없는 단계 종류면 쓸 수 없어 던진다.
 * 제품·동작·끝내는 때·영역이 비어 있는 것은 정상 데이터다.
 */
export function toGuideModel(raw: unknown, guideId: string): GuideModel {
  if (!isRecord(raw)) throw new GuideContractError("가이드 응답이 객체가 아닙니다");
  if (typeof raw.guideId !== "string" || raw.guideId.toLowerCase() !== guideId.toLowerCase())
    throw new GuideContractError(
      `요청한 가이드(${guideId})와 응답(${String(raw.guideId)})이 다릅니다`,
    );
  const version = raw.guideVersion;
  if (typeof version !== "number" || !Number.isInteger(version) || version < 1)
    throw new GuideContractError(`guideVersion이 1 이상 정수가 아닙니다: ${String(version)}`);
  if (!Array.isArray(raw.steps)) throw new GuideContractError("steps가 배열이 아닙니다");

  const ids = new Set<string>();
  const orders = new Set<number>();
  const guided: GuideStepModel[] = [];
  for (const step of raw.steps) {
    if (!isRecord(step)) throw new GuideContractError("단계가 객체가 아닙니다");
    const stepId = text(step.stepId);
    const order = step.order;
    if (!stepId) throw new GuideContractError("stepId가 없는 단계가 있습니다");
    if (typeof order !== "number" || !Number.isInteger(order) || order < 1)
      throw new GuideContractError(`${stepId}의 order가 1 이상 정수가 아닙니다`);
    if (ids.has(stepId)) throw new GuideContractError(`단계 ID ${stepId}가 겹칩니다`);
    if (orders.has(order)) throw new GuideContractError(`단계 순서 ${order}가 겹칩니다`);
    ids.add(stepId);
    orders.add(order);
    if (step.type === "EXCLUDED") continue;
    if (step.type !== "GUIDE")
      throw new GuideContractError(`${stepId}의 단계 종류(${String(step.type)})를 알 수 없습니다`);

    // 모르는 화장 종류는 기본 가이드가 없으므로 기타로 보고 설명만 보여 준다
    const makeup = isMakeup(step.part) ? step.part : "other";
    if (makeup !== step.part)
      console.warn(`${stepId}의 화장 종류(${String(step.part)})를 몰라 기타로 봅니다`);
    guided.push({
      stepId,
      order,
      makeup,
      label: text(step.partLabel) ?? MAKEUP_LABEL[makeup],
      summary: text(step.summary),
      actions: actionsOf(step.actions),
      doneWhen: text(step.doneWhen),
      product: productOf(step.referenceProduct),
      matchCategory: isMatchCategory(step.matchCategory) ? step.matchCategory : null,
      subSteps: subStepsOf(stepId, step.subSteps),
    });
  }
  guided.sort((a, b) => a.order - b.order);
  // 서버와 세는 규칙이 어긋나도 화면은 실제 단계로 돈다. 차이만 알린다
  if (raw.stepCount !== guided.length)
    console.warn(
      `stepCount(${String(raw.stepCount)})와 GUIDE 단계 수(${guided.length})가 다릅니다`,
    );

  return {
    guideId,
    guideVersion: version,
    videoId: text(raw.videoId) ?? "",
    youtubeVideoId: text(raw.youtubeVideoId),
    thumbnailUrl: text(raw.thumbnailUrl),
    title: text(raw.title) ?? "",
    channelTitle: text(raw.channelTitle) ?? "",
    meshVersion: text(raw.meshVersion),
    steps: guided,
  };
}

/** 단계별 영역을 기존 영역 형식으로 모은다. 영역이 하나도 없는 가이드면 null */
export function toGuideArea(model: GuideModel): GuideArea | null {
  if (!model.meshVersion) return null;
  return {
    videoId: model.videoId,
    meshVersion: model.meshVersion as GuideArea["meshVersion"],
    steps: model.steps.map(({ stepId, order, makeup, subSteps }) => ({
      stepId,
      order,
      makeup,
      subSteps,
    })),
  };
}
