package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.entity.AgreementType;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.entity.UserAgreement;
import com.mairor.backend.users.repository.UserAgreementRepository;
import com.mairor.backend.users.repository.UserRepository;
import jakarta.servlet.http.Cookie;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회원가입 API 계약 (API-USERS-001). 실제 호출 조건 그대로 인증·CSRF 토큰 없이 허용 Origin 헤더만 보낸다. {@code @WithMockUser}나
 * {@code csrf()}를 붙이지 않는 것이 이 테스트의 핵심이다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
@AutoConfigureMockMvc
@Transactional
@ExtendWith(OutputCaptureExtension.class)
class UserControllerTest {

  private static final String ORIGIN = "http://localhost:3000";
  private static final String PASSWORD = "ExampleOnly!2026";

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository userRepository;
  @Autowired private UserAgreementRepository userAgreementRepository;
  @Autowired private PasswordEncoder passwordEncoder;

  private static String body(String email, String password, String confirm) {
    return """
        {"email": %s, "password": %s, "passwordConfirm": %s, "agreements": %s}"""
        .formatted(quote(email), quote(password), quote(confirm), SignUpRequests.AGREEMENTS_JSON);
  }

  /** 필수 3개 + 지정한 {@code agreements}(JSON 배열 문자열)만 가진 본문. */
  private static String bodyWithAgreements(String agreementsJson) {
    return """
        {"email": "member@example.com", "password": "%s", "passwordConfirm": "%s", "agreements": %s}"""
        .formatted(PASSWORD, PASSWORD, agreementsJson);
  }

  private static String agreement(String type, String version, boolean agreed) {
    return "{\"type\": \"%s\", \"version\": \"%s\", \"agreed\": %s}"
        .formatted(type, version, agreed);
  }

  private static String quote(String value) {
    return value == null ? "null" : "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
  }

