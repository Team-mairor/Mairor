package com.mairor.backend.common.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import tools.jackson.databind.ObjectMapper;

/** 노션 공통 규약: camelCase, 열거값 UPPER_SNAKE_CASE, 날짜는 UTC ISO-8601, null 필드 생략. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class JsonConventionTest {

  enum MatchStatus {
    SAME,
    SUBSTITUTE,
    NONE
  }

  record Sample(String videoId, MatchStatus matchStatus, Instant completedAt, String missing) {}

  @Autowired private ObjectMapper objectMapper;

  @Test
  void serializesByConvention() {
    Sample sample =
        new Sample("abc", MatchStatus.SUBSTITUTE, Instant.parse("2026-01-02T03:04:05Z"), null);

    String json = objectMapper.writeValueAsString(sample);

    assertThat(json).contains("\"videoId\":\"abc\"");
    assertThat(json).contains("\"matchStatus\":\"SUBSTITUTE\"");
    assertThat(json).contains("\"completedAt\":\"2026-01-02T03:04:05Z\"");
    assertThat(json).doesNotContain("missing");
  }

  @Test
  void pageResponse_keepsContract() {
    PageQuery query = new PageQuery(2, 10);

    String json = objectMapper.writeValueAsString(PageResponse.empty(query));

    assertThat(json).isEqualTo("{\"items\":[],\"page\":2,\"size\":10,\"hasNext\":false}");
  }
}
