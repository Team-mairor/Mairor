import type { MeshAnchor } from "./types";

/** 등록 사진에서 찾은 원래 눈썹 테두리. 찾지 못한 쪽은 비운다 */
export type FaceBrows = Partial<Record<"rightBrow" | "leftBrow", MeshAnchor[]>>;

// 등록 사진과 그 사진에서 찾은 눈썹은 실행 동안의 메모리에만 둔다.
let registered: { runId: string; photo: Blob; brows: FaceBrows | null } | null = null;
// 눈썹은 등록을 마친 뒤에 찾아지기도 하므로, 바뀌면 보고 있는 화면에 알린다
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

/** 등록 사진·눈썹이 바뀌면 부른다. useSyncExternalStore에 넘긴다 */
export function subscribeFacePhoto(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function saveFacePhoto(runId: string, photo: Blob) {
  registered = { runId, photo, brows: null };
  notify();
}

export function facePhoto(runId: string): Blob | null {
  return registered?.runId === runId ? registered.photo : null;
}

/** 지금 등록 사진의 실행에만 붙인다. 그사이 다시 찍었거나 지웠으면 버린다 */
export function saveFaceBrows(runId: string, photo: Blob, brows: FaceBrows) {
  if (registered?.runId !== runId || registered.photo !== photo) return;
  registered.brows = brows;
  notify();
}

export function faceBrows(runId: string): FaceBrows | null {
  return registered?.runId === runId ? registered.brows : null;
}

export function clearFacePhoto(expectedRunId?: string) {
  if (expectedRunId === undefined || registered?.runId === expectedRunId) {
    registered = null;
    notify();
  }
}
