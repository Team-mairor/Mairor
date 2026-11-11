"""S3 연결: 사진 서명 주소가 지역 주소로 나와야 AI 서버가 내려받을 수 있다."""

import unittest
from unittest import mock

from processor.clients import s3


class ConnectTests(unittest.TestCase):
    def test_signed_url_uses_the_regional_endpoint(self):
        fake = {"aws_region": "ap-northeast-2", "aws_access_key": "AKIAEXAMPLE", "aws_secret_key": "example"}
        with mock.patch.dict(s3.CREDS, fake):
            url = s3.connect().generate_presigned_url(
                "get_object", Params={"Bucket": "bucket-a", "Key": "videos/v/frames/000001.jpg"}, ExpiresIn=60)
        self.assertTrue(url.startswith("https://bucket-a.s3.ap-northeast-2.amazonaws.com/videos/v/frames/000001.jpg?"))
        self.assertIn("ap-northeast-2%2Fs3%2Faws4_request", url)


if __name__ == "__main__":
    unittest.main()
