package com.mairor.backend.videos.support;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.external.youtube.YouTubeException;
import org.springframework.http.HttpStatus;

/** 영상 API 의 오류 응답(API 명세 v2 API-VIDEO-001 · 004). */
public final class VideoErrors {

  public static final String VIDEO_PROVIDER_ERROR = "VIDEO_PROVIDER_ERROR";
  public static final String VIDEO_PROVIDER_TIMEOUT = "VIDEO_PROVIDER_TIMEOUT";
  public static final String VIDEO_SEARCH_UNAVAILABLE = "VIDEO_SEARCH_UNAVAILABLE";
  public static final String VIDEO_UNSUPPORTED_FOR_ANALYSIS = "VIDEO_UNSUPPORTED_FOR_ANALYSIS";

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
