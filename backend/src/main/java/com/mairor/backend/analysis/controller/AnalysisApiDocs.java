package com.mairor.backend.analysis.controller;

/** 분석 작업 API 문서의 응답 예시. 애너테이션 값으로 쓰려고 상수로 둔다. */
final class AnalysisApiDocs {

  private AnalysisApiDocs() {}

  static final String STATUS_RUNNING =
      """
      {
        "jobId": "2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f",
        "videoId": "7d3e2a1b-6c5f-4e8d-9a0b-2c3d4e5f6a7b",
        "status": "RUNNING",
        "progressStage": "BUILDING_GUIDE",
        "progressPercent": null,
        "estimatedRemainingSeconds": null,
        "stageProgress": {"item": "LANDMARKS", "done": 840, "total": 2000},
        "retryable": false,
        "reviewStatus": "NOT_READY",
        "guideAvailable": false,
        "guideId": null,
        "foundProducts": [],
        "foundProductCount": 0,
        "totalProductCount": null,
        "failureCode": null,
        "failureMessage": null,
        "pollAfterSeconds": 3,
        "createdAt": "2026-11-03T03:00:00Z",
        "completedAt": null
      }""";
}
