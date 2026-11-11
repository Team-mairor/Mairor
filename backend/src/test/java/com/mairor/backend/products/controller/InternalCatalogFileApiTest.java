package com.mairor.backend.products.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.InternalTokenFilter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 파일 적재(from-file)와 근거 조회 API 의 인증·요청 검증·응답 계약. 처리 규칙은 CatalogImportFileServiceTest 가 본다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + InternalCatalogFileApiTest.TOKEN,
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8"
    })
@AutoConfigureMockMvc
class InternalCatalogFileApiTest {

  static final String TOKEN = "test-internal-token";
  private static final String FROM_FILE = "/v1/internal/catalog/import-runs/from-file";
  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Path DIRECTORY = newDirectory();

  private static Path newDirectory() {
    try {
      return Files.createTempDirectory("catalog-runs-api-test");
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  @DynamicPropertySource
  static void directory(DynamicPropertyRegistry registry) {
    registry.add("catalog.import.result-dir", DIRECTORY::toString);
  }

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void setUp() throws IOException {
    clean();
    jdbc.update(
        "insert into product_categories (code, label, matchable, shade_selectable, sort_order)"
            + " values ('EYE', '아이', true, true, 3)");
    jdbc.update(
        "insert into product_types (code, category_code, label, sort_order)"
            + " values ('MASCARA', 'EYE', '마스카라', 2)");
  }

  @AfterEach
  void tearDown() throws IOException {
    clean();
  }

  private void clean() throws IOException {
    for (String table :
        List.of(
            "product_shade_colors",
            "product_shade_option_aliases",
            "product_shades",
            "catalog_import_items",
            "products",
            "catalog_import_runs",
            "product_category_parts",
            "product_types",
            "product_categories")) {
      jdbc.update("delete from " + table);
    }
    try (var stream = Files.list(DIRECTORY)) {
      for (Path file : stream.toList()) {
        Files.delete(file);
      }
    }
  }

  private void writeFile(String name) throws Exception {
    ObjectNode collected = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    collected.put("itemKey", "000001");
    ObjectNode row = MAPPER.createObjectNode();
    row.put("itemKey", "000001");
    row.set("collected", collected);
    var evidence = row.putArray("evidence");
    for (var shade : collected.path("shades")) {
      ObjectNode record = evidence.addObject();
      record.put("evidenceKey", shade.path("colors").get(0).path("evidenceKey").asString());
      record.put("method", "pixel_median_lab");
    }
    String header =
        "{\"runId\":\"api-run\",\"startedAt\":\"2026-11-08T21:30:00+09:00\","
            + "\"seed\":\"OFFICIAL:etude.com\",\"collectorVersion\":\"0.1.0\"}";
    Files.writeString(
        DIRECTORY.resolve(name),
        header + "\n" + MAPPER.writeValueAsString(row) + "\n",
        StandardCharsets.UTF_8);
  }

  private MockHttpServletRequestBuilder fromFile(String json) {
    return post(FROM_FILE)
        .header(InternalTokenFilter.HEADER, TOKEN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  @Test
  void fromFileAndEvidenceRequireTheInternalToken() throws Exception {
    mockMvc
        .perform(
            post(FROM_FILE)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"resultFile\":\"a.jsonl\"}"))
        .andExpect(status().isUnauthorized());
    mockMvc
        .perform(get("/v1/internal/catalog/shade-colors/" + UUID.randomUUID() + "/evidence"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void aFileIsImportedAndTheColorsEvidenceCanBeRead() throws Exception {
    writeFile("api.jsonl");

    mockMvc
        .perform(fromFile("{\"resultFile\":\"api.jsonl\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.finished").value(true))
        .andExpect(jsonPath("$.processed").value(1))
        .andExpect(jsonPath("$.unreadable").value(0));

    String colorId =
        jdbc.queryForObject(
            "select id::text from product_shade_colors where source_evidence_key is not null"
                + " limit 1",
            String.class);
    mockMvc
        .perform(
            get("/v1/internal/catalog/shade-colors/" + colorId + "/evidence")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.itemKey").value("000001"))
        .andExpect(jsonPath("$.runId").value("api-run"))
        .andExpect(jsonPath("$.resultFile").value("api.jsonl"))
        .andExpect(jsonPath("$.fileAvailable").value(true))
        .andExpect(jsonPath("$.evidence.method").value("pixel_median_lab"));
  }

  @Test
  void badRequestsGetTheirOwnCodes() throws Exception {
    mockMvc.perform(fromFile("{\"resultFile\":\"../x.jsonl\"}")).andExpect(status().isBadRequest());
    mockMvc.perform(fromFile("{}")).andExpect(status().isBadRequest());
    mockMvc
        .perform(fromFile("{\"resultFile\":\"a.jsonl\",\"limit\":0}"))
        .andExpect(status().isBadRequest());
    mockMvc
        .perform(fromFile("{\"resultFile\":\"gone.jsonl\"}"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("RESULT_FILE_NOT_FOUND"));
    mockMvc
        .perform(
            get("/v1/internal/catalog/shade-colors/" + UUID.randomUUID() + "/evidence")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("COLOR_NOT_FOUND"));
  }
}
