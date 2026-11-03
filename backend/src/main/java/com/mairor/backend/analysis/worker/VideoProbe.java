package com.mairor.backend.analysis.worker;

/** ffprobe 로 잰 영상 파일의 원본 정보. */
public record VideoProbe(int width, int height, double fps, double durationSeconds) {}
