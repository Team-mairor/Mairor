package com.mairor.backend.pouch.event;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchCatalogRepository;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.event.CatalogColorChanged;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentMatchers;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PouchCatalogColorChangeListenerTest {

  @Mock private PouchItemRepository pouchItems;
  @Mock private PouchVersionRepository pouchVersions;
  @Mock private PouchCatalogRepository catalog;

  private PouchCatalogColorChangeListener listener() {
    return new PouchCatalogColorChangeListener(pouchItems, pouchVersions, catalog);
  }

  private static PouchItem linked(UUID userId, UUID shadeId, PouchColor color) {
    return new PouchItem(
        userId,
        RegistrationMode.CATALOG,
        UUID.randomUUID(),
        shadeId,
        "LIP",
        "LIP_TINT",
        "브랜드",
        "제품",
        "01",
        color);
  }

  private void catalogColorIs(UUID shadeId, String hex, Boolean estimated) {
    when(catalog.findShadeColors(Set.of(shadeId)))
        .thenReturn(Collections.singletonList(new Object[] {shadeId, hex, estimated}));
  }

  @Test
  void incrementsEachAffectedMemberOnceForOneColorChangeEvent() {
    UUID shadeId = UUID.randomUUID();
    UUID first = new UUID(0L, 1L);
    UUID second = new UUID(0L, 2L);
    when(pouchItems.findDistinctUserIdByShadeIdIn(Set.of(shadeId)))
        .thenReturn(List.of(first, second));
    when(pouchItems.findAllByShadeIdInAndUserIdIn(Set.of(shadeId), Set.of(first, second)))
        .thenReturn(List.of(linked(first, shadeId, null), linked(second, shadeId, null)));
    catalogColorIs(shadeId, "#BE5953", false);

    listener().onColorChanged(new CatalogColorChanged(Set.of(shadeId)));

    verify(pouchVersions).increment(first);
    verify(pouchVersions).increment(second);
  }

  @Test
  void locksEveryAffectedMemberInIdOrderBeforeTouchingTheirItems() {
    UUID shadeId = UUID.randomUUID();
    UUID low = new UUID(0L, 1L);
    UUID high = new UUID(0L, 2L);
    when(pouchItems.findDistinctUserIdByShadeIdIn(Set.of(shadeId))).thenReturn(List.of(high, low));
    when(pouchItems.findAllByShadeIdInAndUserIdIn(Set.of(shadeId), Set.of(low, high)))
        .thenReturn(List.of(linked(low, shadeId, null)));
    catalogColorIs(shadeId, "#BE5953", false);

    listener().onColorChanged(new CatalogColorChanged(Set.of(shadeId)));

    InOrder order = inOrder(pouchVersions, pouchItems);
    order.verify(pouchVersions).lockByUserId(low);
    order.verify(pouchVersions).lockByUserId(high);
    order.verify(pouchItems).findAllByShadeIdInAndUserIdIn(Set.of(shadeId), Set.of(low, high));
    order.verify(pouchVersions).increment(low);
    order.verify(pouchVersions).increment(high);
  }

  @Test
  void aMemberWhoAppearsWhileLockingIsLockedBumpedAndUpdatedToo() {
    UUID shadeId = UUID.randomUUID();
    UUID early = new UUID(0L, 5L);
    UUID late = new UUID(0L, 3L);
    // 첫 조회에는 early 만 있고, early 를 잠그는 사이 late 의 항목이 커밋돼 다음 조회에 나타난다
    when(pouchItems.findDistinctUserIdByShadeIdIn(Set.of(shadeId)))
        .thenReturn(List.of(early))
        .thenReturn(List.of(early, late));
    PouchItem lateItem = linked(late, shadeId, null);
    when(pouchItems.findAllByShadeIdInAndUserIdIn(Set.of(shadeId), Set.of(early, late)))
        .thenReturn(List.of(linked(early, shadeId, null), lateItem));
    catalogColorIs(shadeId, "#BE5953", false);

    listener().onColorChanged(new CatalogColorChanged(Set.of(shadeId)));

    verify(pouchVersions).lockByUserId(early);
    verify(pouchVersions).lockByUserId(late);
    verify(pouchVersions).increment(early);
    verify(pouchVersions).increment(late);
    assertThat(lateItem.getColor()).isEqualTo(PouchColor.catalog("#BE5953", false));
  }

  @Test
  void copiesTheCatalogColorOverTheMembersColor() {
    UUID shadeId = UUID.randomUUID();
    UUID first = new UUID(0L, 1L);
    UUID second = new UUID(0L, 2L);
    PouchItem typed = linked(first, shadeId, PouchColor.userInput("#C0FFEE"));
    PouchItem empty = linked(second, shadeId, null);
    when(pouchItems.findDistinctUserIdByShadeIdIn(Set.of(shadeId)))
        .thenReturn(List.of(first, second));
    when(pouchItems.findAllByShadeIdInAndUserIdIn(Set.of(shadeId), Set.of(first, second)))
        .thenReturn(List.of(typed, empty));
    catalogColorIs(shadeId, "#BE5953", true);

    listener().onColorChanged(new CatalogColorChanged(Set.of(shadeId)));

    assertThat(typed.getColor()).isEqualTo(PouchColor.catalog("#BE5953", true));
    assertThat(empty.getColor()).isEqualTo(PouchColor.catalog("#BE5953", true));
  }

  @Test
  void aShadeWithoutAUsableColorClearsTheCatalogCopyAndKeepsTheMembersColor() {
    UUID shadeId = UUID.randomUUID();
    UUID first = new UUID(0L, 1L);
    UUID second = new UUID(0L, 2L);
    PouchItem copied = linked(first, shadeId, PouchColor.catalog("#BE5953", false));
    PouchItem typed = linked(second, shadeId, PouchColor.userInput("#C0FFEE"));
    when(pouchItems.findDistinctUserIdByShadeIdIn(Set.of(shadeId)))
        .thenReturn(List.of(first, second));
    when(pouchItems.findAllByShadeIdInAndUserIdIn(Set.of(shadeId), Set.of(first, second)))
        .thenReturn(List.of(copied, typed));
    catalogColorIs(shadeId, null, null);

    listener().onColorChanged(new CatalogColorChanged(Set.of(shadeId)));

    assertThat(copied.getColor()).isNull();
    assertThat(typed.getColor()).isEqualTo(PouchColor.userInput("#C0FFEE"));
  }

  @Test
  void doesNothingWhenNoItemUsesTheChangedShades() {
    UUID shadeId = UUID.randomUUID();
    when(pouchItems.findDistinctUserIdByShadeIdIn(Set.of(shadeId))).thenReturn(List.of());

    listener().onColorChanged(new CatalogColorChanged(Set.of(shadeId)));

    verify(pouchItems, never())
        .findAllByShadeIdInAndUserIdIn(ArgumentMatchers.any(), ArgumentMatchers.any());
    verify(catalog, never()).findShadeColors(Set.of(shadeId));
    verify(pouchVersions, never()).lockByUserId(ArgumentMatchers.any());
    verify(pouchVersions, never()).increment(ArgumentMatchers.any());
  }
}
