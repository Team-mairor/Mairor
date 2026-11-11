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
 * <p>결과 파일은 저장소에 남겨 두고 지우지 않는다. 그래도 파일이 없으면 오류가 아니라 {@code fileAvailable=false}로 알린다. 그때는 같은 값을 다시
 * 수집해서 판단한다. 저장소에 닿지 못한 것은 파일이 없는 것과 달라 503 으로 올린다.
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
   *     COLOR_EVIDENCE_NOT_RECORDED}: 적재가 만든 칸이 아니라(직접 넣은 칸) 근거를 찾아갈 키가 없으면. 503 {@code
   *     SERVICE_UNAVAILABLE}: 저장소에서 결과 파일을 받지 못하면
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
      return absent(e, null);
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
      return absent(e, false);
    }
  }

  /** 파일이 없거나 이름이 틀린 것만 "파일 없음"으로 본다. 저장소 장애(503)는 그대로 올려 운영자가 잠시 뒤 다시 보게 한다. */
  private static <T> T absent(BusinessException e, T value) {
    String code = e.code();
    if (CatalogRunFileReader.FILE_NOT_FOUND.equals(code)
        || CatalogRunFileReader.INVALID_FILE.equals(code)) {
      return value;
    }
    throw e;
  }
}
