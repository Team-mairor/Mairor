"""유튜브 영상·소리 받기 (yt-dlp)."""

import logging
import time
from pathlib import Path

from processor.core.paths import DOWNLOAD_DIR


logger = logging.getLogger("VideoProcessor")

ORIGINAL_VIDEO = "bestvideo[height<=1080][vcodec^=avc1]/bestvideo[height<=1080][ext=mp4]/bestvideo"
# yt-dlp는 고른 포맷에 따라 mp4/m4a/webm 중 하나로 저장하므로 확장자를 고정하지 않는다
DOWNLOAD_EXTS = (".mp4", ".m4a", ".webm")
DOWNLOAD_ATTEMPTS = 3
RETRY_WAIT = 5.0


def extract_video_id(url: str) -> str:
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url


def find_cached_download(folder: Path, name: str, min_bytes: int) -> Path | None:
    for p in folder.glob(f"{name}.*"):
        if p.suffix in DOWNLOAD_EXTS and p.stat().st_size > min_bytes:
            return p
    return None


def download(url: str, fmt: str, folder: Path, name: str) -> tuple[Path, dict]:
    """yt-dlp로 받는다. 유튜브가 403으로 거절하면 RETRY_WAIT초 쉬고 다시 받는다(모두 DOWNLOAD_ATTEMPTS번).

    yt-dlp는 연결 끊김·5xx만 스스로 다시 받고 403은 바로 실패로 끝낸다. 다시 부르면 받을 주소를 새로 얻고
    받던 파일은 이어 받는다. 영상 없음·비공개 같은 다른 실패는 다시 받아도 같으므로 바로 올린다.
    """
    import yt_dlp

    options = {"format": fmt, "outtmpl": str(folder / f"{name}.%(ext)s"), "quiet": True, "no_warnings": True}
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
            return Path(info["requested_downloads"][0]["filepath"]), info
        except yt_dlp.utils.DownloadError as error:
            if attempt == DOWNLOAD_ATTEMPTS or "HTTP Error 403" not in str(error):
                raise
            logger.warning("[Download] %s 유튜브 403 거절, %.0f초 뒤 다시 받기 (%d/%d)",
                           name, RETRY_WAIT, attempt, DOWNLOAD_ATTEMPTS - 1)
            time.sleep(RETRY_WAIT)


# --- Step 1A: 1080p 비디오 다운로드 ---
def download_video_stream(video_id: str, url: str, folder=None) -> tuple[Path, float, int]:
    t0 = time.time()
    folder = Path(folder) if folder is not None else DOWNLOAD_DIR
    folder.mkdir(parents=True, exist_ok=True)

    cached = find_cached_download(folder, video_id, 10 * 1024 * 1024)
    if cached:
        logger.info(f"[Task A: 비디오 다운로드] 로컬 캐시 파일 재사용 ({cached.name}, {cached.stat().st_size / (1024*1024):.1f} MB)")
        return cached, 0.01, cached.stat().st_size

    logger.info(f"[Task A: 비디오 다운로드] 1080p H.264 단일 스트림 다운로드 시작: {url}")
    target_file, _ = download(url, ORIGINAL_VIDEO, folder, video_id)

    elapsed = time.time() - t0
    fsize = target_file.stat().st_size
    logger.info(f"[Task A: 비디오 다운로드 완료] {target_file.name} {fsize / (1024*1024):.1f} MB ({elapsed:.2f}초)")
    return target_file, elapsed, fsize
