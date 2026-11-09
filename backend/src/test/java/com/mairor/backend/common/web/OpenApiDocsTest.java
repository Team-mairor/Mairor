package com.mairor.backend.common.web;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.is;
import static org.hamcrest.Matchers.matchesPattern;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.Product;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** 개발(dev) 기본 설정: API 문서와 Swagger UI 가 로그인 없이 열리고, 다른 API 는 그대로 보호된다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocsTest {

  /**
   * 문서에 나오는 API 수(메서드 단위). 파우치 등록 POST·목록 GET·상세 GET·수정 PATCH·삭제 DELETE, 수집 상품 판정 시험 POST, 영상 검색
   * GET·선택 POST, 분석 요청 POST, 노트북 작업 POST 4개 포함. API 를 추가하면 함께 올린다.
   */
  private static final int ALL_OPERATIONS = 52;

  @Autowired private MockMvc mockMvc;

  @Test
  void apiDocs_isPublicAndDescribesTheApi() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath("$.paths['/health']").exists());
  }

  @Test
  void apiDocs_includesSignUp() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/signup'].post").exists());
  }

  /** Swagger UI 의 기본 입력이 "string" 이 아니라 바로 보낼 수 있는 값(필수 약관 3개 포함)이어야 한다. */
  @Test
  void apiDocs_signUpHasUsableExample() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/signup'].post.requestBody.content['application/json'].examples")
                .isNotEmpty())
        .andExpect(
            jsonPath("$.components.schemas.SignupAgreement.properties.version.example")
                .value("2026-10-26"))
        .andExpect(
            jsonPath("$.components.schemas.SignupAgreement.properties.type.example").value("TERMS"))
        .andExpect(
            jsonPath("$.components.schemas.SignUpRequest.properties.email.example")
                .value("user@example.com"));
  }

  @Test
  void apiDocs_includesEmailVerification() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/email-verification'].post").exists())
        .andExpect(jsonPath("$.paths['/v1/users/email-verification/verification'].post").exists());
  }

  @Test
  void apiDocs_includesGoogleLoginStartAsAPublicRedirect() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/oauth/google'].get.tags[0]").value("Google 로그인"))
        .andExpect(jsonPath("$.paths['/v1/users/oauth/google'].get.security").doesNotExist())
        .andExpect(jsonPath("$.paths['/v1/users/oauth/google'].get.responses['302']").exists())
        .andExpect(
            jsonPath("$.paths['/v1/users/oauth/google'].get.responses['429'].description")
                .value(containsString("USERS_LOGIN_RATE_LIMITED")))
        .andExpect(
            jsonPath("$.paths['/v1/users/oauth/google'].get.responses['503'].description")
                .value(containsString("USERS_GOOGLE_AUTH_UNAVAILABLE")));
  }

  @Test
  void apiDocs_includesPasswordResetAndDocumentsItsErrorCodes() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/password-reset'].post.tags[0]").value("비밀번호 재설정"))
        .andExpect(jsonPath("$.paths['/v1/users/password-reset'].post.security").doesNotExist())
        .andExpect(
            jsonPath("$.paths['/v1/users/password-reset'].post.responses['429'].description")
                .value(containsString("USERS_RESET_RATE_LIMITED")))
        .andExpect(
            jsonPath("$.paths['/v1/users/password-reset'].post.responses['503'].description")
                .value(containsString("USERS_RESET_SEND_FAILED")))
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/password-reset/verification'].post.responses['400'].description")
                .value(containsString("USERS_RESET_CODE_INVALID")))
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/password-reset/verification'].post.responses['410'].description")
                .value(containsString("USERS_RESET_CODE_EXPIRED")))
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/password-reset/verification'].post.responses['429'].description")
                .value(containsString("USERS_RESET_CODE_ATTEMPTS_EXCEEDED")))
        .andExpect(
            jsonPath("$.components.schemas.PasswordResetRequest.properties.email.example")
                .value("user@example.com"))
        .andExpect(jsonPath("$.paths['/v1/users/password-reset/password'].put").exists())
        .andExpect(
            jsonPath("$.paths['/v1/users/password-reset/password'].put.security").doesNotExist())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/password-reset/password'].put.responses['410'].description")
                .value(containsString("USERS_RESET_TOKEN_EXPIRED")))
        .andExpect(
            jsonPath("$.paths['/v1/users/password-reset/password'].put.parameters").doesNotExist());
  }

  @Test
  void apiDocs_includesEmailAvailability() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/email-availability'].post").exists());
  }

  // ---- 로그인·기기 관리 ----

  @Test
  void apiDocs_includesLoginLogoutAndMe() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/login'].post").exists())
        .andExpect(jsonPath("$.paths['/v1/users/logout'].post").exists())
        .andExpect(jsonPath("$.paths['/v1/users/me'].get").exists());
  }

  @Test
  void apiDocs_includesDeviceManagement() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/me/sessions'].get").exists())
        .andExpect(jsonPath("$.paths['/v1/users/me/sessions'].delete").exists())
        .andExpect(jsonPath("$.paths['/v1/users/me/sessions/{sessionRef}'].delete").exists());
  }

  /** Swagger UI 의 기본 입력이 "string" 이 아니라 바로 보낼 수 있는 값이어야 한다. */
  @Test
  void apiDocs_loginHasUsableExamples() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/login'].post.requestBody.content['application/json'].examples")
                .isNotEmpty())
        .andExpect(
            jsonPath("$.components.schemas.LoginRequest.properties.email.example")
                .value("user@example.com"))
        .andExpect(jsonPath("$.components.schemas.LoginResponse.properties.csrfToken").exists())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/login'].post.responses['200'].content['application/json'].examples")
                .isNotEmpty());
  }

  @Test
  void apiDocs_loginDocumentsEveryErrorWithItsRealCode() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/login'].post.responses['400']").exists())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/login'].post.responses['401'].content['application/json'].examples.USERS_INVALID_CREDENTIALS")
                .exists())
        .andExpect(jsonPath("$.paths['/v1/users/login'].post.responses['403']").exists())
        .andExpect(jsonPath("$.paths['/v1/users/login'].post.responses['415']").exists())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/login'].post.responses['429'].content['application/json'].examples.USERS_LOGIN_RATE_LIMITED")
                .exists())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/login'].post.responses['429'].content['application/json'].examples.TOO_MANY_REQUESTS")
                .exists())
        .andExpect(
            jsonPath("$.paths['/v1/users/login'].post.responses['429'].headers['Retry-After']")
                .exists());
  }

  @Test
  void apiDocs_loginSetsTheSessionCookieAndLogoutExpiresIt() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath("$.paths['/v1/users/login'].post.responses['200'].headers['Set-Cookie']")
                .exists())
        .andExpect(
            jsonPath("$.paths['/v1/users/logout'].post.responses['204'].headers['Set-Cookie']")
                .exists());
  }

  @Test
  void apiDocs_describesTheSessionCookieAndCsrfTokenSchemes() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.components.securitySchemes.sessionCookie.type").value("apiKey"))
        .andExpect(jsonPath("$.components.securitySchemes.sessionCookie.in").value("cookie"))
        .andExpect(
            jsonPath("$.components.securitySchemes.sessionCookie.name").value("__Host-sessionId"))
        .andExpect(jsonPath("$.components.securitySchemes.csrfToken.type").value("apiKey"))
        .andExpect(jsonPath("$.components.securitySchemes.csrfToken.in").value("header"))
        .andExpect(jsonPath("$.components.securitySchemes.csrfToken.name").value("X-CSRF-TOKEN"));
  }

  /** 로그인은 공개이고, 로그인이 필요한 API 는 세션 쿠키를, 변경 요청은 세션 쿠키와 CSRF 토큰을 함께 요구한다(둘 중 하나가 아니다). */
  @Test
  void apiDocs_marksWhichEndpointsNeedWhichCredentials() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/login'].post.security").doesNotExist())
        .andExpect(jsonPath("$.paths['/v1/users/me'].get.security.length()").value(1))
        .andExpect(jsonPath("$.paths['/v1/users/me'].get.security[0].sessionCookie").exists())
        .andExpect(jsonPath("$.paths['/v1/users/me'].get.security[0].csrfToken").doesNotExist())
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions'].get.security[0].sessionCookie").exists())
        .andExpect(jsonPath("$.paths['/v1/users/logout'].post.security.length()").value(1))
        .andExpect(jsonPath("$.paths['/v1/users/logout'].post.security[0].sessionCookie").exists())
        .andExpect(jsonPath("$.paths['/v1/users/logout'].post.security[0].csrfToken").exists())
        .andExpect(jsonPath("$.paths['/v1/users/me/sessions'].delete.security.length()").value(1))
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions'].delete.security[0].csrfToken").exists())
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions/{sessionRef}'].delete.security.length()")
                .value(1))
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions/{sessionRef}'].delete.security[0].csrfToken")
                .exists());
  }

  @Test
  void apiDocs_protectedEndpointsDocumentTheirAuthErrors() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/me'].get.responses['401']").exists())
        .andExpect(jsonPath("$.paths['/v1/users/me/sessions'].get.responses['401']").exists())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/logout'].post.responses['403'].content['application/json'].examples.CSRF_INVALID")
                .exists())
        .andExpect(jsonPath("$.paths['/v1/users/me/sessions'].delete.responses['403']").exists())
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions/{sessionRef}'].delete.responses['403']")
                .exists())
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions/{sessionRef}'].delete.responses['404']")
                .exists());
  }

  @Test
  void apiDocs_deviceListDoesNotExposeInternalParameters() throws Exception {
    // 인증된 principal 같은 내부 인자가 요청 파라미터로 새어 나오면 안 된다
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/me/sessions'].get.parameters").doesNotExist())
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions/{sessionRef}'].delete.parameters.length()")
                .value(1))
        .andExpect(
            jsonPath("$.paths['/v1/users/me/sessions/{sessionRef}'].delete.parameters[0].name")
                .value("sessionRef"));
  }

  /** 카테고리·종류 목록은 로그인이 필요한 조회라 세션 쿠키만 요구하고, 401 과 성공 예시·필드 예시를 문서에 싣는다. */
  @Test
  void apiDocs_includesProductCategoriesAsAMemberOnlyRead() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/product-categories'].get.tags[0]").value("화장품 카탈로그"))
        .andExpect(jsonPath("$.paths['/v1/product-categories'].get.security.length()").value(1))
        .andExpect(
            jsonPath("$.paths['/v1/product-categories'].get.security[0].sessionCookie").exists())
        .andExpect(
            jsonPath("$.paths['/v1/product-categories'].get.security[0].csrfToken").doesNotExist())
        .andExpect(jsonPath("$.paths['/v1/product-categories'].get.parameters").doesNotExist())
        .andExpect(jsonPath("$.paths['/v1/product-categories'].get.responses['401']").exists())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/product-categories'].get.responses['200'].content['application/json'].examples")
                .isNotEmpty())
        .andExpect(
            jsonPath("$.components.schemas.ProductCategoryResponse.properties.code.example")
                .value("BASE"))
        .andExpect(
            jsonPath("$.components.schemas.ProductTypeResponse.properties.code.example")
                .value("CUSHION"))
        // 호환 부위 코드는 정해지지 않았으므로 예시에 임의의 코드를 싣지 않는다
        .andExpect(
            jsonPath(
                    "$.components.schemas.ProductCategoryResponse.properties.compatibleParts.example")
                .isArray())
        .andExpect(
            jsonPath(
                    "$.components.schemas.ProductCategoryResponse.properties.compatibleParts.example.length()")
                .value(0))
        .andExpect(
            jsonPath(
                    "$.components.schemas.ProductCategoryResponse.properties.compatibleParts.items.example")
                .doesNotExist());
  }

  /** 제품 검색·상세는 로그인이 필요한 조회라 세션 쿠키만 요구하고, 오류 응답과 예시를 싣는다. 검색 조건은 쿼리 파라미터 4개로 펼쳐 보인다. */
  @Test
  void apiDocs_includesProductSearchAndDetailAsMemberOnlyReads() throws Exception {
    String search = "$.paths['/v1/products'].get";
    String detail = "$.paths['/v1/products/{productId}'].get";
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(search + ".tags[0]").value("화장품 카탈로그"))
        .andExpect(jsonPath(detail + ".tags[0]").value("화장품 카탈로그"))
        .andExpect(jsonPath(search + ".security.length()").value(1))
        .andExpect(jsonPath(search + ".security[0].sessionCookie").exists())
        .andExpect(jsonPath(search + ".security[0].csrfToken").doesNotExist())
        .andExpect(jsonPath(detail + ".security[0].sessionCookie").exists())
        .andExpect(jsonPath(detail + ".security[0].csrfToken").doesNotExist())
        .andExpect(jsonPath(search + ".parameters.length()").value(4))
        .andExpect(
            jsonPath(
                search + ".parameters[*].name",
                containsInAnyOrder("category", "type", "brand", "name")))
        .andExpect(jsonPath(search + ".parameters[*].in", everyItem(is("query"))))
        // brand·name 길이 제한이 엔티티 상한과 같게 보여야 한다 (@CatalogText 만으로는 표시되지 않는다)
        .andExpect(
            jsonPath(search + ".parameters[?(@.name == 'brand')].schema.maxLength")
                .value(Product.BRAND_MAX_LENGTH))
        .andExpect(
            jsonPath(search + ".parameters[?(@.name == 'name')].schema.maxLength")
                .value(Product.NAME_MAX_LENGTH))
        .andExpect(jsonPath(search + ".parameters[?(@.name == 'name')].schema.minLength").value(1))
        // 네 값 모두 필수다 (@CatalogText 만 붙은 brand·name 도 필수로 보여야 한다)
        .andExpect(jsonPath(search + ".parameters[*].required", everyItem(is(true))))
        .andExpect(
            jsonPath(search + ".parameters[?(@.name == 'type')].schema.example").value("LIP_TINT"))
        .andExpect(jsonPath(detail + ".parameters.length()").value(1))
        .andExpect(jsonPath(detail + ".parameters[0].name").value("productId"))
        .andExpect(jsonPath(detail + ".parameters[0].in").value("path"))
        .andExpect(
            jsonPath(search + ".responses['200'].content['application/json'].examples")
                .isNotEmpty())
        .andExpect(
            jsonPath(
                    search
                        + ".responses['400'].content['application/json'].examples.VALIDATION_FAILED")
                .exists())
        .andExpect(jsonPath(search + ".responses['401']").exists())
        .andExpect(
            jsonPath(detail + ".responses['200'].content['application/json'].examples")
                .isNotEmpty())
        .andExpect(jsonPath(detail + ".responses['400']").exists())
        .andExpect(
            jsonPath(detail + ".responses['404'].content['application/json'].examples.NOT_FOUND")
                .exists())
        .andExpect(jsonPath(detail + ".responses['401']").exists())
        .andExpect(
            jsonPath("$.components.schemas.ColorInfoResponse.properties.hex.example")
                .value("#F2665A"))
        .andExpect(
            jsonPath("$.components.schemas.ColorInfoResponse.properties.source.example")
                .value("CATALOG"))
        .andExpect(
            jsonPath("$.components.schemas.ShadeColorResponse.properties.colorId.example")
                .isNotEmpty())
        .andExpect(
            jsonPath("$.components.schemas.ShadeColorResponse.properties.sortOrder.example")
                .value(1))
        .andExpect(
            jsonPath("$.components.schemas.ShadeResponse.properties.colors.description")
                .isNotEmpty())
        .andExpect(
            jsonPath("$.components.schemas.ProductResponse.properties.type.example")
                .value("LIP_TINT"));
  }

  @Test
  void apiDocs_catalogDryRunUsesTheInternalTokenAndDocumentsItsResults() throws Exception {
    String dryRun = "$.paths['/v1/internal/catalog/import-runs/dry-run'].post";

    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(dryRun + ".tags[0]").value("운영 · 화장품 카탈로그 수집"))
        .andExpect(jsonPath(dryRun + ".summary").value("수집 상품 판정 시험"))
        .andExpect(jsonPath(dryRun + ".security[0].internalToken").exists())
        .andExpect(
            jsonPath(dryRun + ".responses['200'].content['application/json'].examples")
                .isNotEmpty())
        .andExpect(
            jsonPath(
                    dryRun
                        + ".responses['400'].content['application/json'].examples.VALIDATION_FAILED")
                .exists())
        .andExpect(jsonPath(dryRun + ".responses['401']").exists())
        .andExpect(jsonPath("$.components.schemas.Item.properties.outcome.description").exists());
  }

  /** Swagger UI 의 그룹 이름이 한국어로 통일돼 있어야 한다(기본값 user-controller 같은 영문 이름이 남으면 안 된다). */
  @Test
  void apiDocs_everyOperationIsGroupedUnderAKoreanTag() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths.*.*.tags[*]").isNotEmpty())
        .andExpect(jsonPath("$.paths.*.*.tags[*]", everyItem(matchesPattern(".*[가-힣].*"))))
        .andExpect(jsonPath("$.paths['/v1/users/signup'].post.tags[0]").value("회원가입"))
        .andExpect(jsonPath("$.paths['/v1/users/email-verification'].post.tags[0]").value("이메일 인증"))
        .andExpect(jsonPath("$.paths['/health'].get.tags[0]").value("헬스체크"));
  }

  /** 모든 API 에 한국어 이름(summary)과 설명(description)이 있어야 한다. 새 API 에서 빠뜨리면 여기서 걸린다. */
  @Test
  void apiDocs_everyOperationHasKoreanSummaryAndDescription() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths.*.*.summary", everyItem(matchesPattern(".*[가-힣].*"))))
        .andExpect(jsonPath("$.paths.*.*.description", everyItem(matchesPattern("(?s).*[가-힣].*"))))
        .andExpect(jsonPath("$.paths.*.*.summary", hasSize(ALL_OPERATIONS)))
        .andExpect(jsonPath("$.paths.*.*.description", hasSize(ALL_OPERATIONS)));
  }

  /** 운영 내부 API 는 세션이 아니라 공유 토큰 헤더로 표시한다. */
  @Test
  void apiDocs_internalAnalysisJobsUseTheInternalToken() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath("$.paths['/v1/internal/analysis-jobs'].post.tags[0]").value("운영 · 분석 작업"))
        .andExpect(
            jsonPath("$.paths['/v1/internal/analysis-jobs'].post.security[0].internalToken")
                .exists())
        .andExpect(jsonPath("$.paths['/v1/internal/analysis-jobs'].post.responses['202']").exists())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/internal/analysis-jobs/{jobId}'].get.responses['404'].description")
                .value(containsString("NOT_FOUND")))
        .andExpect(
            jsonPath("$.components.securitySchemes.internalToken.name").value("X-Internal-Token"))
        .andExpect(
            jsonPath(
                    "$.components.schemas.RegisterAnalysisJobRequest.properties.youtubeVideoId.example")
                .value("VxAXD6PP76I"));
  }

  /** Swagger UI 가 로그인 응답의 csrfToken 을 변경 요청에 자동으로 넣는다(springdoc 의 기본 설정은 그대로 유지). */
  @Test
  void swaggerInitializer_autofillsTheCsrfTokenAndKeepsTheDefaultConfig() throws Exception {
    mockMvc
        .perform(get("/swagger-ui/swagger-initializer.js"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("SwaggerUIBundle")))
        .andExpect(content().string(containsString("/v3/api-docs")))
        .andExpect(content().string(containsString("X-CSRF-TOKEN")))
        .andExpect(content().string(containsString("/v1/users/login")));
  }

  @Test
  void swaggerUi_isPublic() throws Exception {
    mockMvc.perform(get("/swagger-ui/index.html")).andExpect(status().isOk());
  }

  @Test
  void swaggerUiConfig_isPublicSoTheScreenCanLoad() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs/swagger-config"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.url").exists());
  }

  @Test
  void otherEndpoints_stillRequireLogin() throws Exception {
    mockMvc
        .perform(get("/v1/any"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }
}
