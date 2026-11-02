/**
 * Returns the post-login destination from `?next=`, accepting only same-site paths.
 * Rejects absolute URLs and protocol-relative `//host` values to prevent open redirects.
 */
export function safeNext(search: string, fallback = "/"): string {
  const next = new URLSearchParams(search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return fallback;
  return next;
}
