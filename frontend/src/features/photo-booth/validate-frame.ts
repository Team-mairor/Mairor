import type { PhotoFrameTemplate } from "./frame";

const positiveInteger = (value: number) => Number.isSafeInteger(value) && value > 0;
const coordinate = (value: number) => Number.isSafeInteger(value) && value >= 0;

/**
 * TS 템플릿의 숫자·배치 규칙을 확인한다. 새 디자인을 등록할 때와 합성 전에 호출한다.
 * JSON 파서가 아니므로 입력은 PhotoFrameTemplate 구조를 충족해야 한다.
 * overlay의 실제 이미지 크기·투명 영역은 이미지 로드 후 별도로 확인해야 한다.
 */
export function assertPhotoFrame(frame: PhotoFrameTemplate): void {
  if (!frame.id.trim() || !positiveInteger(frame.version)) {
    throw new RangeError("프레임 ID와 양의 정수 버전이 필요합니다.");
  }
  if (!positiveInteger(frame.output.width) || !positiveInteger(frame.output.height)) {
    throw new RangeError("프레임 출력 크기는 양의 정수여야 합니다.");
  }
  if (!/^#[0-9a-f]{6}$/i.test(frame.output.background)) {
    throw new RangeError("프레임 배경은 불투명한 #RRGGBB 색상이어야 합니다.");
  }
  if (frame.overlaySrc !== undefined && !/^\/(?!\/)[^\\\s?#]+$/.test(frame.overlaySrc)) {
    throw new RangeError("프레임 이미지는 같은 사이트의 절대 경로여야 합니다.");
  }
  if (
    frame.brand &&
    (!frame.brand.text.trim() ||
      !positiveInteger(frame.brand.fontSize) ||
      !frame.brand.fontFamily.trim() ||
      !coordinate(frame.brand.y) ||
      frame.brand.y > frame.output.height ||
      !/^#[0-9a-f]{6}$/i.test(frame.brand.color))
  ) {
    throw new RangeError("브랜드 워드마크의 텍스트, 위치, 글자 크기, 색상을 확인해야 합니다.");
  }
  if (frame.slots.length !== 4) {
    throw new RangeError("프레임에는 사진 영역이 정확히 네 개 있어야 합니다.");
  }
  for (const [index, slot] of frame.slots.entries()) {
    if (slot.id !== `slot-${index + 1}`) {
      throw new RangeError("사진 영역은 slot-1부터 slot-4까지 순서대로 정의해야 합니다.");
    }
    if (
      !coordinate(slot.x) ||
      !coordinate(slot.y) ||
      !positiveInteger(slot.width) ||
      !positiveInteger(slot.height)
    ) {
      throw new RangeError("사진 영역 좌표는 음수가 아닌 정수, 크기는 양의 정수여야 합니다.");
    }
    if (slot.x + slot.width > frame.output.width || slot.y + slot.height > frame.output.height) {
      throw new RangeError("사진 영역이 프레임 출력 범위를 벗어났습니다.");
    }
    for (const previous of frame.slots.slice(0, index)) {
      if (
        slot.x < previous.x + previous.width &&
        slot.x + slot.width > previous.x &&
        slot.y < previous.y + previous.height &&
        slot.y + slot.height > previous.y
      ) {
        throw new RangeError("프레임의 사진 영역이 서로 겹칩니다.");
      }
    }
  }
}
