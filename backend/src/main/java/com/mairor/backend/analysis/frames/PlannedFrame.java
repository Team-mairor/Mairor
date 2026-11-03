package com.mairor.backend.analysis.frames;

/**
 * 뽑을 프레임 하나.
 *
 * @param frameIndex 원본 영상의 몇 번째 프레임인지(0 부터)
 * @param timestampMs 영상 시각 = round(frameIndex × 1000 / fps)
 * @param stepId 그 시각이 속한 단계. 맨얼굴·단계 사이는 null
 */
public record PlannedFrame(long frameIndex, long timestampMs, String stepId) {}
