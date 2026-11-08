package com.mairor.backend.pouch.event;

import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.event.CatalogColorChanged;
import java.util.UUID;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 파우치 응답 색 칸이 바뀐 회원의 버전을 적재 트랜잭션 안에서 한 번씩 올린다. */
@Component
public class PouchCatalogColorChangeListener {

  private final PouchItemRepository pouchItems;
  private final PouchVersionRepository pouchVersions;

  public PouchCatalogColorChangeListener(
      PouchItemRepository pouchItems, PouchVersionRepository pouchVersions) {
    this.pouchItems = pouchItems;
    this.pouchVersions = pouchVersions;
  }

  @EventListener
  @Transactional(propagation = Propagation.MANDATORY)
  public void onColorChanged(CatalogColorChanged event) {
    for (UUID userId : pouchItems.findDistinctUserIdByShadeIdIn(event.shadeIds())) {
      pouchVersions.increment(userId);
    }
    // 연결 가이드의 reference_version은 324 DB 트리거가 올린다. 여기서 다시 올리면 한 번의 색 변경에 두 번 증가한다.
  }
}
