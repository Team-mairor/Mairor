package com.mairor.backend.products.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.products.dto.request.ProductSearchQuery;
import com.mairor.backend.products.dto.response.ProductResponse;
import com.mairor.backend.products.dto.response.ShadeResponse;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductShadeColorRepository;
import com.mairor.backend.products.repository.ProductShadeRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카탈로그 제품 검색(API-POUCH-001)과 상세 조회(API-POUCH-002).
 *
 * <p>검색은 정규화한 브랜드·제품명과 종류가 정확히 같은 제품만 찾는다. (종류, 브랜드, 제품명)이 유니크라 결과는 0~1건이다. 비슷한 이름의 다른 제품에 연결하지
 * 않는다.
 *
 * <p>호수와 색 칸은 컬렉션을 건드리지 않고 정렬 조회로 따로 읽는다. 색 칸은 호수 ID 목록으로 한 번에 읽는다. 쿼리는 검색 1건 4번(종류·제품·호수·색 칸), 0건
 * 2번, 상세 3번(제품·호수·색 칸)이다. 호수가 없으면 색 칸 쿼리는 나가지 않는다(호수 없는 제품 검색 3번, 상세 2번). 코드가 틀린 요청에만 카테고리 존재 확인
 * 쿼리가 1번 더 나간다.
 */
@Service
@Transactional(readOnly = true)
public class ProductSearchService {

  static final String UNKNOWN_CATEGORY = "없는 카테고리입니다.";
  static final String UNKNOWN_TYPE = "없는 종류이거나 이 카테고리의 종류가 아닙니다.";

  private final ProductCategoryRepository categoryRepository;
  private final ProductTypeRepository typeRepository;
  private final ProductRepository productRepository;
  private final ProductShadeRepository shadeRepository;
  private final ProductShadeColorRepository colorRepository;

  public ProductSearchService(
      ProductCategoryRepository categoryRepository,
      ProductTypeRepository typeRepository,
      ProductRepository productRepository,
      ProductShadeRepository shadeRepository,
      ProductShadeColorRepository colorRepository) {
    this.categoryRepository = categoryRepository;
    this.typeRepository = typeRepository;
    this.productRepository = productRepository;
    this.shadeRepository = shadeRepository;
    this.colorRepository = colorRepository;
  }

  /**
   * 형식 검사({@code @Valid})를 통과한 쿼리로 찾는다.
   *
   * @return 정확히 일치하는 제품. 없으면 빈 목록
   * @throws BusinessException 400 {@code VALIDATION_FAILED}: 카테고리가 없으면 {@code category}, 종류가 없거나 다른
   *     카테고리 소속이면 {@code type}
   */
  public List<ProductResponse> search(ProductSearchQuery query) {
    requireTypeInCategory(query.category(), query.type());
    return productRepository
        .findExact(query.type(), query.brand(), query.name())
        .map(product -> List.of(toResponse(product)))
        .orElse(List.of());
  }

  /**
   * @throws BusinessException 404 {@code NOT_FOUND}: 제품이 없으면
   */
  public ProductResponse get(UUID productId) {
    return productRepository
        .findById(productId)
        .map(this::toResponse)
        .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
  }

  /**
   * 정상 요청은 종류 조회 한 번으로 끝난다. 종류가 없거나 소속이 다를 때만 카테고리가 있는지 확인해서, 없는 카테고리에 있는 종류를 붙인 요청도 {@code
   * category} 로 알려 준다.
   */
  private void requireTypeInCategory(String categoryCode, String typeCode) {
    Optional<ProductType> type = typeRepository.findById(typeCode);
    if (type.isPresent() && type.get().getCategory().getCode().equals(categoryCode)) {
      return;
    }
    if (!categoryRepository.existsById(categoryCode)) {
      throw invalid("category", UNKNOWN_CATEGORY);
    }
    throw invalid("type", UNKNOWN_TYPE);
  }

  private ProductResponse toResponse(Product product) {
    List<ProductShade> shades =
        shadeRepository.findByProductIdOrderBySortOrderAscNameNormalizedAsc(product.getId());
    Map<UUID, List<ProductShadeColor>> colorsByShade =
        shades.isEmpty()
            ? Map.of()
            : colorRepository
                .findByShadeIdInOrderByShadeIdAscSortOrderAsc(
                    shades.stream().map(ProductShade::getId).toList())
                .stream()
                .collect(Collectors.groupingBy(c -> c.getShade().getId()));
    return ProductResponse.of(
        product,
        shades.stream()
            .map(s -> ShadeResponse.of(s, colorsByShade.getOrDefault(s.getId(), List.of())))
            .toList());
  }

  private static BusinessException invalid(String field, String reason) {
    return new BusinessException(
        ErrorCode.VALIDATION_FAILED.status(),
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError(field, reason)),
        null);
  }
}
