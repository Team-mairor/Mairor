import type { FaceDetector, FaceLandmarker } from "@mediapipe/tasks-vision";

export const MEDIAPIPE_WASM_PATH = "/mediapipe/wasm";
export const FACE_LANDMARKER_MODEL_PATH = "/models/face_landmarker.task";
export const FACE_DETECTOR_MODEL_PATH = "/models/blaze_face_short_range.tflite";

export interface LandmarkerConfidence {
  minFaceDetectionConfidence: number;
  minFacePresenceConfidence: number;
  minTrackingConfidence: number;
}

// 화장 중에는 손·브러시 가림과 근접 촬영이 잦아 추적 유지 기준을 기본값(0.5)보다 낮춘다.
const DEFAULT_CONFIDENCE: LandmarkerConfidence = {
  minFaceDetectionConfidence: 0.5,
  minFacePresenceConfidence: 0.3,
  minTrackingConfidence: 0.3,
};

// 브라우저에서만 호출한다. 서버 렌더링 때 로드되지 않도록 동적으로 import한다.
export async function createFaceLandmarker(
  confidence: Partial<LandmarkerConfidence> = {},
): Promise<FaceLandmarker> {
  const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");

  const fileset = await FilesetResolver.forVisionTasks(MEDIAPIPE_WASM_PATH);

  const create = (delegate: "GPU" | "CPU") =>
    FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: FACE_LANDMARKER_MODEL_PATH, delegate },
      runningMode: "VIDEO",
      numFaces: 1,
      outputFaceBlendshapes: true,
      outputFacialTransformationMatrixes: true,
      ...DEFAULT_CONFIDENCE,
      ...confidence,
    });

  // WebGL2를 쓸 수 없는 기기에서는 느리더라도 CPU로 돌린다.
  try {
    return await create("GPU");
  } catch (e) {
    console.warn("GPU로 얼굴 추적을 시작하지 못해 CPU로 다시 시도합니다", e);
    return create("CPU");
  }
}

// 랜드마크 추적은 얼굴 하나만 따라가므로, 가장 큰 얼굴을 확인하는 가벼운 검출기를 따로 둔다.
export async function createFaceDetector(): Promise<FaceDetector> {
  const { FaceDetector, FilesetResolver } = await import("@mediapipe/tasks-vision");

  const fileset = await FilesetResolver.forVisionTasks(MEDIAPIPE_WASM_PATH);

  return FaceDetector.createFromOptions(fileset, {
    baseOptions: {
      modelAssetPath: FACE_DETECTOR_MODEL_PATH,
      delegate: "GPU",
    },
    runningMode: "VIDEO",
  });
}
