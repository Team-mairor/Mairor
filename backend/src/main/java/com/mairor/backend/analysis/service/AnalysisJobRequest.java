package com.mairor.backend.analysis.service;

/**
 * 분석 작업 접수 입력. 1차는 운영자가 영상 메타를 함께 넣는다(YouTube Data API 연동은 6단계).
 *
 * @param sourceObjectKey 운영자가 저장소에 올린 영상 파일의 키
 */
public record AnalysisJobRequest(
    String youtubeVideoId,
    String sourceObjectKey,
    String title,
    String channelTitle,
    int durationSeconds) {}
