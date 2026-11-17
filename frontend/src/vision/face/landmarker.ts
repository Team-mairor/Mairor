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

export type Delegate = "GPU" | "CPU";

/** 기기별 성능 비교용 설정. 기본은 GPU를 먼저 시도하고 blendshape(눈 뜬 정도)를 계산한다. */
export interface LandmarkerPreference {
  delegate: Delegate | "auto";
  blendshapes: boolean;
}

const preference: LandmarkerPreference = { delegate: "auto", blendshapes: true };

export function landmarkerPreference() {
  return { ...preference, confidence: { ...DEFAULT_CONFIDENCE } };
}

/** 실제로 만든 추적 모델의 실행 방식과 GPU 이름 (확인 화면 표시용) */
export const landmarkerInfo: { delegate: Delegate | null; gpu: string | null } = {
  delegate: null,
  gpu: null,
};

/** 주소의 ?delegate=gpu|cpu, ?blendshapes=off 로 설정을 바꾼다. 다음에 만드는 모델부터 적용된다. */
export function applyLandmarkerParams(search: string) {
  const params = new URLSearchParams(search);
  const delegate = params.get("delegate")?.toUpperCase();
  preference.delegate = delegate === "GPU" || delegate === "CPU" ? delegate : "auto";
  preference.blendshapes = params.get("blendshapes") !== "off";
}

let cachedGpuName: string | null | undefined;

/**
 * 브라우저가 쓰는 GPU 이름. 소프트웨어 렌더링(SwiftShader)이면 GPU 가속이 꺼진 것이다.
 * 추적기를 다시 만들 때마다 컨텍스트가 쌓이면 브라우저가 오래된 것(화장 레이어 마스크)부터 끊으므로,
 * 한 번만 구하고 쓴 컨텍스트는 바로 놓는다.
 */
function gpuName(): string | null {
  if (cachedGpuName !== undefined) return cachedGpuName;
  const gl = document.createElement("canvas").getContext("webgl2");
  if (!gl) return (cachedGpuName = null);
  const ext = gl.getExtension("WEBGL_debug_renderer_info");
  cachedGpuName = String(gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
  gl.getExtension("WEBGL_lose_context")?.loseContext();
  return cachedGpuName;
}

// MediaPipe wasm은 자기 INFO 로그("Created TensorFlow Lite XNNPACK delegate for CPU.")를 stderr →
// console.error로 내보낸다. 오류가 아니므로 Next 개발 오버레이에 뜨지 않게 거른다.
// 얼굴 추적기·검출기·피부 분할 모델처럼 MediaPipe 모델을 만드는 곳마다 먼저 부른다.
let infoFiltered = false;
export function filterMediapipeInfo() {
  if (infoFiltered) return;
  infoFiltered = true;
  const original = console.error;
  // TFLite delegate 생성 로그만 거른다. 다른 INFO 접두어는 그대로 오류로 남긴다
  const MEDIAPIPE_INFO = /^INFO: Created TensorFlow Lite .* delegate/;
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && MEDIAPIPE_INFO.test(args[0])) return console.info(...args);
    original(...args);
  };
}

// 브라우저에서만 호출한다. 서버 렌더링 때 로드되지 않도록 동적으로 import한다.
export async function createFaceLandmarker(
  confidence: Partial<LandmarkerConfidence> = {},
): Promise<FaceLandmarker> {
  const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
  filterMediapipeInfo();

  const fileset = await FilesetResolver.forVisionTasks(MEDIAPIPE_WASM_PATH);

  const create = (delegate: Delegate) =>
    FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: FACE_LANDMARKER_MODEL_PATH, delegate },
      runningMode: "VIDEO",
      numFaces: 1,
      outputFaceBlendshapes: preference.blendshapes,
      outputFacialTransformationMatrixes: true,
      ...DEFAULT_CONFIDENCE,
      ...confidence,
    });

  landmarkerInfo.gpu = gpuName();
  const createWith = async (delegate: Delegate) => {
    const landmarker = await create(delegate);
    landmarkerInfo.delegate = delegate;
    return landmarker;
  };
  if (preference.delegate !== "auto") return createWith(preference.delegate);
  // WebGL2를 쓸 수 없는 기기에서는 느리더라도 CPU로 돌린다.
  try {
    return await createWith("GPU");
  } catch (e) {
    console.warn("GPU로 얼굴 추적을 시작하지 못해 CPU로 다시 시도합니다", e);
    return createWith("CPU");
  }
}

// 랜드마크 추적은 얼굴 하나만 따라가므로, 가장 큰 얼굴을 확인하는 가벼운 검출기를 따로 둔다.
export async function createFaceDetector(): Promise<FaceDetector> {
  const { FaceDetector, FilesetResolver } = await import("@mediapipe/tasks-vision");
  filterMediapipeInfo();

  const fileset = await FilesetResolver.forVisionTasks(MEDIAPIPE_WASM_PATH);

  return FaceDetector.createFromOptions(fileset, {
    baseOptions: {
      modelAssetPath: FACE_DETECTOR_MODEL_PATH,
      delegate: "GPU",
    },
    runningMode: "VIDEO",
  });
}
