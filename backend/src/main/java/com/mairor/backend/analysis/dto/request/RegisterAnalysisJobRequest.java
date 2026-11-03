package com.mairor.backend.analysis.dto.request;

import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.videos.entity.Video;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

/** 운영자 분석 작업 등록. 1차는 영상 메타(제목·채널·길이)를 운영자가 함께 넣는다. */
public record RegisterAnalysisJobRequest(
    @Schema(description = "유튜브 영상 ID(11자)", example = "VxAXD6PP76I")
        @NotBlank
        @Pattern(regexp = "[A-Za-z0-9_-]{11}", message = "유튜브 영상 ID 는 11자의 영문·숫자·_·- 다")
        String youtubeVideoId,
    @Schema(description = "운영자가 저장소에 올린 영상 파일의 키", example = "videos/VxAXD6PP76I/source.mp4")
        @NotBlank
        @Size(max = Video.SOURCE_OBJECT_KEY_MAX_LENGTH)
        @Pattern(regexp = "^(?!/)(?!.*\\.\\.).+$", message = "키는 / 로 시작하거나 .. 을 포함할 수 없다")
        String sourceObjectKey,
    @Schema(description = "영상 제목", example = "완성도 up! 요즘 진짜 예뻐진 메이크업")
        @NotBlank
        @Size(max = Video.TITLE_MAX_LENGTH)
        String title,
    @Schema(description = "채널 이름", example = "GO지승")
        @NotBlank
        @Size(max = Video.CHANNEL_TITLE_MAX_LENGTH)
        String channelTitle,
    @Schema(description = "영상 길이(초)", example = "1858") @NotNull @Positive
        Integer durationSeconds) {

  public AnalysisJobRequest toCommand() {
    return new AnalysisJobRequest(
        youtubeVideoId, sourceObjectKey, title, channelTitle, durationSeconds);
  }
}
