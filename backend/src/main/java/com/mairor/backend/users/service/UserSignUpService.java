package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.users.dto.request.SignUpRequest;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.PasswordNormalizer;
import java.util.List;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/**
 * 자체 회원가입 (API-USERS-001). 입력 형식은 {@link SignUpRequest}가 검증하고, 여기서는 확인값 일치·이메일 중복·해시 저장을 처리한다.
 *
 * <p>가입은 계정만 만든다. 세션·토큰은 발급하지 않는다 (로그인은 별도).
 *
 * <p>메서드에 트랜잭션을 걸지 않는다. bcrypt 해시를 계산하는 동안 DB 커넥션을 쥐지 않기 위해서이고, 저장소 호출이 각자 트랜잭션을 연다. 가입이 다른 테이블(약관
 * 동의 등)도 함께 써야 하면 해시는 밖에서 계산하고 저장만 {@code TransactionTemplate}으로 묶는다.
 */
@Service
public class UserSignUpService {

  private static final String EMAIL_DUPLICATE_CODE = "USERS_EMAIL_DUPLICATE";
  private static final String UNIQUE_VIOLATION_SQL_STATE = "23505";

  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;

  public UserSignUpService(UserRepository userRepository, PasswordEncoder passwordEncoder) {
    this.userRepository = userRepository;
    this.passwordEncoder = passwordEncoder;
  }

  public UserResponse signUp(SignUpRequest request) {
    // 확인값도 해시와 같은 NFC 기준으로 비교한다 (입력 방식만 달라 일치하지 않는 일을 막는다)
    String password = PasswordNormalizer.normalize(request.password());
    if (!password.equals(PasswordNormalizer.normalize(request.passwordConfirm()))) {
      throw passwordMismatch();
    }
    if (userRepository.existsByEmail(request.email())) {
      throw emailDuplicate();
    }

    String hash = passwordEncoder.encode(password);
    try {
      return UserResponse.from(userRepository.saveAndFlush(new User(request.email(), hash)));
    } catch (DataIntegrityViolationException e) {
      // 위 조회와 저장 사이에 같은 이메일이 들어온 경우만 중복으로 본다. 그 밖의 제약 위반은 그대로 전달한다.
      if (isEmailUniqueViolation(e)) {
        throw emailDuplicate();
      }
      throw e;
    }
  }

  /** 예외의 원인 사슬에 이메일 유니크 제약({@link User#EMAIL_UNIQUE}) 위반이 있는지 확인한다. */
  static boolean isEmailUniqueViolation(Throwable e) {
    for (Throwable t = e; t != null; t = t.getCause()) {
      if (t instanceof ConstraintViolationException violation
          && UNIQUE_VIOLATION_SQL_STATE.equals(violation.getSQLState())
          && User.EMAIL_UNIQUE.equalsIgnoreCase(violation.getConstraintName())) {
        return true;
      }
    }
    return false;
  }

  private static BusinessException passwordMismatch() {
    return new BusinessException(
        HttpStatus.BAD_REQUEST,
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError("passwordConfirm", "비밀번호와 일치하지 않습니다.")),
        null);
  }

  private static BusinessException emailDuplicate() {
    return new BusinessException(HttpStatus.CONFLICT, EMAIL_DUPLICATE_CODE, "이미 가입된 이메일입니다.");
  }
}
