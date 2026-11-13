package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.service.GuideCatalogGapCollector;
import com.mairor.backend.guides.service.GuideStepProductLinkReconciler;
import com.mairor.backend.products.collect.CollectRequestQueryService;
import com.mairor.backend.products.collect.CollectResultService;
import com.mairor.backend.products.dto.request.CollectJobResultRequest;
import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** S15P31A306-518: 가이드 대조 뒤 단계별 부족분(제품·호수·색 없음)을 수집 요청으로 보내기. */
class GuideCatalogGapCollectorTest extends AnalysisIntegrationTest {

  private static final String TYPE = "TEST_LIP_GAP";

  @Autowired private AnalysisJobService jobs;
  @Autowired private AnalysisJobStore jobStore;
  @Autowired private GuideRepository guideRepository;
  @Autowired private GuideStepProductLinkReconciler reconciler;
  @Autowired private GuideCatalogGapCollector collector;
  @Autowired private CollectResultService results;
  @Autowired private CollectRequestQueryService query;
  @Autowired private ProductCategoryRepository categories;
  @Autowired private ProductTypeRepository types;
  @Autowired private ProductRepository products;
  @Autowired private PlatformTransactionManager transactionManager;

  private String brand;

  @BeforeEach
  void uniqueBrand() {
    brand = "부족" + UUID.randomUUID().toString().substring(0, 8);
  }

  @Test
  void aProductNotInTheCatalogIsRequestedByNameWithoutAType() {
    UUID guideId = reconciled(guide("없는 틴트", "01 레드", null));

    collector.collect(guideId);

    Map<String, Object> request = onlyRequest();
    assertThat(request)
        .containsEntry("trigger", "GUIDE")
        .containsEntry("gap", "PRODUCT_MISSING")
        .containsEntry("category_code", "LIP")
        .containsEntry("type_code", null)
        .containsEntry("name", "없는 틴트")
        .containsEntry("shade_name", "01 레드")
        .containsEntry("status", "QUEUED");
    assertThat(waitingSteps(request)).containsExactly(guideId + "/s1");
    assertThat(query.recent(null, 200))
        .filteredOn(r -> r.requestId().equals(request.get("id")))
        .singleElement()
        .satisfies(
            r -> {
              assertThat(r.gap().name()).isEqualTo("PRODUCT_MISSING");
              assertThat(r.waitingSteps())
                  .singleElement()
                  .satisfies(w -> assertThat(w.guideId()).isEqualTo(guideId));
              assertThat(r.requesters()).isEmpty();
            });
  }

  @Test
  void aMissingShadeRefetchesTheKnownProduct() {
    Catalog catalog = product("있는 틴트", "01 니어", ReviewStatus.AUTO_APPROVED, "로즈");
    UUID guideId = reconciled(guide("있는 틴트", "05 레드", null));

    collector.collect(guideId);

    assertThat(onlyRequest())
        .containsEntry("gap", "SHADE_MISSING")
        .containsEntry("target_product_id", catalog.product().getId())
        .containsEntry("type_code", TYPE)
        .containsEntry("name", "있는 틴트")
        .containsEntry("shade_name", "05 레드");
  }

  @Test
  void aShadeWithoutColorSlotsAsksForItsColorWithTheVideoSlotLabel() {
    Catalog catalog = product("팔레트", "01", null);
    UUID guideId = reconciled(guide("팔레트", "01", "{\"slotNumber\":\"3\"}"));

    collector.collect(guideId);

    assertThat(onlyRequest())
        .containsEntry("gap", "COLOR_MISSING")
        .containsEntry("target_shade_id", catalog.shade().getId())
        .containsEntry("target_color_id", null)
        .containsEntry("target_slot_label", "3");
  }

  @Test
  void aLinkedSlotWhoseColorCannotBeUsedAsksForThatSlot() {
    Catalog catalog = product("단색 틴트", "01", ReviewStatus.BELOW_THRESHOLD, "로즈");
    UUID guideId = reconciled(guide("단색 틴트", "01", null));

    collector.collect(guideId);

    assertThat(onlyRequest())
        .containsEntry("gap", "COLOR_MISSING")
        .containsEntry("target_color_id", catalog.color().getId());
  }

