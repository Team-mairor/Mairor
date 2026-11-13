"""후보 영상의 정보(채널·길이·이용 허락 표시)와 1080p 원본을 받는다(개발용).

영상 처리기(video-processor)와 같은 형식으로 받아 처리기 작업 폴더의 downloads/에 둔다.
그래서 find_steps.py가 같은 파일을 다시 받지 않는다.
실행 (ai/ 폴더에서, yt-dlp가 있는 환경):
  uv run --no-project --with-requirements ../video-processor/requirements.txt \
    python tools/guide_area_training/fetch_videos.py [영상 ID ...]
"""

import sys

import workspace

sys.path.insert(0, str(workspace.PROCESSOR_DIR))

import yt_dlp
from processor.clients.youtube import download_video_stream

INFO_KEYS = (
    "id",
    "title",
    "channel",
    "channel_id",
    "uploader",
    "duration",
    "license",
    "upload_date",
    "availability",
)


def main() -> None:
    wanted = set(sys.argv[1:])
    for video in workspace.load_videos():
        video_id, url = video["videoId"], video["url"]
        if wanted and video_id not in wanted:
            continue
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        workspace.write_json(
            workspace.info_path(video_id), {key: info.get(key) for key in INFO_KEYS}
        )
        path, seconds, size = download_video_stream(
            video_id, url, workspace.processor_dir(video_id) / "downloads"
        )
        print(
            f"{video_id}: {info.get('channel')} {info.get('duration')}초 → {path.name} "
            f"{size / 1e6:.0f}MB ({seconds:.0f}초)"
        )


if __name__ == "__main__":
    main()
