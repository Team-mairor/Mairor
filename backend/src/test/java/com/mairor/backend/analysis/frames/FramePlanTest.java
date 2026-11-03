package com.mairor.backend.analysis.frames;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.analysis.extraction.GuideInput;
import java.util.List;
import org.junit.jupiter.api.Test;

class FramePlanTest {

  private static GuideInput.Step step(String id, double start, double end) {
    return new GuideInput.Step(id, 1, start, end, "blush", "블러셔", "바른다", null, null);
  }

  @Test
  void withoutStepsItIsTwoFramesPerSecond() {
    FramePlan plan = FramePlan.of(60, 10, List.of());

    assertThat(plan.gridStep()).isEqualTo(30);
    assertThat(plan.selectExpression()).isEqualTo("not(mod(n,30))");
    // 0..11초(길이 + 1초 여유) 격자: 0, 30, …, 660
    assertThat(plan.candidates()).hasSize(23);
    assertThat(plan.candidates().get(1).frameIndex()).isEqualTo(30);
    assertThat(plan.candidates().get(1).timestampMs()).isEqualTo(500);
    assertThat(plan.candidates()).allSatisfy(f -> assertThat(f.stepId()).isNull());
  }

  @Test
  void stepBoundariesGetTenFramesPerSecondForThreeSecondsEachSide() {
    FramePlan plan = FramePlan.of(60, 60, List.of(step("s1", 20, 30)));

    assertThat(plan.windowStep()).isEqualTo(6);
    assertThat(plan.windows())
        .containsExactly(new FramePlan.Range(1020, 1380), new FramePlan.Range(1620, 1980));
    assertThat(plan.selectExpression())
        .isEqualTo("not(mod(n,30))+not(mod(n,6))*(between(n,1020,1380)+between(n,1620,1980))");
    List<PlannedFrame> nearStart =
        plan.candidates().stream()
            .filter(f -> f.timestampMs() >= 17_000 && f.timestampMs() <= 23_000)
            .toList();
    assertThat(nearStart).hasSize(61).as("17~23초를 0.1초마다");
    assertThat(plan.candidates())
        .filteredOn(f -> f.timestampMs() > 40_000 && f.timestampMs() < 50_000)
        .hasSize(19)
        .as("창 밖은 0.5초마다");
  }

  @Test
  void stepIdIsTheStepThatContainsTheTimeAndTheLaterOneWhenTheyOverlap() {
    List<GuideInput.Step> steps = List.of(step("s1", 10, 20), step("s2", 18, 19));

    assertThat(FramePlan.stepAt(steps, 5)).isNull();
    assertThat(FramePlan.stepAt(steps, 10)).isEqualTo("s1");
    assertThat(FramePlan.stepAt(steps, 18.5)).isEqualTo("s2");
    assertThat(FramePlan.stepAt(steps, 19.5)).isEqualTo("s1");
    assertThat(FramePlan.stepAt(steps, 20)).isEqualTo("s1");
    assertThat(FramePlan.stepAt(steps, 20.5)).isNull();
  }

  @Test
  void windowsAreClippedAtTheStartAndMergedWhenTheyTouch() {
    FramePlan plan = FramePlan.of(30, 60, List.of(step("s1", 1, 5), step("s2", 6, 9)));

    // 1초 창(-2~4초)은 0 에서 자르고, 1·5·6·9초 창이 서로 겹쳐 0~12초 하나가 된다
    assertThat(plan.windows()).containsExactly(new FramePlan.Range(0, 360));
  }

  @Test
  void nonIntegerFpsRoundsTheSteps() {
    FramePlan plan = FramePlan.of(29.97, 10, List.of());

    assertThat(plan.gridStep()).isEqualTo(15);
    assertThat(plan.candidates().get(1).timestampMs()).isEqualTo(Math.round(15 * 1000 / 29.97));
  }

  @Test
  void truncateKeepsWhatFfmpegProducedButNotFewerThanTheVideoBody() {
    FramePlan plan = FramePlan.of(60, 10, List.of());
    int all = plan.candidates().size(); // 23장: 0..11초

    assertThat(plan.truncate(21)).hasSize(21).as("끝 1초 여유분이 없을 수 있다");
    assertThatThrownBy(() -> plan.truncate(all + 1)).isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> plan.truncate(5))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("적게");
  }
}
