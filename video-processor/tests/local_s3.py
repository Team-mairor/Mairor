"""S3 대신 로컬 폴더에 올리는 테스트용 대역."""

from pathlib import Path


class LocalS3:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()

    def head_bucket(self, **_):
        pass

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        return f"https://local-s3.test/{Params['Key']}?X-Amz-Expires={ExpiresIn}&X-Amz-Signature=test"

    def put_object(self, *, Key, Body, **_):
        # 여러 스레드가 동시에 폴더를 만들 때 Windows resolve()가 긴 경로 접두사를 붙여 비교가 틀리므로 키 자체를 검사한다.
        relative = Path(Key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("local sink path escaped")
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Body)
