import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
import compare as C

class CompareTests(unittest.TestCase):
    def _btn(self, label, x=80, shift=0):
        im = Image.new("RGB", (200, 120), (246, 247, 249))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((x+shift, 40, x+60+shift, 72), 6, fill=(17, 24, 39))
        d.text((x+10+shift, 48), label, fill=(255, 255, 255))
        return im

    def test_identical_is_match(self):
        im = self._btn("Export")
        r = C.compare(im, im, (110, 56), search=4)
        self.assertTrue(r.match, r)
        self.assertLess(r.diff, 1.0)

    def test_relocated_same_label_adjusts(self):
        rec = self._btn("Export", shift=0)
        cur = self._btn("Export", shift=8)
        r = C.compare(rec, cur, (110, 56), search=16)
        self.assertTrue(r.match, r)
        self.assertGreaterEqual(r.offset[0], 4)

    def test_renamed_button_is_mismatch(self):
        # The recorded "Export" (dark) is gone; a light "Share" sits in its place,
        # and a wider dark button has moved left — the Ledgerly drift case.
        rec = self._btn("Export", x=80)
        cur = Image.new("RGB", (200, 120), (246, 247, 249))
        d = ImageDraw.Draw(cur)
        d.rounded_rectangle((8, 40, 90, 72), 6, fill=(17, 24, 39))
        d.text((12, 48), "PDF", fill=(255, 255, 255))
        d.rounded_rectangle((100, 40, 170, 72), 6, fill=(255, 255, 255), outline=(209, 213, 219))
        d.text((118, 48), "Share", fill=(17, 24, 39))
        r = C.compare(rec, cur, (110, 56), search=8)
        self.assertFalse(r.match, r)
        self.assertGreater(r.diff, 12)

if __name__ == "__main__":
    unittest.main()
