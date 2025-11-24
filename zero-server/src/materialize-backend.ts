/**
 * Materialize Backend
 * Handles connection to Materialize and streaming changes via SUBSCRIBE command
 */

import { Client } from "pg";
import QueryStream from "pg-query-stream";

export interface MaterializeConfig {
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
}

export interface ChangeEvent {
  collection: string;
  operation: "insert" | "update" | "delete";
  data: Record<string, any>;
  timestamp: number;
}

export class MaterializeBackend {
  private client: Client;
  private tailClients: Map<string, Client> = new Map();
  private config: MaterializeConfig;
  private subscriptionShutdown: Map<string, () => void> = new Map();
  private isShuttingDown: boolean = false;

  constructor(config: MaterializeConfig) {
    this.config = config;
    this.client = new Client({
      host: config.host,
      port: config.port,
      user: config.user,
      password: config.password,
      database: config.database,
    });
  }

  async connect(): Promise<void> {
    await this.client.connect();
    console.log(
      `Connected to Materialize at ${this.config.host}:${this.config.port}`
    );
  }

  async disconnect(): Promise<void> {
    console.log("Shutting down Materialize backend...");
    this.isShuttingDown = true;

    // Stop all active subscriptions
    for (const [viewName, shutdown] of this.subscriptionShutdown.entries()) {
      console.log(`Stopping subscription for ${viewName}`);
      shutdown();
    }
    this.subscriptionShutdown.clear();

    // Stop all TAIL subscriptions
    for (const [collection, client] of this.tailClients.entries()) {
      try {
        await client.end();
        console.log(`Stopped TAIL for ${collection}`);
      } catch (error) {
        console.error(`Error stopping TAIL for ${collection}:`, error);
      }
    }
    this.tailClients.clear();

    await this.client.end();
    console.log("Disconnected from Materialize");
  }

  /**
   * Subscribe to changes from a Materialize view using SUBSCRIBE
   * @param viewName The materialized view to subscribe to
   * @param callback Function to call when changes occur
   */
  async subscribeToView(
    viewName: string,
    callback: (changes: ChangeEvent[]) => void
  ): Promise<void> {
    // Start the subscription with automatic reconnection
    this.maintainSubscription(viewName, callback);
  }

