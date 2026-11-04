package com.mairor.backend.pouch.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

/** 개인 항목에 복사한 색상. 색이 없으면 이 객체 자체가 null이다. */
@Embeddable
public class PouchColor {

  public enum Source {
    CATALOG,
    USER_INPUT
  }

  private static final Pattern HEX = Pattern.compile("^#[0-9A-Fa-f]{6}$");

  @Column(name = "color_hex", length = 7)
  private String hex;

  @Enumerated(EnumType.STRING)
  @Column(name = "color_source", length = 20)
  private Source source;

  @Column(name = "color_estimated")
  private boolean estimated;

  protected PouchColor() {}

  private PouchColor(String hex, Source source, boolean estimated) {
    if (hex == null || !HEX.matcher(hex).matches()) {
      throw new IllegalArgumentException("색상은 #RRGGBB 형식이어야 한다");
    }
    this.hex = hex.toUpperCase(Locale.ROOT);
    this.source = source;
    this.estimated = estimated;
  }

  public static PouchColor catalog(String hex, boolean estimated) {
    return new PouchColor(hex, Source.CATALOG, estimated);
  }

  public static PouchColor userInput(String hex) {
    return new PouchColor(hex, Source.USER_INPUT, true);
  }

  public String getHex() {
    return hex;
  }

  public Source getSource() {
    return source;
  }

  public boolean isEstimated() {
    return estimated;
  }

  @Override
  public boolean equals(Object other) {
    return other instanceof PouchColor color
        && Objects.equals(hex, color.hex)
        && source == color.source
        && estimated == color.estimated;
  }

  @Override
  public int hashCode() {
    return Objects.hash(hex, source, estimated);
  }
}
