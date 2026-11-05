package com.mairor.backend.products.imports;

import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.List;
import java.util.regex.Pattern;

/**
 * 수집한 상품명·호수명에서 판매 표시를 정리한다. 지우는 것은 **조사에서 확인한 문구와 전체가 일치할 때만**이다. 문구에 어떤 키워드가 들어 있다는 이유로 지우지 않는다.
 * 새 문구는 조사에서 확인한 뒤 이 목록에 추가한다.
 *
 * <ul>
 *   <li>상품명: 앞뒤의 {@code [NEW]}·{@code [BEST]}·{@code [HOT]}. 세트·1+1·기획·증정·리필·용량·리뉴얼 표기는 다른 상품이라 지우지
 *       않는다.
 *   <li>호수명: 앞쪽 {@code [NEW]}·{@code [BEST]}·{@code [HOT]}·{@code [공식몰 단독]}·{@code [일반]}·{@code
 *       [CU콜라보]}와 뒤쪽 {@code +추가N종증정}. 글자가 하나라도 더 붙은 {@code [한정 매트]}·{@code [리필]}, 모든 소괄호, 숫자가 뒤따르는
 *       {@code +}({@code 01+02})는 지우지 않는다.
 * </ul>
 *
 * 화면에 보이는 원문은 바꾸지 않는다. 호수는 {@link #shadeComparisonKey}로 만든 비교 키만 정리한 이름에서 계산한다.
 */
public final class CatalogNameCleaner {

  private static final List<String> PRODUCT_BADGES = List.of("[NEW]", "[BEST]", "[HOT]");

  private static final List<String> SHADE_LEADING_PHRASES =
      List.of("[NEW]", "[BEST]", "[HOT]", "[공식몰 단독]", "[일반]", "[CU콜라보]");

  /** 호수명 뒤쪽 {@code +추가N종증정}. {@code N}은 숫자이고, 앞의 공백만 함께 지운다. */
  private static final Pattern SHADE_TRAILING_GIFT =
      Pattern.compile("\\s*\\+추가[0-9]+종증정$", Pattern.UNICODE_CHARACTER_CLASS);

  private CatalogNameCleaner() {}

  /**
   * 상품명 앞뒤의 판매 배지를 지운다. 배지만 있는 이름이면 지우지 않고 앞뒤 공백만 지운 원래 이름을 돌려준다(빈 이름을 만들지 않는다).
   *
   * @return 앞뒤 공백을 지운 이름
   */
  public static String cleanProductName(String name) {
    String original = CatalogTextNormalizer.trimmed(name);
    String current = original;
    boolean changed = true;
    while (changed) {
      changed = false;
      for (String badge : PRODUCT_BADGES) {
        if (current.startsWith(badge)) {
          current = CatalogTextNormalizer.trimmed(current.substring(badge.length()));
          changed = true;
        }
        if (current.endsWith(badge)) {
          current =
              CatalogTextNormalizer.trimmed(
                  current.substring(0, current.length() - badge.length()));
          changed = true;
        }
      }
    }
    return current.isEmpty() ? original : current;
  }

  /** 호수명에서 확인된 판매 표시를 지운 이름. 지울 것이 없으면 앞뒤 공백만 지운 이름이다. 모두 지워져 빈 이름이 되면 지우지 않은 이름을 돌려준다. */
  public static String cleanShadeName(String shadeName) {
    String original = CatalogTextNormalizer.trimmed(shadeName);
    String current = original;
    boolean changed = true;
    while (changed) {
      changed = false;
      for (String phrase : SHADE_LEADING_PHRASES) {
        if (current.startsWith(phrase)) {
          current = CatalogTextNormalizer.trimmed(current.substring(phrase.length()));
          changed = true;
        }
      }
    }
    current = CatalogTextNormalizer.trimmed(SHADE_TRAILING_GIFT.matcher(current).replaceFirst(""));
    return current.isEmpty() ? original : current;
  }

  /** 이 호수명에 지울 수 있는 확인된 문구가 있는가. 같은 비교 키의 옵션 중 대표를 고를 때, 지울 문구가 없는 옵션을 우선한다. */
  public static boolean hasRemovablePhrase(String shadeName) {
    return !cleanShadeName(shadeName).equals(CatalogTextNormalizer.trimmed(shadeName));
  }

  /**
   * 호수 비교 키. 확인된 판매 표시를 지운 이름을 {@link CatalogTextNormalizer#normalize 정규화}한 값이다. 호수 판정과 파우치·영상 제품의
   * 호수 일치가 이 키를 함께 쓴다.
   *
   * @throws IllegalArgumentException 이름이 비어 있으면
   */
  public static String shadeComparisonKey(String shadeName) {
    return CatalogTextNormalizer.normalize(cleanShadeName(shadeName));
  }
}
