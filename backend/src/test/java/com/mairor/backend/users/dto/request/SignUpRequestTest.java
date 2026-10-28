package com.mairor.backend.users.dto.request;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.users.SignUpRequests;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.text.Normalizer;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class SignUpRequestTest {

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

  private static SignUpRequest request(String email, String password) {
    return SignUpRequests.basic(email, password, password);
  }

  private static Set<ConstraintViolation<SignUpRequest>> violations(SignUpRequest request) {
    return validator.validate(request);
  }

  private static List<String> messages(SignUpRequest request, String field) {
    return violations(request).stream()
        .filter(v -> v.getPropertyPath().toString().equals(field))
        .map(ConstraintViolation::getMessage)
        .collect(Collectors.toList());
  }

  // ---- 이메일 ----

  @Test
  void validRequest_hasNoViolations() {
    assertThat(violations(request("member@example.com", "ExampleOnly!2026"))).isEmpty();
  }

  @Test
  void email_isNormalizedBeforeValidation() {
    SignUpRequest request = request("  Member@Example.COM ", "ExampleOnly!2026");

    assertThat(request.email()).isEqualTo("member@example.com");
    assertThat(violations(request)).isEmpty();
  }

  @ParameterizedTest
  @ValueSource(strings = {"plain", "a@b", "@example.com", "member@", "mem ber@example.com"})
  void email_withInvalidFormat_isRejected(String email) {
    assertThat(messages(request(email, "ExampleOnly!2026"), "email")).contains("올바른 이메일 형식이 아닙니다.");
  }

  @ParameterizedTest
  @ValueSource(strings = {"", "   "})
  void email_blank_isRejected(String email) {
    assertThat(messages(request(email, "ExampleOnly!2026"), "email")).contains("필수 값입니다.");
  }

  @Test
  void email_null_isRejected() {
    assertThat(messages(request(null, "ExampleOnly!2026"), "email")).contains("필수 값입니다.");
  }

  @Test
  void email_lengthLimitAppliesAfterTrimming() {
    // 앞뒤 공백을 빼면 254자: 통과, 공백을 빼도 255자: 거절
    String domain = "@" + "b".repeat(60) + "." + "c".repeat(60) + "." + "d".repeat(60) + ".com";
    String atLimit = "a".repeat(254 - domain.length()) + domain;
    String overLimit = "a" + atLimit;

    assertThat(atLimit).hasSize(254);
    assertThat(messages(request("  " + atLimit + "  ", "ExampleOnly!2026"), "email"))
        .doesNotContain("254자 이하여야 합니다.");
    assertThat(messages(request(overLimit, "ExampleOnly!2026"), "email"))
        .contains("254자 이하여야 합니다.");
  }

  // ---- 비밀번호 길이 ----

  @Test
  void password_lengthBounds() {
    assertThat(messages(request("member@example.com", "abcdef1"), "password"))
        .contains("8자 이상 64자 이하여야 합니다.");
    assertThat(messages(request("member@example.com", "abcdef1!"), "password")).isEmpty();
    assertThat(messages(request("member@example.com", "a1!" + "x".repeat(61)), "password"))
        .isEmpty();
    assertThat(messages(request("member@example.com", "a1!" + "x".repeat(62)), "password"))
        .contains("8자 이상 64자 이하여야 합니다.");
  }

  @Test
  void password_null_isRejected() {
    assertThat(messages(SignUpRequests.basic("member@example.com", null, "x"), "password"))
        .containsExactly("필수 값입니다.");
  }

  @Test
  void passwordConfirm_null_isRejected() {
    assertThat(
            messages(
                SignUpRequests.basic("member@example.com", "ExampleOnly!2026", null),
                "passwordConfirm"))
        .containsExactly("필수 값입니다.");
  }

  // ---- 비밀번호 구성 ----

  @Test
  void password_withoutLetter_isRejected() {
    assertThat(messages(request("member@example.com", "12345678!"), "password"))
        .containsExactly("영문자를 1개 이상 포함해야 합니다.");
  }

  @Test
  void password_withoutDigit_isRejected() {
    assertThat(messages(request("member@example.com", "abcdefgh!"), "password"))
        .containsExactly("숫자를 1개 이상 포함해야 합니다.");
  }

  @Test
  void password_withoutSymbol_isRejected() {
    assertThat(messages(request("member@example.com", "abcdefg1"), "password"))
        .containsExactly("특수문자(!@#$ 등 ASCII 기호)를 1개 이상 포함해야 합니다.");
  }

  @Test
  void password_reportsEveryMissingRule() {
    assertThat(messages(request("member@example.com", "가나다라마바사아"), "password")).hasSize(3);
  }

  @Test
  void password_koreanLetterAndEmojiAreNotSymbols() {
    assertThat(messages(request("member@example.com", "abcdef1가"), "password"))
        .containsExactly("특수문자(!@#$ 등 ASCII 기호)를 1개 이상 포함해야 합니다.");
    assertThat(messages(request("member@example.com", "abcdef1😀"), "password"))
        .containsExactly("특수문자(!@#$ 등 ASCII 기호)를 1개 이상 포함해야 합니다.");
    assertThat(messages(request("member@example.com", "abcdef1 "), "password"))
        .containsExactly("특수문자(!@#$ 등 ASCII 기호)를 1개 이상 포함해야 합니다.");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {"!", "\"", "#", "$", "%", "&", "'", "(", ")", "*", "+", ",", "-", ".", "/"})
  void password_acceptsAsciiSymbols(String symbol) {
    assertThat(messages(request("member@example.com", "abcdef1" + symbol), "password")).isEmpty();
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        ":", ";", "<", "=", ">", "?", "@", "[", "\\", "]", "^", "_", "`", "{", "|", "}", "~"
      })
  void password_acceptsRemainingAsciiSymbols(String symbol) {
    assertThat(messages(request("member@example.com", "abcdef1" + symbol), "password")).isEmpty();
  }

  @Test
  void password_doesNotRequireUppercase() {
    assertThat(messages(request("member@example.com", "abcdef1!"), "password")).isEmpty();
    assertThat(messages(request("member@example.com", "ABCDEF1!"), "password")).isEmpty();
  }

  @Test
  void password_allowsUnicodeAlongsideRequiredCharacters() {
    assertThat(messages(request("member@example.com", "비밀번호abc1!"), "password")).isEmpty();
  }

  // ---- 72바이트 ----

  @Test
  void password_utf8ByteLimit() {
    // "가" 는 3바이트. 23글자(69) + "a1!"(3) = 72바이트: 통과, 24글자(72) + 3 = 75바이트: 거절
    String atLimit = "가".repeat(23) + "a1!";
    String overLimit = "가".repeat(24) + "a1!";

    assertThat(messages(request("member@example.com", atLimit), "password")).isEmpty();
    assertThat(messages(request("member@example.com", overLimit), "password"))
        .containsExactly("UTF-8 기준 72바이트를 넘을 수 없습니다. 한글 등은 글자당 3바이트로 계산됩니다.");
  }

  @Test
  void password_byteLimitIsMeasuredAfterNfcNormalization() {
    // 조합형(NFD) 한글 13글자는 78바이트지만 완성형(NFC)으로는 39바이트
    String decomposed = Normalizer.normalize("가나다라마바사아자차카타파", Normalizer.Form.NFD) + "a1!";

    assertThat(decomposed.getBytes(java.nio.charset.StandardCharsets.UTF_8).length)
        .isGreaterThan(72);
    assertThat(messages(request("member@example.com", decomposed), "password")).isEmpty();
  }

  // ---- 노출 방지 ----

  @Test
  void toString_masksPasswords() {
    String text =
        SignUpRequests.basic("Member@Example.com", "ExampleOnly!2026", "ExampleOnly!2026")
            .toString();

    assertThat(text).contains("member@example.com").doesNotContain("ExampleOnly");
  }

  // ---- 선택 필드 ----

  private static SignUpRequest withProfile(
      String nickname, String name, String phone, String birthDate, String gender) {
    return new SignUpRequest(
        "member@example.com",
        "ExampleOnly!2026",
        "ExampleOnly!2026",
        nickname,
        name,
        phone,
        birthDate == null ? null : LocalDate.parse(birthDate),
        gender,
        SignUpRequests.requiredAgreements(),
        null);
  }

  @Test
  void emailVerificationToken_isTrimmedBlankIsNull_andMasked() {
    SignUpRequest withToken =
        SignUpRequests.withToken(
            "member@example.com", "ExampleOnly!2026", "ExampleOnly!2026", " tok-123 ");
    SignUpRequest blank =
        SignUpRequests.withToken(
            "member@example.com", "ExampleOnly!2026", "ExampleOnly!2026", "   ");

    assertThat(withToken.emailVerificationToken()).isEqualTo("tok-123");
    assertThat(blank.emailVerificationToken()).isNull();
    assertThat(withToken.toString()).doesNotContain("tok-123");
  }

  @Test
  void emailVerificationToken_overTheLengthLimit_isRejected() {
    SignUpRequest request =
        SignUpRequests.withToken(
            "member@example.com", "ExampleOnly!2026", "ExampleOnly!2026", "t".repeat(201));

    assertThat(messages(request, "emailVerificationToken")).contains("200자 이하여야 합니다.");
  }

  @Test
  void profile_allOmitted_hasNoViolations() {
    assertThat(violations(withProfile(null, null, null, null, null))).isEmpty();
  }

  @Test
  void profile_blankValuesAreTreatedAsOmitted() {
    SignUpRequest request = withProfile("   ", "", " - ", null, "  ");

    assertThat(request.nickname()).isNull();
    assertThat(request.name()).isNull();
    assertThat(request.phone()).isNull();
    assertThat(request.gender()).isNull();
    assertThat(violations(request)).isEmpty();
  }

  @Test
  void nickname_isTrimmedAndLengthChecked() {
    assertThat(withProfile("  미러  ", null, null, null, null).nickname()).isEqualTo("미러");
    assertThat(messages(withProfile("가", null, null, null, null), "nickname"))
        .contains("2자 이상 20자 이하여야 합니다.");
    assertThat(messages(withProfile("가나", null, null, null, null), "nickname")).isEmpty();
    assertThat(messages(withProfile("a".repeat(20), null, null, null, null), "nickname")).isEmpty();
    assertThat(messages(withProfile("a".repeat(21), null, null, null, null), "nickname"))
        .contains("2자 이상 20자 이하여야 합니다.");
  }

  @ParameterizedTest
  @ValueSource(strings = {"미 러", "미러!", "mirror-1", "미러😀", "미러@"})
  void nickname_withDisallowedCharacters_isRejected(String nickname) {
    assertThat(messages(withProfile(nickname, null, null, null, null), "nickname"))
        .contains("한글, 영문, 숫자, 밑줄(_)만 사용할 수 있습니다.");
  }

  @Test
  void nickname_allowsHangulLettersDigitsAndUnderscore() {
    assertThat(messages(withProfile("미러_Mirror01", null, null, null, null), "nickname")).isEmpty();
  }

  @Test
  void name_lengthAndCharacters() {
    assertThat(messages(withProfile(null, "홍길동", null, null, null), "name")).isEmpty();
    assertThat(messages(withProfile(null, "Hong Gil Dong", null, null, null), "name")).isEmpty();
    assertThat(messages(withProfile(null, "홍", null, null, null), "name"))
        .contains("2자 이상 50자 이하여야 합니다.");
    assertThat(messages(withProfile(null, "가".repeat(51), null, null, null), "name"))
        .contains("2자 이상 50자 이하여야 합니다.");
    assertThat(messages(withProfile(null, "홍길동1", null, null, null), "name"))
        .contains("한글, 영문, 공백만 사용할 수 있습니다.");
    assertThat(messages(withProfile(null, "홍_길동", null, null, null), "name"))
        .contains("한글, 영문, 공백만 사용할 수 있습니다.");
  }

  @ParameterizedTest
  @ValueSource(strings = {"010-1234-5678", "01012345678", "010 1234 5678", "011-123-4567"})
  void phone_validNumbers_areAccepted(String phone) {
    SignUpRequest request = withProfile(null, null, phone, null, null);

    assertThat(request.phone()).matches("\\d{10,11}");
    assertThat(messages(request, "phone")).isEmpty();
  }

  @Test
  void phone_isNormalizedToDigits() {
    assertThat(withProfile(null, null, "010-1234-5678", null, null).phone())
        .isEqualTo("01012345678");
    assertThat(withProfile(null, null, " 010 123 4567 ", null, null).phone())
        .isEqualTo("0101234567");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "02-1234-5678",
        "010-123-456",
        "010-12345-67890",
        "+82-10-1234-5678",
        "abc",
        "010-12a4-5678"
      })
  void phone_withInvalidFormat_isRejected(String phone) {
    assertThat(messages(withProfile(null, null, phone, null, null), "phone"))
        .contains("올바른 휴대폰 번호 형식이 아닙니다.");
  }

  @Test
  void gender_acceptsOnlyMaleOrFemale() {
    assertThat(messages(withProfile(null, null, null, null, "MALE"), "gender")).isEmpty();
    assertThat(messages(withProfile(null, null, null, null, "FEMALE"), "gender")).isEmpty();
    assertThat(messages(withProfile(null, null, null, null, "OTHER"), "gender"))
        .contains("MALE 또는 FEMALE 이어야 합니다.");
    assertThat(messages(withProfile(null, null, null, null, "male"), "gender"))
        .contains("MALE 또는 FEMALE 이어야 합니다.");
  }

  @Test
  void toString_masksPersonalInformation() {
    String text = withProfile("미러", "홍길동", "01012345678", "2000-01-15", "FEMALE").toString();

    assertThat(text)
        .contains("member@example.com")
        .doesNotContain("미러", "홍길동", "01012345678", "2000-01-15", "FEMALE");
  }
}
