import React from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { SignalReading } from '../lib/store'
import styles from './SpectrumChart.module.css'

interface SpectrumChartProps {
  data: SignalReading[]
}

export const SpectrumChart: React.FC<SpectrumChartProps> = ({ data }) => {
  const chartData = data.map((reading) => ({
    frequency: reading.frequency_mhz.toFixed(1),
    power: reading.power_dbm,
    bandwidth: reading.bandwidth_mhz || 0,
  }))

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Spectrum Analysis</h2>
        <span className={styles.count}>{data.length} readings</span>
      </div>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="frequency"
            label={{ value: 'Frequency (MHz)', position: 'insideBottomRight', offset: -5 }}
          />
          <YAxis label={{ value: 'Power (dBm)', angle: -90, position: 'insideLeft' }} />
          <Tooltip
            contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)' }}
            formatter={(value) => (typeof value === 'number' ? value.toFixed(2) : value)}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="power"
            stroke="#0066cc"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
