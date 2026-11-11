package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Function;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 노트북이 올린 AI 요청 JSON({@code guide_job_request.v2}, S15P31A306-358). BE 에 스키마 검사기가 없어 AI 에 넘기기 전에
 * 필요한 것만 본다: 가이드 입력의 영상 · 단계, 프레임마다 저장소 키. 나머지 형식은 AI 가 검사한다(어긋나면 400 → {@code
 * AI_REQUEST_REJECTED}).
 *
 * <p>프레임 키는 {@code key}를 쓰고, 없으면 우리 버킷의 S3 주소({@code url})에서 뽑는다. 키는 {@code
 * videos/<youtubeVideoId>/} 아래만 받는다.
 */
final class ProcessorRequest {

  /** 프레임 항목과 그 저장소 키. */
  record Frame(ObjectNode node, String key) {}

  private final ObjectNode root;
  private final JsonNode guideInput;
  private final List<Frame> frames;

  private ProcessorRequest(ObjectNode root, JsonNode guideInput, List<Frame> frames) {
    this.root = root;
    this.guideInput = guideInput;
    this.frames = frames;
  }

  /**
   * @param bucket 운영 버킷 이름. 비어 있으면(로컬 저장소) 주소에서 키를 뽑지 않는다
   * @throws AnalysisStepException {@code PROCESSOR_OUTPUT_INVALID}(형식 · 영상 · 키), {@code
   *     NO_VALID_STEPS}(단계 0개)
   */
  static ProcessorRequest parse(
      ObjectMapper objectMapper, String json, String youtubeVideoId, String bucket) {
    JsonNode parsed;
    try {
      parsed = objectMapper.readTree(json);
    } catch (JacksonException e) {
      throw invalid("요청 JSON 을 읽을 수 없습니다: " + e.getOriginalMessage());
    }
    if (!(parsed instanceof ObjectNode root)) {
      throw invalid("요청 JSON 이 객체가 아닙니다.");
    }
    JsonNode guideInput = root.path("guideInput");
    if (!guideInput.isObject()) {
      throw invalid("guideInput 이 없습니다.");
    }
    String videoId = guideInput.path("videoId").asString(null);
    if (!youtubeVideoId.equals(videoId)) {
      throw invalid("guideInput.videoId 가 작업 영상(" + youtubeVideoId + ")과 다릅니다: " + videoId);
    }
    if (!guideInput.path("durationSeconds").isNumber()) {
      throw invalid("guideInput.durationSeconds 가 없습니다.");
    }
    JsonNode steps = guideInput.path("steps");
    if (!steps.isArray()) {
      throw invalid("guideInput.steps 가 없습니다.");
    }
    if (steps.isEmpty()) {
      throw new AnalysisStepException(AnalysisFailureCode.NO_VALID_STEPS, "노트북이 찾은 메이크업 단계가 없습니다.");
    }
    Set<String> stepIds = new HashSet<>();
    for (JsonNode step : steps) {
      String stepId = step.path("stepId").asString("");
      if (stepId.isBlank() || !stepIds.add(stepId)) {
        throw invalid("guideInput.steps 의 stepId 가 비었거나 겹칩니다: " + stepId);
      }
    }

    List<Frame> frames = new ArrayList<>();
    JsonNode frameBlock = root.path("frames");
    if (frameBlock.isObject()) {
      JsonNode items = frameBlock.path("items");
      if (!items.isArray()) {
        throw invalid("frames.items 가 없습니다.");
      }
      String allowed = "videos/" + youtubeVideoId + "/";
      int index = 0;
      for (JsonNode item : items) {
        if (!(item instanceof ObjectNode node)) {
          throw invalid("frames.items[" + index + "] 가 객체가 아닙니다.");
        }
        String key = frameKey(node, bucket);
        if (key == null) {
          throw invalid("frames.items[" + index + "] 의 저장소 키를 알 수 없습니다(key 없음).");
        }
        if (!key.startsWith(allowed) || key.contains("..")) {
          throw invalid("frames.items[" + index + "] 의 키가 " + allowed + " 밖입니다: " + key);
        }
        frames.add(new Frame(node, key));
        index++;
      }
    } else if (!frameBlock.isMissingNode() && !frameBlock.isNull()) {
      throw invalid("frames 가 객체가 아닙니다.");
    }
    return new ProcessorRequest(root, guideInput, frames);
  }

