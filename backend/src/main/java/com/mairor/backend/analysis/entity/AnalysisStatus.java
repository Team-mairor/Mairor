package com.mairor.backend.analysis.entity;

/** 분석 작업 상태. API 명세 v2 AnalysisJobStatus.status 와 같다. PENDING → RUNNING → COMPLETED | FAILED. */
public enum AnalysisStatus {
  PENDING,
  RUNNING,
  COMPLETED,
  FAILED;

  /** 같은 영상에 하나만 있을 수 있는 진행 중 상태({@code uk_analysis_jobs_video_active})인지. */
  public boolean isActive() {
    return this == PENDING || this == RUNNING;
  }
}
