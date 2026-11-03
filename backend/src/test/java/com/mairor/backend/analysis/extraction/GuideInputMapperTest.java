package com.mairor.backend.analysis.extraction;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.analysis.extraction.GuideInput.Step;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * Gemini 답 → 가이드 입력 v2. 형준의 실제 Gemini 실행 결과({@code ai/tools/gemini_runs/eFzG30avtOI_8.json}의 {@code
 * output}, 8분 45초 영상 · 18단계)로 공유 스키마 통과를 보고, 틀린 단계 처리는 작은 JSON 으로 본다.
 */
class GuideInputMapperTest {

  private static final double DURATION = 525.4;

  private final ObjectMapper objectMapper = JsonMapper.builder().build();
  private final GuideInputMapper mapper = new GuideInputMapper(objectMapper);

  @Test
  void realGeminiOutputBecomesAGuideInputThatPassesTheSharedSchema() throws IOException {
    String gemini =
        new ClassPathResource("analysis/gemini-steps-eFzG30avtOI.json")
            .getContentAsString(StandardCharsets.UTF_8);

    GuideInputMapper.Result result = mapper.map(gemini, "eFzG30avtOI", DURATION);

    GuideInput input = result.input();
    assertThat(result.dropped()).isEmpty();
    assertThat(input.steps()).hasSize(18);
    assertThat(input.steps())
        .extracting(Step::order)
        .containsExactlyElementsOf(java.util.stream.IntStream.rangeClosed(1, 18).boxed().toList());
    assertThat(input.steps()).allSatisfy(s -> assertThat(s.stepId()).isEqualTo("s" + s.order()));
    assertThat(input.steps())
        .allSatisfy(
            s -> {
              assertThat(s.endSeconds()).isGreaterThan(s.startSeconds());
              assertThat(s.endSeconds()).isLessThanOrEqualTo(DURATION);
              assertThat(s.facts().area()).isNotNull();
            });
    Step last = input.steps().getLast();
    assertThat(last.startSeconds()).isEqualTo(8 * 60 + 21);
    assertThat(last.endSeconds()).isEqualTo(8 * 60 + 30);
    assertThat(input.steps())
        .filteredOn(s -> s.product() != null && s.product().palette() != null)
        .hasSize(3)
        .allSatisfy(s -> assertThat(s.product().palette().color().value()).isNotBlank());

    String json = objectMapper.writeValueAsString(input);
    assertThat(GuideInputSchema.violations(json)).isEmpty();
    assertThat(GuideInputSchema.violations(json.replace("\"area\":", "\"place\":")))
        .as("검사기가 실제로 막는지: area 가 빠지면 실패")
        .isNotEmpty();
  }

  @Test
  void stepsAreSortedByStartAndRenumbered() {
    String gemini =
        """
        {"steps": [
          %s,
          %s
        ]}
        """
            .formatted(step(7, "05:00", "05:30"), step(3, "01:00", "01:20"));

    GuideInput input = mapper.map(gemini, "abcdefghijk", 600).input();

    assertThat(input.steps()).extracting(Step::stepId).containsExactly("s1", "s2");
    assertThat(input.steps()).extracting(Step::startSeconds).containsExactly(60.0, 300.0);
  }

  @Test
  void overlapsPullTheEarlierStepsEndBackSoShortInnerStepsSurvive() {
    // 레퍼런스의 겹침: s21 페이크 래쉬 19:09~19:12 가 s20 점막 18:51~19:12 안, s33 입꼬리 28:54~28:57 이 s32 입술
    // 28:15~29:16 안
    String gemini =
        """
        {"steps": [%s, %s, %s, %s, %s]}
        """
            .formatted(
                step(20, "18:51", "19:12"),
                step(21, "19:09", "19:12"),
                step(32, "28:15", "29:16"),
                step(33, "28:54", "28:57"),
                step(34, "29:21", "29:28"));

    GuideInputMapper.Result result = mapper.map(gemini, "abcdefghijk", 1858);

    List<Step> steps = result.input().steps();
    assertThat(result.dropped()).isEmpty();
    assertThat(steps).extracting(Step::stepId).containsExactly("s1", "s2", "s3", "s4", "s5");
    assertThat(steps)
        .extracting(Step::startSeconds)
        .containsExactly(1131.0, 1149.0, 1695.0, 1734.0, 1761.0);
    assertThat(steps)
        .extracting(Step::endSeconds)
        .as("앞 단계 끝을 뒤 단계 시작으로 당긴다(s20 → 1149, s32 → 1734)")
        .containsExactly(1149.0, 1152.0, 1734.0, 1737.0, 1768.0);
    assertThat(GuideInputSchema.violations(objectMapper.writeValueAsString(result.input())))
        .isEmpty();
  }

