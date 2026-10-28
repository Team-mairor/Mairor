package com.mairor.backend.users.support;

/**
 * 휴대폰 번호 정규화: 하이픈과 공백을 제거한다. 형식 검증은 요청 DTO 가 정규화한 값에 대해 한다. 공백뿐이거나 빈 값은 {@code null}.
 *
 * <p>국가번호(+82)는 받지 않는다. 국내 번호 10~11자리만 저장한다.
 */
public final class PhoneNormalizer {

  private PhoneNormalizer() {}

  public static String normalize(String phone) {
    if (phone == null) {
      return null;
    }
    String digits = phone.replaceAll("[\\s-]", "");
    return digits.isEmpty() ? null : digits;
  }
}
