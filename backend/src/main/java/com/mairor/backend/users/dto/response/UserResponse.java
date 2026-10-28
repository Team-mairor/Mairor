package com.mairor.backend.users.dto.response;

import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.User;
import java.time.Instant;

/**
 * 회원 응답 (API 명세 User v2). 비밀번호·해시와, 저장은 하지만 내려주지 않는 이름·휴대폰·생년월일·성별·약관 이력은 담지 않는다. 닉네임을 입력하지 않았으면
 * {@code null}.
 */
public record UserResponse(
    String userId, String email, String nickname, AuthProvider provider, Instant createdAt) {

  public static UserResponse from(User user) {
    return new UserResponse(
        user.getId().toString(),
        user.getEmail(),
        user.getNickname(),
        user.getProvider(),
        user.getCreatedAt());
  }
}
