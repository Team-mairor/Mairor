package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import java.text.Normalizer;
import org.junit.jupiter.api.Test;

class NormalizerTest {

  @Test
  void email_stripsSurroundingWhitespaceAndLowercases() {
    assertThat(EmailNormalizer.normalize("  Member@Example.COM \t"))
        .isEqualTo("member@example.com");
  }

  @Test
  void email_keepsNull() {
    assertThat(EmailNormalizer.normalize(null)).isNull();
  }

  @Test
  void email_isIndependentOfDefaultLocale() {
    java.util.Locale original = java.util.Locale.getDefault();
    try {
      java.util.Locale.setDefault(java.util.Locale.forLanguageTag("tr-TR"));
      assertThat(EmailNormalizer.normalize("INFO@EXAMPLE.COM")).isEqualTo("info@example.com");
    } finally {
      java.util.Locale.setDefault(original);
    }
  }

  @Test
  void password_composesToNfcAndKeepsWhitespace() {
    String decomposed = Normalizer.normalize("한글 a1!", Normalizer.Form.NFD);

    String normalized = PasswordNormalizer.normalize(decomposed);

    assertThat(normalized).isEqualTo("한글 a1!");
    assertThat(normalized).contains(" ");
  }

  @Test
  void password_keepsNull() {
    assertThat(PasswordNormalizer.normalize(null)).isNull();
  }
}
