package com.mairor.backend.products.imports;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.products.entity.CatalogImportItem;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.repository.ProductShadeColorRepository;
import java.nio.file.Path;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;

/**
 * 색 칸의 현재 값이 어떤 근거(이미지 URL, 영역, 방법, 품질 점수)에서 나왔는지 실행 결과 파일에서 찾아 준다. DB 에는 근거를 두지 않고 찾아가는 키(적재 건과 근거
 * 키)만 있으므로, 이 조회가 키를 따라 파일을 연다.
 *
 * <p>파일은 보관 기간(30일)이 지나면 지워진다. 파일이 없으면 오류가 아니라 {@code fileAvailable=false}로 알린다. 근거가 필요한 판단(임계값
 * 재검토, 잘못된 색 정정)은 파일이 있을 때 하고, 지난 뒤에는 같은 값을 다시 수집해서 한다.
 */
@Service
public class CatalogEvidenceService {

  public static final String COLOR_NOT_FOUND = "COLOR_NOT_FOUND";
  public static final String EVIDENCE_NOT_RECORDED = "COLOR_EVIDENCE_NOT_RECORDED";

  private final ProductShadeColorRepository colors;
  private final CatalogRunFileReader reader;

  public CatalogEvidenceService(ProductShadeColorRepository colors, CatalogRunFileReader reader) {
    this.colors = colors;
    this.reader = reader;
  }

  /**
   * 근거 조회 결과.
   *
   * @param fileAvailable 실행 결과 파일을 열 수 있었는가
   * @param evidence 그 칸의 근거 기록({@code evidenceKey}가 같은 항목). 파일이 없거나 그 건·키가 파일에 없으면 {@code null}
   */
  public record Evidence(
      UUID colorId,
      String evidenceKey,
      String itemKey,
      String runId,
      String resultFile,
      boolean fileAvailable,
      JsonNode evidence) {}

  /**
   * 색 칸의 현재 값의 근거를 찾는다.
   *
   * @throws BusinessException 404 {@code COLOR_NOT_FOUND}: 칸이 없으면. 404 {@code
   *     COLOR_EVIDENCE_NOT_RECORDED}: 적재가 만든 칸이 아니라(직접 넣은 칸) 근거를 찾아갈 키가 없으면
   */
  @Transactional(readOnly = true)
  public Evidence find(UUID colorId) {
    ProductShadeColor slot =
        colors
            .findById(colorId)
            .orElseThrow(
                () ->
                    new BusinessException(
                        HttpStatus.NOT_FOUND, COLOR_NOT_FOUND, "색 칸을 찾을 수 없습니다: " + colorId));
    CatalogImportItem item = slot.getSourceItem();
    if (item == null || slot.getSourceEvidenceKey() == null) {
      throw new BusinessException(
          HttpStatus.NOT_FOUND, EVIDENCE_NOT_RECORDED, "이 칸은 적재가 만든 칸이 아니라 근거를 찾아갈 키가 없습니다.");
    }
    String file = item.getRun().getResultFile();
    JsonNode evidence = file == null ? null : lookup(file, item.getItemKey(), slot);
    return new Evidence(
        slot.getId(),
        slot.getSourceEvidenceKey(),
        item.getItemKey(),
        item.getRun().getRunId(),
        file,
        evidence != null || fileExists(file),
        evidence);
  }

  private JsonNode lookup(String file, String itemKey, ProductShadeColor slot) {
    Path path;
    try {
      path = reader.resolve(file);
    } catch (BusinessException e) {
      return null;
    }
    JsonNode line = reader.findItem(path, itemKey);
    if (line == null) {
      return null;
    }
    for (JsonNode candidate : line.path("evidence")) {
      if (slot.getSourceEvidenceKey().equals(candidate.path("evidenceKey").asString(null))) {
        return candidate;
      }
    }
    return null;
  }

  private boolean fileExists(String file) {
    if (file == null) {
      return false;
    }
    try {
      reader.resolve(file);
      return true;
    } catch (BusinessException e) {
      return false;
    }
  }
}
