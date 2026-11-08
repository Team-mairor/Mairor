# 상세 이미지 컬러 차트로 호수 색 수집 (S15P31A306-383)

옵션별 사진이 없는 공식 홈은 호수 색을 상세 설명 이미지에 인쇄된 컬러 차트로만 알려 준다.
수집기는 옵션 사진으로 색을 얻지 못한 호수에 한해 이 이미지를 읽는다. 이미 색이 있는 호수는 건드리지 않는다.

## 흐름

모델을 쓰는 실행(`--colors` + 모델)에서, 색이 없는 호수가 하나라도 있을 때만 돈다.

1. **상세 이미지 모으기** (`detail/images.py`): `prdDetail` 같은 상세 영역 안의 이미지를 페이지 순서로 모은다.
   영역을 못 찾으면 에디터 업로드 경로(`/NNEditor/`)의 이미지만 쓴다. gif·svg·작다고 적힌 그림은 표시만 하고 쓰지 않는다.
2. **조각 내기** (`detail/tiles.py`): 이미지를 받아 폭을 줄이지 않고 폭의 1.2배 높이로, 이웃과 15% 이상 겹치게 자른다.
   높이·폭이 300px 미만인 조각과 거의 한 색인 조각은 버린다. 이미지당 조각은 32개까지다.
3. **차트 조각 가리기** (`detail/overview.py`): 조각 8개를 번호를 붙인 연락 시트 한 장으로 모아 "색 차트가 보이는 조각"
   번호만 묻는다. 높이 1만 5천 px 이미지도 모델 호출 몇 번으로 훑는다.
4. **칸 읽기** (`detail/chart.py`, `detail/scan.py`): 가려낸 조각만 원래 크기로 보여 칸 위치와 인쇄된 번호·이름을 읽는다.
   색은 모델이 아니라 그 영역의 픽셀에서 계산한다(`color/cell_reading.py`, 제품 사진과 같은 규칙).
   경계에 걸린 칸은 이웃 조각에 맡기고, 겹친 조각이 같은 칸을 두 번 읽으면 하나로 합친다.
5. **호수에 잇기** (`detail/link.py`): 칸의 번호와 호수 이름의 번호가 같을 때만 `LABEL_IN_IMAGE`로 잇는다.

## 잇는 규칙

- 번호는 이름 맨 앞의 번호(`01 니어`, `#03`, `05호`, `B01`). 맨 앞이 번호가 아니면 이름 안에 번호가 하나일 때만 쓴다.
- 호수 번호가 없거나 한 상품 안에서 겹치면 잇지 않는다.
- 같은 번호의 칸이 여럿이면 칩 > 제품 내용물 > 피부 발색 순으로 고른다. 같은 종류가 여럿이면 색이 ΔE 12 안에서
  같을 때만 품질이 높은 쪽을 쓰고, 다르면 잇지 않는다.
- 이름이 같은 문자(한글끼리, 영문끼리)인데 서로 다르면 다른 제품의 차트로 보고 잇지 않는다.
  한글 이름과 영문 이름(`01 니어`, `01 NEAR`)은 번호로 잇는다.
- 잇지 못한 호수는 `colorStatus=NOT_FOUND`로 두고 사유를 상품 `warnings`에 남긴다:
  `SHADE_NO_NUMBER`, `SHADE_NUMBER_DUPLICATE`, `CHART_NO_MATCH`, `CHART_NAME_CONFLICT`,
  `CHART_NUMBER_AMBIGUOUS`, `CHART_CELL_UNREADABLE`.
- 색이 틀리느니 없는 편이 낫다. 근거가 약하면 색을 만들지 않는다.

## 비용 상한 (상품 하나당)

| 항목 | 상한 | 닿으면 |
| --- | --- | --- |
| 상세 이미지 받기 | 16장 | `DETAIL_IMAGE_LIMIT` |
| 연락 시트 호출 | 8번 | `CHART_OVERVIEW_LIMIT` |
| 칸 읽기 호출 | 12번 | `CHART_READ_LIMIT` |

모델 호출이 실패하면 그 시트·조각만 건너뛰고 `CHART_OVERVIEW_FAILED:<종류>`, `CHART_READ_FAILED:<종류>`를 남긴다.
차단(`BlockedError`)은 그 사이트 수집을 멈춘다.

## 실행 결과 파일에 남는 것

- `raw.detailImages`: 모은 이미지 주소와 쓰지 않은 사유.
- `raw.detailCharts`: 이미지별 크기, 조각 수, 차트로 가려낸 조각, 읽은 칸(라벨·영역·HEX·품질·종류).
- `raw.detailLinks`: 번호로 이은 호수와 칸의 라벨·이미지.
- `evidence`: 이은 칸의 근거(`method=detail_chart_box_pixel_median_lab`, 이미지 주소·해시·영역·점수).

## 브랜드별 채움률 리포트

```
uv run python tools/report_catalog_colors.py brands runs/*.jsonl --min-quality 0.5 --out brands.md
```

호수의 70% 이상이 쓸 수 있는 색(`OPTION_IMAGE`, `SINGLE_SHADE_PRODUCT`, `LABEL_IN_IMAGE`이고 사진 색은
품질이 `--min-quality` 이상)이면 "된 브랜드"다. 품질 임계값은 백엔드가 정하므로 리포트의 값은 가정이다.
