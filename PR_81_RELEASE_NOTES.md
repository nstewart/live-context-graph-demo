# PR #81 Release Notes: Dynamic UX for IVM Demo

## Summary
This PR introduces a dynamic view mode feature to the Query Statistics Page, allowing users to progressively compare query offload, batch computation, and Materialize IVM approaches.

## Breaking Changes

### Default Predicate Changed
**BREAKING**: The default predicate in the triple writer has changed from `'order_status'` to `'quantity'` (line 347 in QueryStatisticsPage.tsx).

**Impact**:
- Users with bookmarked workflows or automated scripts that relied on the default predicate being `order_status` may experience unexpected behavior
- The default now aligns with the orderline subject type, which is the most common use case after selecting an order

**Migration**:
- If you have workflows that depended on the default being `order_status`, you will need to explicitly select `order_status` from the predicate dropdown
- Update any automated scripts or documentation that referenced the old default

**Rationale**:
This change improves the user experience by defaulting to an orderline predicate (`quantity`), which is the appropriate default when drilling down into order line items - the primary use case of the demo.

## New Features

### View Mode Selector
- **Query Offload Mode**: Shows only PostgreSQL VIEW (default)
- **Batch Mode**: Shows PostgreSQL VIEW + Batch MATERIALIZED VIEW
- **Materialize Mode**: Shows all three systems for full comparison

### Enhanced UX
- Progressive disclosure reduces UI complexity for new users
- Dynamic grid layout adapts to selected view mode
- Line item IDs now visible for improved debuggability

## Bug Fixes

### Race Condition Fix
Fixed a race condition in the `tripleSubject` useEffect that could cause user-set subjects to be overridden unexpectedly. The fix introduces a `userSetSubjectRef` to track user-initiated changes vs. automatic updates.

### Unknown Subject Type Handling
Added console warnings for unknown subject type prefixes with graceful fallback to orderline predicates, improving debugging and preventing silent failures.

## Testing
- Added comprehensive test suite for view mode functionality
- Tests cover view mode state transitions, subject type detection, predicate auto-selection, and user input handling
- Test file: `web/src/pages/QueryStatisticsPage.test.tsx`

## Documentation
- This release notes file documents the breaking change in default predicate
- Code includes inline comments explaining the race condition fix and subject type detection logic
