"use client";

import { useEffect, useMemo, useState } from "react";

/**
 * 주소의 ?키=값 을 읽는다. 정적 내보내기라 서버에서는 null이고, 브라우저에서 채운다.
 * useSearchParams는 정적 내보내기에서 가장 가까운 Suspense까지 HTML을 비우므로 쓰지 않는다.
 * 첫 렌더는 늘 null이다. 화면을 옮긴 직후 렌더에서는 주소가 아직 이전 화면 값이라, 그려진 뒤(effect)에 읽는다.
 * 같은 화면 안에서 쿼리만 바뀌면(개발용 바로가기) Navigation API·popstate로 다시 읽는다.
 */
export function useQuery() {
  const [search, setSearch] = useState<string | null>(null);
  useEffect(() => {
    const read = () => setSearch(window.location.search);
    read();
    // Navigation API는 TS 기본 타입에 아직 없다. 없는 브라우저에서는 popstate(뒤로·앞으로)만 따라간다
    const nav = (window as { navigation?: EventTarget }).navigation;
    nav?.addEventListener("currententrychange", read);
    window.addEventListener("popstate", read);
    return () => {
      nav?.removeEventListener("currententrychange", read);
      window.removeEventListener("popstate", read);
    };
  }, []);
  return useMemo(() => (search === null ? null : new URLSearchParams(search)), [search]);
}
