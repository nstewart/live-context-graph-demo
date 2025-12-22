import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';

// Types for propagation tracking
export interface FieldChange {
  old: string | null;
  new: string | null;
}

export interface PropagationEvent {
  mz_ts: string;
  index_name: string;
  doc_id: string;
  operation: 'INSERT' | 'UPDATE' | 'DELETE';
  field_changes: Record<string, FieldChange>;
  timestamp: number;
  display_name: string | null;
}

// Simplified write record - just holds events now
export interface WriteRecord {
  id: string;
  subjectId: string;
  predicate: string;
  value: string;
  timestamp: number;
  propagationEvents: PropagationEvent[];
  status: 'pending' | 'propagated';
}

interface PropagationContextValue {
  writes: WriteRecord[];
  events: PropagationEvent[]; // All events from polling
  registerWrite: (subjectId: string, predicate: string, value: string) => void;
  registerBatchWrite: (writes: Array<{ subjectId: string; predicate: string; value: string }>) => void;
  clearWrites: () => void;
  isPolling: boolean;
  totalIndexUpdates: number;
}

const PropagationContext = createContext<PropagationContextValue | null>(null);

// Propagation API base URL (search-sync service)
const PROPAGATION_API_URL = 'http://localhost:8083';

export function PropagationProvider({ children }: { children: React.ReactNode }) {
  const [writes, setWrites] = useState<WriteRecord[]>([]);
  const [events, setEvents] = useState<PropagationEvent[]>([]);
  const [isPolling, setIsPolling] = useState(true); // Always polling
  const lastMzTs = useRef<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Generate unique ID for write records
  const generateId = () => `write-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  // Register a single write (still useful for tracking what we initiated)
  const registerWrite = useCallback((subjectId: string, predicate: string, value: string) => {
    const newWrite: WriteRecord = {
      id: generateId(),
      subjectId,
      predicate,
      value,
      timestamp: Date.now(),
      propagationEvents: [],
      status: 'pending',
    };
    setWrites((prev) => [newWrite, ...prev].slice(0, 50));
  }, []);

  // Register batch writes
  const registerBatchWrite = useCallback(
    (batchWrites: Array<{ subjectId: string; predicate: string; value: string }>) => {
      const newWrites: WriteRecord[] = batchWrites.map((w) => ({
        id: generateId(),
        subjectId: w.subjectId,
        predicate: w.predicate,
        value: w.value,
        timestamp: Date.now(),
        propagationEvents: [],
        status: 'pending',
      }));
      setWrites((prev) => [...newWrites, ...prev].slice(0, 50));
    },
    []
  );

  // Clear all writes and events
  const clearWrites = useCallback(() => {
    setWrites([]);
    setEvents([]);
    lastMzTs.current = null;
  }, []);

  // Calculate total index updates from events
  const totalIndexUpdates = events.length;

  // Poll for propagation events continuously
  const pollForEvents = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (lastMzTs.current) {
        params.set('since_mz_ts', lastMzTs.current);
      }
      params.set('limit', '100');

      const response = await fetch(`${PROPAGATION_API_URL}/propagation/events/all?${params}`);
      if (!response.ok) {
        return;
      }

      const data = await response.json();
      const newEvents: PropagationEvent[] = data.events || [];

      if (newEvents.length > 0) {
        // Update lastMzTs to the most recent event
        const maxMzTs = newEvents.reduce(
          (max, e) => (e.mz_ts > max ? e.mz_ts : max),
          lastMzTs.current || '0'
        );
        lastMzTs.current = maxMzTs;

        // Add new events (avoid duplicates)
        setEvents((prev) => {
          const existingKeys = new Set(
            prev.map((e) => `${e.mz_ts}-${e.index_name}-${e.doc_id}`)
          );
          const uniqueNewEvents = newEvents.filter(
            (e) => !existingKeys.has(`${e.mz_ts}-${e.index_name}-${e.doc_id}`)
          );
          // Keep last 200 events
          return [...uniqueNewEvents, ...prev].slice(0, 200);
        });

        // Mark any pending writes as propagated
        setWrites((prev) =>
          prev.map((write) =>
            write.status === 'pending' ? { ...write, status: 'propagated' as const } : write
          )
        );
      }
    } catch (error) {
      // Silently ignore polling errors
    }
  }, []);

  // Set up continuous polling
  useEffect(() => {
    // Poll immediately on mount
    pollForEvents();

    // Then poll every 500ms
    pollIntervalRef.current = setInterval(pollForEvents, 500);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [pollForEvents]);

  // Auto-clear old events (older than 5 minutes)
  useEffect(() => {
    const cleanup = setInterval(() => {
      const cutoff = Date.now() / 1000 - 300; // 5 minutes in seconds
      setEvents((prev) => prev.filter((e) => e.timestamp > cutoff));
      // Also clear old writes
      const writeCutoff = Date.now() - 300000;
      setWrites((prev) => prev.filter((w) => w.timestamp > writeCutoff));
    }, 30000);

    return () => clearInterval(cleanup);
  }, []);

  return (
    <PropagationContext.Provider
      value={{
        writes,
        events,
        registerWrite,
        registerBatchWrite,
        clearWrites,
        isPolling,
        totalIndexUpdates,
      }}
    >
      {children}
    </PropagationContext.Provider>
  );
}

export function usePropagation() {
  const context = useContext(PropagationContext);
  if (!context) {
    throw new Error('usePropagation must be used within a PropagationProvider');
  }
  return context;
}
