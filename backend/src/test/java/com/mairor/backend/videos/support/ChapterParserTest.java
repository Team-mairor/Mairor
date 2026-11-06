package com.mairor.backend.videos.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.videos.dto.VideoChapter;
import org.junit.jupiter.api.Test;

/** 설명란 챕터: YouTube 챕터 규칙(0:00 시작, 3개 이상, 오름차순)과 흔한 표기. */
class ChapterParserTest {

  @Test
  void readsChaptersInYouTubeFormat() {
    String description =
        """
        오늘의 메이크업 🌸
        0:00 인트로
        01:35 - 베이스
        (5:10) 아이섀도
        1:02:03 | 마무리
        제품 정보는 아래
        """;

    assertThat(ChapterParser.parse(description))
        .containsExactly(
            new VideoChapter(0, "인트로"),
            new VideoChapter(95, "베이스"),
            new VideoChapter(310, "아이섀도"),
            new VideoChapter(3723, "마무리"));
  }

  @Test
  void noChaptersWhenFirstIsNotZero() {
    assertThat(ChapterParser.parse("0:10 시작\n1:00 베이스\n2:00 립")).isEmpty();
  }

  @Test
  void noChaptersWhenFewerThanThree() {
    assertThat(ChapterParser.parse("0:00 시작\n1:00 끝")).isEmpty();
  }

  @Test
  void noChaptersWhenNotAscending() {
    assertThat(ChapterParser.parse("0:00 시작\n3:00 립\n2:00 베이스")).isEmpty();
  }

  @Test
  void blankDescription() {
    assertThat(ChapterParser.parse(null)).isEmpty();
    assertThat(ChapterParser.parse("  ")).isEmpty();
  }
}
