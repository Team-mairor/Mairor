package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.AuthenticatedUser;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

/**
 * 로그인한 회원 자신의 계정 조회. 세션에 든 principal 의 userId 로 회원을 다시 읽는다. 회원이 사라졌거나 principal 이 회원 principal 이
 * 아니면 로그인되지 않은 것과 같이 401 로 응답한다.
 */
@Service
public class UserAccountService {

  private final UserRepository userRepository;

  public UserAccountService(UserRepository userRepository) {
    this.userRepository = userRepository;
  }

  public UserResponse current(Authentication authentication) {
    if (!(authentication.getPrincipal() instanceof AuthenticatedUser principal)) {
      throw new BusinessException(ErrorCode.UNAUTHORIZED);
    }
    return userRepository
        .findById(principal.userId())
        .map(UserResponse::from)
        .orElseThrow(() -> new BusinessException(ErrorCode.UNAUTHORIZED));
  }
}
