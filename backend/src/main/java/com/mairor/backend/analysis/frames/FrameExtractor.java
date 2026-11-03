package com.mairor.backend.analysis.frames;

import com.mairor.backend.analysis.worker.WorkerProperties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;
import org.springframework.stereotype.Component;

/**
 * ffmpeg 한 번으로 {@link FramePlan}의 프레임만 원본 해상도 JPEG 로 뽑는다. 크기·색은 바꾸지 않는다(현수 요청: 보정 없음, 품질 95 이상 →
 * {@code -q:v 2}).
 *
 * <p>{@code -fps_mode passthrough}로 고른 프레임을 그대로 내보내므로, 나온 파일의 순서({@code 000001.jpg}…)가 계획의 순서다. 장수는
 * {@link FramePlan#truncate(int)}가 맞춰 본다.
 */
@Component
public class FrameExtractor {

  static final String PATTERN = "%06d.jpg";

  private final WorkerProperties properties;

  public FrameExtractor(WorkerProperties properties) {
    this.properties = properties;
  }

  /**
   * @param outDir 비어 있는 폴더. 여기에 {@code 000001.jpg}부터 쓴다
   * @return 뽑힌 파일(이름 순 = 계획 순)
   * @throws FrameExtractionException 실행 실패·시간 초과
   */
  public List<Path> extract(Path video, FramePlan plan, Path outDir) {
    Path err = outDir.resolveSibling("ffmpeg.err");
    List<String> command =
        List.of(
            properties.ffmpegPath(),
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video.toAbsolutePath().toString(),
            "-vf",
            "select='" + plan.selectExpression() + "'",
            "-fps_mode",
            "passthrough",
            "-q:v",
            "2",
            "-f",
            "image2",
            outDir.resolve(PATTERN).toAbsolutePath().toString());
    try {
      Files.createDirectories(outDir);
      Process process =
          new ProcessBuilder(command)
              .redirectOutput(ProcessBuilder.Redirect.DISCARD)
              .redirectError(err.toFile())
              .start();
      if (!process.waitFor(properties.ffmpegTimeout().toMillis(), TimeUnit.MILLISECONDS)) {
        process.destroyForcibly();
        throw new FrameExtractionException(
            "ffmpeg 가 " + properties.ffmpegTimeout() + " 안에 끝나지 않았습니다.", null);
      }
      if (process.exitValue() != 0) {
        throw new FrameExtractionException(
            "ffmpeg 가 실패했습니다(종료 코드 " + process.exitValue() + "): " + lastLine(err), null);
      }
      try (Stream<Path> files = Files.list(outDir)) {
        return files.filter(p -> p.getFileName().toString().endsWith(".jpg")).sorted().toList();
      }
    } catch (IOException e) {
      throw new FrameExtractionException("ffmpeg 를 실행하지 못했습니다: " + e.getMessage(), e);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new FrameExtractionException("ffmpeg 를 기다리다 중단됐습니다.", e);
    }
  }

  private static String lastLine(Path err) {
    try {
      List<String> lines =
          Files.readAllLines(err, StandardCharsets.UTF_8).stream()
              .filter(l -> !l.isBlank())
              .toList();
      return lines.isEmpty() ? "" : lines.getLast().trim();
    } catch (IOException e) {
      return "";
    }
  }
}
