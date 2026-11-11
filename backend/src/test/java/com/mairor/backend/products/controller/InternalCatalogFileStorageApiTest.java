package com.mairor.backend.products.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.InternalTokenFilter;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
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
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 운영 설정({@code catalog.import.source=storage})의 from-file: 결과 파일을 저장소의 {@code catalog-runs/} 에서 받아
 * 적재한다. 저장소는 로컬 폴더 구현이고, 닿지 못하는 경우만 바꿔 끼운다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + InternalCatalogFileStorageApiTest.TOKEN,
      "app.storage.type=local",
      "catalog.import.source=storage",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8"
    })
@AutoConfigureMockMvc
class InternalCatalogFileStorageApiTest {

  static final String TOKEN = "test-internal-token";
  private static final String FROM_FILE = "/v1/internal/catalog/import-runs/from-file";
  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Path BUCKET = newDirectory("catalog-bucket-test");
  private static final Path CACHE = newDirectory("catalog-cache-test");

  private static Path newDirectory(String prefix) {
    try {
      return Files.createTempDirectory(prefix);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  @DynamicPropertySource
  static void directories(DynamicPropertyRegistry registry) {
    registry.add("app.storage.local.root", BUCKET::toString);
    registry.add("catalog.import.result-dir", CACHE::toString);
  }

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @MockitoSpyBean private ObjectStorage storage;

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
    for (Path directory : List.of(CACHE, BUCKET.resolve("catalog-runs"))) {
      if (!Files.isDirectory(directory)) {
        continue;
      }
      try (var stream = Files.list(directory)) {
        for (Path file : stream.toList()) {
          Files.delete(file);
        }
      }
    }
  }

  private void upload(String name) throws Exception {
    ObjectNode collected = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    collected.put("itemKey", "000001");
    ObjectNode row = MAPPER.createObjectNode();
    row.put("itemKey", "000001");
    row.set("collected", collected);
    row.putArray("evidence");
    String header =
        "{\"runId\":\"storage-run\",\"startedAt\":\"2026-11-08T21:30:00+09:00\","
            + "\"seed\":\"OFFICIAL:etude.com\",\"collectorVersion\":\"0.1.0\"}";
    Path object = BUCKET.resolve("catalog-runs").resolve(name);
    Files.createDirectories(object.getParent());
    Files.writeString(
        object, header + "\n" + MAPPER.writeValueAsString(row) + "\n", StandardCharsets.UTF_8);
  }

  private MockHttpServletRequestBuilder fromFile(String name) {
    return post(FROM_FILE)
        .header(InternalTokenFilter.HEADER, TOKEN)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"resultFile\":\"" + name + "\"}");
  }

  @Test
  void aFileInTheStorageIsDownloadedAndImported() throws Exception {
    upload("20261108-213000-etude.jsonl");

    mockMvc
        .perform(fromFile("20261108-213000-etude.jsonl"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.finished").value(true))
        .andExpect(jsonPath("$.processed").value(1));
  }

  @Test
  void aFileMissingFromTheStorageIsNotFound() throws Exception {
    mockMvc
        .perform(fromFile("20261108-213000-none.jsonl"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("RESULT_FILE_NOT_FOUND"));
  }

  @Test
  void evidenceIsUnavailableNotMissingWhenTheStorageIsDown() throws Exception {
    upload("20261108-213000-etude.jsonl");
    mockMvc.perform(fromFile("20261108-213000-etude.jsonl")).andExpect(status().isOk());
    String colorId =
        jdbc.queryForObject(
            "select id::text from product_shade_colors where source_evidence_key is not null"
                + " limit 1",
            String.class);
    try (var cached = Files.list(CACHE)) {
      for (Path file : cached.toList()) {
        Files.delete(file);
      }
    }
    doThrow(new StorageException("닿지 못함", null))
        .when(storage)
        .download(anyString(), any(Path.class));

    mockMvc
        .perform(
            get("/v1/internal/catalog/shade-colors/" + colorId + "/evidence")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"));
  }

  @Test
  void anUnreachableStorageIsUnavailable() throws Exception {
    upload("20261108-213000-etude.jsonl");
    doThrow(new StorageException("닿지 못함", null))
        .when(storage)
        .download(anyString(), any(Path.class));

    mockMvc
        .perform(fromFile("20261108-213000-etude.jsonl"))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"));
  }
}
