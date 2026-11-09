package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.CatalogImportItem;
import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ImportItemOutcome;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogImportItemRepository extends JpaRepository<CatalogImportItem, UUID> {

  /** 같은 실행의 같은 건. {@code (run, itemKey)}가 유니크라 하나뿐이다. */
  Optional<CatalogImportItem> findByRunAndItemKey(CatalogImportRun run, String itemKey);

  /** 한 실행에서 주어진 처리 결과로 끝난 건의 itemKey. 틀린 건·실패한 건을 다시 처리할 때 쓴다. */
  @Query(
      "select i.itemKey from CatalogImportItem i"
          + " where i.run.id = :runId and i.outcome in :outcomes order by i.itemKey")
  List<String> findItemKeysByRunIdAndOutcomeIn(
      @Param("runId") UUID runId, @Param("outcomes") Collection<ImportItemOutcome> outcomes);
}
