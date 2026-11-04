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

/** BE(StrongPasswordValidator)와 같은 bcrypt 한도. NFC로 맞춘 뒤 UTF-8로 센다. 한글은 글자당 3바이트 */
export const PASSWORD_MAX_BYTES = 72;

/** 8~64자 · 영문·숫자 · ASCII 특수문자 각 1개 이상 · UTF-8 72바이트 이하 */
export function passwordRule(pw: string) {
  const len = pw.length >= 8 && pw.length <= 64;
  const mix = /[A-Za-z]/.test(pw) && /\d/.test(pw);
  const spec = /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/.test(pw);
  const bytes = new TextEncoder().encode(pw.normalize("NFC")).length <= PASSWORD_MAX_BYTES;
  return { len, mix, spec, bytes, ok: len && mix && spec && bytes };
}

/** 가입 선택 항목 규칙. BE SignUpRequest와 같다. hint는 틀렸을 때 안내 */
export const PROFILE_RULES = {
  nickname: {
    re: /^[가-힣A-Za-z0-9_]{2,20}$/,
    hint: "2~20자의 한글·영문·숫자·밑줄(_)로 입력해 주세요.",
  },
  name: { re: /^[가-힣A-Za-z ]{2,50}$/, hint: "2~50자의 한글·영문·공백으로 입력해 주세요." },
  phone: { re: /^01[016789]\d{7,8}$/, hint: "휴대폰 번호를 확인해 주세요. 예) 010-1234-5678" },
} as const;
export type ProfileField = keyof typeof PROFILE_RULES;

/** 서버로 보낼 값. 서버처럼 앞뒤 공백(휴대폰은 하이픈·공백)을 빼고, 비었으면 undefined(입력 안 함) */
export function profileValue(field: ProfileField, raw: string) {
  const v = field === "phone" ? raw.replace(/[\s-]/g, "") : raw.normalize("NFC").trim();
  return v || undefined;
}

/** 입력했는데 규칙에 맞지 않으면 안내 문구, 아니면 null */
export function profileProblem(field: ProfileField, raw: string) {
  const v = profileValue(field, raw);
  return v !== undefined && !PROFILE_RULES[field].re.test(v) ? PROFILE_RULES[field].hint : null;
}

/**
 * 가입 때 동의하는 약관 버전. 필수 약관은 BE의 현재 버전(AGREEMENT_*_VERSION)과 같아야 가입된다.
 * 바꿀 때는 BE 환경변수와 이 값을 같이 바꿔 함께 배포한다 (frontend/README.md '약관 버전')
 */
export const AGREEMENT_VERSION = "2026-10-26";
