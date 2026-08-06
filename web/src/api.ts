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

type AudioAsset = {
  asset_id: number;
  url: string;
  status: string;
  kind: string;
  ready: boolean;
};

function audioUrl(path: string): string {
  return path.startsWith("http://") || path.startsWith("https://")
    ? path
    : `${API_BASE_URL}${path}`;
}

export async function resolveWordAudio(wordId: number, force = false): Promise<AudioAsset> {
  return postJson<AudioAsset>("/spelling/audio/assets/resolve", {
    word_id: wordId,
    force
  });
}

export async function playWordAudio(wordId: number, force = false): Promise<void> {
  const asset = await resolveWordAudio(wordId, force);
  await playAudioPath(asset.url);
}

export async function playAudioPath(path: string): Promise<void> {
  const audio = new Audio(audioUrl(path));
  try {
    await audio.play();
  } catch {
    throw new Error("Audio could not be streamed. Check the backend connection and try again.");
  }
}

export async function prefetchAudioPath(path: string): Promise<void> {
  const response = await fetch(audioUrl(path), { cache: "force-cache" });
  if (!response.ok) throw new Error(await responseErrorMessage(response));
  await response.arrayBuffer();
}

export async function prefetchAudioPaths(paths: Array<string | null | undefined>): Promise<void> {
  const unique = [...new Set(paths.filter((path): path is string => Boolean(path)))];
  await Promise.allSettled(unique.map(prefetchAudioPath));
}
