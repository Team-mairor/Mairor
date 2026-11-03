package com.mairor.backend.analysis.frames;

import com.mairor.backend.analysis.extraction.GuideInput;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

/**
 * 영상에서 뽑을 프레임 번호 목록(현수 레퍼런스 프레임 요청). 기본은 초당 약 2장, 단계 시작·끝 앞뒤 3초는 초당 약 10장이다.
 *
 * <p>규칙은 프레임 번호 {@code n}에 대한 정수 규칙이다: {@code n % gridStep == 0}(격자) 또는 경계 창 안에서 {@code n %
 * windowStep == 0}. ffmpeg 도 {@link #selectExpression()}으로 같은 규칙을 써서, ffmpeg 가 낸 그림의 순서가 곧 이 목록의
 * 순서가 된다. fps 가 정수가 아니면(29.97) 간격이 2·10장에서 조금 어긋난다.
 *
 * <p>영상 끝의 정확한 프레임 수는 ffmpeg 가 풀어 봐야 알므로, 목록은 길이보다 1초 더 길게 만들고 실제로 나온 장수만큼 자른다({@link
 * #truncate(int)}).
 */
public final class FramePlan {

  static final double GRID_FPS = 2.0;
  static final double WINDOW_FPS = 10.0;
  static final double WINDOW_SECONDS = 3.0;

  /** 프레임 번호 구간(양 끝 포함). */
  record Range(long from, long to) {}

  private final double fps;
  private final double durationSeconds;
  private final int gridStep;
  private final int windowStep;
  private final List<Range> windows;
  private final List<PlannedFrame> frames;

  private FramePlan(
      double fps,
      double durationSeconds,
      int gridStep,
      int windowStep,
      List<Range> windows,
      List<PlannedFrame> frames) {
    this.fps = fps;
    this.durationSeconds = durationSeconds;
    this.gridStep = gridStep;
    this.windowStep = windowStep;
    this.windows = windows;
    this.frames = frames;
  }

  public static FramePlan of(double fps, double durationSeconds, List<GuideInput.Step> steps) {
    if (!(fps > 0) || !(durationSeconds > 0)) {
      throw new IllegalArgumentException("fps·길이가 0 보다 커야 합니다: " + fps + ", " + durationSeconds);
    }
    Objects.requireNonNull(steps, "steps");
    int gridStep = Math.max(1, (int) Math.round(fps / GRID_FPS));
    int windowStep = Math.max(1, (int) Math.round(fps / WINDOW_FPS));
    // 실제 마지막 프레임은 ffmpeg 가 알려 준다. 1초 여유를 두고 truncate 로 자른다
    long lastCandidate = (long) Math.ceil((durationSeconds + 1) * fps);
    List<Range> windows = windows(steps, fps, lastCandidate);

    List<PlannedFrame> frames = new ArrayList<>();
    int w = 0;
    for (long n = 0; n <= lastCandidate; n++) {
      while (w < windows.size() && windows.get(w).to() < n) {
        w++;
      }
      boolean inWindow = w < windows.size() && windows.get(w).from() <= n;
      if (n % gridStep == 0 || (inWindow && n % windowStep == 0)) {
        long timestampMs = Math.round(n * 1000.0 / fps);
        frames.add(new PlannedFrame(n, timestampMs, stepAt(steps, timestampMs / 1000.0)));
      }
    }
    return new FramePlan(
        fps, durationSeconds, gridStep, windowStep, List.copyOf(windows), List.copyOf(frames));
  }

  /** 단계 시작·끝 앞뒤 창을 프레임 번호로 바꾸고 겹치는 창은 합친다. */
  private static List<Range> windows(List<GuideInput.Step> steps, double fps, long last) {
    List<Range> raw = new ArrayList<>();
    for (GuideInput.Step step : steps) {
      for (double boundary : new double[] {step.startSeconds(), step.endSeconds()}) {
        long from = Math.max(0, (long) Math.ceil((boundary - WINDOW_SECONDS) * fps));
        long to = Math.min(last, (long) Math.floor((boundary + WINDOW_SECONDS) * fps));
        if (from <= to) {
          raw.add(new Range(from, to));
        }
      }
    }
    raw.sort(Comparator.comparingLong(Range::from));
    List<Range> merged = new ArrayList<>();
    for (Range r : raw) {
      if (!merged.isEmpty() && merged.getLast().to() + 1 >= r.from()) {
        Range prev = merged.removeLast();
        merged.add(new Range(prev.from(), Math.max(prev.to(), r.to())));
      } else {
        merged.add(r);
      }
    }
    return merged;
  }

  /**
   * 그 시각을 포함하는 단계. 없으면 null(맨얼굴·단계 사이). 단계는 단계 추출에서 겹치지 않게 맞춰 오지만, 앞 단계 끝과 뒤 단계 시작이 같은 시각이면 뒤 단계로
   * 본다(늦게 시작한 단계).
   */
  static String stepAt(List<GuideInput.Step> steps, double seconds) {
    GuideInput.Step found = null;
    for (GuideInput.Step step : steps) {
      if (step.startSeconds() <= seconds
          && seconds <= step.endSeconds()
          && (found == null || step.startSeconds() > found.startSeconds())) {
        found = step;
      }
    }
    return found == null ? null : found.stepId();
  }

  /**
   * ffmpeg {@code select} 필터 식. {@link #of}와 같은 정수 규칙이다.
   *
   * <p>예: {@code not(mod(n,30))+not(mod(n,6))*(between(n,0,180)+between(n,600,960))}
   */
  public String selectExpression() {
    StringBuilder expr = new StringBuilder("not(mod(n,").append(gridStep).append("))");
    if (!windows.isEmpty()) {
      expr.append("+not(mod(n,").append(windowStep).append("))*(");
      for (int i = 0; i < windows.size(); i++) {
        Range r = windows.get(i);
        if (i > 0) {
          expr.append('+');
        }
        expr.append("between(n,").append(r.from()).append(',').append(r.to()).append(')');
      }
      expr.append(')');
    }
    return expr.toString();
  }

  /**
   * ffmpeg 가 실제로 낸 장수만큼 자른다. 모자란 프레임이 영상 끝 1초(+여유) 안에만 있어야 한다. 그보다 앞이 모자라면 번호가 어긋난 것이다.
   *
   * @throws IllegalStateException 장수가 계획과 맞지 않으면
   */
  public List<PlannedFrame> truncate(int produced) {
    if (produced > frames.size()) {
      throw new IllegalStateException(
          "ffmpeg 가 계획(" + frames.size() + "장)보다 많이 뽑았습니다: " + produced + "장");
    }
    long mustHave = (long) Math.floor((durationSeconds - 1) * fps);
    long expectedAtLeast = frames.stream().filter(f -> f.frameIndex() <= mustHave).count();
    if (produced < expectedAtLeast) {
      throw new IllegalStateException(
          "ffmpeg 가 계획보다 적게 뽑았습니다: " + produced + "장 (영상 끝 1초 전까지만 " + expectedAtLeast + "장)");
    }
    return frames.subList(0, produced);
  }

  /** 자르기 전 목록(영상 끝 + 1초까지). */
  public List<PlannedFrame> candidates() {
    return frames;
  }

  int gridStep() {
    return gridStep;
  }

  int windowStep() {
    return windowStep;
  }

  List<Range> windows() {
    return windows;
  }
}
