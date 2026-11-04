package com.mairor.backend.analysis.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.service.StageProgress.Item;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class StageProgressTest {

  private static final JsonMapper JSON = JsonMapper.builder().build();

  private static JsonNode progress(
      String explanation, String frames, String landmarks, String area) {
    return JSON.readTree(
        "{\"explanation\": "
            + explanation
            + ", \"frames\": "
            + frames
            + ", \"landmarks\": "
            + landmarks
            + ", \"area\": "
            + area
            + "}");
  }

  private static StageProgress building(JsonNode progress) {
    return StageProgress.of(AnalysisStatus.RUNNING, ProgressStage.BUILDING_GUIDE, progress);
  }

  private static String count(long done, long total) {
    return "{\"done\": " + done + ", \"total\": " + total + "}";
  }

  @Test
  void nothingToShowOutsideTheGuideStageOrBeforeTheFirstProgress() {
    JsonNode any = progress(count(1, 19), "null", "null", "null");

    assertThat(StageProgress.of(AnalysisStatus.RUNNING, ProgressStage.SEGMENTING, any)).isNull();
    assertThat(StageProgress.of(AnalysisStatus.PENDING, ProgressStage.QUEUED, null)).isNull();
    assertThat(building(null)).as("진행 알림 전").isNull();
  }

  @Test
  void finishedJobsShowTheFinalStateNotTheLastNumbers() {
    JsonNode any = progress(count(19, 19), count(10, 10), count(10, 10), count(19, 19));

    assertThat(StageProgress.of(AnalysisStatus.COMPLETED, ProgressStage.DONE, any)).isNull();
    assertThat(StageProgress.of(AnalysisStatus.FAILED, ProgressStage.BUILDING_GUIDE, any)).isNull();
  }

  @Test
  void jobWithoutFramesShowsTheExplanation() {
    assertThat(building(progress(count(3, 19), "null", "null", "null")))
        .isEqualTo(new StageProgress(Item.EXPLANATION, 3, 19));
  }

  @Test
  void areaSideShowsWhateverIsInProgressInOrder() {
    assertThat(building(progress(count(0, 19), count(400, 2000), count(0, 2000), count(0, 19))))
        .isEqualTo(new StageProgress(Item.FRAMES, 400, 2000));
    assertThat(building(progress(count(0, 19), count(2000, 2000), count(840, 2000), count(0, 19))))
        .isEqualTo(new StageProgress(Item.LANDMARKS, 840, 2000));
    assertThat(building(progress(count(0, 19), count(2000, 2000), count(2000, 2000), count(8, 19))))
        .isEqualTo(new StageProgress(Item.AREA, 8, 19));
  }

  @Test
  void whenTheAreaSideIsDoneTheRemainingExplanationIsShown() {
    assertThat(
            building(progress(count(15, 19), count(2000, 2000), count(2000, 2000), count(19, 19))))
        .isEqualTo(new StageProgress(Item.EXPLANATION, 15, 19));
  }

  @Test
  void stalledAreaNumbersStayUntilTheCallback() {
    // 영역 계산이 통째로 실패하면 AI 는 숫자를 멈춘 채 설명을 계속한다. 콜백 전까지는 멈춘 영역 숫자가 보인다
    assertThat(
            building(progress(count(19, 19), count(2000, 2000), count(1200, 2000), count(0, 19))))
        .isEqualTo(new StageProgress(Item.LANDMARKS, 1200, 2000));
  }
}
