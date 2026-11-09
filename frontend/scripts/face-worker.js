// classic Worker에서 MediaPipe의 wasm 로더(importScripts)를 실행한다.
globalThis.importScripts("./vision_bundle.js");

let landmarker;
let detector;
const send = (message) => globalThis.postMessage(message);

globalThis.onmessage = async ({ data }) => {
  try {
    if (data.type === "init") {
      const { FaceLandmarker, FaceDetector, FilesetResolver } = globalThis.Vision;
      const fileset = await FilesetResolver.forVisionTasks(
        new URL("./wasm", globalThis.location.href).href,
      );
      const preference = data.preference;
      const create = (delegate) =>
        FaceLandmarker.createFromOptions(fileset, {
          baseOptions: {
            modelAssetPath: new URL("/models/face_landmarker.task", globalThis.location.href).href,
            delegate,
          },
          runningMode: "VIDEO",
          numFaces: 1,
          outputFaceBlendshapes: preference.blendshapes,
          outputFacialTransformationMatrixes: true,
          ...preference.confidence,
        });
      let delegate = preference.delegate === "CPU" ? "CPU" : "GPU";
      try {
        landmarker = await create(delegate);
      } catch (error) {
        if (preference.delegate !== "auto") throw error;
        delegate = "CPU";
        landmarker = await create(delegate);
      }
      try {
        detector = await FaceDetector.createFromOptions(fileset, {
          baseOptions: {
            modelAssetPath: new URL(
              "/models/blaze_face_short_range.tflite",
              globalThis.location.href,
            ).href,
            delegate,
          },
          runningMode: "VIDEO",
        });
      } catch (error) {
        console.warn("가장 큰 얼굴 확인 없이 추적합니다", error);
      }
      send({ type: "ready", delegate });
      return;
    }
    const start = performance.now();
    try {
      const result = landmarker.detectForVideo(data.image, data.timestamp);
      const detected = performance.now();
      let detections;
      if (data.checkLargest && detector) {
        try {
          detections = detector.detectForVideo(data.image, data.timestamp).detections;
        } catch (error) {
          console.warn("얼굴 검출기를 끄고 추적을 계속합니다", error);
          detector.close();
          detector = null;
        }
      }
      send({
        type: "result",
        id: data.id,
        result,
        detections,
        detectMs: detected - start,
        largestMs: performance.now() - detected,
      });
    } finally {
      data.image.close();
    }
  } catch (error) {
    send({
      type: "error",
      id: data.id,
      message: error instanceof Error ? error.message : String(error),
    });
  }
};
