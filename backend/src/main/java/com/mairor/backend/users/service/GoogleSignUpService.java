package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.users.dto.request.GoogleSignUpRequest;
import com.mairor.backend.users.dto.request.SignupAgreement;
import com.mairor.backend.users.dto.response.LoginResponse;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.entity.AgreementType;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.Gender;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.entity.UserAgreement;
import com.mairor.backend.users.entity.UserIdentity;
import com.mairor.backend.users.repository.UserAgreementRepository;
import com.mairor.backend.users.repository.UserIdentityRepository;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.AgreementPolicy;
import com.mairor.backend.users.support.BirthDatePolicy;
import com.mairor.backend.users.support.GoogleAuthFailure;
import com.mairor.backend.users.support.GoogleSignupStore;
import com.mairor.backend.users.support.VerificationHasher;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.util.StringUtils;

/**
 * Google 가입 완료. callback 이 저장한 가입 대기(검증한 Google 계정)에 약관·추가 정보를 더해 회원을 만들고 바로 로그인시킨다. 비밀번호는 없다.
 *
 * <ol>
 *   <li>입력을 검증한다(생년월일·필수 약관). 입력 오류는 가입 대기를 쓰지 않아서 고쳐 다시 보낼 수 있다.
 *   <li>가입 대기를 꺼낸다(1회용). 없거나 만료·이미 사용이면 410.
 *   <li>그사이 같은 이메일로 가입됐으면 409 {@code USERS_ACCOUNT_LINK_REQUIRED}. 자동으로 연결하지 않는다.
 *   <li>회원·Google 연결·약관 동의를 한 트랜잭션에 저장한다. 이메일은 Google 이 확인한 값이라 확인 시각을 가입 시각으로 둔다.
 *   <li>세션을 만들고 로그인 응답을 돌려준다.
 * </ol>
 *
 * <p>저장한 뒤 세션 발급이 실패하면 회원은 남고 응답은 실패다. 사용자는 Google 로 다시 로그인하면 연결된 회원으로 들어온다.
 */
@Service
public class GoogleSignUpService {

  private final GoogleSignupStore signupStore;
  private final VerificationHasher hasher;
  private final AgreementPolicy agreementPolicy;
  private final BirthDatePolicy birthDatePolicy;
  private final UserRepository userRepository;
  private final UserIdentityRepository identityRepository;
  private final UserAgreementRepository agreementRepository;
  private final SessionEstablisher sessionEstablisher;
  private final Clock clock;
  private final TransactionTemplate transactionTemplate;

  public GoogleSignUpService(
      GoogleSignupStore signupStore,
      VerificationHasher hasher,
      AgreementPolicy agreementPolicy,
      BirthDatePolicy birthDatePolicy,
      UserRepository userRepository,
      UserIdentityRepository identityRepository,
      UserAgreementRepository agreementRepository,
      SessionEstablisher sessionEstablisher,
      Clock clock,
      PlatformTransactionManager transactionManager) {
    this.signupStore = signupStore;
    this.hasher = hasher;
    this.agreementPolicy = agreementPolicy;
    this.birthDatePolicy = birthDatePolicy;
    this.userRepository = userRepository;
    this.identityRepository = identityRepository;
    this.agreementRepository = agreementRepository;
    this.sessionEstablisher = sessionEstablisher;
    this.clock = clock;
    this.transactionTemplate = new TransactionTemplate(transactionManager);
  }

  /**
   * @param key 가입 대기 쿠키 값 (없으면 {@code null})
   */
  public LoginResponse signUp(
      String key,
      GoogleSignUpRequest request,
      HttpServletRequest httpRequest,
      HttpServletResponse httpResponse) {
    birthDatePolicy.validate(request.birthDate());
    Map<AgreementType, SignupAgreement> agreements = agreementPolicy.validate(request.agreements());

    Instant now = clock.instant();
    if (!StringUtils.hasText(key)) {
      throw GoogleLoginService.signupExpired();
    }
    GoogleSignupStore.Pending pending =
        signupStore.take(hasher.hashToken(key), now).orElseThrow(GoogleLoginService::signupExpired);
    if (userRepository.existsByEmail(pending.email())) {
      throw accountLinkRequired();
    }

    User user;
    try {
      user =
          transactionTemplate.execute(
              status -> {
                User saved =
                    userRepository.saveAndFlush(
                        new User(
                            pending.email(),
                            null,
                            AuthProvider.GOOGLE,
                            request.nickname(),
                            request.name(),
                            request.phone(),
                            request.birthDate(),
                            request.gender() == null ? null : Gender.valueOf(request.gender()),
                            now));
                identityRepository.saveAndFlush(
                    new UserIdentity(saved, AuthProvider.GOOGLE, pending.subject()));
                agreementRepository.saveAllAndFlush(
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
                return saved;
              });
    } catch (DataIntegrityViolationException e) {
      // 위 확인과 저장 사이에 같은 이메일로 가입됐거나, 같은 Google 계정의 가입이 먼저 끝났다
      if (UserSignUpService.isEmailUniqueViolation(e)) {
        throw accountLinkRequired();
      }
      if (UserSignUpService.isUniqueViolation(e, UserIdentity.PROVIDER_SUBJECT_UNIQUE)) {
        throw GoogleLoginService.signupExpired();
      }
      throw e;
    }

    String csrfToken = sessionEstablisher.establish(user, httpRequest, httpResponse);
    return new LoginResponse(UserResponse.from(user), csrfToken);
  }

  private static BusinessException accountLinkRequired() {
    return new BusinessException(
        HttpStatus.CONFLICT,
        GoogleAuthFailure.ACCOUNT_LINK_REQUIRED.code(),
        "같은 이메일로 가입된 계정이 있습니다. 이메일로 로그인해 주세요.");
  }
}
