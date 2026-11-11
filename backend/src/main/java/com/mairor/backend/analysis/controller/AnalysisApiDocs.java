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

  static final String LIST =
      """
      {
        "items": [
          {
            "jobId": "2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f",
            "videoId": "7d3e2a1b-6c5f-4e8d-9a0b-2c3d4e5f6a7b",
            "youtubeVideoId": "VxAXD6PP76I",
            "title": "완성도 up! 데일리 메이크업",
            "thumbnailUrl": "https://i.ytimg.com/vi/VxAXD6PP76I/hqdefault.jpg",
            "status": "COMPLETED",
            "reviewStatus": "PENDING",
            "guideId": null,
            "requestedAt": "2026-11-11T00:42:24Z",
            "reviewedAt": null
          },
          {
            "jobId": "5a6b7c8d-1e2f-4a3b-9c4d-5e6f7a8b9c0d",
            "videoId": "3f4e5d6c-7b8a-4c9d-8e0f-1a2b3c4d5e6f",
            "youtubeVideoId": "aBcDeFgHiJk",
            "title": "봄 코랄 메이크업",
            "thumbnailUrl": null,
            "status": "COMPLETED",
            "reviewStatus": "APPROVED",
            "guideId": "8e9f0a1b-2c3d-4e5f-a6b7-c8d9e0f1a2b3",
            "requestedAt": "2026-11-10T09:15:00Z",
            "reviewedAt": "2026-11-10T11:02:00Z"
          }
        ],
        "page": 0,
        "size": 20,
        "hasNext": false
      }""";
}
