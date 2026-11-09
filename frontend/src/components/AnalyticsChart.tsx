import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Analytics } from "../types/reporting";
import { formatDate } from "../services/format";

export default function AnalyticsChart({
  items,
}: {
  items: Analytics["items"];
}) {
  const data = [...items].reverse();
  return (
    <div
      className="analytics-chart"
      role="img"
      aria-label="Evolución real de incidencias y navegación por ejecución"
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 12, right: 12, left: -20, bottom: 4 }}
        >
          <CartesianGrid
            stroke="#202b40"
            strokeDasharray="3 5"
            vertical={false}
          />
          <XAxis
            dataKey="id"
            tickFormatter={(id: string) => id.slice(0, 6)}
            tick={{ fill: "#8795ac", fontSize: 11 }}
            minTickGap={24}
          />
          <YAxis
            yAxisId="issues"
            allowDecimals={false}
            tick={{ fill: "#8795ac", fontSize: 11 }}
          />
          <YAxis
            yAxisId="time"
            orientation="right"
            tick={{ fill: "#8795ac", fontSize: 11 }}
            unit=" ms"
            width={78}
          />
          <Tooltip
            labelFormatter={(_, payload) =>
              payload.length
                ? formatDate(payload[0].payload.created_at) +
                  " · " +
                  payload[0].payload.status
                : ""
            }
            contentStyle={{
              background: "#111b2e",
              border: "1px solid #2a3952",
              borderRadius: 10,
            }}
          />
          <Line
            yAxisId="issues"
            dataKey="issues"
            name="Incidencias"
            stroke="#f5b74f"
            strokeWidth={2}
            dot={{ r: 3 }}
            isAnimationActive={false}
          />
          <Line
            yAxisId="time"
            dataKey="average_navigation_ms"
            name="Navegación (ms)"
            stroke="#528fff"
            strokeWidth={2}
            dot={{ r: 3 }}
            isAnimationActive={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
