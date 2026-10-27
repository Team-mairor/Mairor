package com.mairor.backend.users.dto.response;

import com.mairor.backend.users.entity.User;
import java.time.Instant;

/** 회원 응답 (공통 규약의 User). 비밀번호·해시는 담지 않는다. */
public record UserResponse(String userId, String email, Instant createdAt) {

  public static UserResponse from(User user) {
    return new UserResponse(user.getId().toString(), user.getEmail(), user.getCreatedAt());
  }
}
