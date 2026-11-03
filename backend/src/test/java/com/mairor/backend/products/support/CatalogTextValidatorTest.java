package com.mairor.backend.products.support;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.text.Normalizer;
import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

/**
 * {@link CatalogText} 규칙을 Bean Validation 으로 직접 검사한다. 상한은 작게(5자) 잡아 경계를 보기 쉽게 한다.
 *
 * <p>공백은 {@link CatalogTextNormalizer}와 같은 유니코드 기준이고, 길이는 앞뒤 공백을 지운 원문(NFC 전)의 {@link
 * String#length()}다.
 */
class CatalogTextValidatorTest {

  private static final String NBSP = Character.toString(0x00A0);
  private static final String IDEOGRAPHIC_SPACE = Character.toString(0x3000);

  record Holder(@CatalogText(max = 5) String text) {}

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

  private static Set<ConstraintViolation<Holder>> validate(String text) {
    return validator.validate(new Holder(text));
  }

  private static String messageOf(String text) {
    Set<ConstraintViolation<Holder>> violations = validate(text);
    assertThat(violations).hasSize(1);
    return violations.iterator().next().getMessage();
  }

  static Stream<String> blankTexts() {
    return Stream.of("", " ", "\t\n", NBSP, NBSP + IDEOGRAPHIC_SPACE + NBSP);
  }

  @ParameterizedTest
  @MethodSource("blankTexts")
  void blankIncludingUnicodeWhitespaceOnlyIsRequiredError(String text) {
    assertThat(messageOf(text)).isEqualTo(CatalogTextValidator.REQUIRED);
  }

  @Test
  void nullIsRequiredError() {
    assertThat(messageOf(null)).isEqualTo(CatalogTextValidator.REQUIRED);
  }

  @Test
  void lengthIsCountedAfterRemovingLeadingAndTrailingWhitespace() {
    assertThat(validate("abcde")).isEmpty();
    assertThat(validate("  abcde  ")).isEmpty();
    assertThat(messageOf("abcdef")).isEqualTo("5자 이하여야 합니다.");
  }

  @Test
  void nbspAroundTheTextIsNotCountedButNbspInsideIs() {
    assertThat(validate(NBSP + IDEOGRAPHIC_SPACE + "abcde" + NBSP)).isEmpty();
    assertThat(validate("ab" + NBSP + "cd")).isEmpty();
    assertThat(messageOf("abc" + NBSP + "de")).isEqualTo("5자 이하여야 합니다.");
  }

  @Test
  void surrogatePairCountsAsTwoLikeTheEntityLimit() {
    String emoji = new String(Character.toChars(0x1F484));

    assertThat(emoji).hasSize(2);
    assertThat(validate("abc" + emoji)).isEmpty();
    assertThat(messageOf("abcd" + emoji)).isEqualTo("5자 이하여야 합니다.");
  }

  @Test
  void lengthIsCountedBeforeNfc() {
    // U+0344 는 NFC 를 거치면 두 글자로 늘어난다. 원문 기준이면 5자라 통과한다
    String text = "abcd̈́";

    assertThat(Normalizer.normalize(text, Normalizer.Form.NFC)).hasSize(6);
    assertThat(validate(text)).isEmpty();
  }
}
