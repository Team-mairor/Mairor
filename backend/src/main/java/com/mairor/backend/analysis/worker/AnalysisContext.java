package com.mairor.backend.analysis.worker;

import java.nio.file.Path;
import java.util.Objects;
import java.util.UUID;

/**
 * 작업 한 번을 처리하는 동안 단계 처리기끼리 넘겨주는 값. 앞 단계가 채우고 뒤 단계가 읽는다(예: 영상 불러오기가 {@link #sourceFile}을 채우면 프레임 추출이
 * 쓴다).
 *
 * @param workDir 이 작업 전용 임시 폴더. 작업이 끝나면 통째로 지운다
 */
public final class AnalysisContext {

  private final UUID jobId;
  private final UUID videoId;
  private final String youtubeVideoId;
  private final String sourceObjectKey;
  private final Path workDir;
  private Path sourceFile;
  private VideoProbe probe;

  public AnalysisContext(
      UUID jobId, UUID videoId, String youtubeVideoId, String sourceObjectKey, Path workDir) {
    this.jobId = Objects.requireNonNull(jobId, "jobId");
    this.videoId = Objects.requireNonNull(videoId, "videoId");
    this.youtubeVideoId = Objects.requireNonNull(youtubeVideoId, "youtubeVideoId");
    this.sourceObjectKey = sourceObjectKey;
    this.workDir = Objects.requireNonNull(workDir, "workDir");
  }

  public UUID jobId() {
    return jobId;
  }

  public UUID videoId() {
    return videoId;
  }

  public String youtubeVideoId() {
    return youtubeVideoId;
  }

  /** 운영자가 올린 영상 파일의 저장소 키. 없으면 {@code null}. */
  public String sourceObjectKey() {
    return sourceObjectKey;
  }

  public Path workDir() {
    return workDir;
  }

  /** 내려받은 영상 파일. 영상 불러오기 단계 전에는 {@code null}. */
  public Path sourceFile() {
    return sourceFile;
  }

  /** 영상 파일의 ffprobe 값. 영상 불러오기 단계 전에는 {@code null}. */
  public VideoProbe probe() {
    return probe;
  }

  void sourceLoaded(Path file, VideoProbe probe) {
    this.sourceFile = Objects.requireNonNull(file, "file");
    this.probe = Objects.requireNonNull(probe, "probe");
  }
}
