"use client";

import type { Choice } from "@/features/session";
import {
  api,
  ApiError,
  type CreateExecutionRequest,
  type ExecutionAbandonment,
  type ExecutionCompletion,
  type ExecutionSelection,
  type ExecutionSummary,
  type FaceRegistration,
  type FaceRegistrationRequest,
  type PhotoMeta,
} from "@/lib/api";

/** 서버 얼굴 등록 안내 판(FACE_REGISTRATION_NOTICE_VERSION)과 같아야 한다 */
export const FACE_NOTICE_VERSION = "v1";

const EXECUTIONS = "/v1/users/me/executions";

/** 등록 창은 네 조건을 모두 통과해야 찍으므로 checks는 모두 true. 화장 감지는 FE에 없어 false */
export function faceRegistrationRequest(videoId: string, guideId: string): FaceRegistrationRequest {
  return {
    videoId,
    guideId,
    noticeVersion: FACE_NOTICE_VERSION,
    agreed: true,
    checks: {
      lighting: true,
      distance: true,
      frontal: true,
      unobstructed: true,
      makeupDetected: false,
    },
  };
}

/** POST /v1/users/me/face-registrations. multipart image + metadata(JSON) */
export function registerFace(photo: Blob, metadata: FaceRegistrationRequest) {
  const form = new FormData();
  form.append("image", photo, "face.jpg");
  form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));
  return api.post<FaceRegistration>("/v1/users/me/face-registrations", { body: form });
}

/** DELETE /v1/users/me/face-registrations/{id}. 실행에 연결되지 않은 등록을 정리한다 */
export function deleteFaceRegistration(faceRegistrationId: string) {
  return api.delete<void>(
    `/v1/users/me/face-registrations/${encodeURIComponent(faceRegistrationId)}`,
  );
}

/** GET /v1/users/me/face-registrations/{id}. 연결된 executionId를 찾는다 */
export function getFaceRegistration(faceRegistrationId: string) {
  return api.get<FaceRegistration>(
    `/v1/users/me/face-registrations/${encodeURIComponent(faceRegistrationId)}`,
  );
}

/** 얼굴 등록이 사라졌나(404). 실행 생성 404의 원인을 얼굴 등록과 가이드 · 매칭으로 가를 때 쓴다 */
export async function isFaceRegistrationGone(faceRegistrationId: string) {
  try {
    await getFaceRegistration(faceRegistrationId);
    return false;
  } catch (e) {
    return e instanceof ApiError && e.status === 404;
  }
}

/** GUIDE 단계 전부의 선택. 파우치 제품이 아니면 null이고, null이 있으면 acceptMissingProducts=true */
export function executionSelections(
  stepIds: readonly string[],
  choice: Record<string, Choice>,
): Pick<CreateExecutionRequest, "selections" | "acceptMissingProducts"> {
  const selections: ExecutionSelection[] = stepIds.map((stepId) => {
    const c = choice[stepId];
    return { stepId, selectedPouchItemId: c?.kind === "pouch" ? c.id : null };
  });
  return {
    selections,
    acceptMissingProducts: selections.some((s) => s.selectedPouchItemId === null),
  };
}

/** POST /v1/users/me/executions */
export function createExecution(body: CreateExecutionRequest) {
  return api.post<ExecutionSummary>(EXECUTIONS, { body });
}

/** 이 얼굴 등록으로 만든 실행을 지금 선택으로 이어 쓸 수 없다. 새 얼굴 등록으로 새 실행을 만들어야 한다 */
export class ExecutionMismatchError extends Error {
  constructor() {
    super("이 얼굴 등록으로 만든 실행이 지금 선택과 다르다");
    this.name = "ExecutionMismatchError";
  }
}

/** GET …/{executionId}. 진행 중 실행은 만든 세션에서만 보인다 */
function getExecution(executionId: string) {
  return api.get<ExecutionSummary>(`${EXECUTIONS}/${encodeURIComponent(executionId)}`);
}

const sameSelections = (steps: ExecutionSelection[], selections: ExecutionSelection[]) =>
  steps.length === selections.length &&
  selections.every(
    (s) => steps.find((x) => x.stepId === s.stepId)?.selectedPouchItemId === s.selectedPouchItemId,
  );

/**
 * 실행을 시작한다. 이 얼굴 등록으로 이미 시작했으면(409) 그 실행이 진행 중이고 선택이 같을 때만 이어 쓰고,
 * 아니면 ExecutionMismatchError를 던진다(서버 선택은 처음 만들 때 고정된다)
 */
export async function startExecution(body: CreateExecutionRequest): Promise<string> {
  try {
    return (await createExecution(body)).executionId;
  } catch (e) {
    if (!(e instanceof ApiError) || e.code !== "FACE_REGISTRATION_ALREADY_USED") throw e;
    const face = await getFaceRegistration(body.faceRegistrationId);
    if (!face.executionId) throw e;
    const execution = await getExecution(face.executionId).catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    });
    if (execution?.status === "IN_PROGRESS" && sameSelections(execution.steps, body.selections))
      return execution.executionId;
    throw new ExecutionMismatchError();
  }
}

/** PATCH …/{executionId}/photo-consent */
export function setPhotoConsent(executionId: string, enabled: boolean) {
  return api.patch<unknown>(`${EXECUTIONS}/${encodeURIComponent(executionId)}/photo-consent`, {
    body: { enabled },
  });
}

/** PUT /v1/users/me/executions/{id}/steps/{stepId}/photo. 실제 JPEG/PNG 바이트를 전송한다 */
export function uploadStepPhoto(executionId: string, stepId: string, image: Blob) {
  const form = new FormData();
  form.append("image", image, "step.jpg");
  return api.put<PhotoMeta>(
    `${EXECUTIONS}/${encodeURIComponent(executionId)}/steps/${encodeURIComponent(stepId)}/photo`,
    { body: form },
  );
}

/** POST …/{executionId}/completion. 다시 보내도 같은 recordId다. 이미 완료(409)면 실행 조회의 recordId를 쓴다 */
export async function completeExecution(executionId: string): Promise<string> {
  const path = `${EXECUTIONS}/${encodeURIComponent(executionId)}`;
  try {
    return (await api.post<ExecutionCompletion>(`${path}/completion`)).recordId;
  } catch (e) {
    if (!(e instanceof ApiError) || e.code !== "GUIDE_EXECUTION_ALREADY_COMPLETED") throw e;
    const execution = await getExecution(executionId);
    if (!execution.recordId) throw e;
    return execution.recordId;
  }
}

/** POST …/{executionId}/abandonment */
export function abandonExecution(executionId: string) {
  return api.post<ExecutionAbandonment>(
    `${EXECUTIONS}/${encodeURIComponent(executionId)}/abandonment`,
  );
}
