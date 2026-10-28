package com.mairor.backend.users.support;

import java.text.Normalizer;

/**
 * 선택 입력(닉네임·이름 등)의 공통 정규화: 앞뒤 공백을 제거하고 완성형(NFC)으로 맞춘다. 공백뿐이거나 빈 값은 {@code null}(입력 안 함)로 본다.
 *
 * <p>FE 폼이 비워 둔 칸을 {@code ""}로 보내도 선택 필드로 처리하기 위해서다.
 */
public final class TextNormalizer {

  private TextNormalizer() {}

  public static String stripToNull(String value) {
    if (value == null) {
      return null;
    }
    String stripped = Normalizer.normalize(value, Normalizer.Form.NFC).strip();
    return stripped.isEmpty() ? null : stripped;
  }
}
