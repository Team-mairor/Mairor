package com.mairor.backend.videos.repository;

import com.mairor.backend.videos.entity.Video;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VideoRepository extends JpaRepository<Video, UUID> {

  Optional<Video> findByYoutubeVideoId(String youtubeVideoId);
}
