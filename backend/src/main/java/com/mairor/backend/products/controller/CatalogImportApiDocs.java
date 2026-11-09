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

  /** 실행 열기·하트비트·끝내기의 성공 응답. */
  static final String RUN_RESPONSE =
      """
      {
        "id": "0b6c1c36-6f7a-4d7e-9f8e-2f3c4d5e6a7b",
        "runId": "5d1f0c2e9a7b4c3e8f6a1b2c3d4e5f60",
        "status": "RUNNING",
        "startedAt": "2026-11-08T21:30:00+09:00",
        "lastHeartbeatAt": "2026-11-08T12:31:10Z",
        "finishedAt": null,
        "resumed": false
      }""";

  /** 건 묶음의 성공 응답. 새로 반영한 건, 재전송으로 돌려준 건, 틀린 건 세 모양을 싣는다. */
  static final String BATCH_RESPONSE =
      """
      {
        "results": [
          {
            "index": 0, "itemKey": "000001", "outcome": "NEW", "partial": false, "reasons": [],
            "productId": "00000000-0000-4000-8000-000000000101", "colorsApplied": 2,
            "duplicate": false, "recorded": true, "message": null
          },
          {
            "index": 1, "itemKey": "000002", "outcome": "UPDATE", "partial": false, "reasons": [],
            "productId": "00000000-0000-4000-8000-000000000102", "colorsApplied": 0,
            "duplicate": true, "recorded": true, "message": null
          },
          {
            "index": 2, "itemKey": "000003", "outcome": "INVALID", "partial": false,
            "reasons": ["INVALID_FORMAT"], "productId": null, "colorsApplied": 0,
            "duplicate": false, "recorded": true,
            "message": "shades[0].colors[0].hex INVALID_FORMAT: #RRGGBB 대문자여야 한다"
          }
        ]
      }""";

  /** 끝난 실행에 건을 더하려 할 때의 409. */
  static final String RUN_CLOSED =
      """
      {
        "code": "IMPORT_RUN_CLOSED",
        "message": "이미 끝난 적재 실행입니다: 5d1f0c2e9a7b4c3e8f6a1b2c3d4e5f60 (ABANDONED)"
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
