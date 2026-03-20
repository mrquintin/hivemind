import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  ReactNode,
} from "react";
import { checkServerHealth } from "../api/client";

type ConnectionStatus = "checking" | "connected" | "disconnected";

interface ConnectionContextValue {
  status: ConnectionStatus;
  retryCount: number;
  lastCheck: Date | null;
  /** Force an immediate connection check (e.g. after changing server URL). */
  refreshNow: () => void;
}

const ConnectionContext = createContext<ConnectionContextValue>({
  status: "checking",
  retryCount: 0,
  lastCheck: null,
  refreshNow: () => {},
});

export function useConnection() {
  return useContext(ConnectionContext);
}

interface ConnectionProviderProps {
  children: ReactNode;
}

export function ConnectionProvider({ children }: ConnectionProviderProps) {
  const [status, setStatus] = useState<ConnectionStatus>("checking");
  const [retryCount, setRetryCount] = useState(0);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const retryRef = useRef(0);
  const isActiveRef = useRef(true);

  const checkConnection = useCallback(async () => {
    if (!isActiveRef.current) return;

    setStatus("checking");
    const result = await checkServerHealth();

    if (!isActiveRef.current) return;

    setLastCheck(new Date());

    if (result.connected) {
      setStatus("connected");
      retryRef.current = 0;
      setRetryCount(0);
      timeoutRef.current = setTimeout(checkConnection, 30000);
    } else {
      setStatus("disconnected");
      retryRef.current++;
      setRetryCount(retryRef.current);
      const delay = Math.min(2000 + retryRef.current * 1000, 5000);
      console.log(
        `Server disconnected, retrying in ${delay / 1000}s (attempt ${retryRef.current})...`
      );
      timeoutRef.current = setTimeout(checkConnection, delay);
    }
  }, []);

  const refreshNow = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    retryRef.current = 0;
    setRetryCount(0);
    checkConnection();
  }, [checkConnection]);

  useEffect(() => {
    isActiveRef.current = true;
    checkConnection();
    return () => {
      isActiveRef.current = false;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [checkConnection]);

  return (
    <ConnectionContext.Provider
      value={{ status, retryCount, lastCheck, refreshNow }}
    >
      {children}
    </ConnectionContext.Provider>
  );
}
