import io
import subprocess
import tempfile
import unittest
from unittest import mock

from PIL import Image

from processor.tasks.find_steps import caption_check
from processor.tasks.find_steps.caption_check import FULL_FRAME, MARGIN, caption_box, looks_same, read_captions


class CaptionBoxTests(unittest.TestCase):
    def test_boxes_are_joined_with_a_margin(self):
        self.assertEqual(MARGIN, 0.03)
        box = caption_box([[110, 20, 300, 350], [120, 30, 350, 330], None])
        self.assertEqual(box, (0.0, 0.08, 0.38, 0.62))

    def test_no_caption_means_no_rereading(self):
        self.assertIsNone(caption_box([None, None]))
        self.assertIsNone(caption_box([[300, 300, 200, 200], [1, 2, 3]]))

    def test_scattered_captions_fall_back_to_the_whole_frame(self):
        self.assertEqual(caption_box([[50, 20, 200, 300], [800, 600, 950, 980]]), FULL_FRAME)


class LooksSameTests(unittest.TestCase):
    def test_corrected_spellings_of_the_same_product_are_adopted(self):
        pairs = [
            ("hince 싱글 아이섀도우 07 에크루", "hince 싱글 아이섀도우 22 얼루어 로즈"),
            ("OFRA미니 하이라이터데이 드림", "OFRA 미니 하이라이터 데이드림"),
            ("롬앤 슬라이드인 싱글 M01 웬 블러셔", "rom&nd 슬라이드 인 싱글 M01 웜 볼류머"),
            ("베네피트 차차틴트", "benefit 립 앤 치크 틴트 차차틴트"),
            ("컬러그램 누디 블러 립펜슬 05 웜 밀키웨이", "colorgram 누디 블러 립펜슬 05 딸기멜로"),
            ("VDL커버스테인 하이커버 쿠션A00", "VDL 커버스테인 하이커버 쿠션 A00"),
        ]
        for old, new in pairs:
            self.assertTrue(looks_same(old, new), (old, new))
        self.assertTrue(looks_same(None, "hince 22"))

    def test_caption_cut_above_the_shade_line_is_not_adopted(self):
        for shade in ("06 포멜 로즈", "21 모카 프레소", "22 얼루어 로즈"):
            self.assertFalse(looks_same(f"hince 싱글 아이섀도우 {shade}", "hince 싱글 아이섀도우"))

    def test_unrelated_text_is_not_adopted(self):
        self.assertFalse(looks_same("hince 싱글 아이섀도우 06 포멜 로즈", "MAIRA BEAUTY"))
        self.assertFalse(looks_same("espoir 더브로우 밸런스 펜슬 06", "03 눈썹 정리"))


class ReadCaptionsTests(unittest.TestCase):
    def test_unknown_place_skips_gms(self):
        steps = [{"isCosmeticApplication": True, "absStart": 0, "absEnd": 2}]
        with mock.patch.object(caption_check, "generate_content", side_effect=AssertionError("called")):
            self.assertEqual(read_captions(steps, None, None, api_key="k", output_dir=None), {})

    def test_frame_errors_give_an_empty_result(self):
        steps = [{"isCosmeticApplication": True, "absStart": 0, "absEnd": 2}]
        failures = [subprocess.CalledProcessError(1, "ffmpeg"), subprocess.TimeoutExpired("ffmpeg", 60)]
        for grab in [mock.Mock(side_effect=error) for error in failures] + [mock.Mock(return_value=b"")]:
            with mock.patch.object(caption_check, "grab", grab), \
                    mock.patch.object(caption_check, "generate_content", side_effect=AssertionError("called")):
                self.assertEqual(read_captions(steps, None, FULL_FRAME, api_key="k", output_dir=None), {})

    def test_broken_gms_answer_gives_an_empty_result(self):
        steps = [{"isCosmeticApplication": True, "absStart": 0, "absEnd": 2}]
        jpeg = io.BytesIO()
        Image.new("RGB", (64, 64)).save(jpeg, format="JPEG")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(caption_check, "grab", return_value=jpeg.getvalue()), \
                mock.patch.object(caption_check, "generate_content", side_effect=ValueError("not json")):
            self.assertEqual(read_captions(steps, None, FULL_FRAME, api_key="k", output_dir=tmp), {})


