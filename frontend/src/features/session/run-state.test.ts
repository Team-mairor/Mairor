import { describe, expect, it } from "vitest";

import { createRun, EMPTY_RUN, invalidateRun, runHref, runRouteAction } from "./run-state";

const A = "a0000000-0000-4000-8000-000000000001";
const B = "a0000000-0000-4000-8000-000000000002";

describe("실행 진입과 초기화", () => {
  it("같은 가이드도 새 실행이면 이전 선택·동의·진행을 물려받지 않는다", () => {
    const old = {
      ...createRun({ kind: "guide", guideId: A }, "old"),
      guideVersion: 3,
      faceReg: true,
      photoOk: true,
      captures: ["s2"],
      choice: { s1: { kind: "none" as const } },
    };
    const next = createRun({ kind: "guide", guideId: A.toUpperCase(), replay: "report" }, "new");
    expect(next).toMatchObject({
      id: "new",
      guideId: A,
      guideVersion: null,
      faceReg: false,
      photoOk: false,
      captures: [],
      choice: {},
      subOn: {},
      phase: "preparing",
    });
    expect(old.captures).toEqual(["s2"]);
    expect(invalidateRun(old)).toMatchObject({
      id: "old",
      guideId: A,
      guideVersion: 3,
      phase: "invalidated",
      photoOk: false,
      faceReg: false,
      captures: [],
      choice: {},
    });
  });
  it.each(["/loading", "/preview", "/check", "/tutorial/guide", "/tutorial", "/done"])(
    "%s 새로고침은 ID로 새 실행을 만든다",
    (path) => {
      expect(runRouteAction(path, `guideId=${A}`, EMPTY_RUN)).toEqual({
        kind: "start",
        guideId: A,
      });
    },
  );
  it("URL의 다른 가이드는 새 실행이고, 중복·빈·잘못된 ID는 거부한다", () => {
    const run = createRun({ kind: "guide", guideId: A }, "a");
    expect(runRouteAction("/tutorial", `guideId=${B}`, run)).toEqual({ kind: "start", guideId: B });
    for (const search of ["guideId=", "guideId=invalid", `guideId=${A}&guideId=${A}`])
      expect(runRouteAction("/loading", search, run)).toEqual({ kind: "invalidId" });
  });
  it("얼굴·동의·완료 단계를 건너뛸 수 없고 누락된 쿼리는 보존한다", () => {
    const run = createRun({ kind: "guide", guideId: A }, "a");
    expect(runRouteAction("/done", `guideId=${A}`, run)).toEqual({
      kind: "redirect",
      href: runHref("/loading", A),
    });
    // 가이드 실행은 서버 얼굴 등록 ID까지 있어야 등록을 마친 것이다
    expect(runRouteAction("/tutorial", `guideId=${A}`, { ...run, faceReg: true })).toEqual({
      kind: "redirect",
      href: runHref("/loading", A),
    });
    // 서버 실행을 만들기 전에는 안내 · 튜토리얼에 들어가지 않고 제품 체크로 간다
    const registered = { ...run, faceReg: true, faceRegistrationId: "f1" };
    for (const path of ["/tutorial", "/tutorial/guide"])
      expect(runRouteAction(path, `guideId=${A}`, registered)).toEqual({
        kind: "redirect",
        href: runHref("/check", A),
      });
    const started = { ...registered, executionId: "e1" };
    expect(runRouteAction("/tutorial", `guideId=${A}`, started)).toEqual({
      kind: "redirect",
      href: runHref("/tutorial/guide", A),
    });
    expect(runRouteAction("/tutorial/guide", `guideId=${A}`, started)).toEqual({
      kind: "allow",
    });
    expect(runRouteAction("/check", "view=try", run)).toEqual({
      kind: "redirect",
      href: runHref("/check?view=try", A),
    });
    expect(
      runRouteAction("/done", `guideId=${A}`, { ...run, faceReg: true, phase: "completed" }),
    ).toEqual({ kind: "allow" });
    // 완료한 실행은 얼굴 등록 여부와 상관없이 완료 화면으로만 간다
    expect(runRouteAction("/done", `guideId=${A}`, { ...run, phase: "completed" })).toEqual({
      kind: "allow",
    });
    expect(runRouteAction("/loading", `guideId=${A}`, { ...run, phase: "completed" })).toEqual({
      kind: "redirect",
      href: runHref("/done", A),
    });
    expect(runRouteAction("/tutorial", "", EMPTY_RUN)).toEqual({
      kind: "redirect",
      href: "/select",
    });
  });
  it("추가 쿼리가 guideId를 덮어쓰지 않는다", () => {
    const href = runHref("/tutorial/guide?force=1", A.toUpperCase(), { review: "1", guideId: B });
    const p = new URLSearchParams(href.split("?")[1]);
    expect(p.getAll("guideId")).toEqual([A]);
    expect(p.get("review")).toBe("1");
    expect(p.get("force")).toBe("1");
  });
});
