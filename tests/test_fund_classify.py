"""基金归属分类 fallback（关键词）单元测试。"""

import unittest

from src import fund_classify


class TestFallbackClassify(unittest.TestCase):
    def test_gold(self):
        r = fund_classify._fallback("000217", "华安黄金ETF联接")
        self.assertEqual(r["category"], "gold")

    def test_core(self):
        r = fund_classify._fallback("110020", "易方达沪深300ETF联接")
        self.assertEqual(r["category"], "core")

    def test_satellite(self):
        r = fund_classify._fallback("161725", "招商中证白酒指数")
        self.assertEqual(r["category"], "satellite")


if __name__ == "__main__":
    unittest.main()
