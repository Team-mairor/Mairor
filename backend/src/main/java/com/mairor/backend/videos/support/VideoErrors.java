package com.mairor.backend.videos.support;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import org.springframework.http.HttpStatus;

/** 영상 API 의 오류 응답(API 명세 v2 API-VIDEO-001 · 002 · 004 · 005). */
public final class VideoErrors {

  public static final String VIDEO_PROVIDER_ERROR = "VIDEO_PROVIDER_ERROR";
  public static final String VIDEO_PROVIDER_TIMEOUT = "VIDEO_PROVIDER_TIMEOUT";
  public static final String VIDEO_SEARCH_UNAVAILABLE = "VIDEO_SEARCH_UNAVAILABLE";
  public static final String VIDEO_UNSUPPORTED_FOR_ANALYSIS = "VIDEO_UNSUPPORTED_FOR_ANALYSIS";
  public static final String VIDEO_ANALYSIS_UNAVAILABLE = "VIDEO_ANALYSIS_UNAVAILABLE";
  public static final String VIDEO_POPULAR_UNAVAILABLE = "VIDEO_POPULAR_UNAVAILABLE";

  private VideoErrors() {}

  /**
   * 검색 중 YouTube 실패. 할당량 · 키 없음은 503(검색을 지금 쓸 수 없음), 시간 초과는 504, 그 밖은 502. 빈 결과나 다른 목록으로 대신하지
   * 않는다(명세).
   */
  public static BusinessException forSearch(YouTubeException e) {
    return switch (e.kind()) {
      case QUOTA_EXCEEDED, NOT_CONFIGURED ->
          new BusinessException(
              HttpStatus.SERVICE_UNAVAILABLE,
              VIDEO_SEARCH_UNAVAILABLE,
              "지금은 영상 검색을 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.");
      case TIMEOUT -> timeout();
      case UNAVAILABLE -> providerError();
    };
  }

  /** 선택 중 YouTube 실패. 명세의 선택 오류는 502 · 504 뿐이라 할당량 · 키 없음도 502 다. */
  public static BusinessException forSelection(YouTubeException e) {
    return e.kind() == YouTubeException.Kind.TIMEOUT ? timeout() : providerError();
  }

  /**
   * 분석 요청(API-VIDEO-002) 중 라이선스 재확인이 YouTube 실패로 막힘. 명세의 분석 요청 오류에 502 · 504 가 없어 할당량 · 키 없음 · 시간
   * 초과 · 그 밖 모두 503 이다.
   */
  public static BusinessException forAnalysisRequest(YouTubeException e) {
    return new BusinessException(
        HttpStatus.SERVICE_UNAVAILABLE,
        VIDEO_ANALYSIS_UNAVAILABLE,
        "지금은 분석을 요청할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  }

  /**
   * 분석할 수 있는 영상인지 본다: 공개 · 연령 제한 없음 · 라이브 · 예정 아님 · CC BY. 영상 선택(001)과 분석 요청(002)이 같은 기준을 쓴다.
   *
   * @throws BusinessException 409 {@code VIDEO_UNSUPPORTED_FOR_ANALYSIS} — 하나라도 어긋나면
   */
  public static void checkAnalyzable(YouTubeVideo video) {
    if (!"public".equals(video.privacyStatus())) {
      throw unsupported("공개 영상이 아닙니다.");
    }
    if (video.ageRestricted()) {
      throw unsupported("연령 제한 영상입니다.");
    }
    if (!"none".equals(video.liveBroadcastContent()) || video.durationSeconds() <= 0) {
      throw unsupported("라이브 · 예정 영상입니다.");
    }
    if (!video.creativeCommon()) {
      throw unsupported("크리에이티브 커먼즈(CC BY) 영상만 분석할 수 있습니다.");
    }
  }

  /** 인기 영상(API-VIDEO-005)을 셀 선택 기록이 기간 안에 하나도 없음. 승인 가이드 목록 같은 다른 목록으로 대신하지 않는다(명세). */
  public static BusinessException popularUnavailable() {
    return new BusinessException(
        HttpStatus.SERVICE_UNAVAILABLE, VIDEO_POPULAR_UNAVAILABLE, "아직 인기 영상을 보여 드릴 수 없습니다.");
  }

  public static BusinessException unsupported(String reason) {
    return new BusinessException(
        HttpStatus.CONFLICT, VIDEO_UNSUPPORTED_FOR_ANALYSIS, "분석할 수 없는 영상입니다. " + reason);
  }

  private static BusinessException timeout() {
    return new BusinessException(
        HttpStatus.GATEWAY_TIMEOUT, VIDEO_PROVIDER_TIMEOUT, "영상 정보를 가져오는 데 시간이 너무 오래 걸립니다.");
  }

  private static BusinessException providerError() {
    return new BusinessException(
        HttpStatus.BAD_GATEWAY, VIDEO_PROVIDER_ERROR, "영상 정보를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.");
  }
}
