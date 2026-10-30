package com.mairor.backend.users.support;

import java.util.Locale;

/**
 * User-Agent 를 "브라우저 · 운영체제" 한 줄로 줄인다 (예: {@code Chrome · Windows}). 로그인 기기 목록에 보여 주는 용도라 정확한 판별이
 * 아니라 사람이 알아볼 정도면 된다.
 *
 * <p>고정된 이름만 돌려주고 User-Agent 원문은 담지 않는다. 원문은 길이가 제각각이고 임의의 문자가 들어올 수 있어서 저장·출력에 쓰지 않는다. 판별하지 못하면
 * {@link #UNKNOWN}.
 */
public final class DeviceSummary {

  public static final String UNKNOWN = "알 수 없는 기기";

  private DeviceSummary() {}

  public static String of(String userAgent) {
    if (userAgent == null || userAgent.isBlank()) {
      return UNKNOWN;
    }
    String ua = userAgent.toLowerCase(Locale.ROOT);
    String browser = browser(ua);
    String os = os(ua);
    if (browser == null && os == null) {
      return UNKNOWN;
    }
    if (browser == null) {
      return os;
    }
    return os == null ? browser : browser + " · " + os;
  }

  /** 다른 브라우저가 Chrome·Safari 문자열을 함께 싣고 오므로 더 구체적인 것부터 본다. */
  private static String browser(String ua) {
    if (ua.contains("edg/") || ua.contains("edga/") || ua.contains("edgios/")) {
      return "Edge";
    }
    if (ua.contains("opr/") || ua.contains("opera")) {
      return "Opera";
    }
    if (ua.contains("samsungbrowser")) {
      return "Samsung Internet";
    }
    if (ua.contains("whale/")) {
      return "Whale";
    }
    if (ua.contains("firefox/") || ua.contains("fxios")) {
      return "Firefox";
    }
    if (ua.contains("crios") || ua.contains("chrome/")) {
      return "Chrome";
    }
    if (ua.contains("safari/")) {
      return "Safari";
    }
    return null;
  }

  /** iPhone UA 에는 "like Mac OS X", Android UA 에는 "Linux" 가 들어 있어 더 구체적인 것부터 본다. */
  private static String os(String ua) {
    if (ua.contains("windows")) {
      return "Windows";
    }
    if (ua.contains("iphone") || ua.contains("ipad") || ua.contains("ipod")) {
      return "iOS";
    }
    if (ua.contains("android")) {
      return "Android";
    }
    if (ua.contains("cros")) {
      return "ChromeOS";
    }
    if (ua.contains("mac os x") || ua.contains("macintosh")) {
      return "macOS";
    }
    if (ua.contains("linux")) {
      return "Linux";
    }
    return null;
  }
}
