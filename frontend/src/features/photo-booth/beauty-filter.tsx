import { gainsToMatrix, NEUTRAL_GAINS } from "./white-balance";

/** 촬영 화면에 한 번 깔아 두는 보정 필터. 미리보기 영상과 저장되는 사진이 같은 색 보정을 쓴다. */
export const BEAUTY_PREVIEW_FILTER = "url(#photo-beauty-tone)";
/** 저장되는 사진에는 색 보정 뒤에 피부를 부드럽게 하는 단계를 더한다. 라이브 영상에는 무거워 걸지 않는다. */
export const BEAUTY_CAPTURE_FILTER = "url(#photo-beauty-final)";
/** 자동 화이트밸런스 단계의 feColorMatrix id. 영상에서 읽은 배율로 values를 갱신한다. */
export const WHITE_BALANCE_IDS = ["photo-wb-tone", "photo-wb-final"] as const;

const NEUTRAL_MATRIX = gainsToMatrix(NEUTRAL_GAINS);

/** 조명 색에 따른 노란 기운은 자동 화이트밸런스 단계가 맡고, 이어서 중간 톤을 밝혀 뽀얗게 하되 채도는 살려 생기를 남긴다. */
export function PhotoBeautyFilterDefs() {
  return (
    <svg aria-hidden width="0" height="0" className="pointer-events-none absolute">
      <defs>
        <filter id="photo-beauty-tone" colorInterpolationFilters="sRGB">
          <feColorMatrix id="photo-wb-tone" type="matrix" values={NEUTRAL_MATRIX} />
          <feColorMatrix type="saturate" values="1.05" />
          <feComponentTransfer>
            <feFuncR type="gamma" amplitude="1" exponent="0.88" offset="0.004" />
            <feFuncG type="gamma" amplitude="1" exponent="0.88" offset="0.008" />
            <feFuncB type="gamma" amplitude="1" exponent="0.88" offset="0.01" />
          </feComponentTransfer>
        </filter>
        <filter id="photo-beauty-final" colorInterpolationFilters="sRGB">
          <feColorMatrix id="photo-wb-final" type="matrix" values={NEUTRAL_MATRIX} />
          <feColorMatrix type="saturate" values="1.05" />
          <feComponentTransfer result="tone">
            <feFuncR type="gamma" amplitude="1" exponent="0.88" offset="0.004" />
            <feFuncG type="gamma" amplitude="1" exponent="0.88" offset="0.008" />
            <feFuncB type="gamma" amplitude="1" exponent="0.88" offset="0.01" />
          </feComponentTransfer>
          <feGaussianBlur in="tone" stdDeviation="2.5" result="soft" />
          <feComposite
            in="soft"
            in2="tone"
            operator="arithmetic"
            k1="0"
            k2="0.3"
            k3="0.7"
            k4="0"
            result="blend"
          />
          {/* 블러가 가장자리에 투명을 섞어 JPEG에서 어두운 띠가 생기지 않도록 알파를 1로 두고 원본 영역으로 자른다 */}
          <feColorMatrix
            in="blend"
            type="matrix"
            values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0 1"
            result="opaque"
          />
          <feComposite in="opaque" in2="tone" operator="in" />
        </filter>
      </defs>
    </svg>
  );
}
