/** 촬영 화면에 한 번 깔아 두는 보정 필터. 미리보기 영상과 저장되는 사진이 같은 색 보정을 쓴다. */
export const BEAUTY_PREVIEW_FILTER = "url(#photo-beauty-tone)";
/** 저장되는 사진에는 색 보정 뒤에 피부를 부드럽게 하는 단계를 더한다. 라이브 영상에는 무거워 걸지 않는다. */
export const BEAUTY_CAPTURE_FILTER = "url(#photo-beauty-final)";

/** 피부 밝기를 과하게 띄우지 않고 혈색과 입술색을 살리는 자연스러운 톤 보정이다. */
export function PhotoBeautyFilterDefs() {
  return (
    <svg aria-hidden width="0" height="0" className="pointer-events-none absolute">
      <defs>
        <filter id="photo-beauty-tone" colorInterpolationFilters="sRGB">
          <feColorMatrix type="saturate" values="1.12" />
          <feComponentTransfer>
            <feFuncR type="gamma" amplitude="1.02" exponent="0.96" offset="-0.005" />
            <feFuncG type="gamma" amplitude="1" exponent="0.97" offset="-0.005" />
            <feFuncB type="gamma" amplitude="0.98" exponent="0.98" offset="0" />
          </feComponentTransfer>
        </filter>
        <filter id="photo-beauty-final" colorInterpolationFilters="sRGB">
          <feColorMatrix type="saturate" values="1.12" />
          <feComponentTransfer result="tone">
            <feFuncR type="gamma" amplitude="1.02" exponent="0.96" offset="-0.005" />
            <feFuncG type="gamma" amplitude="1" exponent="0.97" offset="-0.005" />
            <feFuncB type="gamma" amplitude="0.98" exponent="0.98" offset="0" />
          </feComponentTransfer>
          <feGaussianBlur in="tone" stdDeviation="2" result="soft" />
          <feComposite
            in="soft"
            in2="tone"
            operator="arithmetic"
            k1="0"
            k2="0.2"
            k3="0.8"
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
