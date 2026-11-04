package com.mairor.backend.pouch.repository;

import com.mairor.backend.pouch.entity.PouchItem;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PouchItemRepository extends JpaRepository<PouchItem, UUID> {

  Optional<PouchItem> findByIdAndUserId(UUID id, UUID userId);

  boolean existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalized(
      UUID userId, String brandNormalized, String nameNormalized, String shadeNameNormalized);
}
