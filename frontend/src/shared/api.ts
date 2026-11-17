/** Centralize bearer storage and safe HTTP failures for the auth slice. */
export const TOKEN_KEY = 'etsip.token';
export const SESSION_EXPIRED = 'etsip:session-expired';

/** Describe an HTTP failure without retaining submitted credentials. */
export class ApiError extends Error {
  /** Initialize a safe UI message and its HTTP status. */
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Perform a same-origin API request with one persisted bearer contract.
 * Args:
 *   path: API-relative path.
 *   options: Fetch options, including JSON body when applicable.
 * Returns:
 *   Parsed API response or undefined for an empty response.
 * Raises:
 *   ApiError: On transport or HTTP failure.
 */
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  const token = localStorage.getItem(TOKEN_KEY);
  if (token && path !== '/auth/login') headers.set('Authorization', `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(0, 'Unable to reach the service. Please try again.');
  }
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') {
      localStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event(SESSION_EXPIRED));
    }
    let detail: unknown;
    try { detail = (await response.json()).detail; } catch { detail = undefined; }
    const message = typeof detail === 'string' ? detail :
      response.status === 422 ? 'Check your email and password.' : 'The request failed. Please try again.';
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  try { return await response.json() as T; } catch {
    throw new ApiError(response.status, 'The service returned an invalid response.');
  }
}
