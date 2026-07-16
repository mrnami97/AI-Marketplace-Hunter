import unittest
from matching.matcher import match_title

class TestMatcher(unittest.TestCase):
    def test_compact(self): self.assertTrue(match_title('MSI RTX3070 Gaming X','RTX 3070').matched)
    def test_wrong(self): self.assertFalse(match_title('GTX 1660 Super','RTX 3070').matched)
    def test_family_variant(self): self.assertTrue(match_title('RTX 3070 Ti','RTX 3070').matched)
    def test_specific_variant(self): self.assertFalse(match_title('RTX 3070','RTX 3070 Ti').matched)
    def test_super_alias(self): self.assertTrue(match_title('RTX2070S Gaming','RTX 2070 Super').matched)

if __name__=='__main__': unittest.main()
