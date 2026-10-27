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
 * POST /v1/users 요청 (SignUpRequest). 비밀번호는 8~64자에 영문자·숫자·기호를 하나씩 포함한다.
 * 규칙에 맞지 않거나 확인값이 다르면 400 VALIDATION_FAILED, 이미 가입된 이메일이면 409 USERS_EMAIL_DUPLICATE
 */
export interface SignUpRequest {
  email: string;
  password: string;
  passwordConfirm: string;
}

/** 회원 (UserResponse) */
export interface User {
  userId: string;
  email: string;
  createdAt: string;
}
