"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  api,
  ApiError,
  isAbortError,
  type Health,
  type MockScenario,
  type SignUpRequest,
  type SignupAgreement,
  type User,
} from "@/lib/api";

const PASSWORD = "debug-Pass1!";
// 필수 약관은 서버의 현재 버전(application.yml의 agreement 기본값)으로 동의해야 가입된다.
const AGREEMENTS: SignupAgreement[] = (["TERMS", "PRIVACY", "AGE_OVER_14"] as const).map(
  (type) => ({ type, version: "2026-10-26", agreed: true }),
);

// BE에 실제로 있는 요청으로 성공·오류·취소 흐름을 확인한다. 실제 기능은 각 화면에서 만든다.
// 모의 응답은 요청 본문을 보지 않으므로, 입력값에 따른 결과는 "실제 서버"로 확인한다.
const SAMPLES = {
  health: {
    label: "헬스체크 (GET /health)",
    run: (options: SampleOptions) => api.get<Health>("/health", options),
  },
  healthTimeout: {
    label: "헬스체크 (100ms 시간 초과, 모의 응답에서 확인)",
    run: (options: SampleOptions) =>
      api.get<Health>("/health", {
        ...options,
        signal: AbortSignal.any([options.signal, AbortSignal.timeout(100)]),
      }),
  },
  signUp: {
    label: "회원가입 (POST /v1/users/signup, 실제 서버면 계정이 만들어짐)",
    run: (options: SampleOptions) =>
      api.post<User>("/v1/users/signup", {
        ...options,
        body: {
          email: `debug+${Date.now()}@example.com`,
          password: PASSWORD,
          passwordConfirm: PASSWORD,
          agreements: AGREEMENTS,
        } satisfies SignUpRequest,
      }),
  },
  signUpInvalid: {
    label: "회원가입 비밀번호 확인 불일치 (실제 서버에서 400)",
    run: (options: SampleOptions) =>
      api.post<User>("/v1/users/signup", {
        ...options,
        body: {
          email: `debug+${Date.now()}@example.com`,
          password: PASSWORD,
          passwordConfirm: `${PASSWORD}x`,
          agreements: AGREEMENTS,
        } satisfies SignUpRequest,
      }),
  },
  csrf: {
    label: "로그아웃 (POST /v1/users/logout, CSRF 토큰 없음 → 403)",
    run: (options: SampleOptions) => api.post("/v1/users/logout", options),
  },
} as const;

type SampleKey = keyof typeof SAMPLES;
type SampleOptions = { signal: AbortSignal; mock: MockScenario | null };

const MODES: { value: MockScenario | "server"; label: string }[] = [
  { value: "success", label: "모의: 성공" },
  { value: "error", label: "모의: 오류" },
  { value: "server", label: "실제 서버" },
];

type Result =
  | { kind: "loading" }
  | { kind: "ok"; data: unknown }
  | { kind: "error"; error: ApiError }
  | { kind: "aborted" };

export default function DebugApiPage() {
  const [sample, setSample] = useState<SampleKey>("health");
  const [mode, setMode] = useState<MockScenario | "server">("success");
  const [result, setResult] = useState<Result | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // 페이지를 떠나면 진행 중인 요청을 취소한다.
  useEffect(() => () => controllerRef.current?.abort(), []);

  async function send() {
    // 새 요청을 보내면 이전 요청은 취소해 늦게 온 응답이 덮어쓰지 않게 한다.
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setResult({ kind: "loading" });
    try {
      const data = await SAMPLES[sample].run({
        signal: controller.signal,
        mock: mode === "server" ? null : mode,
      });
      setResult({ kind: "ok", data: data === undefined ? "(본문 없음)" : data });
    } catch (e) {
      if (isAbortError(e)) {
        if (controllerRef.current === controller) setResult({ kind: "aborted" });
        return;
      }
      setResult({
        kind: "error",
        error: e instanceof ApiError ? e : new ApiError(0, "CLIENT_ERROR", String(e)),
      });
    }
  }

  return (
    <main className="flex flex-1 flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select
          className="h-8 rounded-lg border bg-background px-2"
          value={sample}
          onChange={(e) => setSample(e.target.value as SampleKey)}
        >
          {Object.entries(SAMPLES).map(([key, s]) => (
            <option key={key} value={key}>
              {s.label}
            </option>
          ))}
        </select>
        <select
          className="h-8 rounded-lg border bg-background px-2"
          value={mode}
          onChange={(e) => setMode(e.target.value as MockScenario | "server")}
        >
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
        <Button onClick={send}>요청</Button>
        <Button
          variant="outline"
          onClick={() => controllerRef.current?.abort()}
          disabled={result?.kind !== "loading"}
        >
          취소
        </Button>
      </div>

      {result?.kind === "loading" && <p className="text-sm text-muted-foreground">요청 중…</p>}
      {result?.kind === "aborted" && <p className="text-sm text-muted-foreground">취소했어요.</p>}
      {result?.kind === "ok" && (
        <pre className="max-w-3xl overflow-auto rounded-lg bg-muted p-3 text-xs">
          {JSON.stringify(result.data, null, 2)}
        </pre>
      )}
      {result?.kind === "error" && (
        <dl className="grid max-w-3xl grid-cols-[8rem_1fr] gap-x-4 gap-y-1 font-mono text-sm">
          <dt>status</dt>
          <dd>{result.error.status}</dd>
          <dt>code</dt>
          <dd className="text-destructive">{result.error.code}</dd>
          <dt>message</dt>
          <dd>{result.error.message}</dd>
          <dt>details</dt>
          <dd>
            {result.error.details.length > 0
              ? result.error.details.map((d) => `${d.field}: ${d.reason}`).join(", ")
              : "-"}
          </dd>
          <dt>Retry-After</dt>
          <dd>{result.error.retryAfterSeconds ?? "-"}</dd>
        </dl>
      )}
    </main>
  );
}
