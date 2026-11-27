import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const STORAGE_KEY = 'lumine.debug';

const DebugContext = createContext({ debug: false, setDebug: () => {}, toggle: () => {} });

function readInitial() {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function DebugProvider({ children }) {
  const [debug, setDebugState] = useState(readInitial);

  const setDebug = useCallback((next) => {
    setDebugState(Boolean(next));
    try {
      localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
    } catch {
      /* storage diblokir: tetap jalan dalam sesi */
    }
  }, []);

  const toggle = useCallback(() => setDebug(!debug), [debug, setDebug]);

  useEffect(() => {
    document.documentElement.dataset.debug = debug ? 'on' : 'off';
  }, [debug]);

  const value = useMemo(() => ({ debug, setDebug, toggle }), [debug, setDebug, toggle]);
  return <DebugContext.Provider value={value}>{children}</DebugContext.Provider>;
}

export function useDebug() {
  return useContext(DebugContext);
}

/** Render children hanya saat Mode Debug aktif (default OFF). */
export function DebugOnly({ children, label }) {
  const { debug } = useDebug();
  if (!debug) return null;
  if (label) {
    return (
      <div className="debug-only">
        <span className="debug-only-tag">{label}</span>
        {children}
      </div>
    );
  }
  return children;
}
