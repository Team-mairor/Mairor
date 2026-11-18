/** 촬영 화면에 한 번 깔아 두는 보정 필터. 미리보기 영상과 저장되는 사진이 같은 색 보정을 쓴다. */
export const BEAUTY_PREVIEW_FILTER = "url(#photo-beauty-tone)";
/** 저장되는 사진에는 색 보정 뒤에 피부를 부드럽게 하는 단계를 더한다. 라이브 영상에는 무거워 걸지 않는다. */
export const BEAUTY_CAPTURE_FILTER = "url(#photo-beauty-final)";

/**
 * 노란 조명을 빼고 밝고 뽀얗게 보정한다.
 * 파랑을 올리고 빨강을 내려 노란 기운을 줄이고, 중간 톤을 끌어올리며 어두운 쪽을 살짝 띄운다.
 */
export function PhotoBeautyFilterDefs() {
  return (
    <svg aria-hidden width="0" height="0" className="pointer-events-none absolute">
      <defs>
        <filter id="photo-beauty-tone" colorInterpolationFilters="sRGB">
          <feColorMatrix type="saturate" values="0.92" />
          <feComponentTransfer>
            <feFuncR type="gamma" amplitude="0.96" exponent="0.82" offset="0.01" />
            <feFuncG type="gamma" amplitude="1" exponent="0.82" offset="0.012" />
            <feFuncB type="gamma" amplitude="1.08" exponent="0.82" offset="0.02" />
          </feComponentTransfer>
        </filter>
        <filter id="photo-beauty-final" colorInterpolationFilters="sRGB">
          <feColorMatrix type="saturate" values="0.92" />
          <feComponentTransfer result="tone">
            <feFuncR type="gamma" amplitude="0.96" exponent="0.82" offset="0.01" />
            <feFuncG type="gamma" amplitude="1" exponent="0.82" offset="0.012" />
            <feFuncB type="gamma" amplitude="1.08" exponent="0.82" offset="0.02" />
          </feComponentTransfer>
          <feGaussianBlur in="tone" stdDeviation="3" result="soft" />
          <feComposite
            in="soft"
            in2="tone"
            operator="arithmetic"
            k1="0"
            k2="0.4"
            k3="0.6"
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
