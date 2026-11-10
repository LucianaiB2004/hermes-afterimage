import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overlay_draw import HudState, StepView, render, MINT, RED, VIOLET, CYAN, MAGENTA

class DrawTests(unittest.TestCase):
    def test_match_uses_mint_and_zero_tokens_visible(self):
        im = render(HudState(
            mode="replay", tokens=0, flow_name="Monthly export",
            steps=[StepView("Click “Export”", "Save dialog opens", "current"),
                   StepView("Click “Save”", "→ “Saved”", "pending")],
            current=0, match=True, target=(1400, 240, 1520, 280),
            screen=(1920, 1200),
        ))
        self.assertEqual(im.size, (1920, 1200))
        # viewfinder area should contain mint and cyan/magenta
        crop = im.crop((1380, 210, 1560, 330))
        colors = crop.getcolors(maxcolors=200000) or []
        def has(rgb, tol=40):
            return any(abs(c[1][0]-rgb[0])<tol and abs(c[1][1]-rgb[1])<tol and abs(c[1][2]-rgb[2])<tol and c[1][3]>40
                       for c in colors)
        self.assertTrue(has(MINT) or has(CYAN), "expected mint or cyan in the target brackets")
        # dock is opaque-ish at the bottom center
        dock = im.crop((500, 1055, 1420, 1165))
        self.assertGreater(sum(1 for c in (dock.getcolors(800000) or []) if c[1][3] > 100), 0)

    def test_drift_uses_red_and_purple(self):
        im = render(HudState(
            mode="repair", tokens=1284, flow_name="Monthly export",
            steps=[StepView("Click “Export”", "pixels differ · Δ 21.7", "bad"),
                   StepView("Click “Save”", "→ “Saved”", "pending")],
            current=0, match=False, target=(1450, 240, 1528, 280),
            candidate=(1300, 240, 1440, 280),
            candidate_label='AI  candidate  "Download PDF"  0.93',
            tag="01  TARGET MISSING", screen=(1920, 1200),
        ))
        crop = im.crop((1260, 200, 1600, 400))
        colors = crop.getcolors(400000) or []
        def has(rgb, tol=45):
            return any(abs(c[1][0]-rgb[0])<tol and abs(c[1][1]-rgb[1])<tol and abs(c[1][2]-rgb[2])<tol and c[1][3]>40
                       for c in colors)
        self.assertTrue(has(RED), "expected red on a drifted target")
        self.assertTrue(has(VIOLET), "expected violet on the AI candidate")


    def test_three_long_steps_stay_on_screen(self):
        im = render(HudState(
            mode="replay", tokens=0, flow_name="Delete top sidebar chat",
            steps=[
                StepView("Click the … menu on the top chat", "A menu with a red Delete item appears", "done"),
                StepView("Click Delete in the menu", "A Delete chat? confirmation appears", "current"),
                StepView("Click Delete in the confirmation", "The top chat is removed and the list slides up", "pending"),
            ],
            current=1, match=True, target=(210, 170, 250, 210),
            tag='02  CLICK  "the … menu on the top chat which is way too long for the tag"',
            screen=(1920, 1200),
        ))
        a = im.split()[-1]
        w, h = im.size
        def mx(box):
            return max(a.crop(box).getdata())
        self.assertEqual(mx((0, 0, 8, h)), 0)
        self.assertEqual(mx((w - 8, 0, w, h)), 0)
        self.assertEqual(mx((0, 0, w, 8)), 0)


if __name__ == "__main__":
    unittest.main()
