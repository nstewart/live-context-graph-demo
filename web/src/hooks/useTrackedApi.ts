import { useCallback } from 'react';
import { triplesApi, TripleCreate } from '../api/client';
import { usePropagation } from '../contexts/PropagationContext';

/**
 * Hook that wraps triplesApi with automatic propagation tracking.
 * Use this instead of triplesApi directly to track writes in the PropagationWidget.
 */
export function useTrackedTriplesApi() {
  const { registerWrite, registerBatchWrite } = usePropagation();

  const create = useCallback(
    async (data: TripleCreate) => {
      const result = await triplesApi.create(data);
      registerWrite(data.subject_id, data.predicate, data.object_value);
      return result;
    },
    [registerWrite]
  );

  const createBatch = useCallback(
    async (triples: TripleCreate[]) => {
      const result = await triplesApi.createBatch(triples);
      registerBatchWrite(
        triples.map((t) => ({
          subjectId: t.subject_id,
          predicate: t.predicate,
          value: t.object_value,
        }))
      );
      return result;
    },
    [registerBatchWrite]
  );

  const upsertBatch = useCallback(
    async (triples: TripleCreate[]) => {
      const result = await triplesApi.upsertBatch(triples);
      registerBatchWrite(
        triples.map((t) => ({
          subjectId: t.subject_id,
          predicate: t.predicate,
          value: t.object_value,
        }))
      );
      return result;
    },
    [registerBatchWrite]
  );

  const update = useCallback(
    async (tripleId: number, data: { object_value: string }, subjectId?: string, predicate?: string) => {
      const result = await triplesApi.update(tripleId, data);
      // If subjectId and predicate are provided, track the write
      if (subjectId && predicate) {
        registerWrite(subjectId, predicate, data.object_value);
      }
      return result;
    },
    [registerWrite]
  );

  // Return all the original methods plus our tracked versions
  return {
    // Tracked write methods
    create,
    createBatch,
    upsertBatch,
    update,
    // Pass through read-only methods unchanged
    list: triplesApi.list,
    getSubject: triplesApi.getSubject,
    listSubjects: triplesApi.listSubjects,
    getSubjectCounts: triplesApi.getSubjectCounts,
    // Delete methods (could track these too if needed)
    delete: triplesApi.delete,
    deleteSubject: triplesApi.deleteSubject,
  };
}

/**
 * Helper to extract unique subject IDs from a batch of triples.
 * Useful for tracking which entities were affected by a batch write.
 */
export function extractSubjectIds(triples: TripleCreate[]): string[] {
  return [...new Set(triples.map((t) => t.subject_id))];
}