  @Test
  void anEarlierStepWithNothingLeftIsDropped() {
    // 같은 시각에 시작하면 앞 단계(Gemini 순서가 빠른 쪽)에 남는 구간이 없다
    String gemini =
        """
        {"steps": [%s, %s]}
        """
            .formatted(step(1, "01:40", "01:50"), step(2, "01:40", "01:45"));

    GuideInputMapper.Result result = mapper.map(gemini, "abcdefghijk", 600);

    assertThat(result.input().steps()).hasSize(1);
    assertThat(result.input().steps().getFirst().endSeconds()).isEqualTo(105.0);
    assertThat(result.dropped())
        .singleElement()
        .satisfies(r -> assertThat(r).contains("뒤 단계와 겹쳐 남는 구간 없음"));
  }

  @Test
  void brokenStepsAreDroppedAndTheRestKept() {
    String gemini =
        """
        {"steps": [
          %s,
          %s,
          %s,
          %s,
          %s,
          {"order": 6, "makeup": "lipstick", "partLabel": "립", "startTime": "02:00",
           "endTime": "02:10", "summary": "바른다", "facts": {"area": {"value": "입술", "source": "voice"}}},
          {"order": 7, "makeup": "eyeshadow", "partLabel": "섀도", "startTime": "03:00",
           "endTime": "03:10", "summary": "바른다", "facts": {}},
          {"order": 8, "makeup": "eyeshadow", "partLabel": "섀도", "startTime": "03:20",
           "endTime": "03:30", "summary": "바른다",
           "product": {"brand": "A", "name": "팔레트", "shade": null, "palette": {}},
           "facts": {"area": {"value": "눈두덩", "source": "scene"}}}
        ]}
        """
            .formatted(
                step(1, "00:10", "00:30"),
                step(2, "00:40", "00:40"),
                step(3, "09:58", "10:01"),
                step(4, "09:00", "10:30"),
                step(5, "322", "330"));

    GuideInputMapper.Result result = mapper.map(gemini, "abcdefghijk", 600);

    assertThat(result.input().steps()).hasSize(2);
    assertThat(result.input().steps().get(1).endSeconds())
        .as("영상 길이를 2초 이내로 넘은 끝은 길이로 자른다")
        .isEqualTo(600);
    assertThat(result.dropped())
        .hasSize(6)
        .anySatisfy(r -> assertThat(r).contains("끝이 시작보다 크지 않음"))
        .anySatisfy(r -> assertThat(r).contains("영상 밖"))
        .anySatisfy(r -> assertThat(r).contains("시각 형식"))
        .anySatisfy(r -> assertThat(r).contains("makeup"))
        .anySatisfy(r -> assertThat(r).contains("facts.area"))
        .anySatisfy(r -> assertThat(r).contains("palette.color"));
  }

  @Test
  void optionalFactsAreNullOrEmptyAndBadOnesAreRemoved() {
    String gemini =
        """
        {"steps": [{"order": 1, "makeup": "blush", "partLabel": "블러셔", "startTime": "01:00",
          "endTime": "01:30", "summary": "볼에 바른다",
          "product": {"brand": " ", "name": null, "shade": null, "palette": null},
          "facts": {"area": {"value": "볼 중앙", "source": "voice", "at": "01:05"},
                    "tool": {"value": "", "source": "scene"},
                    "amount": {"value": "조금", "source": "guess"},
                    "tips": [{"value": "톡톡", "source": "voice", "at": "1:2:3:4"}, null],
                    "finishCue": null}}]}
        """;

    GuideInput input = mapper.map(gemini, "abcdefghijk", 600).input();

    Step step = input.steps().getFirst();
    assertThat(step.product()).as("모든 칸이 비면 제품 없음").isNull();
    assertThat(step.facts().area().at()).isEqualTo(65.0);
    assertThat(step.facts().tool()).isNull();
    assertThat(step.facts().amount()).as("모르는 근거 종류").isNull();
    assertThat(step.facts().tips()).hasSize(1);
    assertThat(step.facts().tips().getFirst().at()).as("시각이 틀리면 시각만 뺀다").isNull();
    assertThat(step.facts().cautions()).isEmpty();
    assertThat(GuideInputSchema.violations(objectMapper.writeValueAsString(input))).isEmpty();
  }

  @Test
  void noUsableStepLeavesAnEmptyList() {
    GuideInputMapper.Result result =
        mapper.map("{\"steps\": [" + step(1, "00:10", "00:05") + "]}", "abcdefghijk", 600);

    assertThat(result.input().steps()).isEmpty();
    assertThat(result.dropped()).hasSize(1);
  }

  @Test
  void notJsonOrWithoutStepsIsInvalid() {
    assertThatThrownBy(() -> mapper.map("단계를 찾지 못했습니다", "abcdefghijk", 600))
        .isInstanceOf(InvalidStepOutputException.class);
    assertThatThrownBy(() -> mapper.map("{\"duration\": \"10:00\"}", "abcdefghijk", 600))
        .isInstanceOf(InvalidStepOutputException.class);
  }

  private static String step(int order, String start, String end) {
    return """
        {"order": %d, "makeup": "foundation", "partLabel": "파운데이션", "startTime": "%s",
         "endTime": "%s", "summary": "퍼프로 두드린다", "product": null,
         "facts": {"area": {"value": "얼굴 전체", "source": "scene"}}}"""
        .formatted(order, start, end);
  }
}
