package com.mairor.backend.analysis.worker;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assumptions.assumeThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.json.JsonMapper;

/**
 * ffprobe 출력 해석은 고정 JSON 으로 확인한다(CI 이미지와 개발 PC 에 ffprobe 가 없을 수 있다). 실제 ffprobe 실행은 PATH 에 ffmpeg 가
 * 있을 때만 돈다.
 */
class FfprobeTest {

  private final Ffprobe ffprobe =
      new Ffprobe(
          new WorkerProperties(
              Duration.ofSeconds(5), Path.of("."), "ffprobe", Duration.ofSeconds(30)),
          JsonMapper.builder().build());

  @Test
  void parsesSizeFpsAndDurationFromTheFirstVideoStream() {
    String json =
        """
        {"streams": [
          {"codec_type": "audio", "sample_rate": "48000"},
          {"codec_type": "video", "width": 1920, "height": 1080,
           "avg_frame_rate": "60/1", "r_frame_rate": "60/1", "duration": "1858.200000"}],
         "format": {"duration": "1858.233000"}}
        """;

    VideoProbe probe = ffprobe.parse(json);

    assertThat(probe).isEqualTo(new VideoProbe(1920, 1080, 60.0, 1858.233));
  }

  @Test
  void ntscFrameRateAndMissingFormatDurationFallBack() {
    String json =
        """
        {"streams": [{"codec_type": "video", "width": 1280, "height": 720,
           "avg_frame_rate": "0/0", "r_frame_rate": "30000/1001", "duration": "12.5"}],
         "format": {}}
        """;

    VideoProbe probe = ffprobe.parse(json);

    assertThat(probe.fps()).isCloseTo(29.97, org.assertj.core.data.Offset.offset(0.01));
    assertThat(probe.durationSeconds()).isEqualTo(12.5);
  }

  @Test
  void fileWithoutVideoStreamIsUnreadable() {
    String json =
        """
        {"streams": [{"codec_type": "audio"}], "format": {"duration": "10.0"}}
        """;

    assertThatThrownBy(() -> ffprobe.parse(json))
        .isInstanceOf(FfprobeException.class)
        .hasMessageContaining("영상 스트림이 없습니다");
  }

  @Test
  void notJsonIsUnreadable() {
    assertThatThrownBy(() -> ffprobe.parse("Invalid data found when processing input"))
        .isInstanceOf(FfprobeException.class);
  }

  @Test
  void realFfprobeRejectsAFileThatIsNotAVideo(@TempDir Path dir) throws IOException {
    assumeThat(ffprobeAvailable()).as("PATH 에 ffprobe 가 있을 때만").isTrue();
    Path notVideo = Files.writeString(dir.resolve("source.mp4"), "not a video");

    assertThatThrownBy(() -> ffprobe.probe(notVideo)).isInstanceOf(FfprobeException.class);
  }

  private static boolean ffprobeAvailable() {
    try {
      Process process = new ProcessBuilder("ffprobe", "-version").start();
      return process.waitFor(5, TimeUnit.SECONDS) && process.exitValue() == 0;
    } catch (IOException e) {
      return false;
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      return false;
    }
  }
}
