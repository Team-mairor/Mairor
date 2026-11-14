package com.mairor.backend.pouch.event;

import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.repository.PouchCatalogRepository;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.event.CatalogColorChanged;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카탈로그 색이 바뀌면 그 호수에 연결된 파우치 항목의 색 복사본을 맞추고(S15P31A306-531), 파우치 응답 색 칸이 바뀐 회원의 버전을 적재 트랜잭션 안에서 한 번씩
 * 올린다. 쓸 수 있는 카탈로그 단색이 있으면 회원이 넣은 색보다 그 색을 보여 준다.
 */
@Component
public class PouchCatalogColorChangeListener {

  private final PouchItemRepository pouchItems;
  private final PouchVersionRepository pouchVersions;
  private final PouchCatalogRepository catalog;

  public PouchCatalogColorChangeListener(
      PouchItemRepository pouchItems,
      PouchVersionRepository pouchVersions,
      PouchCatalogRepository catalog) {
    this.pouchItems = pouchItems;
    this.pouchVersions = pouchVersions;
    this.catalog = catalog;
  }

  @EventListener
  @Transactional(propagation = Propagation.MANDATORY)
  public void onColorChanged(CatalogColorChanged event) {
    Set<UUID> locked = lockAffectedMembers(event);
    if (locked.isEmpty()) {
      return;
    }
    // 잠근 회원들의 항목만 고친다. 그래서 색이 바뀐 회원과 버전이 오르는 회원이 같다
    List<PouchItem> items = pouchItems.findAllByShadeIdInAndUserIdIn(event.shadeIds(), locked);
    Map<UUID, PouchColor> colors = catalogColors(event);
    for (PouchItem item : items) {
      item.refreshCatalogColor(colors.get(item.getShadeId()));
    }
    for (UUID userId : locked) {
      pouchVersions.increment(userId);
    }
    // 연결 가이드의 reference_version은 324 DB 트리거가 올린다. 여기서 다시 올리면 한 번의 색 변경에 두 번 증가한다.
  }

  /**
   * 영향 회원의 행을 항목보다 먼저 잠근다. 파우치 쓰기(등록·수정·수집 연결)도 회원 행을 먼저 잠그므로 같은 순서다.
   *
   * <p>한 번에 구한 회원 목록은 잠금을 기다리는 사이 낡을 수 있다(그 사이 같은 호수의 새 항목이 커밋될 수 있다). 그래서 잠근 뒤 회원을 다시 구해, 새로 나타난
   * 회원이 없을 때까지 잠근다. 같은 차례 안에서는 ID 순서로 잠가 겹친 적재끼리 교착하지 않게 한다.
   *
   * @return 잠근 회원들(ID 순서). 영향받는 회원이 없으면 빈 집합
   */
  private Set<UUID> lockAffectedMembers(CatalogColorChanged event) {
    Set<UUID> locked = new TreeSet<>();
    while (true) {
      List<UUID> pending =
          pouchItems.findDistinctUserIdByShadeIdIn(event.shadeIds()).stream()
              .filter(userId -> !locked.contains(userId))
              .sorted()
              .toList();
      if (pending.isEmpty()) {
        return locked;
      }
      for (UUID userId : pending) {
        pouchVersions.lockByUserId(userId);
        locked.add(userId);
      }
    }
  }

  private Map<UUID, PouchColor> catalogColors(CatalogColorChanged event) {
    Map<UUID, PouchColor> colors = new HashMap<>();
    for (Object[] row : catalog.findShadeColors(event.shadeIds())) {
      String hex = (String) row[1];
      if (hex != null) {
        colors.put((UUID) row[0], PouchColor.catalog(hex, Boolean.TRUE.equals(row[2])));
      }
    }
    return colors;
  }
}