  @Test
  void fullyLinkedAndUnidentifiableStepsAskForNothing() {
    product("완전 틴트", "01", ReviewStatus.AUTO_APPROVED, "로즈");
    product("두칸 팔레트", "01", ReviewStatus.AUTO_APPROVED, "로즈", "레드");
    UUID linked = reconciled(guide("완전 틴트", "01", null));
    UUID unidentified = reconciled(guide("두칸 팔레트", "01", null));

    collector.collect(linked);
    collector.collect(unidentified);

    assertThat(requests()).isEmpty();
  }

  @Test
  void theSameGapIsRequestedOnceAndNotAgainRightAfterItEnds() {
    UUID first = reconciled(guide("없는 틴트", null, null));
    UUID second = reconciled(guide("없는 틴트", null, null));

    collector.collect(first);
    collector.collect(second);
    collector.collect(first);

    Map<String, Object> request = onlyRequest();
    assertThat(waitingSteps(request)).containsExactlyInAnyOrder(first + "/s1", second + "/s1");

    jdbc.update(
        "update catalog_collect_requests set status = 'FAILED', reason = 'X', finished_at = now()"
            + " where id = ?",
        request.get("id"));
    assertThat(collector.collect(first)).isZero();
    assertThat(requests()).hasSize(1);
  }

  // --- 결과 판정(부족 유형별 완료 조건) ---

  @Test
  void aMissingProductResolvesOnceOneProductOfTheCategoryArrives() {
    UUID guideId = reconciled(guide("없는 틴트", null, null));
    collector.collect(guideId);
    UUID request = requestId();
    product("없는 틴트", "01", ReviewStatus.AUTO_APPROVED, "로즈");

    assertThat(collected(request).status().name()).isEqualTo("RESOLVED");
  }

  @Test
  void aMissingProductWithAnotherOfficialNameLeavesAnAliasTheGuideCanUse() {
    UUID guideId = reconciled(guide("없는 틴트", "01", null));
    collector.collect(guideId);
    UUID request = requestId();
    Catalog official = product("더 없는 틴트 NEW", "01", ReviewStatus.AUTO_APPROVED, "로즈");
    jdbc.update(
        "update products set source = 'OFFICIAL:shop.example', source_product_id = ? where id = ?",
        official.product().getId().toString(),
        official.product().getId());

    var applied =
        results.apply(request, result(request, "COLLECTED", official.product().getId().toString()));

    assertThat(applied.status().name()).isEqualTo("RESOLVED");
    reconciler.reconcile(guideId);
    assertThat(
            jdbc.queryForObject(
                "select product_id from guide_step_product_links where guide_id = ?",
                UUID.class,
                guideId))
        .isEqualTo(official.product().getId());
  }

  @Test
  void aMissingShadeResolvesOnlyWhenThatShadeArrives() {
    Catalog catalog = product("있는 틴트", "01 니어", ReviewStatus.AUTO_APPROVED, "로즈");
    UUID guideId = reconciled(guide("있는 틴트", "05 레드", null));
    collector.collect(guideId);
    UUID request = requestId();
    UUID second = reconciled(guide("있는 틴트", "06 코랄", null));
    collector.collect(second);
    UUID other =
        requests().stream()
            .map(r -> (UUID) r.get("id"))
            .filter(id -> !id.equals(request))
            .findFirst()
            .orElseThrow();
    addShade(catalog.product().getId(), "05 레드");

    assertThat(collected(request).status().name()).isEqualTo("RESOLVED");
    var unresolved = collected(other);
    assertThat(unresolved.status().name()).isEqualTo("UNRESOLVED");
    assertThat(unresolved.reason()).isEqualTo("SHADE_NOT_FOUND");
  }

