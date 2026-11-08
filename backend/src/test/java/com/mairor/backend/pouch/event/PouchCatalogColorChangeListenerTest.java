package com.mairor.backend.pouch.event;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.products.event.CatalogColorChanged;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PouchCatalogColorChangeListenerTest {

  @Mock private PouchItemRepository pouchItems;
  @Mock private PouchVersionRepository pouchVersions;

  @Test
  void incrementsEachAffectedMemberOnceForOneColorChangeEvent() {
    UUID shadeId = UUID.randomUUID();
    UUID firstUserId = UUID.randomUUID();
    UUID secondUserId = UUID.randomUUID();
    when(pouchItems.findDistinctUserIdByShadeIdIn(Set.of(shadeId)))
        .thenReturn(List.of(firstUserId, secondUserId));
    var listener = new PouchCatalogColorChangeListener(pouchItems, pouchVersions);

    listener.onColorChanged(new CatalogColorChanged(Set.of(shadeId)));

    verify(pouchVersions).increment(firstUserId);
    verify(pouchVersions).increment(secondUserId);
  }
}
