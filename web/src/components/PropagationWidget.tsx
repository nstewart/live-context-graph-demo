import { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown, ChevronRight, Loader2, Trash2 } from 'lucide-react';
import { usePropagation, PropagationEvent } from '../contexts/PropagationContext';

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// Format a field value for display - handles JSON arrays, long strings, etc.
function formatFieldValue(value: string | null): string {
  if (value === null) return '(null)';

  // Check if it looks like a JSON array
  if (value.startsWith('[') && value.endsWith(']')) {
    try {
      const parsed = JSON.parse(value.replace(/'/g, '"').replace(/None/g, 'null').replace(/False/g, 'false').replace(/True/g, 'true'));
      if (Array.isArray(parsed)) {
        return `[${parsed.length} item${parsed.length !== 1 ? 's' : ''}]`;
      }
    } catch {
      // If parsing fails, truncate
      if (value.length > 50) {
        return value.slice(0, 47) + '...';
      }
    }
  }

  // Check if it looks like a JSON object
  if (value.startsWith('{') && value.endsWith('}')) {
    if (value.length > 50) {
      return '{...}';
    }
  }

  // Truncate long strings
  if (value.length > 100) {
    return value.slice(0, 97) + '...';
  }

  return value;
}

function FieldDiff({ field, change }: { field: string; change: { old: string | null; new: string | null } }) {
  const oldFormatted = formatFieldValue(change.old);
  const newFormatted = formatFieldValue(change.new);

  // Skip fields where both values are the same after formatting (e.g., both are "[6 items]")
  if (oldFormatted === newFormatted && change.old !== change.new) {
    // Show that something changed even if the summary is the same
    return (
      <div className="flex items-center gap-2 text-xs font-mono py-0.5">
        <span className="text-gray-400 min-w-[120px]">{field}:</span>
        <span className="text-yellow-400">{newFormatted} (modified)</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-xs font-mono py-0.5">
      <span className="text-gray-400 min-w-[120px]">{field}:</span>
      {change.old !== null && <span className="text-red-400 break-all">{oldFormatted}</span>}
      <span className="text-gray-500">→</span>
      {change.new !== null && <span className="text-green-400 break-all">{newFormatted}</span>}
    </div>
  );
}

function EntityItem({
  docId,
  events,
  isExpanded,
  onToggle
}: {
  docId: string;
  events: PropagationEvent[];
  isExpanded: boolean;
  onToggle: () => void;
}) {
  // Merge all field changes from all events for this doc
  const allFieldChanges: Record<string, { old: string | null; new: string | null }> = {};
  const operations = new Set<string>();

  events.forEach(event => {
    operations.add(event.operation);
    Object.entries(event.field_changes).forEach(([field, change]) => {
      allFieldChanges[field] = change;
    });
  });

  const fieldChangeEntries = Object.entries(allFieldChanges);
  const operation = operations.has('INSERT') ? 'INSERT' : operations.has('DELETE') ? 'DELETE' : 'UPDATE';
  const indexNames = [...new Set(events.map(e => e.index_name))];

  return (
    <div className="ml-4 border-l border-gray-700">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-gray-800 transition-colors text-left"
      >
        {fieldChangeEntries.length > 0 ? (
          isExpanded ? (
            <ChevronDown className="h-3 w-3 text-gray-400 flex-shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 text-gray-400 flex-shrink-0" />
          )
        ) : (
          <span className="w-3" />
        )}
        <span className="text-sm font-mono text-cyan-400">{docId}</span>
        <span
          className={`text-xs px-1.5 py-0.5 rounded ${
            operation === 'INSERT'
              ? 'bg-green-900 text-green-300'
              : operation === 'UPDATE'
              ? 'bg-yellow-900 text-yellow-300'
              : 'bg-red-900 text-red-300'
          }`}
        >
          {operation}
        </span>
        <span className="text-xs text-gray-500">
          {indexNames.join(', ')}
        </span>
        {fieldChangeEntries.length > 0 && !isExpanded && (
          <span className="text-xs text-gray-500">
            ({fieldChangeEntries.length} field{fieldChangeEntries.length !== 1 ? 's' : ''})
          </span>
        )}
      </button>

      {isExpanded && fieldChangeEntries.length > 0 && (
        <div className="ml-8 pb-2 pr-3">
          {fieldChangeEntries.map(([field, change]) => (
            <FieldDiff key={field} field={field} change={change} />
          ))}
        </div>
      )}
    </div>
  );
}

function TimestampGroup({
  mzTs,
  events,
  wallTime,
  isExpanded,
  onToggle,
  expandedEntities,
  onToggleEntity,
}: {
  mzTs: string;
  events: PropagationEvent[];
  wallTime: number;
  isExpanded: boolean;
  onToggle: () => void;
  expandedEntities: Set<string>;
  onToggleEntity: (key: string) => void;
}) {
  // Group events by doc_id
  const eventsByDocId = useMemo(() => {
    const grouped: Record<string, PropagationEvent[]> = {};
    events.forEach(event => {
      if (!grouped[event.doc_id]) {
        grouped[event.doc_id] = [];
      }
      grouped[event.doc_id].push(event);
    });
    return grouped;
  }, [events]);

  const docIds = Object.keys(eventsByDocId);
  const totalFields = events.reduce((sum, e) => sum + Object.keys(e.field_changes).length, 0);

  return (
    <div className="border-b border-gray-800 last:border-b-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-gray-800 transition-colors text-left"
      >
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
        )}
        <div className="flex items-center gap-2 flex-1">
          <span className="text-xs text-gray-500">{formatTime(wallTime)}</span>
          <span className="text-xs font-mono text-gray-400">mz_ts:</span>
          <span className="text-sm font-mono text-white">{mzTs}</span>
        </div>
        <div className="text-xs text-gray-500">
          {docIds.length} doc{docIds.length !== 1 ? 's' : ''}
          {totalFields > 0 && `, ${totalFields} field${totalFields !== 1 ? 's' : ''}`}
        </div>
      </button>

      {isExpanded && (
        <div className="pb-2">
          {docIds.map(docId => (
            <EntityItem
              key={docId}
              docId={docId}
              events={eventsByDocId[docId]}
              isExpanded={expandedEntities.has(`${mzTs}-${docId}`)}
              onToggle={() => onToggleEntity(`${mzTs}-${docId}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PropagationWidget() {
  const { events, clearWrites, isPolling, totalIndexUpdates } = usePropagation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedTimestamps, setExpandedTimestamps] = useState<Set<string>>(new Set());
  const [expandedEntities, setExpandedEntities] = useState<Set<string>>(new Set());

  // Group events by mz_ts
  const eventsByMzTs = useMemo(() => {
    const grouped: Record<string, { events: PropagationEvent[]; wallTime: number }> = {};

    events.forEach(event => {
      if (!grouped[event.mz_ts]) {
        grouped[event.mz_ts] = { events: [], wallTime: event.timestamp * 1000 };
      }
      // Avoid duplicate events
      const exists = grouped[event.mz_ts].events.some(
        e => e.doc_id === event.doc_id && e.index_name === event.index_name && e.operation === event.operation
      );
      if (!exists) {
        grouped[event.mz_ts].events.push(event);
      }
    });

    // Sort by mz_ts descending (most recent first)
    return Object.entries(grouped)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([mzTs, data]) => ({ mzTs, ...data }));
  }, [events]);

  const toggleTimestamp = (mzTs: string) => {
    setExpandedTimestamps(prev => {
      const next = new Set(prev);
      if (next.has(mzTs)) {
        next.delete(mzTs);
      } else {
        next.add(mzTs);
      }
      return next;
    });
  };

  const toggleEntity = (key: string) => {
    setExpandedEntities(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Always show the widget (it polls continuously)
  return (
    <div
      className={`fixed bottom-0 left-64 right-0 bg-gray-900 border-t border-gray-700 transition-all duration-300 z-50 ${
        isExpanded ? 'h-[40vh]' : 'h-10'
      }`}
    >
      {/* Header bar */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full h-10 flex items-center justify-between px-4 hover:bg-gray-800 transition-colors"
      >
        <div className="flex items-center gap-3">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronUp className="h-4 w-4 text-gray-400" />
          )}
          <span className="text-sm font-medium text-white">Write Propagation</span>
          {isPolling && (
            <span className="h-2 w-2 rounded-full bg-green-500" title="Polling active" />
          )}
        </div>

        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">
            Timestamps: <span className="text-white">{eventsByMzTs.length}</span>
            <span className="mx-2 text-gray-600">|</span>
            Index updates: <span className="text-white">{totalIndexUpdates}</span>
          </span>
          {isExpanded && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                clearWrites();
              }}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
              title="Clear all"
            >
              <Trash2 className="h-4 w-4 text-gray-400 hover:text-red-400" />
            </button>
          )}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="h-[calc(40vh-2.5rem)] overflow-y-auto">
          {eventsByMzTs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              No propagation events yet - make a change to see updates flow through
            </div>
          ) : (
            eventsByMzTs.map(({ mzTs, events, wallTime }) => (
              <TimestampGroup
                key={mzTs}
                mzTs={mzTs}
                events={events}
                wallTime={wallTime}
                isExpanded={expandedTimestamps.has(mzTs)}
                onToggle={() => toggleTimestamp(mzTs)}
                expandedEntities={expandedEntities}
                onToggleEntity={toggleEntity}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
