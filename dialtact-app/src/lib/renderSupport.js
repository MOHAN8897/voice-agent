/**
 * Live WebGL or recorded video? The home page's mascot and the sign-in page's effects run
 * live on devices that handle WebGL well, and play recordings of the very same thing
 * (public/media, made by scripts/capture) everywhere else: no WebGL, a software
 * renderer, a phone with 2 GB of memory or less, or Data Saver on.
 *
 * `?render=video` or `?render=live` (or localStorage `dialtact:render`) forces one.
 */
const STORAGE_KEY = 'dialtact:render';
let decided = null;

function decide() {
  if (typeof window === 'undefined') return 'video';
  try {
    const forced = new URLSearchParams(window.location.search).get('render') || window.localStorage.getItem(STORAGE_KEY);
    if (forced === 'live' || forced === 'video') return forced;
  } catch {
    /* storage blocked: decide from the device */
  }
  if (navigator.deviceMemory && navigator.deviceMemory <= 2) return 'video';
  if (navigator.connection?.saveData) return 'video';
  try {
    // A major performance caveat is a software renderer (SwiftShader, llvmpipe, the
    // Microsoft Basic Render Driver): WebGL "works" there at a few frames a second.
    const gl = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true });
    if (!gl) return 'video';
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return 'live';
  } catch {
    return 'video';
  }
}

/** 'live' or 'video', decided once per page load. */
export function renderMode() {
  if (!decided) decided = decide();
  return decided;
}

/**
 * Safari ignores the transparency in VP9 WebM, so it gets the H.264 MP4, recorded on
 * black and blended with `screen` (black then disappears into the black page).
 */
export function videoFormat() {
  if (typeof window === 'undefined') return 'webm';
  const safari = /^((?!chrome|chromium|android|crios|fxios|edg).)*safari/i.test(navigator.userAgent);
  if (safari) return 'mp4';
  return document.createElement('video').canPlayType('video/webm; codecs="vp9"') ? 'webm' : 'mp4';
}
