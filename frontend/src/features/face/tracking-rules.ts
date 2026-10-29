// 추적 상태 판정 기준. 픽스처 생성 스크립트도 Node에서 바로 읽으므로 다른 모듈을 값으로 import하지 않는다.
import type { RegionName } from "./types";

/** 추적이 안정적인지 볼 때 쓰는 핵심 부위 */
export const KEY_REGIONS: readonly RegionName[] = ["leftEye", "rightEye", "lipsOuter"];

/**
 * 핵심 부위가 이 개수보다 적게 보이면(화면 안·카메라 쪽) 추적이 불안정(degraded)한 것으로 본다.
 * 하나만 잘려도 불안정으로 보면, 눈 화장을 하려고 가까이 다가가 입이 화면 밖으로 나갈 때 전부 숨겨진다.
 * 잘린 부위는 화장 레이어·가이드가 부위별로 따로 숨긴다.
 */
export const MIN_KEY_REGIONS_IN_VIEW = 2;

/** 이 각도(라디안)를 넘게 돌리면 반대쪽 부위를 보이지 않는 것으로 본다. */
export const DEFAULT_MAX_YAW = 0.6;
