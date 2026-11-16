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

/** GET /v1/users/oauth/google/signup 응답. Google로 처음 온 사용자의 가입 대기. 없거나 만료면 410 USERS_GOOGLE_SIGNUP_EXPIRED */
export interface GoogleSignupPending {
  /** Google이 확인한 이메일. 가입 이메일 인증을 거치지 않는다 */
  email: string;
  /** Google 표시 이름. 없으면 null */
  name: string | null;
  expiresAt: string;
}

/** POST /v1/users/oauth/google/signup 요청. 이메일 가입에서 이메일·비밀번호·인증 토큰을 뺀 입력. 성공하면 201 LoginResponse로 바로 로그인된다 */
export type GoogleSignUpRequest = Omit<
  SignUpRequest,
  "email" | "password" | "passwordConfirm" | "emailVerificationToken"
>;

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
  /** 분석 단계에서 확인한 제품 */
  foundProducts: FoundProduct[];
  foundProductCount: number;
  totalProductCount: number | null;
  failureCode: string | null;
  failureMessage: string | null;
  /** 폴링할 때 다음 조회까지의 초. null이면 더 바뀌지 않는다 */
  pollAfterSeconds: number | null;
  createdAt: string;
  completedAt: string | null;
}

export interface FoundProduct {
  stepId: string | null;
  part: string | null;
  referenceProduct: ReferenceProduct;
  ownership: "OWNED" | "NOT_OWNED" | "UNKNOWN";
}

export interface ReferenceProduct {
  productId: string | null;
  shadeId: string | null;
  name: string | null;
  shadeName: string | null;
  matchStatus: "MATCHED" | "CANDIDATE" | "UNMATCHED";
  verification: "CONFIRMED" | "ESTIMATED" | "UNKNOWN";
  sources: string[];
  videoConfirmed: boolean | null;
}

/** 색 (ColorInfo). 색이 없으면 객체 자체가 null */
export interface ColorInfo {
  colorSpace: "sRGB";
  /** #RRGGBB */
  hex: string;
  /** 보유 제품 CATALOG | USER_INPUT, 목표 발색 VIDEO_ESTIMATE | CATALOG | MANUAL_REVIEW (명세 4절 ColorInfo 공용이라 string) */
  source: string;
  estimated: boolean;
}

/** 호수 안의 색 칸 하나 (ShadeColor). 단색 호수는 칸 1개, 팔레트는 여러 개 */
export interface ShadeColor {
  colorId: string;
  name: string | null;
  sortOrder: number;
  /** 쓸 수 있는 색이 없으면 null */
  color: ColorInfo | null;
}

/** 호수 (Shade) */
export interface Shade {
  shadeId: string;
  name: string;
  colors: ShadeColor[];
}

/** 카탈로그 제품 (ProductResponse). 호수 선택이 없는 분류는 shades=[] */
export interface Product {
  productId: string;
  brand: string;
  name: string;
  category: string;
  type: string;
  shades: Shade[];
}

/** GET /v1/products?category&type&brand&name 응답. 정확히 같은 제품 0~1건 (0건이면 직접 입력) */
export interface ProductList {
  items: Product[];
}

/** 제품 후보 한 건 (ProductSuggestionResponse). 호수·색은 없고 고른 뒤 제품 상세로 받는다 */
export interface ProductSuggestion {
  productId: string;
  brand: string;
  name: string;
  category: string;
  type: string;
}

/** GET /v1/products/suggestions 응답. 이름이 입력과 가까운 순서 */
export interface ProductSuggestionList {
  items: ProductSuggestion[];
}

export interface ProductType {
  code: string;
  label: string;
}

/** 카테고리 (ProductCategoryResponse). code를 저장하고 label을 보여 준다 */
export interface ProductCategory {
  code: string;
  label: string;
  matchable: boolean;
  /** 등록할 때 호수·컬러를 고르는 분류 */
  shadeSelectable: boolean;
  types: ProductType[];
  compatibleParts: string[];
}

/** GET /v1/product-categories 응답 */
export interface ProductCategoryList {
  items: ProductCategory[];
}

/** 내 파우치 항목 (PouchItemResponse). MANUAL은 productId·shadeId가 null */
export interface PouchItemResponse {
  pouchItemId: string;
  registrationMode: "CATALOG" | "MANUAL";
  productId: string | null;
  shadeId: string | null;
  brand: string;
  name: string;
  category: string;
  type: string;
  shadeName: string | null;
  color: ColorInfo | null;
  colorSource: "CATALOG" | "USER_INPUT" | "NONE";
  createdAt: string;
  updatedAt: string;
}

