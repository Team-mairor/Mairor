package com.mairor.backend.products.controller;

/** 화장품 카탈로그 수집(내부) API 문서의 요청·응답 예시. 애너테이션 값으로 쓰려고 상수로 둔다. 식별자·브랜드는 설명용 값이다. */
final class CatalogImportApiDocs {

  private CatalogImportApiDocs() {}

  /** 판정 시험 요청. 항목 모양은 shared/catalog-import 의 CollectedProduct 이다. */
  static final String DRY_RUN_REQUEST =
      """
      {
        "items": [
          {
            "contractVersion": 1,
            "itemKey": "000001",
            "source": "OFFICIAL:etude.com",
            "sourceProductId": "example-curl-fix-mascara",
            "sourceUrl": "https://www.etude.com/shop/category/eye/example-curl-fix-mascara/",
            "sourceLanguage": "ko",
            "collectedAt": "2026-11-05T10:32:00+09:00",
            "brand": "에뛰드",
            "name": "예시 컬 픽스 마스카라",
            "categoryHint": "EYE",
            "typeHint": "MASCARA",
            "shades": [
              {
                "sourceOptionId": "01-black",
                "name": "01 블랙",
                "sortOrder": 1,
                "slotOrderBasis": "GRID",
                "colorStatus": "EXTRACTED",
                "variantHints": {"volume": null, "composition": null, "formulation": null, "optionAttributes": null, "listPrice": null},
                "colors": [
                  {
                    "sortOrder": 1, "name": null, "nameSource": "NONE",
                    "hex": "#1E1B1C", "colorSource": "PRODUCT_PHOTO",
                    "shadeLink": "OPTION_IMAGE", "colorQuality": 0.93,
                    "evidenceKey": "example-curl-fix-mascara/01-black/1"
                  }
                ]
              }
            ],
            "warnings": []
          }
        ]
      }""";

  /** 판정 시험 성공 응답. 새 제품, 일부만 반영하는 제품, 검사 실패 세 모양을 싣는다. */
  static final String DRY_RUN_RESPONSE =
      """
      {
        "results": [
          {"index": 0, "itemKey": "000001", "outcome": "CREATED", "productId": null, "reasons": [], "issues": []},
          {
            "index": 1, "itemKey": "000002", "outcome": "PARTIAL",
            "productId": "00000000-0000-4000-8000-000000000101",
            "reasons": ["SHADE_LAYOUT_CHANGED"], "issues": []
          },
          {
            "index": 2, "itemKey": "000003", "outcome": "INVALID", "productId": null, "reasons": [],
            "issues": [{"path": "shades[0].colors[0].hex", "code": "INVALID_FORMAT", "message": "#RRGGBB 대문자여야 한다"}]
          }
        ]
      }""";

  /** items 개수가 범위를 벗어난 요청의 400. */
  static final String ITEMS_TOO_MANY =
      """
      {
        "code": "VALIDATION_FAILED",
        "message": "입력값이 올바르지 않습니다.",
        "details": [{"field": "items", "reason": "items 는 100건까지입니다."}]
      }""";
}
