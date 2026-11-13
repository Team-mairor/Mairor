package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.anyCollection;
import static org.mockito.Mockito.anyString;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.guides.dto.response.GuideResponse;
import com.mairor.backend.guides.entity.GuideStepProductLink;
import com.mairor.backend.guides.entity.ReferenceMatchLevel;
import com.mairor.backend.guides.entity.ReferenceMatchReason;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.guides.repository.GuideStepProductLinkRepository;
import com.mairor.backend.guides.service.GuideQueryService;
import com.mairor.backend.guides.service.GuideStepProductLinkReconciler;
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
import com.mairor.backend.products.repository.ProductShadeRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** S15P31A306-324: 단일 근거 매칭, 모호성, 링크 보존, 색 변경 버전을 확인한다. */
class GuideStepProductLinkReconcilerTest extends AnalysisIntegrationTest {

  @Autowired private AnalysisJobService jobs;
  @Autowired private AnalysisJobStore jobStore;
  @Autowired private GuideStepProductLinkReconciler reconciler;
  @Autowired private GuideQueryService guideQuery;
  @Autowired private GuideRepository guideRepository;
  @Autowired private GuideStepProductLinkRepository links;
  @Autowired private ProductCategoryRepository categories;
  @Autowired private ProductTypeRepository types;
  @MockitoSpyBean private ProductRepository products;
  @MockitoSpyBean private ProductShadeRepository shades;
  @Autowired private PlatformTransactionManager transactionManager;

  @Test
  void uniqueProductShadeAndSingleColorAreExposedAndRepeatReconciliationIsStable() {
    CatalogProduct catalog = product("TEST_LIP_UNIQUE", "브랜드 하나", "제품 하나", "05 Ruby", "Rose");
    UUID guideId = guide("브랜드 하나", "제품 하나", "05 Ruby", null);

    clearInvocations(products);
    assertThat(reconciler.reconcile(guideId)).isOne();
    verify(products, times(1)).findExact(anyCollection(), anyString(), anyString());
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(1);
    assertThat(reconciler.reconcile(guideId)).isZero();
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(1);

    GuideResponse response = guideQuery.get(guideId);
    assertThat(response.steps().getFirst().referenceProduct().matchStatus()).isEqualTo("MATCHED");
    assertThat(response.steps().getFirst().referenceProduct().productId())
        .isEqualTo(catalog.product().getId().toString());
    assertThat(response.steps().getFirst().referenceProduct().shadeId())
        .isEqualTo(catalog.shade().getId().toString());
  }

