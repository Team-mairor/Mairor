import type { PouchItem } from "./catalog";

/** 수집이 끝나면 카탈로그에 연결돼 색이 바뀔 수 있는 항목(직접 입력)이 있는지. 있으면 목록을 주기적으로 다시 받는다 */
export function awaitsCatalog(pouch: readonly PouchItem[]) {
  return pouch.some((p) => !p.productId);
}

/** 화면에 보이는 값이 같은지. 같으면 목록을 바꾸지 않아 다시 그리지 않는다 */
export function samePouch(a: readonly PouchItem[], b: readonly PouchItem[]) {
  return (
    a.length === b.length &&
    a.every((x, i) => {
      const y = b[i];
      return (
        x.id === y.id &&
        x.cat === y.cat &&
        x.type === y.type &&
        x.brand === y.brand &&
        x.name === y.name &&
        x.shade === y.shade &&
        (x.color ?? null) === (y.color ?? null) &&
        (x.productId ?? null) === (y.productId ?? null) &&
        (x.shadeId ?? null) === (y.shadeId ?? null)
      );
    })
  );
}
