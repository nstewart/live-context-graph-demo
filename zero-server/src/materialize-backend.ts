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
    // Create a dedicated client for this SUBSCRIBE operation
    const subscribeClient = new Client({
      host: this.config.host,
      port: this.config.port,
      user: this.config.user,
      password: this.config.password,
      database: this.config.database,
    });

    await subscribeClient.connect();
    console.log(`Starting SUBSCRIBE for view: ${viewName}`);

    // SUBSCRIBE is a streaming command that continuously delivers results
    const subscribeQuery = new QueryStream(`SUBSCRIBE ${viewName}`);

    // Execute the streaming query
    const stream = subscribeClient.query(subscribeQuery);

    // Handle rows as they stream in
    stream.on('data', (row: any) => {
      try {
        // Determine operation type from mz_diff column
        // mz_diff: 1 = insert/update, -1 = delete
        const operation = row.mz_diff > 0 ? 'insert' : 'delete';

        const changes: ChangeEvent[] = [{
          collection: viewName,
          operation: operation as 'insert' | 'delete',
          data: this.transformRow(row, viewName),
          timestamp: Date.now(),
        }];

        callback(changes);
      } catch (error) {
        console.error(`Error processing row for ${viewName}:`, error);
      }
    });

    stream.on('error', (error: Error) => {
      console.error(`SUBSCRIBE error for ${viewName}:`, error);
    });

    stream.on('end', () => {
      console.log(`SUBSCRIBE ended for ${viewName}`);
    });

    this.tailClients.set(viewName, subscribeClient);
    console.log(`✅ SUBSCRIBE active for ${viewName}`);
  }

  /**
   * Transform Materialize row data to match Zero schema
   */
  private transformRow(row: any, viewName: string): Record<string, any> {
    switch (viewName) {
      case "orders_flat_mv":
        return {
          id: row.order_id,
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

      case "store_inventory_mv":
        return {
          id: row.store_id,
          store_name: row.store_name,
          store_address: row.store_address,
          store_zone: row.store_zone,
          store_status: row.store_status,
          store_capacity_orders_per_hour: row.store_capacity_orders_per_hour,
        };

      case "courier_schedule_mv":
        return {
          id: row.courier_id,
          courier_name: row.courier_name,
          home_store_id: row.home_store_id,
          vehicle_type: row.vehicle_type,
          courier_status: row.courier_status,
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
