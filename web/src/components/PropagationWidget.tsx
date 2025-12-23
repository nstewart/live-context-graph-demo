import { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown, ChevronRight, Trash2, Database } from 'lucide-react';
import { usePropagation, PropagationEvent, SourceWriteEvent } from '../contexts/PropagationContext';

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
  let displayName: string | null = null;

  events.forEach(event => {
    operations.add(event.operation);
    Object.entries(event.field_changes).forEach(([field, change]) => {
      allFieldChanges[field] = change;
    });
    // Use display_name from the first event that has one
    if (!displayName && event.display_name) {
      displayName = event.display_name;
    }
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
        <span className="text-sm text-cyan-400">
          {displayName ? (
            <>
              {displayName} <span className="font-mono text-gray-500">({docId})</span>
            </>
          ) : (
            <span className="font-mono">{docId}</span>
          )}
        </span>
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
  totalDocs,
  hasMoreDocs,
}: {
  mzTs: string;
  events: PropagationEvent[];
  wallTime: number;
  isExpanded: boolean;
  onToggle: () => void;
  expandedEntities: Set<string>;
  onToggleEntity: (key: string) => void;
  totalDocs: number;
  hasMoreDocs: boolean;
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
          {totalDocs} doc{totalDocs !== 1 ? 's' : ''}
          {hasMoreDocs && <span className="text-yellow-500"> (showing {docIds.length})</span>}
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
          {hasMoreDocs && (
            <div className="ml-4 px-3 py-1 text-xs text-yellow-500">
              ... and {totalDocs - docIds.length} more doc{totalDocs - docIds.length !== 1 ? 's' : ''} not shown
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SourceWriteItem({ write }: { write: SourceWriteEvent }) {
  const oldFormatted = formatFieldValue(write.old_value);
  const newFormatted = formatFieldValue(write.new_value);

  return (
    <div className="flex items-center gap-2 px-3 py-1 text-xs">
      <span className="font-mono text-cyan-400">{write.subject_id}</span>
      <span className="text-gray-500">.</span>
      <span className="font-mono text-purple-400">{write.predicate}</span>
      <span className="text-gray-500">:</span>
      {write.old_value !== null && (
        <span className="font-mono text-red-400">{oldFormatted}</span>
      )}
      <span className="text-gray-500">→</span>
      <span className="font-mono text-green-400">{newFormatted}</span>
    </div>
  );
}

function SourceWriteBatch({
  writes,
  isExpanded,
  onToggle
}: {
  batchId: string;
  writes: SourceWriteEvent[];
  isExpanded: boolean;
  onToggle: () => void;
}) {
  // Group by subject_id to show summary
  const subjects = [...new Set(writes.map(w => w.subject_id))];
  const firstWrite = writes[0];

  return (
    <div className="border-b border-gray-800 last:border-b-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-gray-800 transition-colors text-left"
      >
        {writes.length > 1 ? (
          isExpanded ? (
            <ChevronDown className="h-3 w-3 text-gray-400 flex-shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 text-gray-400 flex-shrink-0" />
          )
        ) : (
          <Database className="h-3 w-3 text-blue-400 flex-shrink-0" />
        )}
        <span className="text-xs text-gray-500">{formatTime(firstWrite.timestamp * 1000)}</span>
        {writes.length === 1 ? (
          // Single write - show inline
          <>
            <span className="font-mono text-xs text-cyan-400">{firstWrite.subject_id}</span>
            <span className="text-gray-500">.</span>
            <span className="font-mono text-xs text-purple-400">{firstWrite.predicate}</span>
            <span className="text-gray-500">:</span>
            {firstWrite.old_value !== null && (
              <span className="font-mono text-xs text-red-400">{formatFieldValue(firstWrite.old_value)}</span>
            )}
            <span className="text-gray-500">→</span>
            <span className="font-mono text-xs text-green-400">{formatFieldValue(firstWrite.new_value)}</span>
          </>
        ) : (
          // Multiple writes - show summary
          <>
            <span className="text-xs text-white">
              {subjects.length} subject{subjects.length !== 1 ? 's' : ''}
            </span>
            <span className="text-xs text-gray-500">
              ({writes.length} triple{writes.length !== 1 ? 's' : ''})
            </span>
            <span
              className={`text-xs px-1.5 py-0.5 rounded ${
                writes[0].operation === 'INSERT'
                  ? 'bg-green-900 text-green-300'
                  : 'bg-yellow-900 text-yellow-300'
              }`}
            >
              {writes[0].operation}
            </span>
          </>
        )}
      </button>

      {isExpanded && writes.length > 1 && (
        <div className="ml-6 pb-2 border-l border-gray-700">
          {writes.map((write, idx) => (
            <SourceWriteItem key={`${write.subject_id}-${write.predicate}-${idx}`} write={write} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function PropagationWidget() {
  const { events, sourceWrites, clearWrites, isPolling, totalIndexUpdates, propagationLimitHit } = usePropagation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedTimestamps, setExpandedTimestamps] = useState<Set<string>>(new Set());
  const [expandedEntities, setExpandedEntities] = useState<Set<string>>(new Set());
  const [expandedBatches, setExpandedBatches] = useState<Set<string>>(new Set());

  // Group source writes by batch_id
  const writesByBatch = useMemo(() => {
    const grouped: Record<string, SourceWriteEvent[]> = {};

    sourceWrites.forEach(write => {
      const key = write.batch_id || `single-${write.timestamp}-${write.subject_id}`;
      if (!grouped[key]) {
        grouped[key] = [];
      }
      grouped[key].push(write);
    });

    // Sort by timestamp of first write in each batch (most recent first)
    return Object.entries(grouped)
      .sort(([, a], [, b]) => b[0].timestamp - a[0].timestamp)
      .map(([batchId, writes]) => ({ batchId, writes }));
  }, [sourceWrites]);

  const toggleBatch = (batchId: string) => {
    setExpandedBatches(prev => {
      const next = new Set(prev);
      if (next.has(batchId)) {
        next.delete(batchId);
      } else {
        next.add(batchId);
      }
      return next;
    });
  };

  // Group events by mz_ts, cap at 100 docs per timestamp and 10 timestamps total
  const { displayedTimestamps, totalTimestamps, timestampsWithMore } = useMemo(() => {
    const grouped: Record<string, { events: PropagationEvent[]; wallTime: number; totalDocs: number }> = {};

    events.forEach(event => {
      if (!grouped[event.mz_ts]) {
        grouped[event.mz_ts] = { events: [], wallTime: event.timestamp * 1000, totalDocs: 0 };
      }
      // Avoid duplicate events
      const exists = grouped[event.mz_ts].events.some(
        e => e.doc_id === event.doc_id && e.index_name === event.index_name && e.operation === event.operation
      );
      if (!exists) {
        grouped[event.mz_ts].totalDocs++;
        // Only keep first 100 docs per timestamp for display
        if (grouped[event.mz_ts].events.length < 100) {
          grouped[event.mz_ts].events.push(event);
        }
      }
    });

    // Sort by mz_ts descending (most recent first)
    const sorted = Object.entries(grouped)
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([mzTs, data]) => ({ mzTs, ...data }));

    // Track which timestamps have more docs than displayed
    const withMore = new Set<string>();
    sorted.forEach(({ mzTs, events, totalDocs }) => {
      if (totalDocs > events.length) {
        withMore.add(mzTs);
      }
    });

    return {
      displayedTimestamps: sorted.slice(0, 10),
      totalTimestamps: sorted.length,
      timestampsWithMore: withMore,
    };
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
            Transactions: <span className="text-white">{writesByBatch.length}</span>
            <span className="mx-2 text-gray-600">→</span>
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
          {sourceWrites.length === 0 && displayedTimestamps.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              No propagation events yet - make a change to see updates flow through
            </div>
          ) : (
            <>
              {/* Source Writes Section */}
              {sourceWrites.length > 0 && (
                <div className="border-b border-gray-700">
                  <div className="px-3 py-2 bg-gray-800/50 flex items-center gap-2">
                    <Database className="h-4 w-4 text-blue-400" />
                    <span className="text-xs font-medium text-blue-400 uppercase tracking-wide">
                      PostgreSQL Writes
                    </span>
                    <span className="text-xs text-gray-500">
                      ({writesByBatch.length} transaction{writesByBatch.length !== 1 ? 's' : ''}, {sourceWrites.length} triple{sourceWrites.length !== 1 ? 's' : ''})
                    </span>
                  </div>
                  <div className="max-h-40 overflow-y-auto">
                    {writesByBatch.slice(0, 10).map(({ batchId, writes }) => (
                      <SourceWriteBatch
                        key={batchId}
                        batchId={batchId}
                        writes={writes}
                        isExpanded={expandedBatches.has(batchId)}
                        onToggle={() => toggleBatch(batchId)}
                      />
                    ))}
                    {writesByBatch.length > 10 && (
                      <div className="px-3 py-1 text-xs text-gray-500">
                        ... and {writesByBatch.length - 10} more transactions
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Propagation Events Section */}
              {displayedTimestamps.length > 0 && (
                <div>
                  <div className="px-3 py-2 bg-gray-800/50 flex items-center gap-2">
                    <span className="text-xs font-medium text-green-400 uppercase tracking-wide">
                      Index Propagation
                    </span>
                    <span className="text-xs text-gray-500">
                      ({totalIndexUpdates} update{totalIndexUpdates !== 1 ? 's' : ''})
                    </span>
                    {propagationLimitHit && (
                      <span className="text-xs text-yellow-500" title="Showing max 100 events per poll - more events may exist">
                        (limit reached)
                      </span>
                    )}
                  </div>
                  {displayedTimestamps.map(({ mzTs, events, wallTime, totalDocs }) => (
                    <TimestampGroup
                      key={mzTs}
                      mzTs={mzTs}
                      events={events}
                      wallTime={wallTime}
                      isExpanded={expandedTimestamps.has(mzTs)}
                      onToggle={() => toggleTimestamp(mzTs)}
                      expandedEntities={expandedEntities}
                      onToggleEntity={toggleEntity}
                      totalDocs={totalDocs}
                      hasMoreDocs={timestampsWithMore.has(mzTs)}
                    />
                  ))}
                  {totalTimestamps > 10 && (
                    <div className="px-3 py-1 text-xs text-gray-500">
                      ... and {totalTimestamps - 10} more timestamp{totalTimestamps - 10 !== 1 ? 's' : ''}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
