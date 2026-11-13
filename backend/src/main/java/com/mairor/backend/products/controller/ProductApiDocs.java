package com.mairor.backend.products.controller;

/** 화장품 카탈로그 API 문서의 응답 예시. 애너테이션 값으로 쓰려고 상수로 둔다. 식별자·브랜드는 설명용 값이다 (개발용 샘플 시드와 같다). */
final class ProductApiDocs {

  private ProductApiDocs() {}

  /** 카테고리·종류 목록 성공 응답. 9개 중 형태가 다른 두 카테고리만 싣는다. */
  static final String CATEGORY_LIST =
      """
      {
        "items": [
          {
            "code": "BASE",
            "label": "베이스",
            "matchable": true,
            "shadeSelectable": true,
            "types": [
              {"code": "CUSHION", "label": "쿠션"},
              {"code": "FOUNDATION", "label": "파운데이션"}
            ],
            "compatibleParts": []
          },
          {
            "code": "FRAGRANCE",
            "label": "향수",
            "matchable": false,
            "shadeSelectable": false,
            "types": [{"code": "PERFUME", "label": "향수"}],
            "compatibleParts": []
          }
        ]
      }""";

  /** 제품 하나. 단색 호수, 팔레트 호수(칸 3개: 쓸 수 있는 색·쓰지 않는 색·색 없음), 칸이 없는 호수를 함께 싣는다. */
  private static final String PRODUCT =
      """
      {
        "productId": "00000000-0000-4000-8000-000000000101",
        "brand": "Mairor Sample",
        "name": "Water Gel Tint",
        "category": "LIP",
        "type": "LIP_TINT",
        "shades": [
          {
            "shadeId": "00000000-0000-4000-8000-000000000201",
            "name": "01 Coral",
            "colors": [
              {
                "colorId": "00000000-0000-4000-8000-000000000401",
                "name": null,
                "sortOrder": 1,
                "color": {"colorSpace": "sRGB", "hex": "#F2665A", "source": "CATALOG", "estimated": false}
              }
            ]
          },
          {
            "shadeId": "00000000-0000-4000-8000-000000000204",
            "name": "01 Dusk",
            "colors": [
              {
                "colorId": "00000000-0000-4000-8000-000000000404",
                "name": "Matte Sand",
                "sortOrder": 1,
                "color": {"colorSpace": "sRGB", "hex": "#D9B8A0", "source": "CATALOG", "estimated": false}
              },
              {
                "colorId": "00000000-0000-4000-8000-000000000405",
                "name": "Shimmer Rose",
                "sortOrder": 2,
                "color": null
              },
              {
                "colorId": "00000000-0000-4000-8000-000000000406",
                "name": null,
                "sortOrder": 3,
                "color": null
              }
            ]
          },
          {
            "shadeId": "00000000-0000-4000-8000-000000000203",
            "name": "03 Nude",
            "colors": []
          }
        ]
      }""";

  /** 제품 검색 성공 응답 (일치 1건). */
  static final String PRODUCT_SEARCH = "{\"items\": [" + PRODUCT + "]}";

  /** 제품 검색 성공 응답 (일치 없음). */
  static final String PRODUCT_SEARCH_EMPTY =
      """
      {"items": []}""";

  /** 제품 후보 검색 성공 응답. */
  static final String PRODUCT_SUGGEST =
      """
      {
        "items": [
          {
            "productId": "00000000-0000-4000-8000-000000000101",
            "brand": "롬앤",
            "name": "블러 퍼지 틴트 #오리지널",
            "category": "LIP",
            "type": "LIP_TINT"
          },
          {
            "productId": "00000000-0000-4000-8000-000000000102",
            "brand": "롬앤",
            "name": "블러 퍼지 틴트 #블랙스펙트럼",
            "category": "LIP",
            "type": "LIP_TINT"
          }
        ]
      }""";

  /** 제품 상세 성공 응답. */
  static final String PRODUCT_DETAIL = PRODUCT;

  /** 종류가 카테고리 소속이 아닌 검색 요청의 400. */
  static final String TYPE_NOT_IN_CATEGORY =
      """
      {
        "code": "VALIDATION_FAILED",
        "message": "입력값이 올바르지 않습니다.",
        "details": [{"field": "type", "reason": "없는 종류이거나 이 카테고리의 종류가 아닙니다."}]
      }""";

  /** 상세 조회할 제품이 없을 때의 404. */
  static final String PRODUCT_NOT_FOUND =
      """
      {"code": "NOT_FOUND", "message": "요청한 리소스를 찾을 수 없습니다."}""";
}
