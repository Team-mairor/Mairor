package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

/** 개인 파우치 항목 삭제. 회원·항목 잠금, 삭제, 버전 갱신을 원자적으로 처리한다. */
@Service
public class PouchDeletionService {

  private final PouchVersionRepository versions;
  private final PouchItemRepository items;

  public PouchDeletionService(PouchVersionRepository versions, PouchItemRepository items) {
    this.versions = versions;
    this.items = items;
  }

  @Transactional(isolation = Isolation.READ_COMMITTED)
  public void delete(UUID userId, UUID pouchItemId) {
    versions.lockByUserId(userId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    var item =
        items
            .findByIdAndUserIdForUpdate(pouchItemId, userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));

    items.delete(item);
    items.flush();
    versions.increment(userId);
  }
}