  @Test
  void aBelowThresholdSlotResolvesOnlyWhenThatSlotBecomesUsable() {
    Catalog catalog = product("단색 틴트", "01", ReviewStatus.BELOW_THRESHOLD, "로즈");
    UUID guideId = reconciled(guide("단색 틴트", "01", null));
    collector.collect(guideId);
    UUID request = requestId();

    var still = collected(request);
    assertThat(still.reason()).isEqualTo("COLOR_NOT_USABLE");

    collector.collect(reconciled(guide("단색 틴트", "01", null)));
    assertThat(requests()).hasSize(1);
    jdbc.update(
        "update product_shade_colors set review_status = 'AUTO_APPROVED' where id = ?",
        catalog.color().getId());
    jdbc.update("delete from catalog_collect_requests where id = ?", request);
    collector.collect(reconciled(guide("단색 틴트", "01", null)));
    assertThat(requests()).isEmpty();
  }

  @Test
  void aShadeWithoutSlotsResolvesByTheVideoSlotNumberOrByAnySlotsForAPalette() {
    Catalog labelled = product("번호 팔레트", "01", null);
    Catalog unlabelled = product("이름 없는 팔레트", "01", null);
    UUID withNumber = reconciled(guide("번호 팔레트", "01", "{\"slotNumber\":\"2\"}"));
    UUID withoutNumber = reconciled(guide("이름 없는 팔레트", "01", null));
    collector.collect(withNumber);
    collector.collect(withoutNumber);
    UUID numbered = requestFor(labelled.shade().getId());
    UUID plain = requestFor(unlabelled.shade().getId());
    addSlots(labelled.shade().getId(), ReviewStatus.BELOW_THRESHOLD, ReviewStatus.AUTO_APPROVED);
    addSlots(
        unlabelled.shade().getId(), ReviewStatus.BELOW_THRESHOLD, ReviewStatus.BELOW_THRESHOLD);

    assertThat(collected(numbered).status().name()).isEqualTo("RESOLVED");
    assertThat(collected(plain).status().name()).isEqualTo("RESOLVED");
  }

  // --- 끝나면 기다리던 가이드를 다시 대조 ---

