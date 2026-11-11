"""S3 연결과 업로드 연결 유지."""

import threading

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from processor.core.config import CREDS, UPLOAD_CONNECTIONS, WARM_PING_INTERVAL


def connect():
    """S3 클라이언트. 서명 주소가 지역 주소(버킷.s3.ap-northeast-2.amazonaws.com)로 나오게 지역 끝점을 쓴다.

    지역 없는 주소(버킷.s3.amazonaws.com)로 서명하면 S3가 us-east-1로 보내 '지역이 틀림'(400)으로 거절한다.
    """
    region = CREDS["aws_region"]
    return boto3.client(
        "s3", region_name=region, endpoint_url=f"https://s3.{region}.amazonaws.com",
        aws_access_key_id=CREDS["aws_access_key"], aws_secret_access_key=CREDS["aws_secret_key"],
        config=Config(max_pool_connections=UPLOAD_CONNECTIONS, retries={"max_attempts": 3, "mode": "standard"},
                      signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def start_connection_warmer(s3, bucket: str):
    """업로드 연결을 미리 맺고 끊기지 않게 계속 쓴다. 돌려준 함수를 부르면 멈추고, 여러 번 불러도 된다."""
    stop = threading.Event()
    # 16개가 한꺼번에 요청해야 풀에 연결 16개가 따로 생기고 모두 쓰인다
    barrier = threading.Barrier(UPLOAD_CONNECTIONS)

    def ping_loop():
        while not stop.is_set():
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                return
            try:
                s3.head_bucket(Bucket=bucket)
            except (BotoCoreError, ClientError):
                pass
            stop.wait(WARM_PING_INTERVAL)

    for _ in range(UPLOAD_CONNECTIONS):
        threading.Thread(target=ping_loop, daemon=True).start()

    def stop_warmer():
        stop.set()
        barrier.abort()

    return stop_warmer
