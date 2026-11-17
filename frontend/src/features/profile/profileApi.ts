/** Call the profile mutations through the existing bearer boundary. */
import { api, ApiError } from '../../shared/api';
import type { PasswordChange, ProfileUpdate, User } from '../../types';

/** Normalize validation feedback to the self-service form rather than login copy. */
async function mutate<T>(path: string, method: string, payload: ProfileUpdate | PasswordChange): Promise<T> {
  try {
    return await api<T>(path, { method, body: JSON.stringify(payload) });
  } catch (failure) {
    if (failure instanceof ApiError && failure.status === 422 && failure.message === 'Check your email and password.') {
      throw new ApiError(422, 'Check the profile fields. New passwords must contain 12–72 UTF-8 bytes.');
    }
    throw failure;
  }
}
/** Save a preference and return the persisted safe identity. */
export function saveProfile(payload: ProfileUpdate): Promise<User> {
  return mutate('/auth/profile', 'PUT', payload);
}
/** Rotate credentials without issuing a new session token. */
export function changePassword(payload: PasswordChange): Promise<void> {
  return mutate('/auth/change-password', 'POST', payload);
}