/** GET /v1/users/me/pouch-items 응답. 최신 등록순, size 최대 100 */
export interface PouchList extends Page<PouchItemResponse> {
  pouchVersion: number;
}

/**
 * POST /v1/users/me/pouch-items 요청 (PouchRegistrationRequest).
 * CATALOG: type·productId(+ 호수 선택 분류면 shadeId)만. MANUAL: category·type·brand·name(+ 호수 선택 분류면 shadeName·colorHex)
 * 실패: 400 VALIDATION_FAILED·POUCH_INVALID_PRODUCT, 409 POUCH_DUPLICATE(같은 브랜드·제품명·호수)
 */
export type PouchRegistrationRequest =
  | { registrationMode: "CATALOG"; type: string; productId: string; shadeId?: string }
  | {
      registrationMode: "MANUAL";
      category: string;
      type: string;
      brand: string;
      name: string;
      shadeName?: string | null;
      colorHex?: string | null;
    };

/**
 * PATCH /v1/users/me/pouch-items/{id} 요청. 생략한 칸은 그대로다.
 * 직접 입력 칸을 바꾸면 서버가 MANUAL로 바꾼다. 실패: 400 POUCH_INVALID_UPDATE·POUCH_INVALID_PRODUCT, 404, 409 POUCH_DUPLICATE
 */
export type PouchUpdateRequest =
  | { registrationMode: "CATALOG"; type: string; productId: string; shadeId?: string }
  | Omit<Extract<PouchRegistrationRequest, { registrationMode: "MANUAL" }>, "registrationMode">;

