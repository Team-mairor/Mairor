package com.mairor.backend.users.dto.request;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.util.Set;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class LoginRequestTest {

  private static ValidatorFactory factory;
  private static Validator validator;

  @BeforeAll
  static void setUp() {
    factory = Validation.buildDefaultValidatorFactory();
    validator = factory.getValidator();
  }

  @AfterAll
  static void tearDown() {
    factory.close();
  }

  private static Set<String> invalidFields(LoginRequest request) {
    return validator.validate(request).stream()
        .map(ConstraintViolation::getPropertyPath)
        .map(Object::toString)
        .collect(java.util.stream.Collectors.toSet());
  }

  @Test
  void normalizesTheEmailButKeepsThePasswordAsTyped() {
    LoginRequest request = new LoginRequest("  Member@Example.COM  ", " Pass word1! ");

    assertThat(request.email()).isEqualTo("member@example.com");
    assertThat(request.password()).isEqualTo(" Pass word1! ");
  }

  @Test
  void toStringMasksThePassword() {
    LoginRequest request = new LoginRequest("member@example.com", "Secret-Password-1!");

    assertThat(request.toString()).doesNotContain("Secret-Password-1!").contains("password=***");
  }

  @Test
  void acceptsAnyEmailShapeBecauseTheLookupJustFails() {
    // 형식 규칙을 응답으로 알려 주지 않는다. 형식이 틀리면 조회에 실패해 401 이 된다
    assertThat(invalidFields(new LoginRequest("not-an-email", "x"))).isEmpty();
  }

  @Test
  void doesNotApplyPasswordStrengthRules() {
    // 정책이 바뀌기 전에 가입한 짧거나 약한 비밀번호도 로그인돼야 한다
    assertThat(invalidFields(new LoginRequest("member@example.com", "a"))).isEmpty();
    assertThat(invalidFields(new LoginRequest("member@example.com", "   "))).isEmpty();
  }

  @Test
  void rejectsMissingOrBlankValues() {
    assertThat(invalidFields(new LoginRequest(null, "x"))).containsExactly("email");
    assertThat(invalidFields(new LoginRequest("   ", "x"))).containsExactly("email");
    assertThat(invalidFields(new LoginRequest("member@example.com", null)))
        .containsExactly("password");
    assertThat(invalidFields(new LoginRequest("member@example.com", "")))
        .containsExactly("password");
  }

  @Test
  void limitsTheInputSizeOnly() {
    String longestEmail = "a".repeat(242) + "@example.com";
    assertThat(longestEmail).hasSize(254);
    assertThat(invalidFields(new LoginRequest(longestEmail, "x"))).isEmpty();
    assertThat(invalidFields(new LoginRequest("a" + longestEmail, "x"))).containsExactly("email");

    assertThat(invalidFields(new LoginRequest("member@example.com", "p".repeat(256)))).isEmpty();
    assertThat(invalidFields(new LoginRequest("member@example.com", "p".repeat(257))))
        .containsExactly("password");
  }
}
