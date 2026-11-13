package com.mairor.backend.analysis.service;

/**
 * 분석 작업 접수 입력. 영상 메타를 함께 넣는다. 운영자 등록 API 는 지웠고(S15P31A306-409) 지금은 worker · 노트북 흐름 테스트가 쓴다.
 *
 * @param sourceObjectKey 운영자가 저장소에 올린 영상 파일의 키
 */
public record AnalysisJobRequest(
    String youtubeVideoId,
    String sourceObjectKey,
    String title,
    String channelTitle,
    int durationSeconds) {}
