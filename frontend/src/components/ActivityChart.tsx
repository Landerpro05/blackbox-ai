import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DashboardResponse } from "../types/api";

export default function ActivityChart({
  data,
}: {
  data: DashboardResponse["trend"];
}) {
  return (
    <div
      className="chart"
      role="img"
      aria-label="Evolución de análisis y errores durante los últimos 14 días UTC"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 10, right: 12, left: -20, bottom: 0 }}
        >
          <defs>
            <linearGradient id="runs-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#528fff" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#528fff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke="#202b40"
            strokeDasharray="3 5"
            vertical={false}
          />
          <XAxis
            dataKey="date"
            tickFormatter={(value: string) =>
              value.slice(5).split("-").reverse().join("/")
            }
            tick={{ fill: "#8795ac", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            minTickGap={22}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: "#8795ac", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#111b2e",
              border: "1px solid #2a3952",
              borderRadius: 10,
            }}
          />
          <Area
            type="monotone"
            dataKey="runs"
            name="Análisis"
            stroke="#528fff"
            fill="url(#runs-fill)"
            strokeWidth={2}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="issues"
            name="Errores"
            stroke="#f5b74f"
            fill="transparent"
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
