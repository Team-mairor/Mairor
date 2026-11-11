package com.mairor.backend.camera.service;

import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.camera.repository.FaceRegistrationOrphanRepository;
import com.mairor.backend.camera.repository.FaceRegistrationRepository;
import com.mairor.backend.photos.service.PhotoRecordService;
import com.mairor.backend.users.repository.UserRepository;
import java.time.Clock;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 미연결 등록은 로그인 세션 수명까지 보관한다. 파일 I/O 대신 접근 차단·삭제 예약만 커밋한다. */
@Service
public class FaceRegistrationLifecycleService {
  private final FaceRegistrationRepository registrations;
  private final FaceRegistrationOrphanRepository orphans;
  private final PhotoRecordService photos;
  private final UserRepository users;
  private final Clock clock;

  public FaceRegistrationLifecycleService(
      FaceRegistrationRepository registrations,
      FaceRegistrationOrphanRepository orphans,
      PhotoRecordService photos,
      UserRepository users,
      Clock clock) {
    this.registrations = registrations;
    this.orphans = orphans;
    this.photos = photos;
    this.users = users;
    this.clock = clock;
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void discardUnlinkedForSession(UUID userId, String sessionId) {
    if (users.findByIdForUpdate(userId).isEmpty()) {
      return;
    }
    for (FaceRegistration registration :
        registrations.findByUserIdAndSessionIdAndStatusAndDiscardedAtIsNullOrderById(
            userId, sessionId, FaceRegistrationStatus.REGISTERED)) {
      discard(registration);
    }
  }

  /** 후보 조회 뒤 세션/등록 상태가 바뀌었을 수 있으므로 잠근 뒤 다시 확인한다. */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void discardIfSessionMissing(UUID userId, UUID registrationId) {
    if (users.findByIdForUpdate(userId).isEmpty()) {
      return;
    }
    registrations
        .findOwnedForUpdate(registrationId, userId)
        .filter(
            value ->
                value.getStatus() == FaceRegistrationStatus.REGISTERED
                    && value.getDiscardedAt() == null
                    && !orphans.sessionExists(value.getSessionId()))
        .ifPresent(this::discard);
  }

  private void discard(FaceRegistration registration) {
    registration.discard(clock.instant());
    photos.requestCleanupInCurrentTransaction(registration.getPhotoId());
  }
}
