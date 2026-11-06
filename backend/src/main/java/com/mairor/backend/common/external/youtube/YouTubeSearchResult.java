package com.mairor.backend.common.external.youtube;

import java.util.List;

/**
 * {@code search.list} 한 페이지.
 *
 * @param videoIds 관련도순 영상 ID
 * @param nextPageToken 다음 페이지 토큰. 마지막이면 null
 */
public record YouTubeSearchResult(List<String> videoIds, String nextPageToken) {

  public YouTubeSearchResult {
    videoIds = List.copyOf(videoIds);
  }
}
