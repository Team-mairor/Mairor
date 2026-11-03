package com.mairor.backend.analysis.frames;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assumptions.assumeThat;

import com.mairor.backend.analysis.extraction.GuideInput;
import com.mairor.backend.analysis.worker.WorkerProperties;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 진짜 ffmpeg 로 합성 영상(ffmpeg {@code testsrc2})에서 뽑는다. CI 이미지·개발 PC 에 ffmpeg 가 없을 수 있어 PATH 에 있을 때만
 * 돈다(없으면 건너뜀).
 */
class FrameExtractorTest {

  private final FrameExtractor extractor =
      new FrameExtractor(
          new WorkerProperties(
              Duration.ofSeconds(5),
              Path.of("."),
              "ffprobe",
              Duration.ofSeconds(30),
              "ffmpeg",
              Duration.ofMinutes(2),
              2));

  @Test
  void extractsExactlyThePlannedFramesAtFullSize(@TempDir Path dir) throws Exception {
    assumeThat(ffmpegAvailable()).as("PATH 에 ffmpeg 가 있을 때만").isTrue();
    Path video = syntheticVideo(dir, 6, 30);
    GuideInput.Step step =
        new GuideInput.Step("s1", 1, 2.0, 4.0, "blush", "블러셔", "바른다", null, null);
    FramePlan plan = FramePlan.of(30, 6.0, List.of(step));

    List<Path> files = extractor.extract(video, plan, dir.resolve("frames"));
    List<PlannedFrame> frames = plan.truncate(files.size());

    // 6초 · 30fps = 0~179번. 2초 창(0~150)과 4초 창(30~210)이 합쳐져 영상 전체가 3장 간격(초당 10장) → 0, 3, …, 177
    assertThat(frames.getFirst().frameIndex()).isZero();
    assertThat(frames.getLast().frameIndex()).isEqualTo(177);
    assertThat(files).hasSize(60);
    assertThat(frames.get(20).stepId()).as("2.0초 = 60번").isEqualTo("s1");
    assertThat(frames.get(19).stepId()).isNull();
    assertThat(files.getFirst().getFileName().toString()).isEqualTo("000001.jpg");
    BufferedImage first = ImageIO.read(files.getFirst().toFile());
    assertThat(first.getWidth()).isEqualTo(640);
    assertThat(first.getHeight()).isEqualTo(360);
  }

  @Test
  void notAVideoFails(@TempDir Path dir) throws IOException {
    assumeThat(ffmpegAvailable()).as("PATH 에 ffmpeg 가 있을 때만").isTrue();
    Path notVideo = Files.writeString(dir.resolve("source.mp4"), "not a video");
    FramePlan plan = FramePlan.of(30, 6.0, List.of());

    assertThatThrownBy(() -> extractor.extract(notVideo, plan, dir.resolve("frames")))
        .isInstanceOf(FrameExtractionException.class)
        .hasMessageContaining("ffmpeg 가 실패했습니다");
  }

  private static Path syntheticVideo(Path dir, int seconds, int fps) throws Exception {
    Path video = dir.resolve("source.mp4");
    Process process =
        new ProcessBuilder(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=" + fps + ":duration=" + seconds,
                "-pix_fmt",
                "yuv420p",
                video.toString())
            .redirectErrorStream(true)
            .redirectOutput(ProcessBuilder.Redirect.DISCARD)
            .start();
    assertThat(process.waitFor(60, TimeUnit.SECONDS)).isTrue();
    assertThat(process.exitValue()).isZero();
    return video;
  }

  private static boolean ffmpegAvailable() {
    try {
      Process process = new ProcessBuilder("ffmpeg", "-version").start();
      process.getInputStream().readAllBytes();
      return process.waitFor(5, TimeUnit.SECONDS) && process.exitValue() == 0;
    } catch (IOException e) {
      return false;
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      return false;
    }
  }
}
