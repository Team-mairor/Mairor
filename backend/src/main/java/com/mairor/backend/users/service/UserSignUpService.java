package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.users.dto.request.SignUpRequest;
import com.mairor.backend.users.dto.request.SignupAgreement;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.entity.AgreementType;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.Gender;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.entity.UserAgreement;
import com.mairor.backend.users.repository.UserAgreementRepository;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.AgreementPolicy;
import com.mairor.backend.users.support.BirthDatePolicy;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.EmailVerificationStoreConfig;
import com.mairor.backend.users.support.PasswordNormalizer;
import com.mairor.backend.users.support.SignupProperties;
import com.mairor.backend.users.support.VerificationHasher;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.hibernate.exception.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 자체 회원가입 (API-USERS-001). 입력 형식은 {@link SignUpRequest}가 검증하고, 여기서는 확인값 일치, 생년월일 범위({@link
 * BirthDatePolicy}), 필수 약관({@link AgreementPolicy}), 이메일 인증({@link SignupProperties}), 중복을 확인한 뒤
 * 저장한다. 세션·토큰은 발급하지 않는다.
 *
 * <p>bcrypt 해시를 계산하는 동안 DB 커넥션을 쥐지 않도록 메서드 전체에는 트랜잭션을 걸지 않고, 회원과 약관 동의 기록 저장만 {@link
 * TransactionTemplate}으로 묶는다.
 */
@Service
public class UserSignUpService {

  private static final Logger log = LoggerFactory.getLogger(UserSignUpService.class);

  private static final String EMAIL_DUPLICATE_CODE = "USERS_EMAIL_DUPLICATE";
  private static final String EMAIL_NOT_VERIFIED_CODE = "USERS_EMAIL_NOT_VERIFIED";
  private static final String UNIQUE_VIOLATION_SQL_STATE = "23505";

  private final UserRepository userRepository;
  private final UserAgreementRepository userAgreementRepository;
  private final PasswordEncoder passwordEncoder;
  private final AgreementPolicy agreementPolicy;
  private final BirthDatePolicy birthDatePolicy;
  private final SignupProperties signupProperties;
  private final EmailVerificationStore verificationStore;
  private final VerificationHasher verificationHasher;
  private final Clock clock;
  private final TransactionTemplate transactionTemplate;

  public UserSignUpService(
      UserRepository userRepository,
      UserAgreementRepository userAgreementRepository,
      PasswordEncoder passwordEncoder,
      AgreementPolicy agreementPolicy,
      BirthDatePolicy birthDatePolicy,
      SignupProperties signupProperties,
      @Qualifier(EmailVerificationStoreConfig.SIGNUP) EmailVerificationStore verificationStore,
      VerificationHasher verificationHasher,
      Clock clock,
      PlatformTransactionManager transactionManager) {
    this.userRepository = userRepository;
    this.userAgreementRepository = userAgreementRepository;
    this.passwordEncoder = passwordEncoder;
    this.agreementPolicy = agreementPolicy;
    this.birthDatePolicy = birthDatePolicy;
    this.signupProperties = signupProperties;
    this.verificationStore = verificationStore;
    this.verificationHasher = verificationHasher;
    this.clock = clock;
    this.transactionTemplate = new TransactionTemplate(transactionManager);
  }

  public UserResponse signUp(SignUpRequest request) {
    // 확인값도 해시와 같은 NFC 기준으로 비교한다 (입력 방식만 달라 일치하지 않는 일을 막는다)
    String password = PasswordNormalizer.normalize(request.password());
    if (!password.equals(PasswordNormalizer.normalize(request.passwordConfirm()))) {
      throw passwordMismatch();
    }
    birthDatePolicy.validate(request.birthDate());
    Map<AgreementType, SignupAgreement> agreements = agreementPolicy.validate(request.agreements());
    Instant now = clock.instant();
    // 토큰은 읽기만 하고, 가입이 커밋된 뒤에 지운다
    String tokenHash =
        signupProperties.requireEmailVerification() ? verifiedToken(request, now) : null;
    if (userRepository.existsByEmail(request.email())) {
      throw emailDuplicate();
    }

    // 해시 계산은 느리므로 트랜잭션(DB 커넥션) 밖에서 한다
    String hash = passwordEncoder.encode(password);
    User user =
        new User(
            request.email(),
            hash,
            AuthProvider.LOCAL,
            request.nickname(),
            request.name(),
            request.phone(),
            request.birthDate(),
            request.gender() == null ? null : Gender.valueOf(request.gender()),
            tokenHash == null ? null : now);
    UserResponse response;
    try {
      response =
          transactionTemplate.execute(
              status -> {
                User saved = userRepository.saveAndFlush(user);
                userAgreementRepository.saveAllAndFlush(
                    agreements.values().stream()
                        .map(
                            a ->
                                new UserAgreement(
                                    saved,
                                    AgreementType.valueOf(a.type()),
                                    a.version(),
                                    a.agreed(),
                                    now))
                        .toList());
                return UserResponse.from(saved);
              });
    } catch (DataIntegrityViolationException e) {
      // 위 조회와 저장 사이에 같은 이메일이 들어온 경우만 중복으로 본다. 그 밖의 제약 위반은 그대로 전달한다.
      if (isEmailUniqueViolation(e)) {
        throw emailDuplicate();
      }
      throw e;
    }
    if (tokenHash != null) {
      discardToken(tokenHash);
    }
    return response;
  }

  /** 인증 토큰이 이 이메일의 유효한 토큰이면 해시를 돌려준다. 아니면 이유를 구별하지 않고 {@code USERS_EMAIL_NOT_VERIFIED}. */
  private String verifiedToken(SignUpRequest request, Instant now) {
    String token = request.emailVerificationToken();
    if (token != null) {
      String hash = verificationHasher.hashToken(token);
      if (verificationStore.hasValidToken(hash, request.email(), now)) {
        return hash;
      }
    }
    throw new BusinessException(
        HttpStatus.BAD_REQUEST, EMAIL_NOT_VERIFIED_CODE, "이메일 인증을 완료해 주세요.");
  }

  /** 지우지 못해도 가입은 성공이다 (토큰은 만료되면 사라지고, 그 이메일은 이미 가입돼 있다). */
  private void discardToken(String tokenHash) {
    try {
      verificationStore.deleteToken(tokenHash);
    } catch (RuntimeException e) {
      log.warn("가입을 마친 이메일 인증 토큰을 지우지 못했습니다. 유효 시간이 지나면 사라집니다.", e);
    }
  }

  /** 예외의 원인 사슬에 이메일 유니크 제약({@link User#EMAIL_UNIQUE}) 위반이 있는지 확인한다. */
  static boolean isEmailUniqueViolation(Throwable e) {
    return isUniqueViolation(e, User.EMAIL_UNIQUE);
  }

  /** 예외의 원인 사슬에 이름이 {@code constraintName} 인 유니크 제약 위반이 있는지 확인한다. */
  static boolean isUniqueViolation(Throwable e, String constraintName) {
    for (Throwable t = e; t != null; t = t.getCause()) {
      if (t instanceof ConstraintViolationException violation
          && UNIQUE_VIOLATION_SQL_STATE.equals(violation.getSQLState())
          && constraintName.equalsIgnoreCase(violation.getConstraintName())) {
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
