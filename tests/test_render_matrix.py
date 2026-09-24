import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/render_matrix.py'


def pixel(path, at):
    return subprocess.check_output([
        'ffmpeg', '-v', 'error', '-ss', str(at), '-i', str(path),
        '-frames:v', '1', '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-',
    ])[:3]


class RenderMatrixTest(unittest.TestCase):
    def test_reorders_video_and_records_source_ranges(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source.mp4'
            subprocess.run([
                'ffmpeg', '-y', '-v', 'error',
                '-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=25:d=1',
                '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=25:d=1',
                '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1',
                '-filter_complex', '[0:v][1:a][2:v][3:a]concat=n=2:v=1:a=1[v][a]',
                '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', str(source),
            ], check=True)
            out = root / 'out'
            plan = root / 'plan.json'
            plan.write_text(json.dumps({
                'source': str(source), 'output_dir': str(out),
                'clips': [{'filename': 'reordered.mp4', 'segments': [[1, 2], [0, 1]]}],
            }))
            subprocess.run([sys.executable, str(SCRIPT), str(plan), '--check'], check=True)
            subprocess.run([sys.executable, str(SCRIPT), str(plan), '--render'], check=True)
            first = pixel(out / 'reordered.mp4', 0.5)
            second = pixel(out / 'reordered.mp4', 1.5)
            self.assertGreater(first[2], first[0])
            self.assertGreater(second[0], second[2])
            record = json.loads((out / '片段来源.json').read_text())
            self.assertEqual(record['clips'][0]['segments'], [[1, 2], [0, 1]])


if __name__ == '__main__':
    unittest.main()