  private static MockHttpServletRequestBuilder signUp(String json) {
    return post("/v1/users/signup")
        .header("Origin", ORIGIN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  // ---- 성공 ----

  @Test
  void signUp_returns201WithUserAndNoSecrets() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(
            jsonPath("$.userId").value(org.hamcrest.Matchers.matchesPattern("[0-9a-f-]{36}")))
        .andExpect(jsonPath("$.email").value("member@example.com"))
        .andExpect(jsonPath("$.createdAt").exists())
        .andExpect(jsonPath("$.password").doesNotExist())
        .andExpect(jsonPath("$.passwordConfirm").doesNotExist())
        .andExpect(jsonPath("$.passwordHash").doesNotExist())
        .andExpect(
            content()
                .string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("bcrypt"))));
  }

  @Test
  void signUp_storesNormalizedEmailAndHashedPassword() throws Exception {
    mockMvc
        .perform(signUp(body("  Member@Example.COM ", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.email").value("member@example.com"));

    User saved =
        userRepository.findAll().stream()
            .filter(u -> u.getEmail().equals("member@example.com"))
            .findFirst()
            .orElseThrow();
    assertThat(saved.getPasswordHash()).startsWith("{bcrypt}$2").doesNotContain(PASSWORD);
    assertThat(passwordEncoder.matches(PASSWORD, saved.getPasswordHash())).isTrue();
  }

  @Test
  void signUp_doesNotLogTheUserIn() throws Exception {
    MvcResult result =
        mockMvc
            .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
            .andExpect(status().isCreated())
            .andReturn();

    // 세션 쿠키를 주지 않고, 쿠키가 있더라도 그대로 실어 보낸 보호된 API는 여전히 401이다
    Cookie[] cookies = result.getResponse().getCookies();
    assertThat(cookies).extracting(Cookie::getName).doesNotContain("__Host-sessionId");
    MockHttpServletRequestBuilder next = get("/v1/any");
    if (cookies.length > 0) {
      next = next.cookie(cookies);
    }
    mockMvc.perform(next).andExpect(status().isUnauthorized());
    assertThat(result.getResponse().getHeader("Authorization")).isNull();
    assertThat(result.getResponse().getHeader("X-CSRF-Token")).isNull();
  }

  @Test
  void signUp_returnsCreatedAtAsUtcIso8601() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(
            jsonPath("$.createdAt")
                .value(
                    org.hamcrest.Matchers.matchesPattern(
                        "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(\\.\\d+)?Z")));
  }

  @ParameterizedTest
  @ValueSource(ints = {8, 64})
  void signUp_acceptsPasswordLengthBounds(int length) throws Exception {
    String password = "a1!" + "x".repeat(length - 3);

    mockMvc
        .perform(signUp(body("len" + length + "@example.com", password, password)))
        .andExpect(status().isCreated());
  }

  @ParameterizedTest
  @ValueSource(ints = {7, 65})
  void signUp_rejectsPasswordLengthOutOfBounds(int length) throws Exception {
    String password = "a1!" + "x".repeat(length - 3);

    mockMvc
        .perform(signUp(body("len" + length + "@example.com", password, password)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("password"));
    assertThat(userRepository.existsByEmail("len" + length + "@example.com")).isFalse();
  }

  @Test
  void signUp_neverWritesThePasswordOrItsHashToTheLog(CapturedOutput output) throws Exception {
    String secret = "LogProbe-Secret-2026!";

    mockMvc
        .perform(signUp(body("logprobe@example.com", secret, secret)))
        .andExpect(status().isCreated());
    mockMvc
        .perform(signUp(body("logprobe@example.com", secret, secret)))
        .andExpect(status().isConflict());
    mockMvc
        .perform(signUp(body("bad-email", secret, secret + "x")))
        .andExpect(status().isBadRequest());
    String hash =
        userRepository.findAll().stream()
            .filter(u -> u.getEmail().equals("logprobe@example.com"))
            .findFirst()
            .orElseThrow()
            .getPasswordHash();

    assertThat(output.getAll())
        .doesNotContain(secret)
        .doesNotContain(hash)
        .doesNotContain("{bcrypt}");
  }

  // ---- 400 ----

  @Test
  void signUp_withInvalidFields_returns400WithFieldDetails() throws Exception {
    mockMvc
        .perform(signUp(body("not-an-email", "short", "short")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(
            jsonPath("$.details[*].field")
                .value(org.hamcrest.Matchers.hasItems("email", "password")));
  }

  @Test
  void signUp_withMissingFields_returns400() throws Exception {
    mockMvc
        .perform(signUp("{}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(
            jsonPath("$.details[*].field")
                .value(org.hamcrest.Matchers.hasItems("email", "password", "passwordConfirm")));
  }

  @Test
  void signUp_withPasswordMissingRule_reportsWhichRule() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", "abcdefgh!", "abcdefgh!")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("password"))
        .andExpect(jsonPath("$.details[0].reason").value("숫자를 1개 이상 포함해야 합니다."));
  }

  @Test
  void signUp_withMismatchedConfirm_returns400OnConfirmField() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD + "x")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("passwordConfirm"));
  }

  @Test
  void signUp_withMalformedJson_returns400() throws Exception {
    mockMvc
        .perform(signUp("{not json"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void signUp_withoutBody_returns400() throws Exception {
    mockMvc
        .perform(
            post("/v1/users/signup")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void signUp_passwordIsNeverEchoedInErrors() throws Exception {
    mockMvc
        .perform(signUp(body("not-an-email", "secret-password-123", "secret-password-123")))
        .andExpect(status().isBadRequest())
        .andExpect(
            content()
                .string(
                    org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("secret-password"))));
  }

  // ---- 선택 필드·provider ----

  /** 필수 3개에 {@code extra}(예: {@code "nickname": "미러"})를 덧붙인 본문. */
  private static String bodyWith(String extra) {
    return """
        {"email": "member@example.com", "password": "%s", "passwordConfirm": "%s", %s,
         "agreements": %s}"""
        .formatted(PASSWORD, PASSWORD, extra, SignUpRequests.AGREEMENTS_JSON);
  }

  private User savedMember() {
    return userRepository.findAll().stream()
        .filter(u -> u.getEmail().equals("member@example.com"))
        .findFirst()
        .orElseThrow();
  }

  @Test
  void signUp_withOnlyRequiredFields_succeedsWithNullNickname() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.nickname").value(org.hamcrest.Matchers.nullValue()))
        .andExpect(jsonPath("$.provider").value("LOCAL"));

    User saved = savedMember();
    assertThat(saved.getProvider().name()).isEqualTo("LOCAL");
    assertThat(saved.getNickname()).isNull();
    assertThat(saved.getName()).isNull();
    assertThat(saved.getPhone()).isNull();
    assertThat(saved.getBirthDate()).isNull();
    assertThat(saved.getGender()).isNull();
  }

  @Test
  void signUp_whenEmailVerificationIsNotRequired_ignoresAnyTokenAndLeavesItUnverified()
      throws Exception {
    // 기본 설정(인증 요구 안 함)에서는 토큰이 없어도 가입되고, 토큰을 보내도 인증된 것으로 치지 않는다
    mockMvc
        .perform(signUp(bodyWith("\"emailVerificationToken\": \"some-token\"")))
        .andExpect(status().isCreated());

    assertThat(savedMember().getEmailVerifiedAt()).isNull();
  }

  @Test
  void signUp_withProfile_storesItButReturnsOnlyNickname() throws Exception {
    mockMvc
        .perform(
            signUp(
                bodyWith(
                    """
                    "nickname": " 미러 ", "name": "홍길동", "phone": "010-1234-5678",
                    "birthDate": "2000-01-15", "gender": "FEMALE\"""")))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.nickname").value("미러"))
        .andExpect(jsonPath("$.provider").value("LOCAL"))
        .andExpect(jsonPath("$.name").doesNotExist())
        .andExpect(jsonPath("$.phone").doesNotExist())
        .andExpect(jsonPath("$.birthDate").doesNotExist())
        .andExpect(jsonPath("$.gender").doesNotExist());

    User saved = savedMember();
    assertThat(saved.getNickname()).isEqualTo("미러");
    assertThat(saved.getName()).isEqualTo("홍길동");
    assertThat(saved.getPhone()).isEqualTo("01012345678");
    assertThat(saved.getBirthDate()).hasToString("2000-01-15");
    assertThat(saved.getGender().name()).isEqualTo("FEMALE");
  }

  @Test
  void signUp_withBlankOptionalFields_treatsThemAsOmitted() throws Exception {
    mockMvc
        .perform(
            signUp(
                bodyWith(
                    """
                    "nickname": "  ", "name": "", "phone": "", "gender": "", "birthDate": null""")))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.nickname").value(org.hamcrest.Matchers.nullValue()));

    User saved = savedMember();
    assertThat(saved.getNickname()).isNull();
    assertThat(saved.getName()).isNull();
    assertThat(saved.getPhone()).isNull();
    assertThat(saved.getGender()).isNull();
  }

  @Test
  void signUp_allowsTheSamePhoneAndNicknameForDifferentMembers() throws Exception {
    String profile = "\"nickname\": \"미러\", \"phone\": \"01012345678\"";
    mockMvc.perform(signUp(bodyWith(profile))).andExpect(status().isCreated());
    mockMvc
        .perform(
            signUp(
                """
                {"email": "other@example.com", "password": "%s", "passwordConfirm": "%s", %s,
                 "agreements": %s}"""
                    .formatted(PASSWORD, PASSWORD, profile, SignUpRequests.AGREEMENTS_JSON)))
        .andExpect(status().isCreated());
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "\"nickname\": \"가\"|nickname",
        "\"nickname\": \"미러!\"|nickname",
        "\"name\": \"홍길동1\"|name",
        "\"phone\": \"02-1234-5678\"|phone",
        "\"gender\": \"OTHER\"|gender"
      })
  void signUp_withInvalidOptionalField_returns400WithFieldName(String caseSpec) throws Exception {
    String[] parts = caseSpec.split("\\|");
    mockMvc
        .perform(signUp(bodyWith(parts[0])))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value(parts[1]));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @Test
  void signUp_withUnparsableBirthDate_returns400WithBirthDateField() throws Exception {
    mockMvc
        .perform(signUp(bodyWith("\"birthDate\": \"2000-13-45\"")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("birthDate"));
    mockMvc
        .perform(signUp(bodyWith("\"birthDate\": \"abc\"")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("birthDate"));
  }

  @Test
  void signUp_withFutureBirthDate_returns400() throws Exception {
    mockMvc
        .perform(signUp(bodyWith("\"birthDate\": \"2999-01-01\"")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("birthDate"));
  }

  @Test
  void signUp_withUnder14BirthDate_returns400() throws Exception {
    String recent = java.time.LocalDate.now().minusYears(10).toString();
    mockMvc
        .perform(signUp(bodyWith("\"birthDate\": \"" + recent + "\"")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("birthDate"));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @Test
  void malformedJson_stillReportsBodyField() throws Exception {
    mockMvc
        .perform(signUp("{\"email\": "))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("body"));
  }

  // ---- 약관 동의 ----

  private List<UserAgreement> savedAgreements() {
    return userAgreementRepository.findByUserId(savedMember().getId());
  }

  @Test
  void signUp_storesEveryAgreementWithTypeVersionAndTime() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.agreements").doesNotExist());

    assertThat(savedAgreements())
        .extracting(a -> a.getType().name(), UserAgreement::getVersion, UserAgreement::isAgreed)
        .containsExactlyInAnyOrder(
            tuple("TERMS", "2026-10-26", true),
            tuple("PRIVACY", "2026-10-26", true),
            tuple("AGE_OVER_14", "2026-10-26", true),
            tuple("MARKETING", "2026-10-26", false));
    assertThat(savedAgreements()).allSatisfy(a -> assertThat(a.getAgreedAt()).isNotNull());
  }

  @Test
  void signUp_withoutMarketing_storesOnlyRequiredAgreements() throws Exception {
    String required =
        "[%s, %s, %s]"
            .formatted(
                agreement("TERMS", "2026-10-26", true),
                agreement("PRIVACY", "2026-10-26", true),
                agreement("AGE_OVER_14", "2026-10-26", true));
    mockMvc.perform(signUp(bodyWithAgreements(required))).andExpect(status().isCreated());

    assertThat(savedAgreements())
        .extracting(a -> a.getType().name())
        .containsExactlyInAnyOrder("TERMS", "PRIVACY", "AGE_OVER_14");
  }

  @Test
  void signUp_withMarketingAgreed_storesItAsAgreed() throws Exception {
    String all =
        "[%s, %s, %s, %s]"
            .formatted(
                agreement("TERMS", "2026-10-26", true),
                agreement("PRIVACY", "2026-10-26", true),
                agreement("AGE_OVER_14", "2026-10-26", true),
                agreement("MARKETING", "2026-10-26", true));
    mockMvc.perform(signUp(bodyWithAgreements(all))).andExpect(status().isCreated());

    assertThat(savedAgreements())
        .filteredOn(a -> a.getType() == AgreementType.MARKETING)
        .singleElement()
        .satisfies(a -> assertThat(a.isAgreed()).isTrue());
  }

  @Test
  void signUp_marketingVersionIsNotCheckedAgainstTheServerVersion() throws Exception {
    String withOldMarketing =
        "[%s, %s, %s, %s]"
            .formatted(
                agreement("TERMS", "2026-10-26", true),
                agreement("PRIVACY", "2026-10-26", true),
                agreement("AGE_OVER_14", "2026-10-26", true),
                agreement("MARKETING", "old-version", true));
    mockMvc.perform(signUp(bodyWithAgreements(withOldMarketing))).andExpect(status().isCreated());

    assertThat(savedAgreements())
        .filteredOn(a -> a.getType() == AgreementType.MARKETING)
        .singleElement()
        .satisfies(a -> assertThat(a.getVersion()).isEqualTo("old-version"));
  }

  @ParameterizedTest
  @ValueSource(strings = {"TERMS", "PRIVACY", "AGE_OVER_14"})
  void signUp_withARequiredAgreementMissing_returns400WithThatType(String missing)
      throws Exception {
    String others =
        java.util.stream.Stream.of("TERMS", "PRIVACY", "AGE_OVER_14")
            .filter(t -> !t.equals(missing))
            .map(t -> agreement(t, "2026-10-26", true))
            .collect(java.util.stream.Collectors.joining(", ", "[", "]"));

    mockMvc
        .perform(signUp(bodyWithAgreements(others)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_REQUIRED_AGREEMENT_MISSING"))
        .andExpect(jsonPath("$.details.length()").value(1))
        .andExpect(jsonPath("$.details[0].field").value("agreements." + missing));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @ParameterizedTest
  @ValueSource(strings = {"TERMS", "PRIVACY", "AGE_OVER_14"})
  void signUp_withARequiredAgreementDeclined_returns400WithThatType(String declined)
      throws Exception {
    String list =
        java.util.stream.Stream.of("TERMS", "PRIVACY", "AGE_OVER_14")
            .map(t -> agreement(t, "2026-10-26", !t.equals(declined)))
            .collect(java.util.stream.Collectors.joining(", ", "[", "]"));

    mockMvc
        .perform(signUp(bodyWithAgreements(list)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_REQUIRED_AGREEMENT_MISSING"))
        .andExpect(jsonPath("$.details[0].field").value("agreements." + declined));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @Test
  void signUp_withStaleVersion_returns400() throws Exception {
    String stale =
        "[%s, %s, %s]"
            .formatted(
                agreement("TERMS", "2025-01-01", true),
                agreement("PRIVACY", "2026-10-26", true),
                agreement("AGE_OVER_14", "2026-10-26", true));

    mockMvc
        .perform(signUp(bodyWithAgreements(stale)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_REQUIRED_AGREEMENT_MISSING"))
        .andExpect(jsonPath("$.details[0].field").value("agreements.TERMS"));
  }

  @Test
  void signUp_withEmptyAgreements_listsEveryRequiredAgreement() throws Exception {
    mockMvc
        .perform(signUp(bodyWithAgreements("[]")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_REQUIRED_AGREEMENT_MISSING"))
        .andExpect(
            jsonPath("$.details[*].field")
                .value(
                    org.hamcrest.Matchers.containsInAnyOrder(
                        "agreements.TERMS", "agreements.PRIVACY", "agreements.AGE_OVER_14")));
  }

  @Test
  void signUp_withoutAgreementsField_returnsValidationFailed() throws Exception {
    mockMvc
        .perform(
            signUp(
                """
                {"email": "member@example.com", "password": "%s", "passwordConfirm": "%s"}"""
                    .formatted(PASSWORD, PASSWORD)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("agreements"));
    mockMvc
        .perform(signUp(bodyWithAgreements("null")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void signUp_withUnknownAgreementType_returnsValidationFailedWithPath() throws Exception {
    String unknown =
        "[%s, %s, %s, %s]"
            .formatted(
                agreement("TERMS", "2026-10-26", true),
                agreement("PRIVACY", "2026-10-26", true),
                agreement("AGE_OVER_14", "2026-10-26", true),
                agreement("NEWSLETTER", "2026-10-26", true));

    mockMvc
        .perform(signUp(bodyWithAgreements(unknown)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("agreements[3].type"));
  }

  @Test
  void signUp_withDuplicateAgreementType_returnsValidationFailed() throws Exception {
    String duplicate =
        "[%s, %s, %s, %s]"
            .formatted(
                agreement("TERMS", "2026-10-26", true),
                agreement("TERMS", "2026-10-26", true),
                agreement("PRIVACY", "2026-10-26", true),
                agreement("AGE_OVER_14", "2026-10-26", true));

    mockMvc
        .perform(signUp(bodyWithAgreements(duplicate)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("agreements"));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @Test
  void signUp_withMalformedAgreementItem_returnsValidationFailedWithPath() throws Exception {
    mockMvc
        .perform(signUp(bodyWithAgreements("[{\"type\": \"TERMS\", \"version\": \"2026-10-26\"}]")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("agreements[0].agreed"));
    mockMvc
        .perform(signUp(bodyWithAgreements("[null]")))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void signUp_reportsEveryProblemAgreementAtOnce() throws Exception {
    String bad =
        "[%s, %s]"
            .formatted(
                agreement("TERMS", "2026-10-26", false), agreement("PRIVACY", "2025-01-01", true));

    mockMvc
        .perform(signUp(bodyWithAgreements(bad)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("USERS_REQUIRED_AGREEMENT_MISSING"))
        .andExpect(
            jsonPath("$.details[*].field")
                .value(
                    org.hamcrest.Matchers.containsInAnyOrder(
                        "agreements.TERMS", "agreements.PRIVACY", "agreements.AGE_OVER_14")));
  }

  // ---- 409 ----

  @Test
  void signUp_withExistingEmail_returns409() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated());

    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_DUPLICATE"));
  }

  @Test
  void signUp_withEmailDifferingOnlyByCaseAndSpaces_returns409() throws Exception {
    mockMvc
        .perform(signUp(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isCreated());

    mockMvc
        .perform(signUp(body("  MEMBER@Example.com ", PASSWORD, PASSWORD)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("USERS_EMAIL_DUPLICATE"));
  }

  // ---- 415 ----

  @Test
  void signUp_withNonJsonContentType_returns415() throws Exception {
    mockMvc
        .perform(
            post("/v1/users/signup")
                .header("Origin", ORIGIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content("x"))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"));
  }

  // ---- 허용 Origin ----

  @Test
  void signUp_withoutOrigin_returns403() throws Exception {
    mockMvc
        .perform(
            post("/v1/users/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  @Test
  void signUp_withDisallowedOrigins_returns403() throws Exception {
    for (String origin :
        new String[] {
          "https://evil.com",
          "null",
          "http://localhost:3001",
          "https://localhost:3000",
          "http://localhost:3000.evil.com"
        }) {
      mockMvc
          .perform(
              post("/v1/users/signup")
                  .header("Origin", origin)
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(body("member@example.com", PASSWORD, PASSWORD)))
          .andExpect(status().isForbidden())
          .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }

  // ---- 열어 준 범위는 가입 경로 하나뿐 ----

  @Test
  void otherEndpoints_stillRequireLogin() throws Exception {
    mockMvc.perform(get("/v1/any")).andExpect(status().isUnauthorized());
    mockMvc.perform(get("/v1/users")).andExpect(status().isUnauthorized());
    mockMvc.perform(get("/v1/users/" + UUID.randomUUID())).andExpect(status().isUnauthorized());
    mockMvc.perform(get("/v1/users/signup")).andExpect(status().isUnauthorized());
  }

  @Test
  void csrfExemption_isLimitedToPostOnTheSignUpPath() throws Exception {
    // 같은 경로의 다른 메서드, 하위 경로의 POST 는 여전히 CSRF 토큰이 필요하다 (토큰 없음 → 403)
    mockMvc
        .perform(
            put("/v1/users/signup")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isForbidden());
    mockMvc
        .perform(
            post("/v1/users/anything")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isForbidden());
  }

  @Test
  void oldSignUpPath_isNoLongerOpen() throws Exception {
    // 구 경로 POST /v1/users 는 공개도 CSRF 제외도 아니므로 가입되지 않는다 (CSRF 필터가 먼저 막아 403)
    mockMvc
        .perform(
            post("/v1/users")
                .header("Origin", ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body("member@example.com", PASSWORD, PASSWORD)))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
    assertThat(userRepository.existsByEmail("member@example.com")).isFalse();
  }
}
