package com.mairor.backend.products.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

/**
 * 호수의 대표 색상. 색상이 없으면 호수의 {@code color} 자체가 {@code null}이고 세 컬럼이 모두 NULL 이다 (DB CHECK 가 일부만 채워진 행을
 * 막는다).
 *
 * <p>HEX 는 항상 {@code #RRGGBB} 대문자로 저장한다. 소문자 입력은 여기서 대문자로 바꾸고, DB CHECK 는 대문자만 허용한다.
 *
 * <p>{@code source}는 카탈로그 색상을 어디서 얻었는지 적는 내부 값이다. 값 범위는 미정이고 API 응답에서는 {@code CATALOG}로 내보낸다. TODO:
 * 색상 출처 값 범위 확정.
 */
@Embeddable
public class ShadeColor {

  private static final Pattern HEX = Pattern.compile("^#[0-9A-Fa-f]{6}$");
  static final int SOURCE_MAX_LENGTH = 30;

  @Column(name = "color_hex", length = 7)
  private String hex;

  @Column(name = "color_source", length = SOURCE_MAX_LENGTH)
  private String source;

  @Column(name = "color_estimated")
  private boolean estimated;

  protected ShadeColor() {}

  private ShadeColor(String hex, String source, boolean estimated) {
    this.hex = hex;
    this.source = source;
    this.estimated = estimated;
  }

  /**
   * @param hex {@code #RRGGBB}. 대소문자 무관, 대문자로 바꿔 저장한다
   * @param source 색상 출처 (1~30자)
   * @param estimated 실제 발색 확인 없이 추정한 값이면 true
   */
  public static ShadeColor of(String hex, String source, boolean estimated) {
    Objects.requireNonNull(hex, "hex");
    Objects.requireNonNull(source, "source");
    if (!HEX.matcher(hex).matches()) {
      throw new IllegalArgumentException("색상은 #RRGGBB 형식이어야 한다: " + hex);
    }
    if (source.isBlank() || source.length() > SOURCE_MAX_LENGTH) {
      throw new IllegalArgumentException("색상 출처는 1~" + SOURCE_MAX_LENGTH + "자여야 한다");
    }
    return new ShadeColor(hex.toUpperCase(Locale.ROOT), source, estimated);
  }

  public String getHex() {
    return hex;
  }

  public String getSource() {
    return source;
  }

  public boolean isEstimated() {
    return estimated;
  }

  @Override
  public boolean equals(Object o) {
    return o instanceof ShadeColor other
        && estimated == other.estimated
        && Objects.equals(hex, other.hex)
        && Objects.equals(source, other.source);
  }

  @Override
  public int hashCode() {
    return Objects.hash(hex, source, estimated);
  }
}
