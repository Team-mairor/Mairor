package com.mairor.backend.videos.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class VideoSearchServiceTest {

  @Test
  void theMakeupWordIsAddedInFrontWhenMissing() {
    assertThat(VideoSearchService.withMakeupWord("데일리")).isEqualTo("메이크업 데일리");
    assertThat(VideoSearchService.withMakeupWord("화장법")).isEqualTo("메이크업 화장법");
  }

  @Test
  void aQueryThatAlreadyHasItIsLeftAlone() {
    assertThat(VideoSearchService.withMakeupWord("데일리 메이크업")).isEqualTo("데일리 메이크업");
    assertThat(VideoSearchService.withMakeupWord("메이크 업 튜토리얼")).isEqualTo("메이크 업 튜토리얼");
    assertThat(VideoSearchService.withMakeupWord("MakeUp GRWM")).isEqualTo("MakeUp GRWM");
    assertThat(VideoSearchService.withMakeupWord("make-up tutorial")).isEqualTo("make-up tutorial");
  }
}
