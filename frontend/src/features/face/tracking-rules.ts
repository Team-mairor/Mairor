// 추적 상태 판정 기준. 픽스처 생성 스크립트도 Node에서 바로 읽으므로 다른 모듈을 값으로 import하지 않는다.
import type { RegionName } from "./types";

/** 이 부위 중 하나라도 화면 밖이거나 돌아가 있으면 추적이 불안정(degraded)한 것으로 본다. */
export const KEY_REGIONS: readonly RegionName[] = ["leftEye", "rightEye", "lipsOuter"];

/** 이 각도(라디안)를 넘게 돌리면 반대쪽 부위를 보이지 않는 것으로 본다. */
export const DEFAULT_MAX_YAW = 0.6;
