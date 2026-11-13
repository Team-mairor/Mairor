"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Fragment,
  Suspense,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { facePhoto } from "@/features/face";
import { faceReady, isRunPath, runHref, runRouteAction, useSession } from "@/features/session";
import { GuideStatus } from "@/features/tutorial";

import { deleteFaceRegistration } from "./execution-api";
import { fetchGuide } from "./guide-api";
import { GuideStore, LOADING } from "./guide-store";
import { RunGuideBoundary } from "./run-guide-boundary";
import { RunGuideContext } from "./use-guide";

interface Route {
  path: string;
  search: string;
}

function RunRouteSync({ onRoute }: { onRoute: (route: Route) => void }) {
  const path = usePathname();
  const search = useSearchParams().toString();
  useLayoutEffect(() => {
    onRoute({ path, search });
  }, [path, search, onRoute]);
  return null;
}

/** 지금 주소의 쿼리. 쿼리만 바뀐 첫 렌더에서 이전 판정으로 본문을 그리지 않게 비교한다 */
function CurrentSearch({ children }: { children: (search: string) => ReactNode }) {
  return children(useSearchParams().toString());
}

export function RunGuideProvider({ children }: { children: ReactNode }) {
  const {
    state,
    storageLoaded,
    sessionChecked,
    startRun,
    continueAnalysis,
    endRun,
    bindGuide,
    invalidateRun,
    expireSession,
  } = useSession();
  const run = state.run;
  const router = useRouter();
  const pathname = usePathname();
  const [route, setRoute] = useState<Route | null>(null);
  const [store] = useState(() => new GuideStore(fetchGuide));
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const key = run.mode === "guide" && state.loggedIn ? `${run.id}:${state.email}` : "";
  const load = snapshot.key === key && key ? snapshot.load : LOADING;
  const initialized = storageLoaded && sessionChecked && route?.path === pathname;
  const action = route ? runRouteAction(route.path, route.search, run) : null;
  const previousPath = useRef<string | null>(null);

  useEffect(() => {
    if (!key || !run.guideId) {
      store.clear();
      return;
    }
    store.activate(key, run.guideId);
    return store.cancel;
  }, [key, run.guideId, store]);

  useEffect(() => {
    if (!key || snapshot.key !== key) return;
    const result = snapshot.load;
    if (result.status === "ready") {
      const g = result.guide;
      bindGuide(run.id, g.guideVersion, {
        id: g.videoId,
        ytid: g.youtubeVideoId ?? "",
        title: g.title,
        ch: g.channelTitle,
        meta: "",
        dur: "",
      });
    } else if (result.status === "invalidated") {
      invalidateRun(run.id);
    } else if (result.status === "login") {
      // 튜토리얼 중이었으면 기록 없이 끝났다고 함께 알린다
      const expired = run.phase === "tutorial" ? "tut" : "basic";
      expireSession();
      router.replace(`/login?expired=${expired}`);
    }
  }, [snapshot, key, run.id, run.phase, bindGuide, invalidateRun, expireSession, router]);

  const bootstrapped = useRef<string | null>(null);
  useEffect(() => {
    if (!initialized || !route) return;
    const previous = previousPath.current;
    previousPath.current = route.path;
    if (!isRunPath(route.path)) {
      bootstrapped.current = null;
      if (previous && isRunPath(previous) && run.id) {
        if (run.faceRegistrationId && !run.executionId)
          deleteFaceRegistration(run.faceRegistrationId).catch((e: unknown) =>
            console.warn("얼굴 등록 정리 실패", e),
          );
        endRun(run.id);
      }
      return;
    }
    if (!state.loggedIn) return;
    const decision = runRouteAction(route.path, route.search, run);
    if (decision.kind === "start") {
      const entry = `${route.path}?${route.search}`;
      if (bootstrapped.current === entry) return;
      bootstrapped.current = entry;
      const sourceJobId = new URLSearchParams(route.search).get("jobId");
      if (
        run.mode === "sample" &&
        run.jobId &&
        run.jobId === sourceJobId &&
        run.phase === "preparing"
      ) {
        continueAnalysis(run.id, sourceJobId, decision.guideId);
      } else {
        if (run.faceRegistrationId && !run.executionId)
          deleteFaceRegistration(run.faceRegistrationId).catch((e: unknown) =>
            console.warn("얼굴 등록 정리 실패", e),
          );
        startRun({ kind: "guide", guideId: decision.guideId });
      }
      router.replace(runHref("/loading", decision.guideId));
    } else if (decision.kind === "redirect") {
      // 실행을 끝낸 직후 남은 주소에서는 다른 화면으로 보내지 않는다. 이어지는 이동을 덮어쓰기 때문이다
      if (!run.id && bootstrapped.current === `${route.path}?${route.search}`) return;
      router.replace(decision.href);
    } else {
      bootstrapped.current = `${route.path}?${route.search}`;
      if (
        run.mode === "guide" &&
        route.path !== "/loading" &&
        run.phase !== "invalidated" &&
        run.phase !== "completed" &&
        // 화면용 사진(메모리)과 서버 등록 ID가 둘 다 있어야 실행을 이어 간다
        (!facePhoto(run.id) || !faceReady(run))
      ) {
        router.replace(runHref("/loading", run.guideId));
      }
    }
  }, [initialized, route, run, state.loggedIn, startRun, continueAnalysis, endRun, router]);

  const search = route?.path === pathname ? route.search : null;
  const value = useMemo(() => ({ load, retry: store.retry, search }), [load, store, search]);
  const body = (sameSearch: boolean) => (
    <RunGuideBoundary path={pathname} initialized={!!initialized && sameSearch} action={action}>
      <Fragment key={isRunPath(pathname) ? run.id : "outside"}>{children}</Fragment>
    </RunGuideBoundary>
  );
  return (
    <RunGuideContext.Provider value={value}>
      {/* 쿼리 관찰자만 Suspense 아래 두어 정적 페이지 본문을 유지한다. */}
      <Suspense fallback={null}>
        <RunRouteSync onRoute={setRoute} />
      </Suspense>
      {isRunPath(pathname) ? (
        <Suspense fallback={<GuideStatus title="준비 상태를 확인하고 있어요" />}>
          <CurrentSearch>{(current) => body(route?.search === current)}</CurrentSearch>
        </Suspense>
      ) : (
        body(true)
      )}
    </RunGuideContext.Provider>
  );
}
