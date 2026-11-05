package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import tools.jackson.databind.ObjectMapper;

class TypeMappingTableTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  private static TypeMappingTable table(String json) {
    return TypeMappingTable.fromJson(MAPPER.readTree(json));
  }

  @Test
  void findsAnEntryByNormalizedSourceAndWholePath() {
    TypeMappingTable table =
        table(
            """
            {"entries": [
              {"source": "OFFICIAL:romand.co.kr", "categoryPath": ["립", "틴트"], "type": "LIP_TINT"},
              {"source": "OFFICIAL:romand.co.kr", "categoryPath": ["립&치크"], "type": "BLUSHER"}
            ]}""");

    assertThat(table.size()).isEqualTo(2);
    assertThat(table.find("OFFICIAL:romand.co.kr", List.of("립", "틴트"))).contains("LIP_TINT");
    assertThat(table.find("official:ROMAND.co.kr", List.of(" 립 ", "틴트"))).contains("LIP_TINT");
    assertThat(table.find("OFFICIAL:romand.co.kr", List.of("립&치크"))).contains("BLUSHER");
  }

  @Test
  void doesNotMatchAPartOfThePathAnotherSourceOrAnEmptyPath() {
    TypeMappingTable table =
        table(
            """
            {"entries": [{"source": "OFFICIAL:romand.co.kr", "categoryPath": ["립", "틴트"], "type": "LIP_TINT"}]}""");

    assertThat(table.find("OFFICIAL:romand.co.kr", List.of("립"))).isEmpty();
    assertThat(table.find("OFFICIAL:romand.co.kr", List.of("립", "틴트", "신상"))).isEmpty();
    assertThat(table.find("OFFICIAL:etude.com", List.of("립", "틴트"))).isEmpty();
    assertThat(table.find("OFFICIAL:romand.co.kr", List.of())).isEmpty();
    assertThat(table.find(null, List.of("립", "틴트"))).isEmpty();
  }

  @Test
  void emptyTableFindsNothing() {
    assertThat(table("{\"entries\": []}").size()).isZero();
    assertThat(TypeMappingTable.empty().find("OFFICIAL:a.com", List.of("립"))).isEmpty();
  }

  @Test
  void rejectsAMalformedFileOrADuplicateKey() {
    assertThatThrownBy(() -> table("{}")).isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                table("{\"entries\": [{\"source\": \"OFFICIAL:a.com\", \"type\": \"LIP_TINT\"}]}"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                table(
                    "{\"entries\": [{\"source\": \"OFFICIAL:a.com\", \"categoryPath\": [], \"type\": \"X\"}]}"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                table(
                    """
                    {"entries": [
                      {"source": "OFFICIAL:a.com", "categoryPath": ["립"], "type": "LIP_TINT"},
                      {"source": "official:a.com", "categoryPath": [" 립"], "type": "LIPSTICK"}
                    ]}"""))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("두 번");
  }

  @Test
  void theShippedMappingFileIsReadable() throws Exception {
    try (var in = new ClassPathResource("catalog/type-mapping.json").getInputStream()) {
      assertThat(TypeMappingTable.fromJson(MAPPER.readTree(in)).size()).isNotNegative();
    }
  }
}
