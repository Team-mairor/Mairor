package com.mairor.backend.photos.repository;

import com.mairor.backend.photos.entity.StoredPhoto;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface StoredPhotoRepository extends JpaRepository<StoredPhoto, UUID> {
  @Query(
      """
      select count(photo) from StoredPhoto photo
      where photo.state = com.mairor.backend.photos.entity.PhotoState.CLEANUP_PENDING
        and photo.cleanupRequestedAt <= :cutoff
      """)
  long countOverdueCleanup(@Param("cutoff") Instant cutoff);

  Optional<StoredPhoto> findByIdAndUserId(UUID id, UUID userId);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select photo from StoredPhoto photo where photo.id = :id")
  Optional<StoredPhoto> findByIdForUpdate(@Param("id") UUID id);

  @Query(value = "select * from photos where id = :id for update skip locked", nativeQuery = true)
  Optional<StoredPhoto> findByIdForCleanup(@Param("id") UUID id);

  @Query(
      """
      select photo.id from StoredPhoto photo
      where (photo.state = com.mairor.backend.photos.entity.PhotoState.CLEANUP_PENDING
          and photo.nextCleanupAt <= :now)
        or (photo.state in (
            com.mairor.backend.photos.entity.PhotoState.PENDING_UPLOAD,
            com.mairor.backend.photos.entity.PhotoState.AVAILABLE)
          and photo.expiresAt <= :now)
      order by photo.createdAt, photo.id
      """)
  List<UUID> findCleanupCandidates(@Param("now") Instant now, Pageable pageable);
}
