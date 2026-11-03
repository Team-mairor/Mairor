package com.mairor.backend.analysis.frames;

import java.util.List;
import java.util.Objects;

/**
 * 프레임 목록({@code videos/{videoId}/jobs/{jobId}/frames.json}). 현수 요청의 칸과 같고, {@code url} 대신 저장소
 * {@code key}를 둔다. 사전 서명 URL 은 만료가 있어서 AI 요청을 보낼 때(-311) 이 키로 만든다.
 *
 * @param videoId 유튜브 영상 ID
 * @param jobId 이 목록을 만든 분석 작업(단계가 작업마다 달라 {@code stepId}가 다르다)
 */
public record FrameManifest(String videoId, String jobId, Source source, List<Item> items) {

  public FrameManifest {
    Objects.requireNonNull(videoId, "videoId");
    Objects.requireNonNull(source, "source");
    items = List.copyOf(items);
  }

  /** 프레임을 뽑은 원본 영상. 길이는 가이드 입력의 {@code durationSeconds}를 쓴다. */
  public record Source(int width, int height, double fps) {}

  /**
   * @param stepId 그 시각이 속한 단계. 맨얼굴·단계 사이는 null
   * @param key 저장소 키 {@code videos/{videoId}/frames/{frameIndex:06d}.jpg}
   */
  public record Item(
      long frameIndex, long timestampMs, String stepId, String key, int width, int height) {}

  /** 시각 구간(양 끝 포함)의 프레임. 현수 요청 "영상 ID 와 시작·끝 시각으로 목록 조회"용. */
  public List<Item> between(long fromMs, long toMs) {
    return items.stream()
        .filter(i -> i.timestampMs() >= fromMs && i.timestampMs() <= toMs)
        .toList();
  }

  public List<Item> forStep(String stepId) {
    return items.stream().filter(i -> Objects.equals(i.stepId(), stepId)).toList();
  }
}
