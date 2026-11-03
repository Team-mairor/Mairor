package com.mairor.backend.analysis.worker;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * ffprobe 로 영상 파일의 가로·세로·fps·길이를 잰다. 운영 이미지({@code backend/Dockerfile})에는 ffmpeg 와 함께 들어 있다.
 *
 * <p>출력은 표준 출력이 아니라 작업 폴더의 파일로 받는다. 파이프로 받으면 출력이 커질 때 버퍼가 차서 프로세스가 멈출 수 있다.
 */
@Component
public class Ffprobe {

  private final WorkerProperties properties;
  private final ObjectMapper objectMapper;

  public Ffprobe(WorkerProperties properties, ObjectMapper objectMapper) {
    this.properties = properties;
    this.objectMapper = objectMapper;
  }

  /**
   * @throws FfprobeException 실행 실패·시간 초과·영상 스트림 없음
   */
  public VideoProbe probe(Path video) {
    Path workDir = video.toAbsolutePath().getParent();
    Path out = workDir.resolve("ffprobe.json");
    Path err = workDir.resolve("ffprobe.err");
    List<String> command =
        List.of(
            properties.ffprobePath(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            video.toAbsolutePath().toString());
    try {
      Process process =
          new ProcessBuilder(command)
              .redirectOutput(out.toFile())
              .redirectError(err.toFile())
              .start();
      if (!process.waitFor(properties.ffprobeTimeout().toMillis(), TimeUnit.MILLISECONDS)) {
        process.destroyForcibly();
        throw new FfprobeException("ffprobe 가 " + properties.ffprobeTimeout() + " 안에 끝나지 않았습니다.");
      }
      if (process.exitValue() != 0) {
        throw new FfprobeException(
            "ffprobe 가 실패했습니다(종료 코드 " + process.exitValue() + "): " + firstLine(err));
      }
      return parse(Files.readString(out, StandardCharsets.UTF_8));
    } catch (IOException e) {
      throw new FfprobeException("ffprobe 를 실행하지 못했습니다: " + e.getMessage(), e);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new FfprobeException("ffprobe 를 기다리다 중단됐습니다.", e);
    }
  }

  /**
   * ffprobe JSON 에서 첫 영상 스트림의 크기·평균 fps 와 파일 길이를 꺼낸다. 길이는 {@code format.duration}, 없으면 스트림의 {@code
   * duration}이다.
   *
   * @throws FfprobeException 영상 스트림이 없거나 값이 비었으면
   */
  VideoProbe parse(String json) {
    JsonNode root;
    try {
      root = objectMapper.readTree(json);
    } catch (JacksonException e) {
      throw new FfprobeException("ffprobe 출력이 JSON 이 아닙니다.", e);
    }
    JsonNode video = null;
    for (JsonNode stream : root.path("streams")) {
      if ("video".equals(stream.path("codec_type").asString(""))) {
        video = stream;
        break;
      }
    }
    if (video == null) {
      throw new FfprobeException("영상 스트림이 없습니다.");
    }
    int width = video.path("width").asInt(0);
    int height = video.path("height").asInt(0);
    double fps = rate(video.path("avg_frame_rate").asString(""));
    if (fps <= 0) {
      fps = rate(video.path("r_frame_rate").asString(""));
    }
    double duration = number(root.path("format").path("duration").asString(""));
    if (duration <= 0) {
      duration = number(video.path("duration").asString(""));
    }
    if (width <= 0 || height <= 0 || fps <= 0 || duration <= 0) {
      throw new FfprobeException(
          "영상 정보가 비었습니다: width=%d height=%d fps=%s duration=%s"
              .formatted(width, height, fps, duration));
    }
    return new VideoProbe(width, height, fps, duration);
  }

  /** {@code "60000/1001"} 같은 분수 → 59.94. 해석할 수 없으면 0. */
  private static double rate(String value) {
    int slash = value.indexOf('/');
    if (slash < 0) {
      return number(value);
    }
    double numerator = number(value.substring(0, slash));
    double denominator = number(value.substring(slash + 1));
    return denominator > 0 ? numerator / denominator : 0;
  }

  private static double number(String value) {
    try {
      return Double.parseDouble(value);
    } catch (NumberFormatException e) {
      return 0;
    }
  }

  private static String firstLine(Path file) throws IOException {
    if (!Files.exists(file)) {
      return "";
    }
    return Files.readAllLines(file, StandardCharsets.UTF_8).stream().findFirst().orElse("").strip();
  }
}