/** 등록(201)·수정(200) 응답 */
export interface PouchWriteResponse {
  item: PouchItemResponse;
  pouchVersion: number;
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

/**
 * POST /v1/users/me/analysis-jobs 응답 (AnalysisJobReceipt, API-VIDEO-002).
 * 200 REUSED_GUIDE(승인 가이드 재사용, jobId=null) · 202 JOINED_JOB(진행 중 작업에 합류) · 202 NEW_JOB(새 작업).
 * 실패: 409 VIDEO_UNSUPPORTED_FOR_ANALYSIS, 429 ANALYSIS_DAILY_LIMIT_EXCEEDED, 503 VIDEO_ANALYSIS_UNAVAILABLE
 */
export interface AnalysisJobReceipt {
  jobId: string | null;
  videoId: string;
  receiptType: "REUSED_GUIDE" | "JOINED_JOB" | "NEW_JOB";
  status: AnalysisJobStatus["status"];
  progressStage: AnalysisJobStatus["progressStage"];
  /** 재사용이면 승인된 가이드 ID, 그 밖에는 null */
  guideId: string | null;
  reviewStatus: AnalysisJobStatus["reviewStatus"];
  pollAfterSeconds: number | null;
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

/**
 * GET /v1/users/me/analysis-jobs 한 줄 (AnalysisJobSummary, API-VIDEO-007). 내가 요청 · 합류한 작업 중 분석이 끝난 것만,
 * 요청 · 합류 시각 최신순. reviewStatus를 고르지 않으면 PENDING · APPROVED만 온다. guideId는 APPROVED일 때만 있다
 */
export interface AnalysisJobSummary {
  jobId: string;
  videoId: string;
  youtubeVideoId: string;
  title: string;
  thumbnailUrl: string | null;
  status: "COMPLETED";
  reviewStatus: "PENDING" | "APPROVED" | "REJECTED";
  guideId: string | null;
  requestedAt: string;
  reviewedAt: string | null;
}

/** 인기 영상 한 줄 (PopularVideoItem, API-VIDEO-005). 검색 결과 칸 + 순위 · 내부 영상 ID. viewCount는 늘 null */
export interface PopularVideoItem extends VideoSearchItem {
  rank: number;
  /** 가이드가 없을 때 영상 선택 없이 바로 분석 요청(API-VIDEO-002)에 쓴다 */
  videoId: string;
}

/**
 * GET /v1/videos/popular 응답 (PopularVideoResponse). 최근 30일 동안 영상을 고른 서로 다른 회원 수 순으로 1~4개.
 * 기록이 하나도 없으면 503 VIDEO_POPULAR_UNAVAILABLE
 */
export interface PopularVideoResponse {
  items: PopularVideoItem[];
  rankingBasis: "DISTINCT_MEMBER_SELECTIONS";
  aggregationScope: "LAST_30_DAYS";
  updatedAt: string;
  nextRefreshAt: string;
}

/** 얼굴 등록 촬영 조건 (FaceChecks). 앞 4개가 모두 true여야 등록된다. makeupDetected는 저장만 한다 */
export interface FaceChecks {
  lighting: boolean;
  distance: boolean;
  frontal: boolean;
  unobstructed: boolean;
  makeupDetected: boolean;
}

/** POST /v1/users/me/face-registrations의 metadata 파트 (FaceRegistrationRequest). videoId는 내부 영상 ID */
export interface FaceRegistrationRequest {
  videoId: string;
  guideId: string | null;
  noticeVersion: string;
  agreed: boolean;
  checks: FaceChecks;
}

/** 얼굴 등록 (FaceRegistration) 중 FE가 쓰는 칸. 실행을 시작하면 executionId가 채워진다 */
export interface FaceRegistration {
  faceRegistrationId: string;
  videoId: string;
  guideId: string | null;
  executionId: string | null;
  status: string;
  noticeVersion: string;
  createdAt: string;
}

/** 실행 시작 때 단계 하나의 제품 선택. 고르지 않은 단계도 null로 보낸다 */
export interface ExecutionSelection {
  stepId: string;
  selectedPouchItemId: string | null;
}

/** POST /v1/users/me/executions 요청 (CreateExecutionRequest). selections는 GUIDE 단계 전부 */
export interface CreateExecutionRequest {
  guideId: string;
  matchId: string;
  faceRegistrationId: string;
  selections: ExecutionSelection[];
  acceptMissingProducts: boolean;
}

/** 실행 단계 스냅샷 중 FE가 쓰는 칸. 시작 때 서버가 확정한 제품 선택과 그 결과 */
export interface ExecutionStep extends ExecutionSelection {
  result: "SAME" | "SUBSTITUTE" | "NONE";
  /** 고른 제품의 색 칸. 기준색이 없어 칸을 정하지 못했으면 null */
  selectedColor: ColorInfo | null;
  /** 제품 없이 진행하는 단계 */
  skipped: boolean;
}

/** 실행 (Execution) 중 FE가 쓰는 칸. steps는 단계마다 확정한 제품 선택 */
export interface ExecutionSummary {
  executionId: string;
  guideId: string;
  status: "IN_PROGRESS" | "COMPLETED" | "ABANDONED";
  recordId: string | null;
  steps: ExecutionStep[];
}

/** POST …/executions/{executionId}/completion 응답. 처음 201, 다시 보내면 200이고 recordId가 같다 */
export interface ExecutionCompletion {
  executionId: string;
  status: "COMPLETED";
  recordId: string;
  completedAt: string;
}

/** POST …/executions/{executionId}/abandonment 응답. cleanupPending은 파일 정리가 남았는지 */
export interface ExecutionAbandonment {
  executionId: string;
  status: "ABANDONED";
  cleanupPending: boolean;
}

/** 사진 메타 (PhotoResponse). url은 세션 쿠키로 읽으므로 <img src>에 그대로 쓴다 */
export interface PhotoMeta {
  photoId: string;
  kind: string;
  contentType: string;
  byteSize: number;
  width: number;
  height: number;
  url: string;
  createdAt: string;
}

/** 리포트 목록 한 줄 (ReportSummary). completedPhoto는 가장 나중에 찍은 단계 사진이고, 찍은 사진이 없으면 null */
export interface ReportSummaryDto {
  recordId: string;
  guideId: string;
  videoId: string;
  youtubeVideoId: string;
  videoTitle: string;
  channelTitle: string;
  thumbnailUrl: string | null;
  completedAt: string;
  completedPhoto: PhotoMeta | null;
  stepCount: number;
  substituteCount: number;
}

/** 리포트 상세의 단계 (ReportStep) 중 FE가 쓰는 칸 */
export interface ReportStepDto {
  stepId: string;
  part: string;
  partLabel: string | null;
  summary: string | null;
  actions: { text: string }[];
  referenceProduct: { name: string | null; shadeName: string | null } | null;
  matchingResult: "SAME" | "SUBSTITUTE" | "NONE";
  selectedProduct: { brand: string; name: string; shadeName: string | null } | null;
  skipped: boolean;
  photo: PhotoMeta | null;
}

/** 리포트 상세 (ReportRecord). 완료 때 저장한 스냅샷이다. youtubeVideoId · thumbnailUrl은 목록에만 있다 */
export interface ReportRecordDto {
  recordId: string;
  executionId: string;
  videoId: string;
  videoTitle: string;
  channelTitle: string;
  guideId: string;
  guideVersion: number;
  completedAt: string;
  completedPhoto: PhotoMeta | null;
  stepCount: number;
  substituteCount: number;
  steps: ReportStepDto[];
}
