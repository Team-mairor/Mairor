package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.imports.TypeResolution.Origin;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/**
 * 수집 상품의 카테고리·종류를 정한다. 순서:
 *
 * <ol>
 *   <li>매핑표({@code catalog/type-mapping.json})에 {@code (출처, 몰 카테고리 경로)}가 있으면 그 종류. 종류가 DB 에 없으면 쓰지
 *       않는다.
 *   <li>수집기가 보낸 {@code typeHint}가 실제 종류이고, {@code categoryHint}가 있으면 그 종류의 카테고리와 같을 때 그 종류. 카테고리만
 *       있고 종류가 없는 힌트는 종류를 정할 수 없어 받아들이지 않는다.
 *   <li>둘 다 안 되면 {@link Optional#empty() 비어 있다}. 호출하는 쪽이 {@code UNCLASSIFIED}로 기록한다. 추측해서 종류를 정하지
 *       않는다.
 * </ol>
 */
@Component
public class CatalogTypeMapper {

  static final String MAPPING_RESOURCE = "catalog/type-mapping.json";

  private final ProductTypeRepository typeRepository;
  private final TypeMappingTable table;

  @Autowired
  public CatalogTypeMapper(ProductTypeRepository typeRepository, ObjectMapper objectMapper) {
    this(typeRepository, load(objectMapper));
  }

  CatalogTypeMapper(ProductTypeRepository typeRepository, TypeMappingTable table) {
    this.typeRepository = typeRepository;
    this.table = table;
  }

  @Transactional(readOnly = true)
  public Optional<TypeResolution> resolve(
      String source, List<String> categoryPath, String categoryHint, String typeHint) {
    Optional<TypeResolution> mapped =
        table
            .find(source, categoryPath)
            .flatMap(typeRepository::findById)
            .map(type -> resolution(type, Origin.MAPPING));
    if (mapped.isPresent()) {
      return mapped;
    }
    if (typeHint == null) {
      return Optional.empty();
    }
    return typeRepository
        .findById(typeHint)
        .filter(type -> categoryHint == null || type.getCategory().getCode().equals(categoryHint))
        .map(type -> resolution(type, Origin.HINT));
  }

  private static TypeResolution resolution(ProductType type, Origin origin) {
    return new TypeResolution(type.getCategory().getCode(), type.getCode(), origin);
  }

  private static TypeMappingTable load(ObjectMapper objectMapper) {
    try (InputStream in = new ClassPathResource(MAPPING_RESOURCE).getInputStream()) {
      return TypeMappingTable.fromJson(objectMapper.readTree(in));
    } catch (IOException e) {
      throw new UncheckedIOException(MAPPING_RESOURCE + " 를 읽지 못했다", e);
    }
  }
}