  @Test
  void aProductThatArrivesLaterUpgradesTheLinkStepByStep() {
    UUID guideId = guide("브랜드 나중", "나중 제품", "01", null);
    reconciler.reconcile(guideId);
    assertThat(links.findByGuideIdAndStepId(guideId, "s1").orElseThrow().getMatchLevel())
        .isEqualTo(ReferenceMatchLevel.NONE);

    CatalogProduct catalog = product("TEST_LIP_LATER", "브랜드 나중", "나중 제품", "01", "Rose");

    assertThat(reconciler.reconcile(guideId)).isOne();
    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getMatchLevel()).isEqualTo(ReferenceMatchLevel.SLOT);
    assertThat(link.getProduct().getId()).isEqualTo(catalog.product().getId());
    assertThat(link.getColor().getId()).isEqualTo(catalog.color().getId());
  }

  @Test
  void aBrandPrefixedSiteNameAndASpacelessVideoShadeStillLink() {
    CatalogProduct catalog = product("TEST_LIP_PREFIX", "브랜드 앞", "브랜드 앞 쥬시 틴트", "02 누카다미아", "Rose");
    UUID guideId = guide("브랜드 앞", "쥬시 틴트", "02누카다미아", null);

    reconciler.reconcile(guideId);

    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getProduct().getId()).isEqualTo(catalog.product().getId());
    assertThat(link.getShade().getId()).isEqualTo(catalog.shade().getId());
  }

  @Test
  void aVideoShadeChoosesTheSeriesProductThatHasIt() {
    product("TEST_LIP_SER_A", "브랜드 시리즈", "블러 퍼지 틴트 #오리지널", "01 오리지널", "Rose");
    CatalogProduct black = product("TEST_LIP_SER_B", "브랜드 시리즈", "블러 퍼지 틴트 #블랙", "03 블랙", "Black");
    jdbc.update(
        "insert into product_name_aliases (id, type_code, brand_normalized, name_compact,"
            + " product_id, created_at) select gen_random_uuid(), p.type_code, p.brand_normalized,"
            + " '블러퍼지틴트', p.id, now() from products p where p.brand = '브랜드 시리즈'");
    UUID guideId = guide("브랜드 시리즈", "블러 퍼지 틴트", "03블랙", null);

    reconciler.reconcile(guideId);

    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getProduct().getId()).isEqualTo(black.product().getId());
    assertThat(link.getShade().getId()).isEqualTo(black.shade().getId());
  }

  @Test
  void aVideoShadeInNoSeriesProductStaysAmbiguous() {
    product("TEST_LIP_SER_C", "브랜드 시리즈둘", "블러 퍼지 틴트 #오리지널", "01 오리지널", "Rose");
    product("TEST_LIP_SER_D", "브랜드 시리즈둘", "블러 퍼지 틴트 #블랙", "03 블랙", "Black");
    jdbc.update(
        "insert into product_name_aliases (id, type_code, brand_normalized, name_compact,"
            + " product_id, created_at) select gen_random_uuid(), p.type_code, p.brand_normalized,"
            + " '블러퍼지틴트', p.id, now() from products p where p.brand = '브랜드 시리즈둘'");
    UUID guideId = guide("브랜드 시리즈둘", "블러 퍼지 틴트", "99 없는 호수", null);

    reconciler.reconcile(guideId);

    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getMatchLevel()).isEqualTo(ReferenceMatchLevel.NONE);
    assertThat(link.getReasonCode()).isEqualTo(ReferenceMatchReason.PRODUCT_AMBIGUOUS);
  }

  @Test
  void ambiguousProductCandidatesAreNotLinked() {
    product("TEST_LIP_AMBIGUOUS_A", "브랜드 둘", "같은 제품", null);
    product("TEST_LIP_AMBIGUOUS_B", "브랜드 둘", "같은 제품", null);
    UUID guideId = guide("브랜드 둘", "같은 제품", null, null);

    assertThat(reconciler.reconcile(guideId)).isOne();
    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getMatchLevel()).isEqualTo(ReferenceMatchLevel.NONE);
    assertThat(link.getReasonCode()).isEqualTo(ReferenceMatchReason.PRODUCT_AMBIGUOUS);

    var response = guideQuery.get(guideId).steps().getFirst().referenceProduct();
    assertThat(response.matchStatus()).isEqualTo("CANDIDATE");
    assertThat(response.productId()).isNull();
    assertThat(response.shadeId()).isNull();
  }

  @Test
  void productNameCompactMatchLinksOnlyTheUniqueCatalogProduct() {
    CatalogProduct catalog = product("TEST_LIP_COMPACT", "브랜드 일곱", "Rose Velvet Tint", null);
    UUID guideId = guide("브랜드 일곱", "RoseVelvetTint", null, null);

    clearInvocations(products);
    assertThat(reconciler.reconcile(guideId)).isOne();
    verify(products, times(1)).findExact(anyCollection(), anyString(), anyString());
    verify(products, times(1)).findCompact(anyCollection(), anyString(), anyString());
    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getMatchLevel()).isEqualTo(ReferenceMatchLevel.PRODUCT);
    assertThat(link.getProduct().getId()).isEqualTo(catalog.product().getId());
  }

  @Test
  void paletteDescriptionDoesNotChooseBetweenMultipleColorSlots() {
    CatalogProduct catalog = product("TEST_LIP_PALETTE", "브랜드 셋", "팔레트", "01", "Red", "Rose");
    UUID guideId = guide("브랜드 셋", "팔레트", "01", "red");

    assertThat(reconciler.reconcile(guideId)).isOne();
    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getProduct().getId()).isEqualTo(catalog.product().getId());
    assertThat(link.getShade().getId()).isEqualTo(catalog.shade().getId());
    assertThat(link.getColor()).isNull();
    assertThat(link.getMatchLevel()).isEqualTo(ReferenceMatchLevel.SHADE);
    assertThat(link.getReasonCode()).isEqualTo(ReferenceMatchReason.SLOT_UNIDENTIFIED);
  }

  @Test
  void conflictingReconciliationPreservesExistingProductAndIsIdempotent() {
    CatalogProduct original = product("TEST_LIP_CONFLICT_A", "브랜드 넷", "기존 제품", null);
    product("TEST_LIP_CONFLICT_B", "브랜드 넷", "새 제품", null);
    UUID guideId = guide("브랜드 넷", "기존 제품", null, null);
    reconciler.reconcile(guideId);
    jdbc.update(
        "update guides set guide_input = ?::jsonb where id = ?::uuid",
        input("브랜드 넷", "새 제품", null, null),
        guideId);

    assertThat(reconciler.reconcile(guideId)).isOne();
    GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
    assertThat(link.getProduct().getId()).isEqualTo(original.product().getId());
    assertThat(link.getReasonCode()).isEqualTo(ReferenceMatchReason.LINK_CONFLICT);
    var reference = guideQuery.get(guideId).steps().getFirst().referenceProduct();
    assertThat(reference.name()).isEqualTo("브랜드 넷 새 제품");
    assertThat(reference.productId()).isNull();
    assertThat(reference.shadeId()).isNull();
    assertThat(reference.matchStatus()).isEqualTo("UNMATCHED");
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(2);
    assertThat(reconciler.reconcile(guideId)).isZero();
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(2);
  }

  @Test
  void onlyChangesToTheLinkedServiceColorAdvanceReferenceVersion() {
    CatalogProduct catalog = product("TEST_LIP_COLOR_VERSION", "브랜드 다섯", "색상 제품", "01", "Red");
    UUID guideId = guide("브랜드 다섯", "색상 제품", "01", null);
    reconciler.reconcile(guideId);
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(1);

    jdbc.update(
        "update product_shade_colors set color_hex = '#BB0000' where id = ?::uuid",
        catalog.color().getId());
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(2);

    jdbc.update(
        "update product_shade_colors set review_status = 'BELOW_THRESHOLD' where id = ?::uuid",
        catalog.color().getId());
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(3);

    jdbc.update(
        "update product_shade_colors set color_hex = '#CC0000' where id = ?::uuid",
        catalog.color().getId());
    assertThat(guideRepository.findById(guideId).orElseThrow().getReferenceVersion()).isEqualTo(3);
  }

  @Test
  void reconciliationWaitsForCatalogColorReplacementOnTheSameShadeLock() throws Exception {
    CatalogProduct catalog = product("TEST_LIP_SHADE_LOCK", "브랜드 잠금", "잠금 제품", "01", "Red");
    UUID guideId = guide("브랜드 잠금", "잠금 제품", "01", null);
    CountDownLatch shadeLocked = new CountDownLatch(1);
    CountDownLatch allowReplacement = new CountDownLatch(1);
    ExecutorService executor = Executors.newFixedThreadPool(2);

    try {
      Future<?> replacement =
          executor.submit(
              () ->
                  new TransactionTemplate(transactionManager)
                      .executeWithoutResult(
                          status -> {
                            shades.findByIdForUpdate(catalog.shade().getId()).orElseThrow();
                            shadeLocked.countDown();
                            await(allowReplacement);
                            jdbc.update(
                                "delete from product_shade_colors where id = ?::uuid",
                                catalog.color().getId());
                          }));

      assertThat(shadeLocked.await(5, TimeUnit.SECONDS)).isTrue();
      clearInvocations(shades);
      Future<Integer> reconciliation = executor.submit(() -> reconciler.reconcile(guideId));

      verify(shades, timeout(5_000)).findByIdForUpdate(catalog.shade().getId());
      assertThat(reconciliation.isDone()).isFalse();

      allowReplacement.countDown();
      replacement.get(5, TimeUnit.SECONDS);
      assertThat(reconciliation.get(5, TimeUnit.SECONDS)).isOne();
      GuideStepProductLink link = links.findByGuideIdAndStepId(guideId, "s1").orElseThrow();
      assertThat(link.getShade().getId()).isEqualTo(catalog.shade().getId());
      assertThat(link.getColor()).isNull();
      assertThat(link.getReasonCode()).isEqualTo(ReferenceMatchReason.NO_COLOR_SLOTS);
    } finally {
      allowReplacement.countDown();
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }

  private static void await(CountDownLatch latch) {
    try {
      if (!latch.await(5, TimeUnit.SECONDS)) {
        throw new IllegalStateException("호수 잠금 테스트 진행 신호를 받지 못했습니다.");
      }
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("호수 잠금 테스트가 중단됐습니다.", e);
    }
  }

  @Test
  void databaseRejectsIDsBeyondTheConfirmedMatchLevel() {
    CatalogProduct catalog = product("TEST_LIP_DB_CONSTRAINT", "브랜드 여섯", "제약 제품", null);
    UUID guideId = guide("브랜드 여섯", "제약 제품", null, null);

    assertThatThrownBy(
            () ->
                jdbc.update(
                    "insert into guide_step_product_links (id, guide_id, step_id, product_id,"
                        + " match_level, created_at, updated_at) values (gen_random_uuid(),"
                        + " ?::uuid, 'invalid-step', ?::uuid, 'NONE', now(), now())",
                    guideId,
                    catalog.product().getId()))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(GuideStepProductLink.MATCH_LEVEL_CHECK);
  }

  private CatalogProduct product(
      String typeCode, String brand, String name, String shadeName, String... colorNames) {
    return new TransactionTemplate(transactionManager)
        .execute(
            status -> {
              ProductCategory lip =
                  categories
                      .findById("LIP")
                      .orElseGet(
                          () -> categories.save(new ProductCategory("LIP", "립", true, true, 5)));
              ProductType type =
                  types
                      .findById(typeCode)
                      .orElseGet(() -> types.save(new ProductType(typeCode, lip, typeCode, 1)));
              Product product = new Product(type, brand, name);
              if (shadeName == null) {
                return new CatalogProduct(products.save(product), null, null);
              }
              ProductShade shade = product.addShade(shadeName, 1, null);
              ProductShadeColor firstColor = null;
              for (int i = 0; i < colorNames.length; i++) {
                ProductShadeColor color =
                    shade.addColor(i + 1, colorNames[i], NameSource.SITE_TEXT);
                color.assignColor(
                    ColorSource.SAMPLE, "#AA0000", false, ReviewStatus.AUTO_APPROVED, null);
                if (i == 0) {
                  firstColor = color;
                }
              }
              return new CatalogProduct(products.save(product), shade, firstColor);
            });
  }

  private UUID guide(String brand, String name, String shade, String paletteColor) {
    String videoId = "VxAXD6PP76I";
    UUID jobId =
        jobs.register(
                new AnalysisJobRequest(
                    videoId, "videos/" + videoId + "/source.mp4", "제품 대조 테스트", "테스트 채널", 60))
            .jobId();
    jobStore.saveGuideInput(jobId, input(brand, name, shade, paletteColor));
    UUID guideId = guideRepository.findByAnalysisJobId(jobId).orElseThrow().getId();
    jdbc.update("update guides set review_status = 'APPROVED' where id = ?", guideId);
    return guideId;
  }

  private static String input(String brand, String name, String shade, String paletteColor) {
    String shadeJson = shade == null ? "null" : "\"" + shade + "\"";
    String paletteJson =
        paletteColor == null
            ? "null"
            : "{\"color\":{\"value\":\"" + paletteColor + "\",\"source\":\"voice\"}}";
    return """
        {"videoId":"VxAXD6PP76I","durationSeconds":60,"steps":[
          {"stepId":"s1","order":1,"startSeconds":0,"endSeconds":10,"makeup":"lip",
           "partLabel":"입술","summary":"립 제품을 바른다.",
           "product":{"brand":"%s","name":"%s","shade":%s,"palette":%s},
           "facts":{"area":{"value":"입술","source":"scene"}}}
        ]}
        """
        .formatted(brand, name, shadeJson, paletteJson);
  }

  private record CatalogProduct(Product product, ProductShade shade, ProductShadeColor color) {}
}
