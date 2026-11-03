package com.mairor.backend.analysis.entity;

/**
 * 분석 진행 단계. API 명세 v2 AnalysisJobStatus.progressStage 와 같고, FE 로딩 화면의 "대기 → 영상 불러오기 → 구간 나누기 → 제품
 * 인식 → 단계 추출 → 가이드 구성" 순서다. FAILED 작업에서는 멈춘 단계를 가리킨다.
 */
public enum ProgressStage {
  QUEUED,
  LOADING_VIDEO,
  SEGMENTING,
  RECOGNIZING_PRODUCTS,
  EXTRACTING_STEPS,
  BUILDING_GUIDE,
  DONE
}
