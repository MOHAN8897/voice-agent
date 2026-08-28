/** Minimum spoken words before first TTS request fires during LLM streaming. */
export const EARLY_TTS_MIN_WORDS = 2;

export function wordCount(text: string): number {
  return (text.trim().match(/\S+/g) || []).length;
}

export function ttsTailText(fullText: string, sentEndIndex: number): string {
  return fullText.slice(sentEndIndex).trim();
}

export function shouldStartEarlyTts(fullText: string, sentEndIndex: number): boolean {
  return sentEndIndex === 0 && wordCount(fullText) >= EARLY_TTS_MIN_WORDS;
}

export async function* parseSseDataLines(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const payload = line.slice(6);
          if (payload !== "[DONE]") yield payload;
        }
      }
    }
    if (buffer.startsWith("data: ")) {
      const payload = buffer.slice(6);
      if (payload !== "[DONE]") yield payload;
    }
  } finally {
    reader.releaseLock();
  }
}
