// 등록 사진은 실행 동안의 메모리에만 둔다.
let registered: { runId: string; photo: Blob } | null = null;

export function saveFacePhoto(runId: string, photo: Blob) {
  registered = { runId, photo };
}

export function moveFacePhoto(fromRunId: string, toRunId: string) {
  if (registered?.runId === fromRunId) registered = { ...registered, runId: toRunId };
}

export function facePhoto(runId: string): Blob | null {
  return registered?.runId === runId ? registered.photo : null;
}

export function clearFacePhoto(expectedRunId?: string) {
  if (expectedRunId === undefined || registered?.runId === expectedRunId) registered = null;
}
