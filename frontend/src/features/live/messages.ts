import type { CameraErrorKind } from "@/vision/face";

/** 카메라 오류 종류별 제목·설명 */
export const CAMERA_ERROR_TEXT: Partial<Record<CameraErrorKind, [string, string]>> = {
  "permission-denied": [
    "카메라 권한이 꺼져 있어요",
    "설정에서 카메라를 허용하면 내 얼굴에 입혀 볼 수 있어요.",
  ],
  "not-found": ["카메라를 찾을 수 없어요", "카메라가 연결돼 있는지 확인해 주세요."],
  "in-use": ["다른 앱이 카메라를 쓰고 있어요", "다른 앱을 닫은 뒤 다시 시도해 주세요."],
  "tracker-failed": ["얼굴 인식을 불러오지 못했어요", "네트워크를 확인하고 다시 시도해 주세요."],
  disconnected: ["카메라 연결이 끊어졌어요", "카메라 연결을 확인한 뒤 다시 시도해 주세요."],
  insecure: ["보안 연결이 아니에요", "카메라는 HTTPS 주소에서만 사용할 수 있어요."],
  unsupported: ["카메라를 지원하지 않는 브라우저예요", "최신 Chrome에서 다시 열어 주세요."],
  blocked: [
    "이 화면에서는 카메라 사용이 차단되어 있어요",
    "브라우저나 관리자 정책으로 카메라를 쓸 수 없어요.",
  ],
  unknown: ["카메라를 시작하지 못했어요", "잠시 후 다시 시도해 주세요."],
};

export type LiveAlert = "lost" | "turn" | "cover" | "far" | "light";
export const ALERT: Record<LiveAlert, [string, string]> = {
  lost: ["얼굴이 화면을 벗어났어요", "화면 가운데로 돌아오면 메이크업이 다시 보여요."],
  turn: ["고개를 정면으로 돌려 주세요", "옆으로 많이 돌리면 색이 어긋나서 잠시 숨겼어요."],
  cover: ["손이나 도구가 얼굴을 가리고 있어요", "가린 동안 메이크업을 잠시 숨겼어요."],
  far: ["조금 더 가까이 와 주세요", "얼굴이 작게 보이면 색이 정확하지 않아요."],
  light: [
    "조명이 바뀌었어요",
    "처음 등록한 얼굴보다 어두워요. 밝은 곳으로 옮기면 색이 정확해져요.",
  ],
};

/** ?alert= 값 중 아는 것만 받는다. 모르는 값은 알림 없음 */
export function parseAlert(value: string | null | undefined): LiveAlert | null {
  return value && Object.hasOwn(ALERT, value) ? (value as LiveAlert) : null;
}
