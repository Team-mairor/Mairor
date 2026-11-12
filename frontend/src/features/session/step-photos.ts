// 현재 실행 화면과 완료 직후 미리보기에 쓰는 로컬 캐시. 서버 리포트는 API에서 사진 URL을 다시 읽는다.
import type { PhotoBox } from "@/features/face";

export interface StepPhoto {
  /** 얼굴 전체 사진 (JPEG data URL) */
  url: string;
  /** 그 단계 부위를 확대해 보여 줄 네모. 얼굴 전체를 쓰는 단계면 null */
  box: PhotoBox | null;
}

/** 실행 id → 단계 id → 사진 */
const photos = new Map<string, Map<string, StepPhoto>>();
/** 완료 기록을 남긴 실행. 실행이 끝나도 리포트에서 계속 보여 준다 */
const kept = new Set<string>();

/** 단계당 사진 1장. 다시 찍으면 덮어쓴다 */
export function saveStepPhoto(runId: string, stepId: string, photo: StepPhoto) {
  if (!photos.has(runId)) photos.set(runId, new Map());
  photos.get(runId)!.set(stepId, photo);
}

export function stepPhoto(runId: string | undefined, stepId: string): StepPhoto | null {
  return (runId && photos.get(runId)?.get(stepId)) || null;
}

/** 완료 기록을 남긴 실행의 사진은 실행이 끝나도 남긴다 */
export function keepStepPhotos(runId: string) {
  kept.add(runId);
}

/** 기록을 남기지 않은 실행의 사진을 지운다. 실행이 끝나거나 무효가 되거나 바뀔 때 부른다 */
export function discardUnsavedStepPhotos() {
  for (const id of photos.keys()) if (!kept.has(id)) photos.delete(id);
}

/** 촬영 기록을 비우고 다시 시작할 때 그 실행의 사진도 비운다. 완료 기록을 남긴 실행은 그대로 둔다 */
export function resetStepPhotos(runId: string) {
  if (!kept.has(runId)) photos.delete(runId);
}

/** 리포트를 지울 때 그 실행의 사진도 지운다 */
export function deleteStepPhotos(runId: string) {
  photos.delete(runId);
  kept.delete(runId);
}
