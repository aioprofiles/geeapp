import asyncio, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from geebot import media

FF = shutil.which("ffmpeg")


@unittest.skipUnless(FF, "ffmpeg not installed")
class MediaTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = os.path.join(self.d, "s.mp3")
        os.system(f"ffmpeg -y -v error -f lavfi -i sine=frequency=440:duration=6 -c:a libmp3lame {self.src}")

    def test_clip_and_embed(self):
        out = os.path.join(self.d, "c.mp3")
        self.assertTrue(asyncio.run(media.cut_clip(self.src, 2, out)))
        self.assertLess(os.path.getsize(out), os.path.getsize(self.src))
        o2 = os.path.join(self.d, "e.mp3")
        self.assertTrue(asyncio.run(media.embed_lyrics(self.src, o2, "T", "A", "line one\nline two")))
        probe = os.popen(f"ffprobe -v error -show_entries format_tags -of default=nw=1 {o2}").read()
        self.assertIn("lyrics", probe.lower())

    def test_reel_filter_writes_files(self):
        vf = media.reel_filter([(0, 2, "hello"), (2, 4, "world")], "f.ttf", self.d)
        self.assertEqual(vf.count("drawtext"), 2)
        self.assertTrue(os.path.exists(os.path.join(self.d, "l1.txt")))


if __name__ == "__main__":
    unittest.main()
