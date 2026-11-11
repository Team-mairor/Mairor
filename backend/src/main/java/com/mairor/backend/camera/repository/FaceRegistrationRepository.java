package com.mairor.backend.camera.repository;

import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface FaceRegistrationRepository extends JpaRepository<FaceRegistration, UUID> {
  Optional<FaceRegistration> findByIdAndUserIdAndSessionIdAndDiscardedAtIsNull(
      UUID id, UUID userId, String sessionId);

  Optional<FaceRegistration> findByIdAndUserId(UUID id, UUID userId);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query(
      "select registration from FaceRegistration registration where registration.id = :id and registration.userId = :userId")
  Optional<FaceRegistration> findOwnedForUpdate(@Param("id") UUID id, @Param("userId") UUID userId);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  Optional<FaceRegistration> findByUserIdAndSessionIdAndVideoIdAndStatusAndDiscardedAtIsNull(
      UUID userId, String sessionId, UUID videoId, FaceRegistrationStatus status);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  List<FaceRegistration> findByUserIdAndSessionIdAndStatusAndDiscardedAtIsNullOrderById(
      UUID userId, String sessionId, FaceRegistrationStatus status);
}