  /**
   * Maintain a SUBSCRIBE subscription with automatic reconnection
   */
  private async maintainSubscription(
    viewName: string,
    callback: (changes: ChangeEvent[]) => void
  ): Promise<void> {
    const RETRY_DELAY_MS = 30000; // 30 seconds
    let attempt = 0;
    let currentClient: Client | null = null;

    // Register shutdown handler
    const shutdownHandler = () => {
      console.log(`[${viewName}] Shutdown requested`);
      if (currentClient) {
        currentClient.end().catch(() => {});
      }
    };
    this.subscriptionShutdown.set(viewName, shutdownHandler);

    while (!this.isShuttingDown) {
      attempt++;
      let subscribeClient: Client | null = null;

      try {
        console.log(`[${viewName}] Starting SUBSCRIBE (attempt ${attempt})...`);

        // Create a dedicated client for this SUBSCRIBE operation
        subscribeClient = new Client({
          host: this.config.host,
          port: this.config.port,
          user: this.config.user,
          password: this.config.password,
          database: this.config.database,
        });
        currentClient = subscribeClient; // Track for shutdown

        await subscribeClient.connect();

        // Set cluster to 'serving' where the indexed views are located
        await subscribeClient.query('SET CLUSTER = serving;');
        console.log(`[${viewName}] Connected, setting up SUBSCRIBE stream...`);

        // SUBSCRIBE TO with PROGRESS option for continuous timestamp updates
        // PROGRESS ensures we get updates even when there are no data changes
        // Use batchSize=1 and highWaterMark=0 for immediate delivery with no buffering
        const subscribeQuery = new QueryStream(
          `SUBSCRIBE TO (SELECT * FROM ${viewName}) WITH (PROGRESS)`,
          [],
          { batchSize: 1, highWaterMark: 0 }
        );

        // Execute the streaming query
        const stream = subscribeClient.query(subscribeQuery);

        // Track progress by timestamp - when timestamp advances, broadcast accumulated changes
        let lastProgress: string | null = null;
        let pendingChanges: Map<string, ChangeEvent> = new Map(); // id -> consolidated event
        let rowCount = 0;
        let isSnapshot = true;
        let snapshotTimer: NodeJS.Timeout | null = null;
        let streamEnded = false;

        const broadcastPending = () => {
          if (pendingChanges.size > 0) {
            const changes = Array.from(pendingChanges.values());
            console.log(`[${viewName}] Broadcasting ${changes.length} changes`);
            callback(changes);
            pendingChanges.clear();
          }
        };

    // Handle rows as they stream in
    stream.on('data', (row: any) => {
      try {
        const currentTimestamp = row.mz_timestamp;
        const isProgressMessage = row.mz_progressed === true;

        if (isProgressMessage) {
          // Progress message - timestamp advanced but no data changes
          console.log(`⏰ ${viewName}: Progress update at ts=${currentTimestamp}`);

          if (lastProgress !== null && Number(currentTimestamp) > Number(lastProgress)) {
            if (isSnapshot) {
              console.log(`${viewName}: Snapshot complete, now streaming real-time`);
              isSnapshot = false;
            }
            if (pendingChanges.size > 0) {
              console.log(`🔔 ${viewName}: Broadcasting ${pendingChanges.size} pending changes`);
              broadcastPending();
            }
          }

          lastProgress = currentTimestamp;
          return;
        }

        // Data row (not a progress message)
        rowCount++;

        // Accumulate this change
        const operation = row.mz_diff > 0 ? 'insert' : 'delete';
        const transformedData = this.transformRow(row, viewName);

        // CRITICAL: Check if timestamp INCREASED before consolidating this event
        // This broadcasts the PREVIOUS timestamp's events before starting the new timestamp batch
        // This prevents broadcasting the current event before all events at its timestamp arrive
        if (lastProgress !== null && Number(currentTimestamp) > Number(lastProgress)) {
          if (isSnapshot) {
            console.log(`${viewName}: Snapshot complete (${rowCount} rows), DISCARDING snapshot data (clients already have initial state)`);
            isSnapshot = false;
            // Clear pending changes - don't broadcast the snapshot!
            // Clients already received the full state via queryView()
            pendingChanges.clear();
          } else if (pendingChanges.size > 0) {
            console.log(`🔔 ${viewName}: Timestamp advanced! Broadcasting ${pendingChanges.size} changes from PREVIOUS timestamp`);
            broadcastPending();
          }
        }

        // Log first data row
        if (rowCount === 1) {
          console.log(`${viewName}: Receiving snapshot at ts=${currentTimestamp}`);
        }

        // Consolidate by ID to handle UPDATE = DELETE + INSERT at same timestamp
        const recordId = transformedData.id || transformedData.order_id || String(rowCount);
        const existing = pendingChanges.get(recordId);

        if (existing) {
          // Already have an event for this ID at this timestamp
          // DELETE (-1) + INSERT (+1) = UPDATE (net 0, keep insert data)
          // Handle both orders: DELETE+INSERT and INSERT+DELETE
          if (existing.operation === 'delete' && operation === 'insert') {
            // DELETE then INSERT = UPDATE (upsert with new data)
            pendingChanges.set(recordId, {
              collection: viewName,
              operation: 'insert',
              data: transformedData,
              timestamp: Date.now(),
            });
          } else if (existing.operation === 'insert' && operation === 'delete') {
            // INSERT then DELETE = also an UPDATE (keep the INSERT data)
            // Don't remove! This is just events arriving in opposite order
            // Keep existing insert - it has the new state we want
            // (no change needed, existing insert stays)
          } else {
            // Same operation twice or other combination - keep latest
            pendingChanges.set(recordId, {
              collection: viewName,
              operation: operation as 'insert' | 'delete',
              data: transformedData,
              timestamp: Date.now(),
            });
          }
        } else {
          // First event for this ID in this batch
          pendingChanges.set(recordId, {
            collection: viewName,
            operation: operation as 'insert' | 'delete',
            data: transformedData,
            timestamp: Date.now(),
          });
        }

        // Log post-snapshot updates
        if (!isSnapshot && rowCount % 10 === 0) {
          console.log(`📥 ${viewName}: Received ${rowCount} updates, ts=${currentTimestamp}`);
        }

        lastProgress = currentTimestamp;

        // Reset snapshot timer
        if (isSnapshot && snapshotTimer) {
          clearTimeout(snapshotTimer);
        }
        if (isSnapshot) {
          snapshotTimer = setTimeout(() => {
            console.log(`${viewName}: Snapshot timeout - DISCARDING ${pendingChanges.size} accumulated rows (clients already have initial state)`);
            isSnapshot = false;
            // Clear pending changes - don't broadcast the snapshot!
            pendingChanges.clear();
          }, 2000);
        }
      } catch (error) {
        console.error(`Error processing row for ${viewName}:`, error);
      }
    });

        // Wait for stream to end (will reconnect on end or error)
        await new Promise<void>((resolve, reject) => {
          stream.on('end', () => {
            if (!streamEnded) {
              streamEnded = true;
              console.log(`[${viewName}] Stream ended, processed ${rowCount} rows`);
              if (snapshotTimer) clearTimeout(snapshotTimer);
              broadcastPending();
              resolve(); // Trigger reconnection
            }
          });

          stream.on('error', (error: Error) => {
            if (!streamEnded) {
              streamEnded = true;
              console.error(`[${viewName}] SUBSCRIBE error:`, error);
              reject(error); // Trigger reconnection
            }
          });
        });

        // If we get here, stream ended normally
        console.log(`[${viewName}] SUBSCRIBE stream closed`);

      } catch (error) {
        if (this.isShuttingDown) {
          console.log(`[${viewName}] Stopped due to shutdown`);
          break;
        }

        console.error(`[${viewName}] Error in SUBSCRIBE (attempt ${attempt}):`, error);

        // Clean up client
        if (subscribeClient) {
          try {
            await subscribeClient.end();
          } catch (cleanupError) {
            console.error(`[${viewName}] Error cleaning up client:`, cleanupError);
          }
        }
        currentClient = null;

        // Wait before retrying
        if (!this.isShuttingDown) {
          console.log(`[${viewName}] Retrying in ${RETRY_DELAY_MS / 1000} seconds...`);
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS));
        }
      }
    }

    // Cleanup
    this.subscriptionShutdown.delete(viewName);
    console.log(`[${viewName}] Subscription maintenance stopped`);
  }

  /**
   * Transform Materialize row data to match Zero schema
   */
  private transformRow(row: any, viewName: string): Record<string, any> {
    switch (viewName) {
      case "orders_flat_mv":
        return {
          id: row.order_id, // Primary key for Zero
          order_id: row.order_id, // Keep for backwards compatibility
          order_number: row.order_number,
          order_status: row.order_status,
          store_id: row.store_id,
          customer_id: row.customer_id,
          delivery_window_start: row.delivery_window_start,
          delivery_window_end: row.delivery_window_end,
          order_total_amount: row.order_total_amount,
          customer_name: row.customer_name,
          customer_address: row.customer_address,
          store_name: row.store_name,
          store_zone: row.store_zone,
          assigned_courier_id: row.assigned_courier_id,
          delivery_task_status: row.delivery_task_status,
        };

      case "stores_flat":
        return {
          id: row.store_id, // Primary key for Zero
          store_id: row.store_id, // Keep for backwards compatibility
          store_name: row.store_name,
          store_address: row.store_address,
          store_zone: row.store_zone,
        };

      case "store_inventory_mv":
        return {
          id: row.inventory_id, // Primary key for Zero
          inventory_id: row.inventory_id,
          store_id: row.store_id,
          product_id: row.product_id,
          stock_level: row.stock_level,
          replenishment_eta: row.replenishment_eta,
          effective_updated_at: row.effective_updated_at,
        };

      case "courier_schedule_mv":
        return {
          id: row.courier_id, // Primary key for Zero
          courier_id: row.courier_id, // Keep for backwards compatibility
          courier_name: row.courier_name,
          home_store_id: row.home_store_id,
          vehicle_type: row.vehicle_type,
          courier_status: row.courier_status,
          tasks: row.tasks || [], // JSONB array of tasks
        };

      default:
        return row;
    }
  }

  /**
   * Query current state from a view
   */
  async queryView(viewName: string): Promise<any[]> {
    const result = await this.client.query(`SELECT * FROM ${viewName}`);
    return result.rows.map((row) => this.transformRow(row, viewName));
  }
}
