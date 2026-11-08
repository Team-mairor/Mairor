// BE 코드(common.error·common.web·users) 기준. docs/references/api-spec.md와 다르면 코드를 따른다.
// 필드명은 camelCase, 열거값은 UPPER_SNAKE_CASE, 날짜는 UTC ISO-8601 문자열이다.
// BE는 값이 없는 필드도 빼지 않고 null로 보내므로, null이 될 수 있는 필드는 `| null`로 둔다.

/** 오류 응답 본문 (ErrorResponse). details는 입력 필드 오류일 때만 오고, 없으면 필드 자체가 빠진다. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details?: FieldError[];
}

export interface FieldError {
  field: string;
  reason: string;
}

/** 목록 응답 (PageResponse). 항목이 없어도 items는 빈 배열이고, 전체 개수는 주지 않는다. */
export interface Page<T> {
  items: T[];
  page: number;
  size: number;
  hasNext: boolean;
}

/** 목록 요청 파라미터 (PageQuery). page는 0부터, size는 1~100·기본 20. 벗어나면 400 VALIDATION_FAILED */
export interface PageQuery {
  page?: number;
  size?: number;
}

/** GET /health */
export interface Health {
  status: "UP";
}

/**
 * POST /v1/users/signup 요청 (SignUpRequest). 비밀번호는 8~64자에 영문자·숫자·기호를 하나씩 포함한다.
 * 규칙에 맞지 않거나 확인값이 다르면 400 VALIDATION_FAILED, 필수 약관이 빠지면 400 USERS_REQUIRED_AGREEMENT_MISSING,
 * 이미 가입된 이메일이면 409 USERS_EMAIL_DUPLICATE
 */
export interface SignUpRequest {
  email: string;
  password: string;
  passwordConfirm: string;
  nickname?: string;
  name?: string;
  phone?: string;
  /** YYYY-MM-DD, 만 14세 이상 */
  birthDate?: string;
  gender?: "MALE" | "FEMALE";
  /** TERMS·PRIVACY·AGE_OVER_14는 서버의 현재 버전으로 동의해야 한다 */
  agreements: SignupAgreement[];
  /** 가입에 이메일 인증을 요구하도록 설정했을 때만 필수 */
  emailVerificationToken?: string;
}

export interface SignupAgreement {
  type: "TERMS" | "PRIVACY" | "AGE_OVER_14" | "MARKETING";
  version: string;
  agreed: boolean;
}

/** 회원 (UserResponse) */
export interface User {
  userId: string;
  email: string;
  nickname: string | null;
  provider: "LOCAL" | "GOOGLE";
  createdAt: string;
}

/** POST /v1/users/login 요청. 실패 원인(미가입·비밀번호 오류·Google 전용 계정)은 모두 401 USERS_INVALID_CREDENTIALS */
export interface LoginRequest {
  email: string;
  password: string;
}

/** 로그인·내 계정 조회(GET /v1/users/me) 응답 (LoginResponse). csrfToken은 고치지 않고 setCsrfToken()에 넣는다 */
export interface LoginResponse {
  user: User;
  csrfToken: string;
}

/** POST /v1/users/email-availability 응답 */
export interface EmailAvailability {
  email: string;
  available: boolean;
}

/** 인증번호 발송 응답. 가입 이메일 인증(POST /v1/users/email-verification)·비밀번호 재설정(POST /v1/users/password-reset) 공통 */
export interface CodeSent {
  expiresInSeconds: number;
  resendAvailableInSeconds: number;
}

/** POST /v1/users/email-verification/verification 응답. 토큰은 가입 요청의 emailVerificationToken으로 보낸다 */
export interface EmailVerified {
  verificationToken: string;
  expiresAt: string;
}

/** POST /v1/users/password-reset/verification 응답. 토큰은 새 비밀번호 저장(PUT /v1/users/password-reset/password)에 보낸다 */
export interface PasswordResetVerified {
  resetToken: string;
  expiresAt: string;
}
