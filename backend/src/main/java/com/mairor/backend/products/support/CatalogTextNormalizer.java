package com.mairor.backend.products.support;

import java.text.Normalizer;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

/**
 * 카탈로그 텍스트(브랜드·제품명·호수명)를 중복 판정과 검색에 쓰는 비교용 키로 바꾼다. 화면에 보여주는 원문은 바꾸지 않고, 엔티티가 원문과 이 값을 함께 저장한다.
 *
 * <p>순서: NFC 정규화 → 유니코드 공백(NBSP·전각 공백·탭 등) 연속을 한 칸으로 축약 → 앞뒤 공백 제거 → {@link Locale#ROOT} 소문자화.
 * {@link String#strip()}은 NBSP 를 공백으로 보지 않아서, 공백 판정은 유니코드 {@code White_Space} 기준 정규식으로 한다.
 *
 * <p>SQL 시드(db/seed)의 정규화 컬럼도 이 규칙으로 계산한 값을 직접 적는다. 시드와 이 규칙이 어긋나면 {@code ProductSeedSqlTest}가
 * 실패한다.
 */
public final class CatalogTextNormalizer {

  private static final Pattern WHITESPACE_RUN =
      Pattern.compile("\\s+", Pattern.UNICODE_CHARACTER_CLASS);

  private CatalogTextNormalizer() {}

  /**
   * @throws NullPointerException 값이 {@code null}이면
   * @throws IllegalArgumentException 정규화 결과가 빈 문자열이면 (빈 값·공백만 있는 값)
   */
  public static String normalize(String text) {
    Objects.requireNonNull(text, "text");
    String composed = Normalizer.normalize(text, Normalizer.Form.NFC);
    String collapsed = WHITESPACE_RUN.matcher(composed).replaceAll(" ").strip();
    if (collapsed.isEmpty()) {
      throw new IllegalArgumentException("정규화하면 빈 문자열이 되는 값은 쓸 수 없다");
    }
    return collapsed.toLowerCase(Locale.ROOT);
  }
}
