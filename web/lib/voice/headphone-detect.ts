/** Best-effort headphone / headset detection for relaxing echo guards. */

const HEADPHONE_LABEL_RE =
  /headphone|headset|earbud|airpod|buds|wired|bluetooth|bt\s|usb audio|external mic/i;

export function labelLooksLikeHeadphones(label: string): boolean {
  return HEADPHONE_LABEL_RE.test(label);
}

/** Inspect MediaStreamTrack label after getUserMedia (most reliable in-session signal). */
export function headphonesFromStream(stream: MediaStream | null): boolean {
  if (!stream) return false;
  for (const track of stream.getAudioTracks()) {
    const label = track.label || "";
    if (labelLooksLikeHeadphones(label)) return true;
  }
  return false;
}

/** enumerateDevices — labels often empty until after permission; call post-getUserMedia. */
export async function detectHeadphones(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
    return false;
  }
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    for (const d of devices) {
      if (d.kind !== "audioinput") continue;
      if (labelLooksLikeHeadphones(d.label || "")) return true;
    }
  } catch {
    /* permission or privacy */
  }
  return false;
}
