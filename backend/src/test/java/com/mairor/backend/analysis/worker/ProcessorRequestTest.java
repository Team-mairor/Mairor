package com.mairor.backend.analysis.worker;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** 노트북 AI 요청 JSON 해석 · 검사 · AI 본문(S15P31A306-358). */
class ProcessorRequestTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final String VIDEO = "VxAXD6PP76I";
  private static final String BUCKET = "mairor-prod-media";

  private static String request(String videoId, String steps, String frames) {
    return "{\"callbackUrl\": \"https://api.mairor.com/api/v1/callbacks/guide-jobs/x\","
        + " \"guideInput\": {\"videoId\": \""
        + videoId
        + "\", \"durationSeconds\": 1858.2, \"steps\": ["
        + steps
        + "]}"
        + (frames == null ? "" : ", \"frames\": " + frames)
        + "}";
  }

  private static final String STEPS =
      "{\"stepId\": \"s1\", \"order\": 1, \"makeup\": \"eyeshadow\", \"eyeZone\": \"upperLid\"},"
          + " {\"stepId\": \"s2\", \"order\": 2, \"makeup\": \"lip\"}";

  private static String frames(String... items) {
    return "{\"source\": {\"width\": 1920, \"height\": 1080, \"fps\": 60}, \"items\": ["
        + String.join(",", items)
        + "]}";
  }

  private static String frame(String extra) {
    return "{\"frameIndex\": 1680, \"timestampMs\": 28000, \"stepId\": \"s1\", \"width\": 1920,"
        + " \"height\": 1080, "
        + extra
        + "}";
  }

  private static ProcessorRequest parse(String json) {
    return ProcessorRequest.parse(JSON, json, VIDEO, BUCKET);
  }

  @Test
  void keyIsUsedAndTheAiBodyIsRewritten() {
    String key = "videos/VxAXD6PP76I/jobs/j1/frames/step_01/frame_001680.jpg";
    ProcessorRequest request =
        parse(
            request(
                VIDEO,
                STEPS,
                frames(frame("\"key\": \"" + key + "\", \"url\": \"https://example.com/x.jpg\""))));

    assertThat(request.stepCount()).isEqualTo(2);
    assertThat(request.frames()).extracting(ProcessorRequest.Frame::key).containsExactly(key);

    JsonNode body =
        JSON.readTree(
            request.aiRequest("http://be/cb", "http://be/progress", k -> "https://signed/" + k));
    assertThat(body.path("callbackUrl").asString()).isEqualTo("http://be/cb");
    assertThat(body.path("progressUrl").asString()).isEqualTo("http://be/progress");
    JsonNode item = body.path("frames").path("items").get(0);
    assertThat(item.path("url").asString()).isEqualTo("https://signed/" + key);
    assertThat(item.has("key")).as("AI 에는 key 를 보내지 않는다").isFalse();
    assertThat(item.path("frameIndex").asInt()).isEqualTo(1680);
    assertThat(body.path("guideInput").path("steps").get(0).path("eyeZone").asString())
        .as("가이드 입력은 그대로 넘긴다")
        .isEqualTo("upperLid");
    assertThat(JSON.readTree(request.guideInputJson()).path("videoId").asString()).isEqualTo(VIDEO);
  }

  @Test
  void keyIsTakenFromOurBucketUrlWhenMissing() {
    ProcessorRequest virtualHost =
        parse(
            request(
                VIDEO,
                STEPS,
                frames(
                    frame(
                        "\"url\": \"https://mairor-prod-media.s3.ap-northeast-2.amazonaws.com/"
                            + "videos/VxAXD6PP76I/frames/step_01/frame_001680.jpg\""))));
    assertThat(virtualHost.frames().getFirst().key())
        .isEqualTo("videos/VxAXD6PP76I/frames/step_01/frame_001680.jpg");

    assertThat(
            ProcessorRequest.keyFromS3Url(
                "https://s3.ap-northeast-2.amazonaws.com/mairor-prod-media/videos/a/b%20c.jpg?X-Amz=1",
                BUCKET))
        .isEqualTo("videos/a/b c.jpg");
    assertThat(
            ProcessorRequest.keyFromS3Url(
                "https://other-bucket.s3.amazonaws.com/videos/a/b.jpg", BUCKET))
        .isNull();
    assertThat(ProcessorRequest.keyFromS3Url("https://example.com/videos/a.jpg", BUCKET)).isNull();
    assertThat(
            ProcessorRequest.keyFromS3Url(
                "https://mairor-prod-media.s3.amazonaws.com/videos/a.jpg", ""))
        .as("로컬 저장소(버킷 없음)면 뽑지 않는다")
        .isNull();
  }

  @Test
  void framesCanBeDroppedWhenTheyCannotBeDelivered() {
    String key = "videos/VxAXD6PP76I/jobs/j1/frames/step_01/frame_001680.jpg";
    ProcessorRequest request =
        parse(request(VIDEO, STEPS, frames(frame("\"key\": \"" + key + "\""))));

    JsonNode body =
        JSON.readTree(request.aiRequestWithoutFrames("http://be/cb", "http://be/progress"));
    assertThat(body.has("frames")).as("로컬 저장소처럼 AI 가 받을 수 없으면 프레임을 뺀다").isFalse();
    assertThat(body.path("callbackUrl").asString()).isEqualTo("http://be/cb");
    assertThat(body.path("progressUrl").asString()).isEqualTo("http://be/progress");
    assertThat(body.path("guideInput").path("steps").size()).isEqualTo(2);
    assertThat(request.frames()).as("원본은 바꾸지 않는다").hasSize(1);
  }

  @Test
  void withoutFramesTheBodyHasNoFrames() {
    ProcessorRequest request = parse(request(VIDEO, STEPS, null));
    assertThat(request.frames()).isEmpty();
    assertThat(JSON.readTree(request.aiRequest("c", "p", k -> k)).has("frames")).isFalse();
  }

  @Test
  void brokenRequestsAreRejected() {
    assertCode("{not json", AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
    assertCode("[]", AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
    assertCode("{}", AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
    assertCode(request("zzzzzzzzzzz", STEPS, null), AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
    assertCode(request(VIDEO, "", null), AnalysisFailureCode.NO_VALID_STEPS);
    assertCode(
        request(VIDEO, "{\"stepId\": \"s1\"}, {\"stepId\": \"s1\"}", null),
        AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
    assertCode(
        request(VIDEO, STEPS, frames(frame("\"url\": \"https://example.com/x.jpg\""))),
        AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
    assertCode(
        request(VIDEO, STEPS, frames(frame("\"key\": \"videos/otherVideo1/frames/a.jpg\""))),
        AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
    assertCode(
        request(VIDEO, STEPS, frames(frame("\"key\": \"videos/VxAXD6PP76I/../x/a.jpg\""))),
        AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID);
  }

  private static void assertCode(String json, AnalysisFailureCode code) {
    assertThatThrownBy(() -> parse(json))
        .isInstanceOf(AnalysisStepException.class)
        .extracting(e -> ((AnalysisStepException) e).code())
        .isEqualTo(code);
  }
}
