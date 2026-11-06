package com.mairor.backend.videos.repository;

import com.mairor.backend.videos.entity.Video;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VideoRepository extends JpaRepository<Video, UUID> {

  Optional<Video> findByYoutubeVideoId(String youtubeVideoId);

  /** 검색 결과에 가이드 상태를 붙일 때 쓴다. 저장된 적 없는 영상은 빠진다. */
  List<Video> findByYoutubeVideoIdIn(Collection<String> youtubeVideoIds);
}
