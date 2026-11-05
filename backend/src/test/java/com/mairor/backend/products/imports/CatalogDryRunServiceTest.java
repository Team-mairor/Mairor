package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.products.dto.request.CatalogDryRunRequest;
import com.mairor.backend.products.dto.response.CatalogDryRunResponse;
import com.mairor.backend.products.dto.response.CatalogDryRunResponse.Outcome;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;

/** 판정 시험 서비스의 건별 격리. 판정 중 예상하지 못한 오류가 나도 그 건만 실패하고 나머지는 판정한다. */
class CatalogDryRunServiceTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Path SAMPLES = Path.of("..", "shared", "catalog-import", "samples");

  private static JsonNode sample(String file) throws Exception {
    return MAPPER.readTree(Files.readString(SAMPLES.resolve(file)));
  }

  private static CatalogDryRunRequest request(JsonNode... items) {
    ArrayNode array = MAPPER.createArrayNode();
    for (JsonNode item : items) {
      array.add(item);
    }
    return new CatalogDryRunRequest(array);
  }

  @Test
  void aPlanningErrorFailsOnlyThatItem() throws Exception {
    CatalogMatchPlanner planner = mock(CatalogMatchPlanner.class);
    when(planner.plan(any())).thenThrow(new IllegalStateException("boom"));
    CatalogDryRunService service = new CatalogDryRunService(planner);

    CatalogDryRunResponse response =
        service.dryRun(
            request(sample("etude_option_image.json"), sample("invalid_incomplete_source.json")));

    assertThat(response.results()).hasSize(2);
    assertThat(response.results().get(0).outcome()).isEqualTo(Outcome.FAILED);
    assertThat(response.results().get(0).itemKey()).isEqualTo("000003");
    assertThat(response.results().get(0).issues()).isEmpty();
    // 검사에 실패한 항목은 계획까지 가지 않고 INVALID 로 남는다
    assertThat(response.results().get(1).outcome()).isEqualTo(Outcome.INVALID);
  }

  @Test
  void aNullRequestOrNullItemsIsABadRequest() {
    CatalogDryRunService service = new CatalogDryRunService(mock(CatalogMatchPlanner.class));

    assertThatThrownBy(() -> service.dryRun(null)).isInstanceOf(BusinessException.class);
    assertThatThrownBy(() -> service.dryRun(new CatalogDryRunRequest(null)))
        .isInstanceOf(BusinessException.class);
  }
}
