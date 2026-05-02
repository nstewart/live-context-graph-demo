import { useState, useEffect, useMemo } from "react";
import { Edit3 } from "lucide-react";
import { queryStatsApi, searchApi } from "../api/client";

const predicatesBySubjectType: Record<string, string[]> = {
  order: ['order_status', 'order_number', 'delivery_window_start', 'delivery_window_end'],
  orderline: ['quantity', 'order_line_unit_price', 'line_sequence'],
  customer: ['customer_name', 'customer_email', 'customer_address'],
  store: ['store_name', 'store_zone', 'store_address'],
  product: ['product_name', 'category', 'unit_price', 'perishable', 'unit_weight_grams'],
  inventory: ['stock_level', 'replenishment_eta'],
  courier: ['courier_name', 'courier_phone', 'courier_status'],
  task: ['task_status', 'assigned_to', 'eta'],
};

const placeholdersByPredicate: Record<string, string> = {
  order_status: 'DELIVERED', order_number: 'FM-1234',
  delivery_window_start: '2025-01-15T10:00:00', delivery_window_end: '2025-01-15T12:00:00',
  quantity: '5', order_line_unit_price: '12.99', line_sequence: '1',
  customer_name: 'John Doe', customer_email: 'john@example.com', customer_address: '123 Main St',
  store_name: 'Downtown Market', store_zone: 'MAN', store_address: '456 Broadway',
  product_name: 'Organic Apples', category: 'Produce', unit_price: '4.99',
  perishable: 'true', unit_weight_grams: '500',
  stock_level: '100', replenishment_eta: '2025-01-16T08:00:00',
  courier_name: 'Jane Smith', courier_phone: '555-1234', courier_status: 'ACTIVE',
  task_status: 'COMPLETED', assigned_to: 'courier:C-001', eta: '2025-01-15T11:00:00',
};

interface WriteTripleFormProps {
  initialSubject?: string;
  onWritten?: () => void;
}

export const WriteTripleForm = ({ initialSubject = "", onWritten }: WriteTripleFormProps) => {
  const [subject, setSubject]     = useState(initialSubject);
  const [predicate, setPredicate] = useState("quantity");
  const [value, setValue]         = useState("");
  const [status, setStatus]       = useState<string | null>(null);
  const [impact, setImpact]       = useState<{ impacted: number; total: number; pct: number } | null>(null);
  const [watchingImpact, setWatchingImpact] = useState(false);

  useEffect(() => { setSubject(initialSubject); }, [initialSubject]);

  const availablePredicates = useMemo(() => {
    let base = predicatesBySubjectType.orderline;
    if (subject) {
      const colonIdx = subject.indexOf(':');
      const prefix = colonIdx > -1
        ? subject.slice(0, colonIdx).toLowerCase()
        : subject.includes('_') ? subject.split('_')[0].toLowerCase() : '';
      if (prefix) base = predicatesBySubjectType[prefix] ?? predicatesBySubjectType.orderline;
    }
    return predicate && !base.includes(predicate) ? [predicate, ...base] : base;
  }, [subject, predicate]);

  useEffect(() => {
    if (availablePredicates.length > 0 && !availablePredicates.includes(predicate)) {
      setPredicate(availablePredicates[0]);
    }
  }, [availablePredicates, predicate]);

  const watchImpact = async (lowerBound: number) => {
    setWatchingImpact(true);
    setImpact(null);
    let lastImpacted = -1;
    for (let i = 0; i < 8; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const res = await searchApi.indexImpact(lowerBound);
        const data = res.data;
        if (data.impacted > 0 && data.impacted === lastImpacted) break;
        lastImpacted = data.impacted;
        setImpact(data);
      } catch {
        break;
      }
    }
    setWatchingImpact(false);
  };

  const handleWrite = async () => {
    if (!subject || !predicate || !value) return;
    if (subject.length > 255) { flash("Error: Subject too long"); return; }
    if (predicate.length > 255) { flash("Error: Predicate too long"); return; }
    if (value.length > 1000) { flash("Error: Value too long"); return; }
    if (!subject.includes(':') && !subject.includes('_')) {
      flash("Error: Subject should be 'type:id' or 'type_id'"); return;
    }
    setImpact(null);
    try {
      const res = await queryStatsApi.writeTriple({ subject_id: subject, predicate, object_value: value });
      flash(`Written at ${new Date().toLocaleTimeString()}`);
      onWritten?.();
      if (res.data.mz_timestamp_lower_bound != null) {
        watchImpact(res.data.mz_timestamp_lower_bound);
      }
    } catch {
      flash("Write failed");
    }
  };

  const flash = (msg: string) => {
    setStatus(msg);
    setTimeout(() => setStatus(null), 3000);
  };

  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <Edit3 className="h-4 w-4 text-purple-600" />
        <span className="font-medium text-gray-900">Write a Triple</span>
        <span className="text-xs text-gray-500">— Update an order property and observe propagation</span>
      </div>

      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex-1 min-w-[120px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">Subject</label>
          <input
            type="text"
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-white"
            placeholder="order:FM-1001"
          />
        </div>
        <div className="flex-1 min-w-[120px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">Predicate</label>
          <select
            value={predicate}
            onChange={e => setPredicate(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-white"
          >
            {availablePredicates.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="flex-1 min-w-[120px]">
          <label className="block text-xs font-medium text-gray-600 mb-1">Value</label>
          <input
            type="text"
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleWrite(); }}
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-white"
            placeholder={placeholdersByPredicate[predicate] || 'value'}
          />
        </div>
        <button
          onClick={handleWrite}
          disabled={!subject || !predicate || !value}
          className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm"
        >
          Write
        </button>
        {status && (
          <span className={`text-sm flex items-center gap-1 ${status.startsWith('Error') ? 'text-red-600' : 'text-green-600'}`}>
            <span className={`inline-block w-2 h-2 rounded-full ${status.startsWith('Error') ? 'bg-red-500' : 'bg-green-500'}`} />
            {status}
          </span>
        )}
      </div>
      {(watchingImpact || impact) && (
        <div className="mt-2 text-xs text-gray-600 flex items-center gap-1.5">
          {watchingImpact && !impact && (
            <span className="text-gray-400 animate-pulse">Watching pipeline...</span>
          )}
          {impact && (
            <>
              <span className="font-mono text-purple-700 font-semibold">{impact.impacted}</span>
              <span className="text-gray-400">/</span>
              <span className="font-mono text-gray-600">{impact.total}</span>
              <span className="text-gray-500">docs re-indexed</span>
              <span className={`font-semibold ml-1 ${impact.pct > 10 ? 'text-orange-600' : 'text-purple-600'}`}>
                ({impact.pct}%)
              </span>
              {watchingImpact && <span className="text-gray-400 animate-pulse ml-1">…</span>}
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default WriteTripleForm;
