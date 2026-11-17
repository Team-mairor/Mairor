"use client";

import {
  createContext,
  useContext,
  useMemo,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";

import { usePersistedState } from "./storage";

/** localStorage 키 하나에 묶이는 상태 저장소. 바뀌는 이유가 같은 값끼리 하나씩 만든다 */
export function createStore<T>(
  name: string,
  key: string,
  empty: T,
  parse: (raw: unknown) => T | undefined,
) {
  interface Value {
    value: T;
    set: Dispatch<SetStateAction<T>>;
    loaded: boolean;
  }
  const Context = createContext<Value | null>(null);

  function Provider({ children, initial }: { children: ReactNode; initial?: T }) {
    const [value, set, loaded] = usePersistedState(key, initial ?? empty, parse);
    const context = useMemo(() => ({ value, set, loaded }), [value, set, loaded]);
    return <Context.Provider value={context}>{children}</Context.Provider>;
  }

  function useStore() {
    const context = useContext(Context);
    if (!context) throw new Error(`${name}은 SessionProvider 안에서만 쓸 수 있습니다`);
    return context;
  }

  return { Provider, useStore, empty };
}
