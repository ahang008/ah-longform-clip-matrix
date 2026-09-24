#!/usr/bin/env python3
"""Render reviewed non-contiguous ranges from one local video into a clip matrix."""

import argparse
import json
import subprocess
from pathlib import Path


def probe(path):
    raw = subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries',
        'format=duration:stream=codec_type,width,height', '-of', 'json', str(path),
    ])
    return json.loads(raw)


def validate(plan):
    source = Path(plan['source']).expanduser()
    if not source.is_file():
        raise ValueError(f'source missing: {source}')
    info = probe(source)
    streams = info.get('streams', [])
    if not any(s.get('codec_type') == 'video' for s in streams) or not any(s.get('codec_type') == 'audio' for s in streams):
        raise ValueError('source must contain video and audio')
    if any(s.get('codec_type') == 'subtitle' for s in streams):
        raise ValueError('source has a separate subtitle stream; review subtitle rendering before using this script')
    duration = float(info['format']['duration'])
    clips = plan.get('clips')
    if not isinstance(clips, list) or not clips:
        raise ValueError('clips must be a non-empty list')
    names = set()
    for clip in clips:
        name = clip['filename']
        if Path(name).name != name or not name.endswith('.mp4') or name in names:
            raise ValueError(f'invalid or duplicate filename: {name}')
        names.add(name)
        ranges = clip['segments']
        if not isinstance(ranges, list) or not ranges:
            raise ValueError(f'{name}: segments must be non-empty')
        for item in ranges:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError(f'{name}: each segment must be [start, end]')
            start, end = map(float, item)
            if not (0 <= start < end <= duration + 0.01):
                raise ValueError(f'{name}: invalid source range {item} for {duration:.3f}s video')
    return source, Path(plan['output_dir']).expanduser(), clips, duration


def render(source, target, ranges):
    filters = []
    for index, (start, end) in enumerate(ranges):
        filters.append(f'[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{index}]')
        filters.append(f'[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{index}]')
    inputs = ''.join(f'[v{i}][a{i}]' for i in range(len(ranges)))
    filters.append(f'{inputs}concat=n={len(ranges)}:v=1:a=1[v][a]')
    subprocess.run([
        'ffmpeg', '-nostdin', '-n', '-v', 'error', '-i', str(source),
        '-filter_complex', ';'.join(filters), '-map', '[v]', '-map', '[a]',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(target),
    ], check=True)
    details = probe(target)
    expected = sum(float(end) - float(start) for start, end in ranges)
    actual = float(details['format']['duration'])
    if abs(actual - expected) > 0.2:
        raise RuntimeError(f'{target.name}: duration mismatch: {actual:.3f} versus {expected:.3f}')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(target), '-f', 'null', '-'], check=True)
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path, help='JSON plan with source, output_dir, and clips')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='validate source and all ranges without writing')
    mode.add_argument('--render', action='store_true', help='render every clip and verify full decode')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    source, output_dir, clips, duration = validate(plan)
    print(f'source: {source} ({duration:.3f}s)')
    for clip in clips:
        total = sum(float(b) - float(a) for a, b in clip['segments'])
        print(f"{clip['filename']}: {len(clip['segments'])} ranges, {total:.3f}s")
    if args.check:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    if any((output_dir / clip['filename']).exists() for clip in clips):
        raise FileExistsError('one or more outputs already exist; choose a fresh output directory')
    for clip in clips:
        target = output_dir / clip['filename']
        actual = render(source, target, clip['segments'])
        print(f'verified: {target} ({actual:.3f}s)', flush=True)
    (output_dir / '片段来源.json').write_text(json.dumps({
        'source': str(source), 'clips': clips,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
