/** Fetch typed resources while ignoring obsolete responses after navigation. */
import { useCallback, useEffect, useState } from 'react';
/** Represent loading, errors and retries without retaining stale resource data. */
export function useResource<T>(load: () => Promise<T>, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    let current = true;
    setData(null);
    setError('');
    setLoading(enabled);
    if (enabled) load().then(value => {
      if (current) setData(value);
    }).catch((failure: unknown) => {
      if (current) setError(failure instanceof Error ? failure.message : 'Unable to load data.');
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [load, enabled, revision]);
  return { data, loading, error, retry };
}
