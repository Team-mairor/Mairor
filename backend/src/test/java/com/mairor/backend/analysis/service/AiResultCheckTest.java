package com.mairor.backend.analysis.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** AI 결과 검사 규칙(S15P31A306-363): 영상 · 단계 ID · 영역, 실패 상세 문구. */
class AiResultCheckTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final String VIDEO = "abcdefghijk";
  private static final JsonNode INPUT =
      JSON.readTree(
          "{\"videoId\": \"abcdefghijk\", \"steps\": [{\"stepId\": \"s1\"}, {\"stepId\": \"s2\"},"
              + " {\"stepId\": \"s3\"}]}");

  private static AiGuideJobCallbackRequest completed(String videoId, String stepIds, String area) {
    StringBuilder steps = new StringBuilder();
    String[] ids = stepIds.isEmpty() ? new String[0] : stepIds.split(",");
    for (int i = 0; i < ids.length; i++) {
      steps
          .append(i == 0 ? "" : ",")
          .append("{\"stepId\": \"")
          .append(ids[i])
          .append("\", \"order\": ")
          .append(i + 1)
          .append(", \"actions\": []}");
    }
    return new AiGuideJobCallbackRequest(
        "ai-1",
        videoId,
        "COMPLETED",
        JSON.readTree("{\"steps\": [" + steps + "]}"),
        area == null ? null : JSON.readTree(area),
        null);
  }

  private static String area(String videoId) {
    return "{\"videoId\": \"" + videoId + "\", \"meshVersion\": \"v1\", \"steps\": []}";
  }

  @Test
  void matchingResultPasses() {
    assertThat(
            AiResultCheck.problems(VIDEO, INPUT, true, completed(VIDEO, "s1,s2,s3", area(VIDEO))))
        .isEmpty();
    assertThat(AiResultCheck.problems(VIDEO, INPUT, false, completed(VIDEO, "s3,s1,s2", null)))
        .as("순서는 보지 않고, 프레임 없이 맡긴 작업은 area 가 없어도 된다")
        .isEmpty();
  }

  @Test
  void otherVideoIsRejected() {
    List<String> problems =
        AiResultCheck.problems(
            VIDEO, INPUT, true, completed("zzzzzzzzzzz", "s1,s2,s3", area(VIDEO)));
    assertThat(problems).singleElement().asString().contains("videoId").contains("zzzzzzzzzzz");
  }

  @Test
  void areaOfOtherVideoIsRejected() {
    assertThat(
            AiResultCheck.problems(
                VIDEO, INPUT, true, completed(VIDEO, "s1,s2,s3", area("zzzzzzzzzzz"))))
        .singleElement()
        .asString()
        .startsWith("area.videoId");
  }

  @Test
  void missingUnknownAndDuplicatedStepsAreRejected() {
    assertThat(AiResultCheck.problems(VIDEO, INPUT, false, completed(VIDEO, "s1,s2", null)))
        .containsExactly("guide.steps 에 빠진 단계: s3");
    assertThat(AiResultCheck.problems(VIDEO, INPUT, false, completed(VIDEO, "s1,s2,s3,s9", null)))
        .containsExactly("guide.steps 에 가이드 입력에 없는 단계: s9");
    assertThat(AiResultCheck.problems(VIDEO, INPUT, false, completed(VIDEO, "s1,s2,s2,s3", null)))
        .containsExactly("guide.steps 에 같은 단계가 두 번 이상: s2");
  }

  @Test
  void longStepListsAreShortened() {
    StringBuilder input = new StringBuilder("{\"steps\": [");
    for (int i = 1; i <= 8; i++) {
      input.append(i == 1 ? "" : ",").append("{\"stepId\": \"s").append(i).append("\"}");
    }
    JsonNode eight = JSON.readTree(input.append("]}").toString());
    assertThat(AiResultCheck.problems(VIDEO, eight, false, completed(VIDEO, "", null)))
        .containsExactly("guide.steps 에 빠진 단계: s1, s2, s3, s4, s5 외 3개");
  }

  @Test
  void framesSentButNoAreaIsRejected() {
    assertThat(AiResultCheck.problems(VIDEO, INPUT, true, completed(VIDEO, "s1,s2,s3", null)))
        .containsExactly("프레임을 보낸 작업인데 area 가 없음");
  }

  @Test
  void failureMessageCarriesTheDetails() {
    JsonNode error =
        JSON.readTree(
            "{\"code\": \"GENERATION_FAILED\", \"message\": \"단계 설명을 만들지 못했습니다.\", \"details\":"
                + " [{\"field\": \"steps.0\", \"reason\": \"no key (config)\"},"
                + " {\"field\": \"steps.1\", \"reason\": \"no key (config)\"}]}");
    assertThat(AiResultCheck.failureMessage(error, "기본"))
        .isEqualTo("단계 설명을 만들지 못했습니다. — steps.0: no key (config); steps.1: no key (config)");
    assertThat(AiResultCheck.failureMessage(JSON.readTree("{\"code\": \"X\"}"), "기본"))
        .isEqualTo("기본");
    assertThat(AiResultCheck.failureMessage(null, "기본")).isEqualTo("기본");
  }
}
