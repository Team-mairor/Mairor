const POUCH_OPENED_AT = "mairor-pouch-opened-at";

export const POUCH_OPEN_COOLDOWN_MS = 5 * 60 * 1000;

/** 같은 브라우저 탭에서 최근에 본 파우치 진입 연출은 다시 재생하지 않는다. */
export function shouldPlayPouchOpenFx(
  storage: Pick<Storage, "getItem" | "setItem">,
  now = Date.now(),
) {
  try {
    const last = Number(storage.getItem(POUCH_OPENED_AT));
    const elapsed = now - last;
    if (Number.isFinite(last) && last > 0 && elapsed >= 0 && elapsed < POUCH_OPEN_COOLDOWN_MS)
      return false;
    storage.setItem(POUCH_OPENED_AT, String(now));
  } catch {
    // 저장소를 쓸 수 없는 브라우저에서도 진입 자체는 막지 않는다.
  }
  return true;
}
