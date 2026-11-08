package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.StringJoiner;
import tools.jackson.databind.JsonNode;

/**
 * AI 가이드 결과가 그 작업의 결과가 맞는지 보는 규칙(S15P31A306-363). 형식(필수 칸)은 {@link AiResultService}가 먼저 본다.
 *
 * <ul>
 *   <li>영상: 콜백 {@code videoId}와 {@code area.videoId}(있으면)가 작업 영상의 YouTube ID 와 같다
 *   <li>단계: {@code guide.steps[].stepId} 집합이 가이드 입력의 단계 ID 집합과 같고 중복이 없다(순서는 보지 않는다)
 *   <li>영역: 프레임을 보낸 작업이면 {@code area}가 있다. 프레임 없이 맡긴 작업은 없어도 된다
 * </ul>
 *
 * <p>이 클래스는 상태를 갖지 않는 규칙 묶음이다. 어긋남마다 사람이 읽을 사유 한 줄을 돌려준다.
 */
final class AiResultCheck {

  /** 사유 한 줄에 단계 ID 를 몇 개까지 적을지. 나머지는 "외 N개". */
  private static final int LISTED_IDS = 5;

  private AiResultCheck() {}

  /**
   * @param expectedVideoId 작업 영상의 YouTube ID
   * @param guideInput AI 에 보낸 가이드 입력({@code steps[].stepId})
   * @param framesSent 프레임을 실어 맡겼는가
   * @return 어긋난 사유. 맞으면 빈 목록
   */
  static List<String> problems(
      String expectedVideoId,
      JsonNode guideInput,
      boolean framesSent,
      AiGuideJobCallbackRequest result) {
    List<String> problems = new ArrayList<>();
    if (!expectedVideoId.equals(result.videoId())) {
      problems.add("videoId 가 작업 영상(" + expectedVideoId + ")과 다름: " + result.videoId());
    }

    JsonNode area = result.area();
    boolean hasArea = area != null && !area.isNull() && !area.isMissingNode();
    if (hasArea) {
      String areaVideoId = area.path("videoId").asString(null);
      if (!expectedVideoId.equals(areaVideoId)) {
        problems.add("area.videoId 가 작업 영상(" + expectedVideoId + ")과 다름: " + areaVideoId);
      }
    } else if (framesSent) {
      problems.add("프레임을 보낸 작업인데 area 가 없음");
    }

    Set<String> expected = stepIds(guideInput.path("steps"), null);
    List<String> duplicated = new ArrayList<>();
    Set<String> actual = stepIds(result.guide().path("steps"), duplicated);
    if (!duplicated.isEmpty()) {
      problems.add("guide.steps 에 같은 단계가 두 번 이상: " + list(duplicated));
    }
    List<String> missing = new ArrayList<>(expected);
    missing.removeAll(actual);
    if (!missing.isEmpty()) {
      problems.add("guide.steps 에 빠진 단계: " + list(missing));
    }
    List<String> unknown = new ArrayList<>(actual);
    unknown.removeAll(expected);
    if (!unknown.isEmpty()) {
      problems.add("guide.steps 에 가이드 입력에 없는 단계: " + list(unknown));
    }
    return problems;
  }

  /**
   * AI 실패의 사람이 읽을 메시지. {@code error.details}가 있으면 {@code "<message> — <field>: <reason>; …"}로 붙인다.
   * 길이는 저장할 때 자른다.
   *
   * @param fallback {@code error.message}가 없을 때 쓸 문구
   */
  static String failureMessage(JsonNode error, String fallback) {
    String message = error == null ? null : error.path("message").asString(null);
    String base = message == null || message.isBlank() ? fallback : message;
    String details = details(error);
    return details.isEmpty() ? base : base + " — " + details;
  }

  /** {@code error.details}를 {@code "field: reason; …"} 한 줄로. 없으면 빈 문자열. */
  static String details(JsonNode error) {
    if (error == null || !error.path("details").isArray()) {
      return "";
    }
    StringJoiner joined = new StringJoiner("; ");
    for (JsonNode detail : error.path("details")) {
      String field = detail.path("field").asString("");
      String reason = detail.path("reason").asString("");
      joined.add(field.isEmpty() ? reason : field + ": " + reason);
    }
    return joined.toString();
  }

  private static Set<String> stepIds(JsonNode steps, List<String> duplicated) {
    Set<String> ids = new LinkedHashSet<>();
    if (!steps.isArray()) {
      return ids;
    }
    for (JsonNode step : steps) {
      String id = step.path("stepId").asString("");
      if (!ids.add(id) && duplicated != null && !duplicated.contains(id)) {
        duplicated.add(id);
      }
    }
    return ids;
  }

  private static String list(List<String> ids) {
    List<String> shown = ids.subList(0, Math.min(LISTED_IDS, ids.size()));
    String text = String.join(", ", shown);
    return ids.size() > LISTED_IDS ? text + " 외 " + (ids.size() - LISTED_IDS) + "개" : text;
  }
}
