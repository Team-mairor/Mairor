package com.mairor.backend.analysis.extraction;

import com.mairor.backend.analysis.extraction.GuideInput.Fact;
import com.mairor.backend.analysis.extraction.GuideInput.Facts;
import com.mairor.backend.analysis.extraction.GuideInput.Palette;
import com.mairor.backend.analysis.extraction.GuideInput.Product;
import com.mairor.backend.analysis.extraction.GuideInput.Step;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Gemini 단계 추출 답 → 가이드 입력 v2. 공유 스키마의 필수 칸과 스키마 밖 검사(끝 &gt; 시작, 끝 ≤ 영상 길이, {@code stepId}·{@code
 * order} 중복 없음)를 여기서 맞춘다.
 *
 * <p>단계 하나가 틀렸다고 영상 전체를 버리지 않는다. 쓸 수 없는 단계만 버리고 이유를 {@link Result#dropped()}에 남긴다. 남은 단계는 시작 시각 순으로
 * 줄 세워 겹치지 않게 하고(앞 단계 끝을 뒤 단계 시작으로 당김), {@code order}를 1부터 다시 매기고 {@code stepId}를 {@code s<order>}로
 * 둔다.
 */
@Component
public class GuideInputMapper {

  /** 끝 시각이 영상 길이를 이만큼까지 넘으면 반올림으로 보고 길이로 자른다(30:59 처럼). 더 넘으면 버린다. */
  static final double END_TOLERANCE_SECONDS = 2.0;

  static final Set<String> MAKEUP =
      Set.of(
          "foundation",
          "eyeshadow",
          "eyeliner",
          "blush",
          "lip",
          "brow",
          "mascara",
          "contour",
          "highlight",
          "other");

  static final Set<String> SOURCES = Set.of("voice", "onscreenText", "scene", "estimated");

  /**
   * @param input 남은 단계로 만든 가이드 입력. 단계가 0개일 수 있다
   * @param dropped 버린 단계와 이유(로그·기록용)
   */
  public record Result(GuideInput input, List<String> dropped) {}

  private final ObjectMapper objectMapper;

  public GuideInputMapper(ObjectMapper objectMapper) {
    this.objectMapper = objectMapper;
  }

  /**
   * @throws InvalidStepOutputException 답이 JSON 이 아니거나 {@code steps} 목록이 없다
   */
  public Result map(String geminiText, String videoId, double durationSeconds) {
    JsonNode root;
    try {
      root = objectMapper.readTree(geminiText);
    } catch (JacksonException e) {
      throw new InvalidStepOutputException("단계 추출 답이 JSON 이 아닙니다.", e);
    }
    JsonNode rawSteps = root.path("steps");
    if (!rawSteps.isArray()) {
      throw new InvalidStepOutputException("단계 추출 답에 steps 목록이 없습니다.", null);
    }

    List<Candidate> kept = new ArrayList<>();
    List<String> dropped = new ArrayList<>();
    int index = 0;
    for (JsonNode raw : rawSteps) {
      index++;
      String label = "#" + index + " order=" + raw.path("order").asString("?");
      String problem = problem(raw, durationSeconds);
      if (problem != null) {
        dropped.add(label + ": " + problem);
        continue;
      }
      kept.add(toCandidate(raw, index, durationSeconds));
    }

    kept.sort(
        Comparator.comparingDouble(Candidate::start)
            .thenComparingInt(Candidate::geminiOrder)
            .thenComparingInt(Candidate::index));
    List<Candidate> ordered = withoutOverlaps(kept, dropped);
    List<Step> steps = new ArrayList<>(ordered.size());
    for (int i = 0; i < ordered.size(); i++) {
      Candidate c = ordered.get(i);
      int order = i + 1;
      steps.add(
          new Step(
              "s" + order,
              order,
              c.start(),
              c.end(),
              c.makeup(),
              c.partLabel(),
              c.summary(),
              c.product(),
              c.facts()));
    }
    return new Result(new GuideInput(videoId, durationSeconds, List.copyOf(steps)), dropped);
  }

  /**
   * 단계가 겹치지 않게 한다(현수 MR !82 리뷰). AI 는 단계 시작 직전·끝 직후 사진을 비교하므로, 겹치면 앞 단계 화장이 뒤 단계 영역에 섞인다.
   *
   * <p>겹치면 <b>앞 단계의 끝을 뒤 단계의 시작으로 당긴다.</b> 레퍼런스의 겹침은 짧은 단계(페이크 래쉬, 입꼬리)가 긴 단계 안에 통째로 들어간 경우라, 뒤 단계를
   * 미루면 제품이 다른 실제 단계가 사라진다. 앞 단계에 남는 구간이 없을 때만 앞 단계를 버린다. 앞 단계 뒤쪽 남은 구간(예: 입술 1737~1756초)은 어느 단계에도
   * 들어가지 않는다.
   */
  private static List<Candidate> withoutOverlaps(List<Candidate> sorted, List<String> dropped) {
    List<Candidate> result = new ArrayList<>(sorted.size());
    for (int i = 0; i < sorted.size(); i++) {
      Candidate c = sorted.get(i);
      double end = i + 1 < sorted.size() ? Math.min(c.end(), sorted.get(i + 1).start()) : c.end();
      if (end <= c.start()) {
        dropped.add(
            "#"
                + c.index()
                + " order="
                + c.geminiOrder()
                + ": 뒤 단계와 겹쳐 남는 구간 없음("
                + c.start()
                + " ~ "
                + c.end()
                + ", 뒤 단계 시작 "
                + sorted.get(i + 1).start()
                + ")");
        continue;
      }
      result.add(
          new Candidate(
              c.index(),
              c.geminiOrder(),
              c.start(),
              end,
              c.makeup(),
              c.partLabel(),
              c.summary(),
              c.product(),
              c.facts()));
    }
    return result;
  }

  /** 버려야 할 이유. 쓸 수 있으면 null. */
  private static String problem(JsonNode raw, double duration) {
    if (!MAKEUP.contains(text(raw.path("makeup")))) {
      return "makeup 값이 목록에 없음(" + raw.path("makeup").asString("") + ")";
    }
    if (text(raw.path("partLabel")) == null) {
      return "partLabel 없음";
    }
    if (text(raw.path("summary")) == null) {
      return "summary 없음";
    }
    Double start = StepTime.parse(text(raw.path("startTime")));
    Double end = StepTime.parse(text(raw.path("endTime")));
    if (start == null || end == null) {
      return "시각 형식이 틀림(" + raw.path("startTime") + " ~ " + raw.path("endTime") + ")";
    }
    if (end <= start) {
      return "끝이 시작보다 크지 않음(" + start + " ~ " + end + ")";
    }
    if (start >= duration || end > duration + END_TOLERANCE_SECONDS) {
      return "영상 밖(" + start + " ~ " + end + ", 길이 " + duration + ")";
    }
    if (fact(raw.path("facts").path("area")) == null) {
      return "facts.area 없음";
    }
    JsonNode palette = raw.path("product").path("palette");
    if (palette.isObject() && fact(palette.path("color")) == null) {
      return "팔레트인데 고른 색(product.palette.color) 없음";
    }
    return null;
  }

  private static Candidate toCandidate(JsonNode raw, int index, double duration) {
    double start = StepTime.parse(text(raw.path("startTime")));
    double end = Math.min(StepTime.parse(text(raw.path("endTime"))), duration);
    JsonNode facts = raw.path("facts");
    return new Candidate(
        index,
        raw.path("order").asInt(index),
        start,
        end,
        text(raw.path("makeup")),
        text(raw.path("partLabel")),
        text(raw.path("summary")),
        product(raw.path("product")),
        new Facts(
            fact(facts.path("area")),
            fact(facts.path("tool")),
            fact(facts.path("amount")),
            fact(facts.path("strength")),
            fact(facts.path("finishCue")),
            facts(facts.path("tips")),
            facts(facts.path("cautions"))));
  }

  private static Product product(JsonNode node) {
    if (!node.isObject()) {
      return null;
    }
    JsonNode palette = node.path("palette");
    Palette parsed = palette.isObject() ? new Palette(fact(palette.path("color"))) : null;
    String brand = text(node.path("brand"));
    String name = text(node.path("name"));
    String shade = text(node.path("shade"));
    if (brand == null && name == null && shade == null && parsed == null) {
      return null;
    }
    return new Product(brand, name, shade, parsed);
  }

  /** 값과 근거 종류가 있어야 사실이다. 시각이 틀리면 시각만 뺀다. */
  private static Fact fact(JsonNode node) {
    if (!node.isObject()) {
      return null;
    }
    String value = text(node.path("value"));
    String source = text(node.path("source"));
    if (value == null || source == null || !SOURCES.contains(source)) {
      return null;
    }
    return new Fact(value, source, StepTime.parse(text(node.path("at"))));
  }

  private static List<Fact> facts(JsonNode node) {
    List<Fact> result = new ArrayList<>();
    for (JsonNode item : node) {
      Fact fact = fact(item);
      if (fact != null) {
        result.add(fact);
      }
    }
    return List.copyOf(result);
  }

  private static String text(JsonNode node) {
    if (!node.isString()) {
      return null;
    }
    String value = node.asString().trim();
    return value.isEmpty() ? null : value;
  }

  private record Candidate(
      int index,
      int geminiOrder,
      double start,
      double end,
      String makeup,
      String partLabel,
      String summary,
      Product product,
      Facts facts) {}
}
