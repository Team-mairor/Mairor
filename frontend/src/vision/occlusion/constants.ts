/** shared/occlusion/README.md의 입력 · 출력 규격 */
export const OCCLUSION_MODEL_URL = "/models/occlusion_bisenet.v1.web.fp16.onnx";
/** onnxruntime-web 실행 파일을 두는 자리(scripts/sync-mediapipe-assets.mjs가 복사한다) */
export const OCCLUSION_RUNTIME_PATH = "/occlusion-runtime/";
/** 출력 라벨 가운데 가림(손 · 붓 · 펜슬 · 퍼프 · 제품 · 머리카락 · 자막) */
export const OCCLUSION_LABEL = 19;
export const OCCLUSION_CLASSES = 20;
/** 얼굴 점을 감싼 네모의 긴 변에 곱하는 자르기 배율 */
export const OCCLUSION_CROP_SCALE = 1.4;
export const IMAGENET_MEAN = [0.485, 0.456, 0.406] as const;
export const IMAGENET_STD = [0.229, 0.224, 0.225] as const;
