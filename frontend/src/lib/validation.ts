/** 회원 입력 검증 규칙. API-USERS-001 기준 */

export const EMAIL_MAX = 254;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** 앞뒤 공백 제거 + 소문자. 이 값으로 중복·형식을 본다 */
export function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

export function isValidEmail(email: string) {
  const n = normalizeEmail(email);
  return EMAIL_RE.test(n) && n.length <= EMAIL_MAX;
}

/** 8~64자 · 영문·숫자 · ASCII 특수문자 각 1개 이상 */
export function passwordRule(pw: string) {
  const len = pw.length >= 8 && pw.length <= 64;
  const mix = /[A-Za-z]/.test(pw) && /\d/.test(pw);
  const spec = /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/.test(pw);
  return { len, mix, spec, ok: len && mix && spec };
}

/** bcrypt 한도. 한글은 영문보다 길게 계산된다 */
export const PASSWORD_MAX_BYTES = 72;

export function passwordBytes(pw: string) {
  return new TextEncoder().encode(pw).length;
}