  @Test
  void aFinishedRequestReconcilesTheWaitingGuideAndRaisesItsReferenceVersion()
      throws InterruptedException {
    UUID guideId = reconciled(guide("나중 틴트", "01", null));
    collector.collect(guideId);
    UUID request = requestId();
    int versionBefore = guideRepository.findById(guideId).orElseThrow().getReferenceVersion();
    Catalog arrived = product("나중 틴트", "01", ReviewStatus.AUTO_APPROVED, "로즈");

    assertThat(collected(request).status().name()).isEqualTo("RESOLVED");

    UUID linked = null;
    for (int i = 0; i < 50 && linked == null; i++) {
      Thread.sleep(100);
      linked =
          jdbc.queryForObject(
              "select color_id from guide_step_product_links where guide_id = ?",
              UUID.class,
              guideId);
    }
    assertThat(linked).isEqualTo(arrived.color().getId());
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion())
        .isGreaterThan(versionBefore);
  }

  private CollectResultService.Applied collected(UUID request) {
    return results.apply(request, result(request, "COLLECTED", null));
  }

  private static CollectJobResultRequest result(UUID request, String status, String sourceId) {
    List<CollectJobResultRequest.Collected> collected =
        sourceId == null
            ? List.of()
            : List.of(
                new CollectJobResultRequest.Collected(
                    "000001", "OFFICIAL:shop.example", sourceId, "https://shop.example/p/1"));
    return new CollectJobResultRequest(
        1,
        request.toString(),
        CollectJobResultRequest.Status.valueOf(status),
        null,
        "20261113-000000-job-a.jsonl",
        "r-1",
        null,
        collected,
        List.of(),
        OffsetDateTime.now());
  }

  private UUID requestId() {
    jdbc.update(
        "update catalog_collect_requests set status = 'SENT', sent_at = now() where brand = ?"
            + " and status = 'QUEUED'",
        brand);
    return (UUID) onlyRequest().get("id");
  }

  private UUID requestFor(UUID shadeId) {
    jdbc.update(
        "update catalog_collect_requests set status = 'SENT', sent_at = now() where"
            + " target_shade_id = ? and status = 'QUEUED'",
        shadeId);
    return jdbc.queryForObject(
        "select id from catalog_collect_requests where target_shade_id = ?", UUID.class, shadeId);
  }

  private void addShade(UUID productId, String name) {
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order,"
            + " created_at, updated_at) values (gen_random_uuid(), ?, ?, lower(?), 9, now(), now())",
        productId,
        name,
        name);
  }

  private void addSlots(UUID shadeId, ReviewStatus... statuses) {
    for (int i = 0; i < statuses.length; i++) {
      jdbc.update(
          "insert into product_shade_colors (id, shade_id, sort_order, name, name_normalized,"
              + " name_source, color_hex, color_source, color_estimated, review_status, created_at,"
              + " updated_at) values (gen_random_uuid(), ?, ?, null, null, 'NONE', '#AA0000',"
              + " 'SAMPLE', false, ?, now(), now())",
          shadeId,
          i + 1,
          statuses[i].name());
    }
  }

  private UUID reconciled(UUID guideId) {
    reconciler.reconcile(guideId);
    return guideId;
  }

  private UUID guide(String name, String shade, String paletteJson) {
    String videoId = UUID.randomUUID().toString().substring(0, 11);
    UUID jobId =
        jobs.register(
                new AnalysisJobRequest(
                    videoId, "videos/" + videoId + "/source.mp4", "부족분 테스트", "테스트 채널", 60))
            .jobId();
    String input =
        """
        {"videoId":"%s","durationSeconds":60,"steps":[
          {"stepId":"s1","order":1,"startSeconds":0,"endSeconds":10,"makeup":"lip",
           "partLabel":"입술","summary":"립 제품을 바른다.",
           "product":{"brand":"%s","name":"%s","shade":%s,"palette":%s},
           "facts":{"area":{"value":"입술","source":"scene"}}}
        ]}
        """
            .formatted(
                videoId,
                brand,
                name,
                shade == null ? "null" : "\"" + shade + "\"",
                paletteJson == null ? "null" : paletteJson);
    jobStore.saveGuideInput(jobId, input);
    return guideRepository.findByAnalysisJobId(jobId).orElseThrow().getId();
  }

  private Catalog product(String name, String shadeName, ReviewStatus status, String... slots) {
    return new TransactionTemplate(transactionManager)
        .execute(
            tx -> {
              ProductCategory lip =
                  categories
                      .findById("LIP")
                      .orElseGet(
                          () -> categories.save(new ProductCategory("LIP", "립", true, true, 5)));
              ProductType type =
                  types
                      .findById(TYPE)
                      .orElseGet(() -> types.save(new ProductType(TYPE, lip, TYPE, 1)));
              Product product = new Product(type, brand, name);
              ProductShade shade = product.addShade(shadeName, 1, null);
              ProductShadeColor first = null;
              for (int i = 0; i < slots.length; i++) {
                ProductShadeColor color = shade.addColor(i + 1, slots[i], NameSource.SITE_TEXT);
                color.assignColor(ColorSource.SAMPLE, "#AA0000", false, status, null);
                if (i == 0) {
                  first = color;
                }
              }
              return new Catalog(products.save(product), shade, first);
            });
  }

  private List<Map<String, Object>> requests() {
    return jdbc.queryForList(
        "select * from catalog_collect_requests where trigger = 'GUIDE' and brand = ?", brand);
  }

  private Map<String, Object> onlyRequest() {
    List<Map<String, Object>> rows = requests();
    assertThat(rows).hasSize(1);
    return rows.getFirst();
  }

  private List<String> waitingSteps(Map<String, Object> request) {
    return jdbc
        .queryForList(
            "select guide_id, step_id from catalog_collect_request_guides where request_id = ?",
            request.get("id"))
        .stream()
        .map(row -> row.get("guide_id") + "/" + row.get("step_id"))
        .toList();
  }

  private record Catalog(Product product, ProductShade shade, ProductShadeColor color) {}
}
