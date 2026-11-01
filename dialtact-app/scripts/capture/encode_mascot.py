"""Turn the frames from capture-mascot.mjs into the videos the home page plays.

    python scripts/capture/encode_mascot.py <frames-dir> [out-dir]

For every clip it writes, into public/media/mascot by default:
  <CLIP>.webm  VP9 with a transparent background (Chrome, Edge, Firefox, Android)
  <CLIP>.mp4   H.264 on black, for Safari, which ignores WebM transparency; the page
               blends it with `screen` so the black disappears into the black page
and a manifest.json the page reads. Each clip is cropped to the area its frames
actually cover; the manifest keeps that box so the page puts it back in place. The
idle loop's first frame becomes poster.webp, shown before any video has loaded.

ffmpeg comes from $FFMPEG, else `ffmpeg` on the PATH.
"""
import json
import os
import subprocess
import sys

from PIL import Image

FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')
PAD = 10


def content_box(folder):
    """The union of every frame's visible pixels, padded and grown to a multiple of 16 on
    each side (Chrome's VP9 decoder can draw a green band on other sizes)."""
    box = None
    for name in sorted(os.listdir(folder)):
        with Image.open(os.path.join(folder, name)) as image:
            alpha = image.getchannel('A').point(lambda a: 255 if a > 6 else 0)
            frame = alpha.getbbox()
            width, height = image.size
        if frame:
            box = frame if box is None else (min(box[0], frame[0]), min(box[1], frame[1]), max(box[2], frame[2]), max(box[3], frame[3]))
    left, top = max(0, box[0] - PAD), max(0, box[1] - PAD)
    w = min(width // 16 * 16, -(-(box[2] + PAD - left) // 16) * 16)
    h = min(height // 16 * 16, -(-(box[3] + PAD - top) // 16) * 16)
    return min(left, width - w), min(top, height - h), w, h


def ffmpeg(*args):
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', *args], check=True)


def main():
    frames_dir = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), '..', '..', 'public', 'media', 'mascot')
    os.makedirs(out_dir, exist_ok=True)
    source = json.load(open(os.path.join(frames_dir, 'manifest.json'), encoding='utf-8'))
    fps = source['fps']
    manifest = {'fps': fps, 'width': source['width'], 'height': source['height'], 'clips': {}}

    for clip, info in source['clips'].items():
        folder = os.path.join(frames_dir, clip)
        x, y, w, h = content_box(folder)
        frames = os.path.join(folder, 'f%04d.png')
        crop = f'crop={w}:{h}:{x}:{y}'
        ffmpeg('-framerate', str(fps), '-i', frames, '-vf', crop,
               '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '42',
               '-row-mt', '1', '-deadline', 'good', '-cpu-used', '1', '-auto-alt-ref', '0', '-an',
               os.path.join(out_dir, f'{clip}.webm'))
        ffmpeg('-framerate', str(fps), '-i', frames,
               '-filter_complex', f'[0:v]{crop}[fg];color=black:s={w}x{h}:r={fps}[bg];[bg][fg]overlay=shortest=1,format=yuv420p',
               '-c:v', 'libx264', '-crf', '27', '-preset', 'slow', '-movflags', '+faststart', '-an',
               os.path.join(out_dir, f'{clip}.mp4'))
        manifest['clips'][clip] = {'loop': info['loop'], 'frames': info['frames'], 'box': [x, y, w, h]}
        sizes = [os.path.getsize(os.path.join(out_dir, f'{clip}.{ext}')) // 1024 for ext in ('webm', 'mp4')]
        print(f'{clip}: {w}x{h} at {x},{y}  webm {sizes[0]} KB, mp4 {sizes[1]} KB')

    with Image.open(os.path.join(frames_dir, 'IDLE', 'f0000.png')) as first:
        x, y, w, h = manifest['clips']['IDLE']['box']
        first.crop((x, y, x + w, y + h)).save(os.path.join(out_dir, 'poster.webp'), quality=82)

    with open(os.path.join(out_dir, 'manifest.json'), 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
