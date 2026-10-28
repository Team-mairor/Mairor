package com.mairor.backend.users.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.dto.request.SignUpRequest;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import java.text.Normalizer;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.annotation.Transactional;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@Transactional
class UserSignUpServiceTest {

  private static final String PASSWORD = "ExampleOnly!2026";

  @Autowired private UserSignUpService service;
  @Autowired private PasswordEncoder passwordEncoder;

  @MockitoSpyBean private UserRepository userRepository;

  private static SignUpRequest request(String email, String password) {
    return SignUpRequests.basic(email, password, password);
  }

  @Test
  void signUp_storesNormalizedEmailAndBcryptHash() {
    UserResponse response = service.signUp(request("  Member@Example.COM ", PASSWORD));

    assertThat(response.userId()).isNotNull();
    assertThat(UUID.fromString(response.userId())).isNotNull();
    assertThat(response.email()).isEqualTo("member@example.com");
    assertThat(response.createdAt()).isNotNull();

    User saved = userRepository.findById(UUID.fromString(response.userId())).orElseThrow();
    assertThat(saved.getEmail()).isEqualTo("member@example.com");
    assertThat(saved.getPasswordHash()).startsWith("{bcrypt}$2").doesNotContain(PASSWORD);
    assertThat(passwordEncoder.matches(PASSWORD, saved.getPasswordHash())).isTrue();
  }

  @Test
  void signUp_hashesPasswordAfterNfcNormalization() {
    String decomposed = Normalizer.normalize("비밀번호abc1!", Normalizer.Form.NFD);
    String composed = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

    UserResponse response = service.signUp(request("member@example.com", decomposed));

    User saved = userRepository.findById(UUID.fromString(response.userId())).orElseThrow();
    assertThat(passwordEncoder.matches(composed, saved.getPasswordHash())).isTrue();
  }

  @Test
  void signUp_confirmDifferingOnlyByUnicodeForm_isAccepted() {
    String composed = Normalizer.normalize("비밀번호abc1!", Normalizer.Form.NFC);
    String decomposed = Normalizer.normalize(composed, Normalizer.Form.NFD);
    assertThat(decomposed).isNotEqualTo(composed);

    UserResponse response =
        service.signUp(SignUpRequests.basic("member@example.com", composed, decomposed));

    User saved = userRepository.findById(UUID.fromString(response.userId())).orElseThrow();
    assertThat(passwordEncoder.matches(composed, saved.getPasswordHash())).isTrue();
  }

  @Test
  void signUp_keepsWhitespaceInThePassword() {
    String withSpaces = " ExampleOnly!2026 ";

    UserResponse response = service.signUp(request("member@example.com", withSpaces));

    User saved = userRepository.findById(UUID.fromString(response.userId())).orElseThrow();
    assertThat(passwordEncoder.matches(withSpaces, saved.getPasswordHash())).isTrue();
    assertThat(passwordEncoder.matches(withSpaces.strip(), saved.getPasswordHash())).isFalse();
  }

  @Test
  void signUp_mismatchedConfirm_returns400WithFieldDetail() {
    SignUpRequest mismatched = SignUpRequests.basic("member@example.com", PASSWORD, PASSWORD + " ");

    assertThatThrownBy(() -> service.signUp(mismatched))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.status()).isEqualTo(HttpStatus.BAD_REQUEST);
              assertThat(e.code()).isEqualTo("VALIDATION_FAILED");
              assertThat(e.details()).hasSize(1);
              assertThat(e.details().get(0).field()).isEqualTo("passwordConfirm");
            });
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @Test
  void signUp_existingEmail_returns409() {
    service.signUp(request("member@example.com", PASSWORD));

    assertThatThrownBy(() -> service.signUp(request("member@example.com", PASSWORD)))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.status()).isEqualTo(HttpStatus.CONFLICT);
              assertThat(e.code()).isEqualTo("USERS_EMAIL_DUPLICATE");
            });
  }

  @Test
  void signUp_emailDifferingOnlyByCaseAndSpaces_returns409() {
    service.signUp(request("member@example.com", PASSWORD));

    assertThatThrownBy(() -> service.signUp(request("  MEMBER@Example.com ", PASSWORD)))
        .isInstanceOfSatisfying(
            BusinessException.class, e -> assertThat(e.code()).isEqualTo("USERS_EMAIL_DUPLICATE"));
  }

  @Test
  void signUp_duplicateSlippingPastTheLookup_isStillReportedAs409() {
    // 조회와 저장 사이에 같은 이메일이 들어온 상황: 조회는 없다고 답하지만 DB 유니크 제약이 막는다
    userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}existing"));
    doReturn(false).when(userRepository).existsByEmail("member@example.com");

    assertThatThrownBy(() -> service.signUp(request("member@example.com", PASSWORD)))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.status()).isEqualTo(HttpStatus.CONFLICT);
              assertThat(e.code()).isEqualTo("USERS_EMAIL_DUPLICATE");
            });
  }

  @Test
  void signUp_mismatchedConfirm_doesNotTouchTheRepository() {
    SignUpRequest mismatched =
        SignUpRequests.basic("member@example.com", PASSWORD, "Other!2026abc");

    assertThatThrownBy(() -> service.signUp(mismatched)).isInstanceOf(BusinessException.class);

    verify(userRepository, never()).existsByEmail("member@example.com");
    verify(userRepository, never()).saveAndFlush(org.mockito.ArgumentMatchers.any());
  }

  // ---- 제약 위반 판별: 실제 DB가 만든 예외로 확인한다 ----

  @Test
  void isEmailUniqueViolation_trueForRealDuplicateEmailError() {
    userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThatThrownBy(
            () -> userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}other")))
        .isInstanceOfSatisfying(
            DataIntegrityViolationException.class,
            e -> assertThat(UserSignUpService.isEmailUniqueViolation(e)).isTrue());
  }

  @Test
  void isEmailUniqueViolation_falseForOtherConstraintErrors() {
    // 이메일이 비어 있는 NOT NULL 위반은 중복이 아니다
    assertThatThrownBy(() -> userRepository.saveAndFlush(new User(null, "{bcrypt}hash")))
        .isInstanceOfSatisfying(
            Exception.class,
            e -> assertThat(UserSignUpService.isEmailUniqueViolation(e)).isFalse());
  }
}
