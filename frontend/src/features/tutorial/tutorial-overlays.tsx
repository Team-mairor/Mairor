import { PillButton } from "@/components/ui/pill-button";
import type { StepPhoto } from "@/domain/session";
import { errorMessage } from "@/lib/api";

/** 마지막 사진 전 3초 카운트다운을 화면 전체에 크게 보여 준다 */
export function CountdownOverlay({ countdown }: { countdown: number }) {
  return (
    <div
      className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-night/55 px-8 text-center text-white"
      role="status"
      aria-live="assertive"
      aria-label={`마지막 사진 촬영까지 ${countdown}초`}
    >
      <span className="font-serif text-[clamp(120px,30vw,220px)] leading-none tabular-nums">
        {countdown}
      </span>
      <span className="text-[21px] font-bold">잠시 후 마지막 사진을 촬영해요</span>
      <span className="text-[16px] text-white/80">아래 버튼을 누르면 촬영을 취소할 수 있어요</span>
    </div>
  );
}

/**
 * 마지막 사진을 저장하기 전에 확인하는 화면. 준비 카드처럼 상단 바(z-[5]) 아래에 깔아,
 * 저장이 계속 실패해도 나가기를 누를 수 있게 한다
 */
export function PhotoReview({
  photo,
  error,
  saving,
  onRetake,
  onConfirm,
}: {
  photo: StepPhoto;
  /** 저장에 실패한 이유. 없으면 null */
  error: unknown;
  saving: boolean;
  onRetake: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="absolute inset-0 z-[4] flex flex-col items-center gap-3.5 bg-night px-7 pt-[84px] pb-[18px]">
      <div className="relative aspect-[3/4] w-[70%] overflow-hidden rounded-[24px] bg-black">
        {/* eslint-disable-next-line @next/next/no-img-element -- 메모리의 data URL이라 next/image가 필요 없다 */}
        <img
          src={photo.url}
          alt="방금 찍은 마지막 사진"
          className="absolute inset-0 size-full object-contain"
        />
      </div>
      <p className="text-[19px] font-bold text-white">이 사진으로 완성할까요?</p>
      {error !== null && (
        <p
          role="alert"
          className="w-full rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-error"
        >
          사진을 저장하지 못했어요. {errorMessage(error)} 다시 시도하거나 다시 찍어 주세요.
        </p>
      )}
      <div className="flex w-full items-center gap-3">
        <PillButton
          variant="line"
          size="cta"
          onClick={onRetake}
          disabled={saving}
          className="text-white"
        >
          다시 찍기
        </PillButton>
        <PillButton
          size="cta"
          trailing
          onClick={onConfirm}
          disabled={saving}
          className="min-w-0 flex-1"
        >
          {saving ? "저장 중…" : "이 사진으로 완성"}
        </PillButton>
      </div>
    </div>
  );
}

const NOTICE = "rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold";

/** 촬영 상태에 따른 안내 문구. 한 번에 해당하는 것만 겹쳐 보인다 */
export function ShotNotices({
  selfie,
  countdown,
  shot,
  last,
  reloadRegions,
}: {
  /** 마지막 사진을 셀카 화면으로 찍는 중이다 */
  selfie: boolean;
  countdown: number | null;
  shot: { state: string; saving: boolean; error: unknown };
  last: boolean;
  /** 촬영할 부위 정보를 못 불러와 다시 불러와야 한다 */
  reloadRegions: boolean;
}) {
  return (
    <>
      {selfie && countdown === null && shot.state === "idle" && (
        <p role="status" className={`${NOTICE} text-ink`}>
          얼굴 전체가 화면에 들어오게 맞춘 뒤 촬영하기를 눌러 주세요.
        </p>
      )}
      {selfie && countdown !== null && (
        <p className={`${NOTICE} text-ink`}>
          잠시 후 마지막 사진을 촬영해요. 아래 버튼을 누르면 취소할 수 있어요.
        </p>
      )}
      {shot.state === "outOfView" && (
        <p role="status" className={`${NOTICE} text-ink`}>
          {last ? "얼굴 전체가" : "이 단계 부위가"} 화면에 다 보이게 조금 뒤로 가 주세요. 촬영을
          그만두려면 왼쪽 버튼을 눌러 주세요.
        </p>
      )}
      {shot.saving && (
        <p role="status" className={`${NOTICE} text-ink`}>
          사진을 저장하고 있어요. 잠시만 기다려 주세요.
        </p>
      )}
      {reloadRegions && (
        <p role="alert" className={`${NOTICE} text-error`}>
          촬영할 부위 정보를 불러오지 못했어요. 인터넷 연결을 확인한 뒤 다시 불러와 주세요.
        </p>
      )}
      {shot.state === "failed" && countdown === null && !reloadRegions && (
        <p role="alert" className={`${NOTICE} text-error`}>
          {shot.error
            ? `사진을 저장하지 못했어요. ${errorMessage(shot.error)} 다시 찍어 주세요.`
            : "사진을 저장하지 못했어요. 카메라가 켜져 있고 얼굴이 화면에 보이는지 확인한 뒤 다시 찍어 주세요."}
        </p>
      )}
    </>
  );
}

/** 카메라 노출·화이트밸런스를 맞추는 동안 화면을 덮는 안내 */
export function CameraTuningOverlay() {
  return (
    <div
      className="pointer-events-none absolute inset-0 z-[6] flex flex-col items-center justify-center gap-3 bg-night px-8 text-center text-white"
      role="status"
      aria-live="polite"
    >
      <span className="font-display text-[40px] leading-tight">카메라 밝기를 맞추고 있어요</span>
      <span className="text-[19px] font-semibold text-white/80">
        잠시 정면을 보고 가만히 있어 주세요
      </span>
    </div>
  );
}

/** 기준 사진 수집이 멈췄을 때 카메라 렌즈를 보게 하는 안내 */
export function LookAtCameraOverlay() {
  return (
    <div
      className="pointer-events-none absolute inset-0 z-[6] flex flex-col items-center justify-center gap-3 bg-night/85 px-8 text-center text-white backdrop-blur-sm"
      role="alert"
      aria-live="assertive"
    >
      <span className="font-display text-[44px] leading-tight">카메라 렌즈를 봐 주세요</span>
      <span className="text-[19px] font-semibold text-white/80">
        화면이 아니라 카메라를 바라보면 사진 수집을 계속해요
      </span>
    </div>
  );
}
