/**
 * Zero Server Entry Point
 * Starts the real-time sync server for Materialize to Zero clients
 */

import * as dotenv from "dotenv";
import { ZeroServer } from "./server";

// Load environment variables
dotenv.config();

const PORT = parseInt(process.env.PORT || "8090", 10);
const MZ_HOST = process.env.MZ_HOST || "localhost";
const MZ_PORT = parseInt(process.env.MZ_PORT || "6875", 10);
const MZ_USER = process.env.MZ_USER || "materialize";
const MZ_PASSWORD = process.env.MZ_PASSWORD || "materialize";
const MZ_DATABASE = process.env.MZ_DATABASE || "materialize";

// Parse collections from comma-separated list
const COLLECTIONS = (
  process.env.ZERO_COLLECTIONS || "orders,stores,couriers,inventory,triples"
).split(",").map((c) => c.trim());

async function main() {
  console.log("Starting Zero Server...");
  console.log(`Materialize: ${MZ_HOST}:${MZ_PORT}`);
  console.log(`Collections: ${COLLECTIONS.join(", ")}`);

  const server = new ZeroServer({
    port: PORT,
    materialize: {
      host: MZ_HOST,
      port: MZ_PORT,
      user: MZ_USER,
      password: MZ_PASSWORD,
      database: MZ_DATABASE,
    },
    collections: COLLECTIONS,
  });

  // Handle graceful shutdown
  process.on("SIGTERM", async () => {
    console.log("SIGTERM signal received: closing server");
    await server.stop();
    process.exit(0);
  });

  process.on("SIGINT", async () => {
    console.log("SIGINT signal received: closing server");
    await server.stop();
    process.exit(0);
  });

  try {
    await server.start();
  } catch (error) {
    console.error("Fatal error starting server:", error);
    process.exit(1);
  }
}

main().catch((error) => {
  console.error("Unhandled error:", error);
  process.exit(1);
});
