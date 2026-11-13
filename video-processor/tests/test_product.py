"""영상 속 제품 글자를 브랜드·제품명·호수로 다듬는다: 가격 빼기, 브랜드 대표 이름, 이름 앞의 같은 브랜드 떼기."""

import unittest

from processor.tasks.find_steps.product import label, split_product


class SplitProductTests(unittest.TestCase):
    def test_price_line_read_from_the_caption_is_dropped(self):
        # 운영 tiAQfOhz_GQ: 자막의 ₩를 W로 읽어 이름 끝에 가격이 붙었다
        read = {"brand": "THESAEM", "name": "Cover Perfection Triple Pot Concealer W 12,000", "shade": None}
        self.assertEqual(split_product(read),
                         {"brand": "더샘", "name": "Cover Perfection Triple Pot Concealer", "shade": None})
        self.assertEqual(split_product("롬앤 쥬시 래스팅 틴트 25 (9,900원)")["name"], "쥬시 래스팅 틴트 25")

    def test_shade_that_only_looks_like_money_is_kept(self):
        self.assertEqual(split_product({"brand": "클리오", "name": "킬커버 쿠션", "shade": "W 21"})["shade"], "W 21")

    def test_brand_alias_becomes_the_listed_name_and_leaves_the_product_name(self):
        product = split_product({"brand": "ESPOIR", "name": "에스쁘아 더 브로우 밸런스 펜슬", "shade": "03 소프트 브라운"})
        self.assertEqual(product, {"brand": "에스쁘아", "name": "더 브로우 밸런스 펜슬", "shade": "03 소프트 브라운"})
        self.assertEqual(label(product), "에스쁘아 더 브로우 밸런스 펜슬 03 소프트 브라운")

    def test_one_line_name_starting_with_a_listed_brand_is_split(self):
        self.assertEqual(split_product("Heart Percent 도트 온무드 글로스"),
                         {"brand": "하트퍼센트", "name": "도트 온무드 글로스", "shade": None})
        self.assertEqual(split_product("ESPOIR 에스쁘아 프레쉬 세팅 파우더 AD"),
                         {"brand": "에스쁘아", "name": "프레쉬 세팅 파우더 AD", "shade": None})

    def test_unlisted_brand_is_kept_as_read(self):
        self.assertEqual(split_product({"brand": "Giverny", "name": "Giverny 밀착 커버 파운데이션", "shade": "17호"}),
                         {"brand": "Giverny", "name": "밀착 커버 파운데이션", "shade": "17호"})
        self.assertEqual(split_product("Giverny 밀착 커버 파운데이션"),
                         {"brand": None, "name": "Giverny 밀착 커버 파운데이션", "shade": None})

    def test_placeholder_words_mean_no_product(self):
        for value in (None, "null", "없음", "tool", {"brand": None, "name": "N/A", "shade": None}):
            self.assertIsNone(split_product(value))
        self.assertIsNone(label(None))


if __name__ == "__main__":
    unittest.main()
