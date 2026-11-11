import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api";

import {
  completeExecution,
  ExecutionMismatchError,
  executionSelections,
  faceRegistrationRequest,
  registerFace,
  startExecution,
} from "./execution-api";

const VIDEO_ID = "b0000000-0000-4000-8000-000000000001";
const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
const FACE_ID = "f0000000-0000-4000-8000-000000000001";
const EXECUTION_ID = "e0000000-0000-4000-8000-000000000001";
const RECORD_ID = "r0000000-0000-4000-8000-000000000001";

afterEach(() => vi.restoreAllMocks());

describe("faceRegistrationRequest", () => {
  it("내부 영상 · 가이드 ID, 안내 판 v1, 동의, 서버 이름의 촬영 조건을 담는다", () => {
    expect(faceRegistrationRequest(VIDEO_ID, GUIDE_ID)).toEqual({
      videoId: VIDEO_ID,
      guideId: GUIDE_ID,
      noticeVersion: "v1",
      agreed: true,
      checks: {
        lighting: true,
        distance: true,
        frontal: true,
        unobstructed: true,
        makeupDetected: false,
      },
    });
  });
});

describe("registerFace", () => {
  it("image와 JSON metadata 파트로 보낸다", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ faceRegistrationId: FACE_ID });
    const photo = new Blob(["jpeg"], { type: "image/jpeg" });
    await registerFace(photo, faceRegistrationRequest(VIDEO_ID, GUIDE_ID));
    const [path, options] = post.mock.calls[0];
    expect(path).toBe("/v1/users/me/face-registrations");
    const form = options?.body as FormData;
    expect(form.get("image")).toBeInstanceOf(Blob);
    const metadata = form.get("metadata") as Blob;
    expect(metadata.type).toBe("application/json");
    expect(JSON.parse(await metadata.text())).toMatchObject({ videoId: VIDEO_ID, agreed: true });
  });
});

describe("executionSelections", () => {
  it("가이드 단계를 순서대로 모두 보내고, 파우치를 고르지 않은 단계는 null이다", () => {
    expect(
      executionSelections(["s1", "s2", "s3"], {
        s1: { kind: "pouch", id: "p1" },
        s2: { kind: "none" },
      }),
    ).toEqual({
      selections: [
        { stepId: "s1", selectedPouchItemId: "p1" },
        { stepId: "s2", selectedPouchItemId: null },
        { stepId: "s3", selectedPouchItemId: null },
      ],
      acceptMissingProducts: true,
    });
  });

  it("모두 골랐으면 acceptMissingProducts는 false다", () => {
    expect(
      executionSelections(["s1"], { s1: { kind: "pouch", id: "p1", auto: true } })
        .acceptMissingProducts,
    ).toBe(false);
  });
});

describe("startExecution", () => {
  const selections = [
    { stepId: "s1", selectedPouchItemId: "p1" },
    { stepId: "s2", selectedPouchItemId: null },
  ];
  const body = {
    guideId: GUIDE_ID,
    matchId: "m1",
    faceRegistrationId: FACE_ID,
    selections,
    acceptMissingProducts: true,
  };
  const alreadyUsed = new ApiError(409, "FACE_REGISTRATION_ALREADY_USED", "이미 사용");
  /** 얼굴 등록 조회는 기존 실행을, 실행 조회는 execution을 준다 */
  const existing = (execution: unknown) =>
    vi.spyOn(api, "get").mockImplementation(async (path: string) => {
      if (path.startsWith("/v1/users/me/face-registrations/")) return { executionId: EXECUTION_ID };
      if (execution instanceof Error) throw execution;
      return execution;
    });

  it("만든 실행의 ID를 돌려준다", async () => {
    vi.spyOn(api, "post").mockResolvedValue({ executionId: EXECUTION_ID });
    await expect(startExecution(body)).resolves.toBe(EXECUTION_ID);
  });

  it("이 얼굴로 이미 시작한 실행이 진행 중이고 선택이 같으면 이어 쓴다", async () => {
    vi.spyOn(api, "post").mockRejectedValue(alreadyUsed);
    const get = existing({ executionId: EXECUTION_ID, status: "IN_PROGRESS", steps: selections });
    await expect(startExecution(body)).resolves.toBe(EXECUTION_ID);
    expect(get).toHaveBeenCalledWith(`/v1/users/me/face-registrations/${FACE_ID}`);
    expect(get).toHaveBeenCalledWith(`/v1/users/me/executions/${EXECUTION_ID}`);
  });

  it("선택이 달라졌으면 이어 쓰지 않는다", async () => {
    vi.spyOn(api, "post").mockRejectedValue(alreadyUsed);
    existing({
      executionId: EXECUTION_ID,
      status: "IN_PROGRESS",
      steps: [selections[0], { stepId: "s2", selectedPouchItemId: "p2" }],
    });
    await expect(startExecution(body)).rejects.toBeInstanceOf(ExecutionMismatchError);
  });

  it("기존 실행이 끝났거나(404) 진행 중이 아니면 이어 쓰지 않는다", async () => {
    vi.spyOn(api, "post").mockRejectedValue(alreadyUsed);
    existing(new ApiError(404, "NOT_FOUND", "없음"));
    await expect(startExecution(body)).rejects.toBeInstanceOf(ExecutionMismatchError);
    vi.restoreAllMocks();
    vi.spyOn(api, "post").mockRejectedValue(alreadyUsed);
    existing({ executionId: EXECUTION_ID, status: "COMPLETED", steps: selections });
    await expect(startExecution(body)).rejects.toBeInstanceOf(ExecutionMismatchError);
  });

  it("그 밖의 오류는 그대로 던진다", async () => {
    const stale = new ApiError(409, "GUIDE_MATCH_STALE", "낡은 매칭");
    vi.spyOn(api, "post").mockRejectedValue(stale);
    await expect(startExecution(body)).rejects.toBe(stale);
  });
});

describe("completeExecution", () => {
  it("완료 응답의 recordId를 돌려준다", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ recordId: RECORD_ID });
    await expect(completeExecution(EXECUTION_ID)).resolves.toBe(RECORD_ID);
    expect(post).toHaveBeenCalledWith(`/v1/users/me/executions/${EXECUTION_ID}/completion`);
  });

  it("이미 완료(409)면 실행 조회의 recordId로 성공 처리한다", async () => {
    vi.spyOn(api, "post").mockRejectedValue(
      new ApiError(409, "GUIDE_EXECUTION_ALREADY_COMPLETED", "이미 완료"),
    );
    vi.spyOn(api, "get").mockResolvedValue({ recordId: RECORD_ID });
    await expect(completeExecution(EXECUTION_ID)).resolves.toBe(RECORD_ID);
  });
});
