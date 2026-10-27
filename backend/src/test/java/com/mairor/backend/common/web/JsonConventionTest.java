package com.mairor.backend.common.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import tools.jackson.databind.ObjectMapper;

/**
 * 노션 공통 규약: camelCase, 열거값 UPPER_SNAKE_CASE, 날짜는 UTC ISO-8601, 값이 없는 필드는 생략하지 않고 null. 오류 응답의
 * details만 없으면 생략한다.
 */
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
    assertThat(json).contains("\"missing\":null");
  }

  @Test
  void pageResponse_keepsContract() {
    PageQuery query = new PageQuery(2, 10);

    String json = objectMapper.writeValueAsString(PageResponse.empty(query));

    assertThat(json).isEqualTo("{\"items\":[],\"page\":2,\"size\":10,\"hasNext\":false}");
  }

  @Test
  void errorResponse_omitsDetailsWhenAbsent() {
    String json = objectMapper.writeValueAsString(ErrorResponse.of(ErrorCode.NOT_FOUND));

    assertThat(json).isEqualTo("{\"code\":\"NOT_FOUND\",\"message\":\"요청한 리소스를 찾을 수 없습니다.\"}");
  }
}
