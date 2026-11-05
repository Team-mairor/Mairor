export { resolveStep, resolveSubStep } from "./area";
export {
  fetchGuide,
  type GuideActionDto,
  type GuideDto,
  type GuideStepDto,
  type ReferenceProductDto,
} from "./guide-api";
export {
  GuideContractError,
  MAKEUP_LABEL,
  toGuideArea,
  toGuideModel,
  type GuideModel,
  type GuideStepModel,
} from "./guide-model";
export {
  checkGuideArea,
  GuideOverlay,
  loadDefaultGuideSet,
  loadGuideArea,
  loadGuideSet,
  useStepInView,
} from "./guide-overlay";
export { GuideRenderer, isStepVisible, type Projection } from "./renderer";
export type * from "./types";
export { useGuide, type GuideLoad } from "./use-guide";
