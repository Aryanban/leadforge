"use client";

import {
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
} from "recharts";
import type { TimeSeriesResponse } from "@/lib/api";

/**
 * The outreach activity chart.
 *
 * This lives in its own module so it can be loaded on demand. `recharts`
 * plus its d3 dependencies are ~100 kB of JavaScript, and they were ending
 * up in the *shared* chunk - which meant every route (the inbox, the scraper,
 * the settings page, the lead database) downloaded a charting library that
 * only the overview ever renders. Importing this module through
 * `next/dynamic` moves recharts into a chunk that is fetched only when the
 * overview page actually shows the chart.
 */
export default function ActivityChart({ series }: { series: TimeSeriesResponse }) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series.days} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#64748b" }}
            tickFormatter={(v: string) => v.slice(5)}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fontSize: 10, fill: "#64748b" }} allowDecimals={false} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #e2e8f0" }}
            labelStyle={{ color: "#475569" }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line type="monotone" dataKey="sent" stroke="#2563eb" strokeWidth={2} dot={false} name="Sent" />
          <Line type="monotone" dataKey="opened" stroke="#7c3aed" strokeWidth={2} dot={false} name="Opened" />
          <Line type="monotone" dataKey="replied" stroke="#059669" strokeWidth={2} dot={false} name="Replied" />
          <Line type="monotone" dataKey="bounced" stroke="#dc2626" strokeWidth={2} dot={false} name="Bounced" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