  /** 가이드 입력 JSON(가이드 행에 저장한다). */
  String guideInputJson() {
    return guideInput.toString();
  }

  int stepCount() {
    return guideInput.path("steps").size();
  }

  List<Frame> frames() {
    return frames;
  }

  /**
   * AI 에 보낼 본문. 노트북 JSON 을 그대로 두고 {@code callbackUrl} · {@code progressUrl}을 BE 주소로, 프레임 {@code
   * url}을 서명한 주소로 바꾸고 {@code key}를 뺀다. 원본은 바꾸지 않는다.
   *
   * @param sign 저장소 키 → 로그인 없이 받을 수 있는 주소
   */
  String aiRequest(String callbackUrl, String progressUrl, Function<String, String> sign) {
    ObjectNode body = root.deepCopy();
    body.put("callbackUrl", callbackUrl);
    body.put("progressUrl", progressUrl);
    JsonNode items = body.path("frames").path("items");
    for (int i = 0; i < frames.size(); i++) {
      ObjectNode item = (ObjectNode) items.get(i);
      item.put("url", sign.apply(frames.get(i).key()));
      item.remove("key");
    }
    return body.toString();
  }

  /**
   * 프레임을 빼고 AI 에 보낼 본문. 저장소가 AI 가 받을 수 있는 주소를 주지 못할 때(로컬, {@link
   * com.mairor.backend.analysis.service.AiFrameDelivery}) 쓴다. AI 는 영역 없이 설명만 만든다.
   */
  String aiRequestWithoutFrames(String callbackUrl, String progressUrl) {
    ObjectNode body = root.deepCopy();
    body.put("callbackUrl", callbackUrl);
    body.put("progressUrl", progressUrl);
    body.remove("frames");
    return body.toString();
  }

  /** 프레임 항목의 저장소 키. {@code key}가 있으면 그것, 없으면 우리 버킷 S3 주소에서 뽑는다. */
  static String frameKey(ObjectNode item, String bucket) {
    String key = item.path("key").asString(null);
    if (key != null && !key.isBlank()) {
      return key;
    }
    return keyFromS3Url(item.path("url").asString(null), bucket);
  }

  /**
   * {@code https://<bucket>.s3[.<region>].amazonaws.com/<key>} 또는 {@code
   * https://s3[.<region>].amazonaws.com/<bucket>/<key>} 꼴이면 키, 아니면 {@code null}. 서명 칸(쿼리)은 버린다.
   */
  static String keyFromS3Url(String url, String bucket) {
    if (url == null || bucket == null || bucket.isBlank()) {
      return null;
    }
    URI uri;
    try {
      uri = URI.create(url);
    } catch (IllegalArgumentException e) {
      return null;
    }
    String host = uri.getHost();
    String path = uri.getRawPath();
    if (host == null || path == null || !host.endsWith(".amazonaws.com")) {
      return null;
    }
    String raw;
    if (host.startsWith(bucket + ".s3")) {
      raw = path.startsWith("/") ? path.substring(1) : path;
    } else if (host.startsWith("s3") && path.startsWith("/" + bucket + "/")) {
      raw = path.substring(bucket.length() + 2);
    } else {
      return null;
    }
    String key = URLDecoder.decode(raw.replace("+", "%2B"), StandardCharsets.UTF_8);
    return key.isBlank() ? null : key;
  }

  private static AnalysisStepException invalid(String message) {
    return new AnalysisStepException(AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID, message);
  }
}
