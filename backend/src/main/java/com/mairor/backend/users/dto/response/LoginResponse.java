package com.mairor.backend.users.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * 로그인·내 계정 조회 응답. {@code csrfToken} 은 이후 변경 요청(POST·PUT·PATCH·DELETE)의 {@code X-CSRF-TOKEN} 헤더에 실어
 * 보낸다. 로그인할 때마다 새로 발급되므로 이전에 받은 토큰은 쓸 수 없다.
 */
public record LoginResponse(
    UserResponse user,
    @Schema(description = "변경 요청의 X-CSRF-TOKEN 헤더에 넣는 값. 메모리에만 두고 로컬 저장소에 저장하지 않는다")
        String csrfToken) {

  /** 토큰이 로그에 남지 않도록 마스킹한다. */
  @Override
  public String toString() {
    return "LoginResponse[user=" + user + ", csrfToken=***]";
  }
}
