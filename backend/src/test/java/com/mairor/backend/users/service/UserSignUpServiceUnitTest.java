package com.mairor.backend.users.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserAgreementRepository;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.AgreementPolicy;
import com.mairor.backend.users.support.AgreementProperties;
import com.mairor.backend.users.support.EmailVerificationProperties;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.SignupProperties;
import com.mairor.backend.users.support.VerificationHasher;
import java.time.Clock;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.transaction.PlatformTransactionManager;

/** DB 오류가 이메일 중복이 아니면 그대로 전달되는지 확인한다 (다른 제약 위반을 409로 오인하지 않는다). */
class UserSignUpServiceUnitTest {

  private final UserRepository userRepository = mock(UserRepository.class);
  private final UserSignUpService service =
      new UserSignUpService(
          userRepository,
          mock(UserAgreementRepository.class),
          PasswordEncoderFactories.createDelegatingPasswordEncoder(),
          new AgreementPolicy(
              new AgreementProperties(
                  new AgreementProperties.Versions(
                      SignUpRequests.CURRENT_VERSION,
                      SignUpRequests.CURRENT_VERSION,
                      SignUpRequests.CURRENT_VERSION))),
          new SignupProperties(false),
          mock(EmailVerificationStore.class),
          new VerificationHasher(
              new EmailVerificationProperties(
                  "secret",
                  Duration.ofMinutes(10),
                  Duration.ofSeconds(60),
                  5,
                  5,
                  Duration.ofMinutes(30))),
          Clock.systemUTC(),
          mock(PlatformTransactionManager.class));

  @Test
  void signUp_otherIntegrityViolation_isRethrownUnchanged() {
    DataIntegrityViolationException other =
        new DataIntegrityViolationException("not-null violation", new RuntimeException("boom"));
    when(userRepository.existsByEmail("member@example.com")).thenReturn(false);
    when(userRepository.saveAndFlush(any(User.class))).thenThrow(other);

    assertThatThrownBy(
            () ->
                service.signUp(
                    SignUpRequests.basic(
                        "member@example.com", "ExampleOnly!2026", "ExampleOnly!2026")))
        .isSameAs(other);
  }

  @Test
  void isEmailUniqueViolation_falseWithoutAConstraintViolationCause() {
    assertThat(UserSignUpService.isEmailUniqueViolation(new RuntimeException("x"))).isFalse();
    assertThat(UserSignUpService.isEmailUniqueViolation(null)).isFalse();
  }
}
