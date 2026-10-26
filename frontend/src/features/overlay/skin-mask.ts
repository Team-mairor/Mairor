import type { ImageSegmenter, MPMask } from "@mediapipe/tasks-vision";

import { MEDIAPIPE_WASM_PATH } from "@/features/face/landmarker";

export const SKIN_SEGMENTER_MODEL_PATH = "/models/selfie_multiclass_256x256.tflite";

// 모델 입력이 256×256이라 영상을 이 너비로 줄여 넣는다. 결과 마스크도 같은 크기다.
const INPUT_WIDTH = 256;
// 얼굴 피부 확률이 이 범위에서 0 → 1로 바뀐다. 경계를 부드럽게 한다.
const EDGE = [0.3, 0.7] as const;
// 직전 마스크와 섞는 비율. 프레임마다 판정이 흔들려 경계가 깜빡이는 것을 줄인다.
const KEEP = 0.4;

async function createSegmenter(): Promise<ImageSegmenter> {
  const { FilesetResolver, ImageSegmenter } = await import("@mediapipe/tasks-vision");
  // 모델이 없을 때 GPU 실패로 오해하지 않도록, GPU·CPU를 시도하기 전에 먼저 확인한다.
  const model = await fetch(SKIN_SEGMENTER_MODEL_PATH, { method: "HEAD" });
  if (!model.ok) {
    throw new Error(
      `피부 분할 모델이 없습니다 (${model.status}). npm run sync:mediapipe로 내려받아 주세요`,
    );
  }
  const fileset = await FilesetResolver.forVisionTasks(MEDIAPIPE_WASM_PATH);
  const create = (delegate: "GPU" | "CPU") =>
    ImageSegmenter.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: SKIN_SEGMENTER_MODEL_PATH, delegate },
      runningMode: "VIDEO",
      outputConfidenceMasks: true,
      outputCategoryMask: false,
    });
  try {
    return await create("GPU");
  } catch (e) {
    console.warn("GPU로 피부 분할을 시작하지 못해 CPU로 다시 시도합니다", e);
    return create("CPU");
  }
}

/**
 * 영상에서 얼굴 피부 영역을 알파 이미지로 만든다.
 * 앞머리·손·브러시처럼 얼굴을 가린 곳은 0이라, 화장 레이어에 곱하면 가린 곳에 칠하지 않는다.
 */
export class SkinMask {
  /** 영상과 같은 비율의 작은 알파 이미지 */
  readonly canvas = document.createElement("canvas");
  private readonly input = document.createElement("canvas");
  private readonly inputCtx = this.input.getContext("2d")!;
  private readonly maskCtx = this.canvas.getContext("2d")!;
  private image: ImageData | null = null;
  private previous: Float32Array | null = null;
  private faceSkin = -1;
  private lastTimestamp = -1;
  private disposed = false;
  /** 마지막 분할에 걸린 시간 (ms) */
  lastMs = 0;
  /** 마스크를 새로 쓸 때마다 늘어난다. 같으면 화면 쪽에서 다시 그리지 않아도 된다 */
  version = 0;

  private constructor(private readonly segmenter: ImageSegmenter) {
    // 모델 라벨: background, hair, body-skin, face-skin, clothes, others
    this.faceSkin = segmenter.getLabels().findIndex((l) => l.toLowerCase().includes("face"));
    if (this.faceSkin < 0) this.faceSkin = 3;
  }

  static async create() {
    return new SkinMask(await createSegmenter());
  }

  /** 지금 영상 프레임으로 마스크를 갱신한다. */
  update(video: HTMLVideoElement) {
    if (this.disposed || !video.videoWidth) return;
    const width = INPUT_WIDTH;
    const height = Math.round((video.videoHeight / video.videoWidth) * INPUT_WIDTH);
    if (this.input.width !== width || this.input.height !== height) {
      this.input.width = this.canvas.width = width;
      this.input.height = this.canvas.height = height;
      this.image = this.maskCtx.createImageData(width, height);
      this.previous = null;
    }
    this.inputCtx.drawImage(video, 0, 0, width, height);

    const start = performance.now();
    // VIDEO 모드는 단조 증가하는 타임스탬프가 필요하다.
    const timestamp = Math.max(start, this.lastTimestamp + 1);
    this.lastTimestamp = timestamp;
    const result = this.segmenter.segmentForVideo(this.input, timestamp);
    // 마스크를 읽다가 예외가 나도 결과는 해제한다.
    try {
      this.readMask(result.confidenceMasks?.[this.faceSkin]);
    } finally {
      result.close();
    }
    this.lastMs = performance.now() - start;
  }

  private readMask(mask: MPMask | undefined) {
    if (mask && this.image) {
      const values = mask.getAsFloat32Array();
      const data = this.image.data;
      const previous = this.previous ?? new Float32Array(values.length).fill(-1);
      for (let i = 0; i < values.length; i++) {
        let t = Math.max(0, Math.min(1, (values[i] - EDGE[0]) / (EDGE[1] - EDGE[0])));
        if (previous[i] >= 0) t = previous[i] * KEEP + t * (1 - KEEP);
        previous[i] = t;
        data[i * 4] = data[i * 4 + 1] = data[i * 4 + 2] = 255;
        data[i * 4 + 3] = t * 255;
      }
      this.previous = previous;
      this.maskCtx.putImageData(this.image, 0, 0);
      this.version++;
    }
  }

  dispose() {
    // 계속 실패해 미리 끈 뒤 effect 정리에서 다시 불릴 수 있다.
    if (this.disposed) return;
    this.disposed = true;
    this.segmenter.close();
  }
}
