const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function responseErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    // Fall through to the response text for non-JSON errors.
  }
  return text || response.statusText || "Request failed.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json() as Promise<T>;
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export async function deleteJson(path: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
}

export async function playAudio(
  text: string,
  variant?: {
    voice?: string;
    model?: string;
    wordId?: number;
    mode?: "word" | "dictation";
    force?: boolean;
  }
): Promise<void> {
  const params = new URLSearchParams({ text });
  if (variant?.voice) params.set("voice", variant.voice);
  if (variant?.model) params.set("model", variant.model);
  if (variant?.wordId) params.set("word_id", String(variant.wordId));
  if (variant?.mode) params.set("mode", variant.mode);
  if (variant?.force) params.set("force", "true");
  const response = await fetch(`${API_BASE_URL}/spelling/audio?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.onended = () => URL.revokeObjectURL(url);
  await audio.play();
}

export async function playAudioPath(path: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.onended = () => URL.revokeObjectURL(url);
  await audio.play();
}
