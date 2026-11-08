// BE 코드(common.error·common.web·users) 기준. 노션 API 명세와 다르면 코드를 따른다.
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

/** 분석 작업의 지금 단계 안에서 센 수 (StageProgress). 전체 %가 아니다. 지금은 BUILDING_GUIDE에서만 온다 */
export interface StageProgress {
  item: "FRAMES" | "LANDMARKS" | "AREA" | "EXPLANATION";
  done: number;
  total: number;
}

/** 분석 작업 상태 (AnalysisJobStatus). 상태 조회(GET /v1/users/me/analysis-jobs/{jobId})와 SSE status 이벤트가 같다 */
export interface AnalysisJobStatus {
  jobId: string;
  videoId: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  /** FAILED면 멈춘 단계 */
  progressStage:
    | "QUEUED"
    | "LOADING_VIDEO"
    | "SEGMENTING"
    | "RECOGNIZING_PRODUCTS"
    | "EXTRACTING_STEPS"
    | "BUILDING_GUIDE"
    | "DONE";
  /** 지금은 COMPLETED일 때만 100 */
  progressPercent: number | null;
  /** 지금은 늘 null */
  estimatedRemainingSeconds: number | null;
  stageProgress: StageProgress | null;
  retryable: boolean;
  reviewStatus: "NOT_READY" | "PENDING" | "APPROVED" | "REJECTED";
  guideAvailable: boolean;
  guideId: string | null;
  /** 제품 인식이 연결되기 전에는 늘 빈 목록 */
  foundProducts: unknown[];
  foundProductCount: number;
  totalProductCount: number | null;
  failureCode: string | null;
  failureMessage: string | null;
  /** 폴링할 때 다음 조회까지의 초. null이면 더 바뀌지 않는다 */
  pollAfterSeconds: number | null;
  createdAt: string;
  completedAt: string | null;
}

/** 설명란 챕터 (VideoChapter) */
export interface VideoChapter {
  startSeconds: number;
  label: string;
}

/** 영상 검색 결과 한 줄 (VideoSearchItem). CC BY 영상만 오고 분석할 수 없는 영상은 빠진다 */
export interface VideoSearchItem {
  youtubeVideoId: string;
  title: string;
  channelTitle: string;
  durationSeconds: number;
  thumbnailUrl: string | null;
  /** 숨긴 영상은 null */
  viewCount: number | null;
  publishedAt: string | null;
  /** 검수 승인된 가이드. 승인 전·없음은 null */
  guideId: string | null;
  guideAvailable: boolean;
}

/**
 * GET /v1/videos/search?q=&pageToken=&size= 응답 (VideoSearchPage). 마지막 페이지면 nextPageToken이 null.
 * 실패: 400 VALIDATION_FAILED, 502 VIDEO_PROVIDER_ERROR, 503 VIDEO_SEARCH_UNAVAILABLE, 504 VIDEO_PROVIDER_TIMEOUT
 */
export interface VideoSearchPage {
  items: VideoSearchItem[];
  nextPageToken: string | null;
  size: number;
}

/** POST /v1/videos 요청 (VideoSelectionRequest) */
export interface VideoSelectionRequest {
  youtubeVideoId: string;
}

/**
 * POST /v1/videos 응답 (VideoSelection). 분석은 만들지 않는다.
 * 실패: 409 VIDEO_UNSUPPORTED_FOR_ANALYSIS(CC BY 아님·비공개·삭제·연령 제한·라이브), 502 VIDEO_PROVIDER_ERROR, 504 VIDEO_PROVIDER_TIMEOUT
 */
export interface VideoSelection extends VideoSearchItem {
  /** 서비스 내부 영상 ID. 분석 요청(API-VIDEO-002)에 쓴다 */
  videoId: string;
  chapters: VideoChapter[];
  /** 내가 요청해 진행 중인 분석 작업 */
  analysisJobId: string | null;
  /** 진행 중이면 NOT_READY, 아니면 가장 최근 가이드의 검수 상태, 분석한 적 없으면 null */
  reviewStatus: "NOT_READY" | "PENDING" | "APPROVED" | "REJECTED" | null;
}
