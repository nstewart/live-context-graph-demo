/**
 * Zero Schema Definition
 * Maps Materialize views to Zero collections for real-time sync
 */

export interface Schema {
  version: 1;
  tables: {
    orders: {
      tableName: "orders";
      columns: {
        id: { type: "string" };
        order_number: { type: "string" };
        order_status: { type: "string" };
        store_id: { type: "string" };
        customer_id: { type: "string" };
        delivery_window_start: { type: "string" };
        delivery_window_end: { type: "string" };
        order_total_amount: { type: "number" };
        customer_name: { type: "string" };
        customer_address: { type: "string" };
        store_name: { type: "string" };
        store_zone: { type: "string" };
        assigned_courier_id: { type: "string | null" };
        delivery_task_status: { type: "string | null" };
      };
      primaryKey: ["id"];
    };

    stores: {
      tableName: "stores";
      columns: {
        id: { type: "string" };
        store_name: { type: "string" };
        store_address: { type: "string" };
        store_zone: { type: "string" };
        store_status: { type: "string" };
        store_capacity_orders_per_hour: { type: "number | null" };
      };
      primaryKey: ["id"];
    };

    inventory: {
      tableName: "inventory";
      columns: {
        id: { type: "string" };
        store_id: { type: "string" };
        product_id: { type: "string" };
        stock_level: { type: "number" };
        replenishment_eta: { type: "string | null" };
      };
      primaryKey: ["id"];
    };

    couriers: {
      tableName: "couriers";
      columns: {
        id: { type: "string" };
        courier_name: { type: "string" };
        home_store_id: { type: "string" };
        vehicle_type: { type: "string" };
        courier_status: { type: "string" };
      };
      primaryKey: ["id"];
    };

    courier_tasks: {
      tableName: "courier_tasks";
      columns: {
        id: { type: "string" };
        courier_id: { type: "string" };
        task_status: { type: "string" };
        order_id: { type: "string" };
        eta: { type: "string | null" };
        route_sequence: { type: "number" };
      };
      primaryKey: ["id"];
    };

    triples: {
      tableName: "triples";
      columns: {
        id: { type: "number" };
        subject_id: { type: "string" };
        predicate: { type: "string" };
        object_value: { type: "string" };
        object_type: { type: "string" };
        created_at: { type: "string" };
        updated_at: { type: "string" };
      };
      primaryKey: ["id"];
    };
  };
}

export type OrderStatus =
  | "CREATED"
  | "PICKING"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "CANCELLED";

export type StoreStatus = "OPEN" | "LIMITED" | "CLOSED";

export type CourierStatus = "AVAILABLE" | "BUSY" | "OFF_DUTY";

export type TaskStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
