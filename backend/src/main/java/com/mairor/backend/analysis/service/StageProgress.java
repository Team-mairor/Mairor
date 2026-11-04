package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * 지금 진행 단계 안에서 센 수. 화면은 "가이드 생성 중: 얼굴 분석 840 / 2,000장"처럼 보인다. 전체 %가 아니다.
 *
 * <p>지금은 가이드 구성(BUILDING_GUIDE)에서만 있다. AI 진행 알림의 숫자 넷(설명·사진·얼굴 점·영역) 중 오래 걸리는 쪽에서 지금 진행 중인 것을
 * 고른다(ADR-012 「진행률 계산」). 다른 단계는 아직 셀 숫자를 남기지 않아 {@code null}이다.
 *
 * @param item 무엇을 센 수인지
 * @param done 끝난 수(실패한 것 포함)
 * @param total 전체 수
 */
public record StageProgress(Item item, long done, long total) {

  /** 센 대상. 사진·얼굴 점은 장, 영역·설명은 단계 수다. */
  public enum Item {
    FRAMES,
    LANDMARKS,
    AREA,
    EXPLANATION
  }

  /** 영역 쪽 숫자. AI 는 이 순서로 차례로 올린다(사진 받기 → 얼굴 점 → 영역). */
  private static final List<Item> AREA_ORDER = List.of(Item.FRAMES, Item.LANDMARKS, Item.AREA);

  /**
   * 저장된 진행 숫자에서 지금 보일 것을 고른다.
   *
   * <ul>
   *   <li>가이드 구성 중이 아니거나 진행 알림을 아직 못 받았으면 {@code null}
   *   <li>프레임 없이 맡긴 작업({@code frames}가 {@code null})이면 설명
   *   <li>영역 쪽이 남았으면 사진 → 얼굴 점 → 영역 중 처음으로 덜 끝난 것. 영역 쪽이 다 끝났으면 설명
   * </ul>
   *
   * <p>완료는 숫자가 아니라 작업 상태로만 본다. 영역 계산이 통째로 실패하면 AI 는 영역 숫자를 멈춘 채 설명을 계속하므로, 콜백이 올 때까지 멈춘 영역 숫자가 보인다.
   *
   * @param progress 진행 알림 숫자({@code AiProgressService}가 검사해 저장한 모양). 없으면 {@code null}
   */
  public static StageProgress of(AnalysisStatus status, ProgressStage stage, JsonNode progress) {
    if (status != AnalysisStatus.RUNNING
        || stage != ProgressStage.BUILDING_GUIDE
        || progress == null
        || !progress.isObject()) {
      return null;
    }
    StageProgress explanation = count(Item.EXPLANATION, progress.get("explanation"));
    if (isNull(progress.get("frames"))) {
      return explanation;
    }
    for (Item item : AREA_ORDER) {
      StageProgress count = count(item, progress.get(item.name().toLowerCase()));
      if (count == null) {
        return explanation;
      }
      if (count.done() < count.total()) {
        return count;
      }
    }
    return explanation;
  }

  private static StageProgress count(Item item, JsonNode node) {
    if (node == null || !node.isObject()) {
      return null;
    }
    return new StageProgress(item, node.path("done").asLong(0), node.path("total").asLong(0));
  }

  private static boolean isNull(JsonNode node) {
    return node == null || node.isNull();
  }
}
