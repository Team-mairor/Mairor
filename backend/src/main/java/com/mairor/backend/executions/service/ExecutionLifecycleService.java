package com.mairor.backend.executions.service;

import com.mairor.backend.executions.dto.ExecutionAbandonmentResponse;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import com.mairor.backend.photos.service.PhotoCleanupService;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** DB 종료 처리를 커밋한 다음 외부 저장소 파일 정리를 시도한다. */
@Service
public class ExecutionLifecycleService {
  private final ExecutionLifecyclePersistenceService persistence;
  private final PhotoCleanupService cleanup;
  private final StoredPhotoRepository photos;

  public ExecutionLifecycleService(
      ExecutionLifecyclePersistenceService persistence,
      PhotoCleanupService cleanup,
      StoredPhotoRepository photos) {
    this.persistence = persistence;
    this.cleanup = cleanup;
    this.photos = photos;
  }

  public ExecutionAbandonmentResponse abandon(UUID userId, String sessionId, UUID executionId) {
    var result = persistence.abandon(userId, sessionId, executionId);
    cleanup(result.photoIds());
    boolean pending = result.photoIds().stream().anyMatch(this::cleanupPending);
    return new ExecutionAbandonmentResponse(executionId, result.response().status(), pending);
  }

  public void abandonSession(UUID userId, String sessionId) {
    persistence.abandonSession(userId, sessionId).stream()
        .map(ExecutionLifecyclePersistenceService.SessionAbandonment::photoIds)
        .forEach(this::cleanup);
  }

  private void cleanup(List<UUID> photoIds) {
    for (UUID photoId : photoIds) {
      try {
        cleanup.cleanup(photoId);
      } catch (RuntimeException ignored) {
        // 접근은 DB에서 이미 차단되었고, cleanupPending 원장은 스케줄러가 재시도한다.
      }
    }
  }

  private boolean cleanupPending(UUID photoId) {
    return photos
        .findById(photoId)
        .map(photo -> photo.getState() == PhotoState.CLEANUP_PENDING)
        .orElse(false);
  }
}