class FixStepsTests(unittest.TestCase):
    def test_unrelated_caption_is_reported_not_adopted(self):
        from processor.tasks.find_steps.caption_check import apply_captions

        steps = [
            {"absStart": 0, "absEnd": 5, "productName": "hince 22", "makeup": "eyeshadow", "events": []},
            {"absStart": 6, "absEnd": 9, "productName": "hince 07", "makeup": "eyeshadow", "events": []},
        ]
        fixed, report = apply_captions(steps, {0: "MAIRA BEAUTY", 1: "MAIRA BEAUTY"})
        self.assertEqual([s["productName"] for s in fixed], ["hince 22", "hince 07"])
        self.assertEqual(len(report["rejectedCaptions"]), 2)

    def test_shades_read_without_numbers_stay_separate_steps(self):
        from processor.tasks.find_steps.caption_check import apply_captions

        steps = [
            {"absStart": 0, "absEnd": 5, "productName": "hince 싱글 아이섀도우 06", "makeup": "eyeshadow", "events": []},
            {"absStart": 6, "absEnd": 9, "productName": "hince 싱글 아이섀도우 21", "makeup": "eyeshadow", "events": []},
            {"absStart": 10, "absEnd": 12, "productName": "hince 싱글 아이섀도우 22", "makeup": "eyeshadow", "events": []},
        ]
        fixed, _ = apply_captions(steps, {i: "hince 싱글 아이섀도우" for i in range(3)})
        self.assertEqual(len(fixed), 3)

    def test_caption_cut_at_the_right_edge_is_not_adopted(self):
        # tiAQfOhz_GQ: 상자가 오른쪽 글자를 잘라 받은 이름의 앞부분만 읽혔다
        self.assertFalse(looks_same("더샘 Cover Perfection Triple Pot Concealer", "더샘 Cover Perfection Triple Pot Conc"))
        self.assertFalse(looks_same("2AN ART SKETCH BROW PENCIL 01 라이트 브라운", "2AN Art Sketch Brow Pencil 01 라이"))
        self.assertFalse(looks_same("클리오 Glass & Highlighter 4 레몬별 사탕", "클리오 Glass & Highlighter 4. 레몬별 사"))
        self.assertTrue(looks_same("네이밍 Fluffy Powder Blush", "네이밍 Fluffy Powder Blush Toast"))

    def test_shade_cut_short_is_not_adopted_even_with_a_typo_in_the_name(self):
        from processor.tasks.find_steps.caption_check import apply_captions

        product = {"brand": "HERA", "name": "Sensual Powder Matte Liquide", "shade": "400 데어베어"}
        steps = [{"absStart": 0, "absEnd": 5, "product": product, "makeup": "lip", "events": [],
                  "productName": "HERA Sensual Powder Matte Liquide 400 데어베어"}]
        caption = {"brand": "HERA", "name": "Sensual Powder Matte Liqude", "shade": "4"}
        fixed, report = apply_captions(steps, {0: caption})
        self.assertEqual(fixed[0]["product"], product)
        self.assertEqual(len(report["rejectedCaptions"]), 1)

    def test_caption_read_in_three_parts_is_kept_on_the_step(self):
        from processor.tasks.find_steps.caption_check import apply_captions

        steps = [{"absStart": 0, "absEnd": 5, "productName": "ESPOIR 비글로우 파운데이션 W 32,000",
                  "makeup": "foundation", "events": []}]
        caption = {"brand": "ESPOIR", "name": "비글로우 파운데이션", "shade": "AD 3C 웨딩피치"}
        fixed, report = apply_captions(steps, {0: caption})
        self.assertEqual(fixed[0]["product"], {"brand": "에스쁘아", "name": "비글로우 파운데이션", "shade": "AD 3C 웨딩피치"})
        self.assertEqual(fixed[0]["productName"], "에스쁘아 비글로우 파운데이션 AD 3C 웨딩피치")
        self.assertEqual(fixed[0]["videoProductName"], "ESPOIR 비글로우 파운데이션 W 32,000")
        self.assertEqual(report["rejectedCaptions"], [])


if __name__ == "__main__":
    unittest.main()
