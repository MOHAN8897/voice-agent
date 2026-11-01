"""Turn capture-effects.mjs frames into seamless looping videos for the sign-in page.

    python scripts/capture/encode_effects.py <frames-dir> [out-dir]

A `crossfade` effect was recorded one second past its loop length: the first second of
the loop is faded from that extra tail into the start, so the last frame runs straight
into the first. A `pingpong` effect plays forward, then back. Writes <effect>.webm
(VP9), <effect>.mp4 (H.264) and <effect>.webp (a still, shown until the video plays)
into public/media/effects by default.
ffmpeg comes from $FFMPEG, else `ffmpeg` on the PATH.
"""
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image

FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')
# Chrome's VP9 decoder draws a green band across the top of frames whose height is not a
# multiple of 16, so frames are trimmed to one (from the bottom and right).
TRIM = 'crop=trunc(iw/16)*16:trunc(ih/16)*16:0:0'


def ffmpeg(*args):
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', *args], check=True)


def main():
    frames_dir = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), '..', '..', 'public', 'media', 'effects')
    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(os.listdir(frames_dir)):
        folder = os.path.join(frames_dir, name)
        info = json.load(open(os.path.join(folder, 'effect.json'), encoding='utf-8'))
        loop, fade, fps = info['loopFrames'], info['fadeFrames'], info['fps']
        frame = lambda i: Image.open(os.path.join(folder, f'f{i:04d}.png')).convert('RGB')
        with tempfile.TemporaryDirectory() as looped:
            if info['mode'] == 'pingpong':
                order = list(range(loop)) + list(range(loop - 2, 0, -1))
                for i, source_index in enumerate(order):
                    frame(source_index).save(os.path.join(looped, f'f{i:04d}.png'))
            else:
                for i in range(loop):
                    image = Image.blend(frame(loop + i), frame(i), i / fade) if i < fade else frame(i)
                    image.save(os.path.join(looped, f'f{i:04d}.png'))
            source = os.path.join(looped, 'f%04d.png')
            ffmpeg('-framerate', str(fps), '-i', source, '-vf', TRIM, '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuv420p', '-b:v', '0', '-crf', '40',
                   '-row-mt', '1', '-deadline', 'good', '-cpu-used', '1', '-an', os.path.join(out_dir, f'{name}.webm'))
            ffmpeg('-framerate', str(fps), '-i', source, '-vf', TRIM, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '26', '-preset', 'slow',
                   '-movflags', '+faststart', '-an', os.path.join(out_dir, f'{name}.mp4'))
            Image.open(os.path.join(looped, 'f0000.png')).save(os.path.join(out_dir, f'{name}.webp'), quality=80)
        sizes = [os.path.getsize(os.path.join(out_dir, f'{name}.{ext}')) // 1024 for ext in ('webm', 'mp4', 'webp')]
        print(f'{name}: {info["mode"]}, webm {sizes[0]} KB, mp4 {sizes[1]} KB, still {sizes[2]} KB')


if __name__ == '__main__':
    main()
