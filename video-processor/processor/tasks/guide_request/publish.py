"""AI 서버 요청 JSON을 조립·검증하고 로컬과 S3에 남긴다."""

import json
import logging

import jsonschema

from processor.core.config import CREDS, FRAME_URL_TTL_SECONDS
from processor.core.paths import GUIDE_REQUEST_SCHEMA


logger = logging.getLogger("VideoProcessor")


def request_key(key_prefix):
    """요청 JSON의 S3 key. BE에 완료를 알릴 때도 이 key를 보낸다."""
    return f"{key_prefix}/guide_job_request.json"


def publish_guide_request(video_id, video_meta, guide_steps, frames, s3, work_dir, key_prefix=None):
    """AI 서버 v2 요청 JSON을 조립·검증하고 로컬과 S3에 남긴다. 검증에 실패하면 S3에 올리지 않는다.

    S3에는 key_prefix(기본 videos/{video_id}) 아래에 올린다. 사진 주소는 FRAME_URL_TTL_SECONDS 동안 쓸 수 있는
    서명 주소다. AI 서버는 주소로 그냥 내려받고 버킷은 공개가 아니다. 프레임마다 S3 key도 넣는다.
    연결 모드에서는 BE가 key로 서명한 주소로 url을 바꿔 AI에 보낸다.
    """
    key_prefix = key_prefix or f"videos/{video_id}"
    logger.info(">>> [STEP 4] AI 서버 v2 규격(guide_job_request.v2.schema.json) 조립 및 검증...")
    schema = json.loads(GUIDE_REQUEST_SCHEMA.read_text(encoding="utf-8"))
    guide_job_request = {
        "callbackUrl": f"https://api.mairor.com/api/v1/callbacks/guide-jobs/{video_id}",
        "progressUrl": f"https://api.mairor.com/api/v1/progress/guide-jobs/{video_id}",
        "guideInput": {
            "videoId": video_id,
            "durationSeconds": video_meta["durationSeconds"],
            "steps": guide_steps
        },
        "frames": {
            "source": {
                "width": video_meta["width"],
                "height": video_meta["height"],
                "fps": video_meta["fps"]
            },
            "items": [
                {
                    "frameIndex": f["frameNumber"],
                    "timestampMs": f["timestampMs"],
                    "stepId": f["stepId"],
                    "url": s3.generate_presigned_url("get_object", Params={"Bucket": CREDS["s3_bucket"], "Key": f["key"]},
                                                     ExpiresIn=FRAME_URL_TTL_SECONDS),
                    "key": f["key"],
                    "width": f["width"],
                    "height": f["height"]
                }
                for f in frames
            ]
        }
    }
    if not frames:
        guide_job_request["frames"] = None

    # 검증에 실패해도 원인을 볼 수 있게 로컬 요청본은 먼저 남긴다
    result_json_path = work_dir / f"{video_id}_guide_job_request.json"
    req_json_str = json.dumps(guide_job_request, ensure_ascii=False, indent=2)
    result_json_path.write_text(req_json_str, encoding="utf-8")
    try:
        jsonschema.validate(instance=guide_job_request, schema=schema)
    except jsonschema.ValidationError as err:
        logger.error(f"[STEP 4 검증 실패] 메타데이터 업로드 중단 (로컬 요청본: {result_json_path}): {err.message}")
        raise
    logger.info("[STEP 4 검증 성공] AI 서버 가이드 요청 v2 스키마 100% 통과 (VALID)!")

    s3_req_key = request_key(key_prefix)
    s3_input_key = f"{key_prefix}/guide_input.json"
    s3.put_object(Bucket=CREDS["s3_bucket"], Key=s3_req_key, Body=req_json_str.encode("utf-8"),
                  ContentType="application/json")
    s3.put_object(Bucket=CREDS["s3_bucket"], Key=s3_input_key,
                  Body=json.dumps(guide_job_request["guideInput"], ensure_ascii=False, indent=2).encode("utf-8"),
                  ContentType="application/json")
    s3_req_url = f"s3://{CREDS['s3_bucket']}/{s3_req_key}"
    logger.info(f"[STEP 4] 가이드 설명 메타데이터 S3 업로드 완료: {s3_req_url}")
    return guide_job_request, result_json_path, s3_req_url
