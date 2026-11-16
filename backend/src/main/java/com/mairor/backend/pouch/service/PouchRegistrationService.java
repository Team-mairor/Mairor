package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.dto.PouchRegistrationRequest;
import com.mairor.backend.pouch.dto.PouchRegistrationResponse;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.event.PouchItemRegisteredManually;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 개인 파우치 등록. 회원 잠금·저장·버전 증가를 한 READ_COMMITTED 트랜잭션으로 처리한다.
 *
 * <p>직접 입력(MANUAL) 등록이면 {@link PouchItemRegisteredManually}를 알린다. 커밋된 뒤 수집 요청을 만들고, 그게 실패해도 등록은
 * 그대로다.
 */
@Service
public class PouchRegistrationService {

  private final PouchVersionRepository versions;
  private final PouchItemRepository items;
  private final PouchRegistrationValidator validator;
  private final ApplicationEventPublisher events;

  public PouchRegistrationService(
      PouchVersionRepository versions,
      PouchItemRepository items,
      PouchRegistrationValidator validator,
      ApplicationEventPublisher events) {
    this.versions = versions;
    this.items = items;
    this.validator = validator;
    this.events = events;
  }

  @Transactional(isolation = Isolation.READ_COMMITTED)
  public PouchRegistrationResponse register(UUID userId, PouchRegistrationRequest request) {
    if (versions.lockByUserId(userId).isEmpty()) {
      throw new BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "회원을 찾을 수 없습니다.");
    }

    PouchItem item = validator.prepare(userId, request);
    if (items.existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalized(
        userId,
        item.getBrandNormalized(),
        item.getNameNormalized(),
        item.getShadeNameNormalized())) {
      throw PouchDuplicateHandling.duplicate();
    }

    try {
      PouchItem saved = items.saveAndFlush(item);
      long pouchVersion = versions.increment(userId);
      if (saved.getRegistrationMode() == RegistrationMode.MANUAL) {
        events.publishEvent(new PouchItemRegisteredManually(userId, saved.getId()));
      }
      return new PouchRegistrationResponse(PouchItemResponse.from(saved), pouchVersion);
    } catch (DataIntegrityViolationException e) {
      if (PouchDuplicateHandling.isDuplicateConstraint(e)) {
        throw PouchDuplicateHandling.duplicate();
      }
      throw e;
    }
  }
}
