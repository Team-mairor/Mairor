package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class DeviceSummaryTest {

  private static final String CHROME_WINDOWS =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          + "Chrome/130.0.0.0 Safari/537.36";
  private static final String EDGE_WINDOWS = CHROME_WINDOWS + " Edg/130.0.0.0";
  private static final String SAFARI_MAC =
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
          + "Version/17.1 Safari/605.1.15";
  private static final String SAFARI_IPHONE =
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
          + "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1";
  private static final String CHROME_IPHONE =
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
          + "(KHTML, like Gecko) CriOS/130.0.0.0 Mobile/15E148 Safari/604.1";
  private static final String CHROME_ANDROID =
      "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) "
          + "Chrome/130.0.0.0 Safari/537.36";
  private static final String SAMSUNG_ANDROID =
      "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) "
          + "SamsungBrowser/25.0 Chrome/121.0.0.0 Safari/537.36";
  private static final String FIREFOX_LINUX =
      "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0";

  @Test
  void summarizesCommonBrowsersAndSystems() {
    assertThat(DeviceSummary.of(CHROME_WINDOWS)).isEqualTo("Chrome · Windows");
    assertThat(DeviceSummary.of(SAFARI_MAC)).isEqualTo("Safari · macOS");
    assertThat(DeviceSummary.of(CHROME_ANDROID)).isEqualTo("Chrome · Android");
    assertThat(DeviceSummary.of(FIREFOX_LINUX)).isEqualTo("Firefox · Linux");
  }

  @Test
  void prefersTheMoreSpecificBrowser() {
    // Edge·삼성 인터넷·iOS Chrome 은 Chrome/Safari 문자열도 함께 싣고 온다
    assertThat(DeviceSummary.of(EDGE_WINDOWS)).isEqualTo("Edge · Windows");
    assertThat(DeviceSummary.of(SAMSUNG_ANDROID)).isEqualTo("Samsung Internet · Android");
    assertThat(DeviceSummary.of(CHROME_IPHONE)).isEqualTo("Chrome · iOS");
  }

  @Test
  void recognizesIosEvenThoughTheUserAgentSaysMacOsX() {
    assertThat(DeviceSummary.of(SAFARI_IPHONE)).isEqualTo("Safari · iOS");
  }

  @Test
  void fallsBackWhenItCannotTell() {
    assertThat(DeviceSummary.of(null)).isEqualTo(DeviceSummary.UNKNOWN);
    assertThat(DeviceSummary.of("")).isEqualTo(DeviceSummary.UNKNOWN);
    assertThat(DeviceSummary.of("   ")).isEqualTo(DeviceSummary.UNKNOWN);
    assertThat(DeviceSummary.of("curl/8.4.0")).isEqualTo(DeviceSummary.UNKNOWN);
  }

  @Test
  void usesOnlyOneOfThePartsWhenTheOtherIsUnknown() {
    assertThat(DeviceSummary.of("Mozilla/5.0 (Windows NT 10.0) Gecko")).isEqualTo("Windows");
  }

  @Test
  void neverEchoesTheRawUserAgentAndStaysShort() {
    String hostile = "<script>alert(1)</script>".repeat(500) + " Chrome/130 Windows";

    String summary = DeviceSummary.of(hostile);

    assertThat(summary).isEqualTo("Chrome · Windows");
    assertThat(summary.length()).isLessThanOrEqualTo(100);
  }
}
