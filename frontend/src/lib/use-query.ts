"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * 주소의 ?키=값 을 읽는다. 정적 내보내기라 서버에서는 null이고, 브라우저에서 채운다.
 * 같은 화면 안에서 쿼리만 바뀌어도(개발용 바로가기) 다시 읽는다. 루트 레이아웃의 Suspense가 경계다.
 */
export function useQuery() {
  const search = useSearchParams();
  const [params, setParams] = useState<URLSearchParams | null>(null);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소창 값은 브라우저에서만 읽을 수 있다
    setParams(new URLSearchParams(search.toString()));
  }, [search]);
  return params;
}
