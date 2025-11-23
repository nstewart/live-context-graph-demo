/**
 * Zero Server
 * WebSocket server that syncs data from Materialize to Zero clients
 */

import express from "express";
import { Server as WebSocketServer } from "ws";
import { createServer } from "http";
import cors from "cors";
import { MaterializeBackend, ChangeEvent } from "./materialize-backend";

export interface ServerConfig {
  port: number;
  materialize: {
    host: string;
    port: number;
    user: string;
    password: string;
    database: string;
  };
  collections: string[];
}

export class ZeroServer {
  private app: express.Application;
  private httpServer: ReturnType<typeof createServer>;
  private wss: WebSocketServer;
  private mzBackend: MaterializeBackend;
  private config: ServerConfig;
  private clients: Set<any> = new Set();
  private subscriptions: Map<string, Set<any>> = new Map(); // Track which clients are subscribed to which collections

  constructor(config: ServerConfig) {
    this.config = config;
    this.app = express();
    this.httpServer = createServer(this.app);
    this.wss = new WebSocketServer({ server: this.httpServer });
    this.mzBackend = new MaterializeBackend(config.materialize);

    this.setupExpress();
    this.setupWebSocket();
  }

  private setupExpress() {
    this.app.use(cors());
    this.app.use(express.json());

    // Health check endpoint
    this.app.get("/health", (req, res) => {
      res.json({
        status: "ok",
        clients: this.clients.size,
        collections: this.config.collections,
      });
    });

    // Get current state for initial sync
    this.app.get("/api/sync/:collection", async (req, res) => {
      try {
        const collection = req.params.collection;
        const viewName = this.getViewName(collection);
        const data = await this.mzBackend.queryView(viewName);
        res.json({ collection, data });
      } catch (error) {
        console.error("Error fetching collection:", error);
        res.status(500).json({ error: "Failed to fetch collection" });
      }
    });
  }

  private setupWebSocket() {
    this.wss.on("connection", (ws) => {
      console.log("New WebSocket client connected");
      this.clients.add(ws);

      ws.on("message", async (message) => {
        try {
          const msg = JSON.parse(message.toString());
          await this.handleMessage(ws, msg);
        } catch (error) {
          console.error("Error handling message:", error);
          ws.send(JSON.stringify({ error: "Invalid message format" }));
        }
      });

      ws.on("close", () => {
        console.log("Client disconnected");
        this.clients.delete(ws);

        // Remove from all subscriptions
        this.subscriptions.forEach((subscribers, collection) => {
          subscribers.delete(ws);
        });
      });

      ws.on("error", (error) => {
        console.error("WebSocket error:", error);
        this.clients.delete(ws);
      });

      // Send welcome message
      ws.send(
        JSON.stringify({
          type: "connected",
          collections: this.config.collections,
        })
      );
    });
  }

  private async handleMessage(ws: any, msg: any) {
    switch (msg.type) {
      case "subscribe":
        // Client wants to subscribe to a collection
        const collection = msg.collection;
        console.log(`Client subscribing to ${collection}`);

        // Track this subscription
        if (!this.subscriptions.has(collection)) {
          this.subscriptions.set(collection, new Set());
        }

        // Check if this client is already subscribed
        const subscribers = this.subscriptions.get(collection)!;
        if (subscribers.has(ws)) {
          console.log(`Client already subscribed to ${collection}, skipping`);
          break;
        }

        subscribers.add(ws);

        // Send current state
        try {
          const viewName = this.getViewName(collection);
          console.log(`Querying view: ${viewName}`);
          const data = await this.mzBackend.queryView(viewName);
          console.log(`Retrieved ${data.length} items from ${viewName}`);
          ws.send(
            JSON.stringify({
              type: "initial-state",
              collection,
              data,
            })
          );
          console.log(`Sent initial state for ${collection}`);
        } catch (error) {
          console.error(`Error sending initial state for ${collection}:`, error);
          ws.send(
            JSON.stringify({
              type: "error",
              message: `Failed to load ${collection}`,
            })
          );
        }
        break;

      case "unsubscribe":
        // Client unsubscribing from a collection
        console.log(`Client unsubscribing from ${msg.collection}`);
        const unsubscribers = this.subscriptions.get(msg.collection);
        if (unsubscribers) {
          unsubscribers.delete(ws);
        }
        break;

      default:
        console.log("Unknown message type:", msg.type);
    }
  }

  private getViewName(collection: string): string {
    // Map collection names to Materialize view names
    const viewMap: Record<string, string> = {
      orders: "orders_flat_mv",
      stores: "store_inventory_mv",
      couriers: "courier_schedule_mv",
      inventory: "store_inventory_mv",
      courier_tasks: "delivery_task_mv",
      triples: "triples",
    };

    return viewMap[collection] || collection;
  }

  private broadcastChanges(collection: string, changes: ChangeEvent[]) {
    console.log(`🔔 Broadcasting ${changes.length} changes for ${collection} to ${this.subscriptions.get(collection)?.size || 0} subscribers`);

    // Log first change for debugging
    if (changes.length > 0) {
      const firstChange = changes[0];
      console.log(`  First change: ${firstChange.operation} on ${firstChange.collection}`,
                  firstChange.data.id || firstChange.data.order_id);
    }

    const message = JSON.stringify({
      type: "changes",
      changes,
    });

    // Only send to clients subscribed to this collection
    const subscribers = this.subscriptions.get(collection);
    if (subscribers) {
      let sentCount = 0;
      subscribers.forEach((client) => {
        if (client.readyState === 1) {
          // WebSocket.OPEN
          client.send(message);
          sentCount++;
        }
      });
      console.log(`  ✅ Sent to ${sentCount} connected clients`);
    } else {
      console.log(`  ⚠️ No subscribers for ${collection}`);
    }
  }

  async start(): Promise<void> {
    // Connect to Materialize
    await this.mzBackend.connect();

    // Start HTTP server FIRST (don't block on subscriptions)
    this.httpServer.listen(this.config.port, () => {
      console.log(`Zero Server listening on port ${this.config.port}`);
      console.log(`WebSocket endpoint: ws://localhost:${this.config.port}`);
      console.log(`Monitoring collections: ${this.config.collections.join(", ")}`);
    });

    // Subscribe to all configured collections for real-time updates
    console.log('Setting up real-time TAIL subscriptions...');
    for (const collection of this.config.collections) {
      const viewName = this.getViewName(collection);
      console.log(`Starting TAIL for ${collection} (${viewName})`);

      try {
        await this.mzBackend.subscribeToView(viewName, (changes) => {
          console.log(`Broadcasting ${changes.length} changes for ${collection}`);

          // CRITICAL FIX: Update collection names to match frontend subscription
          // Backend sends "orders_flat_mv", frontend expects "orders"
          const normalizedChanges = changes.map(change => ({
            ...change,
            collection: collection, // Replace viewName with frontend collection name
          }));

          this.broadcastChanges(collection, normalizedChanges);
        });
        console.log(`✅ TAIL subscription active for ${collection}`);
      } catch (error) {
        console.error(`❌ Failed to start TAIL for ${collection}:`, error);
      }
    }

    console.log('Real-time streaming enabled for all collections');
  }

  async stop(): Promise<void> {
    console.log("Stopping Zero Server...");

    // Close all WebSocket connections
    this.wss.clients.forEach((client) => {
      client.close();
    });
    this.wss.close();

    // Disconnect from Materialize
    await this.mzBackend.disconnect();

    // Close HTTP server
    this.httpServer.close();

    console.log("Zero Server stopped");
  }
}
