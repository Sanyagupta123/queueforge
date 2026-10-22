import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

interface ActivityPoint {
  label: string
  succeeded: number
  failed: number
}

interface ActivityChartProps {
  data: ActivityPoint[]
}

export default function ActivityChart({ data }: ActivityChartProps) {
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 12, right: 8, left: -22, bottom: 0 }}>
          <defs>
            <linearGradient id="successFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#27c99a" stopOpacity={0.23} />
              <stop offset="100%" stopColor="#27c99a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#252e37" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: '#65717d', fontSize: 10 }} axisLine={false} tickLine={false} interval={2} />
          <YAxis allowDecimals={false} tick={{ fill: '#65717d', fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ background: '#151c23', border: '1px solid #303b45', borderRadius: 8, fontSize: 12 }} />
          <Area type="monotone" dataKey="succeeded" name="Succeeded" stroke="#27c99a" fill="url(#successFill)" strokeWidth={2} />
          <Area type="monotone" dataKey="failed" name="Retry / dead" stroke="#f2aa59" fill="none" strokeWidth={1.5} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
