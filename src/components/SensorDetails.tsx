import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import styles from './SensorDetails.module.css'

interface Sensor {
  id: string
  device_id: string
  name: string
  location: string
  sensor_type: string
  status: string
  created_at: string
}

interface Reading {
  timestamp: string
  value: number
  unit: string
}

interface Alert {
  id: string
  alert_type: string
  message: string
  severity: string
  triggered_at: string
}

interface Props {
  sensor: Sensor
  onBack: () => void
  onRefresh: () => void
}

export function SensorDetails({ sensor, onBack }: Props) {
  const [readings, setReadings] = useState<Reading[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)

  useEffect(() => {
    loadData()
  }, [sensor.id])

  const loadData = async () => {
    try {
      setLoading(true)

      const { data: readingsData } = await supabase
        .from('sensor_readings')
        .select('timestamp, value, unit')
        .eq('sensor_id', sensor.id)
        .order('timestamp', { ascending: false })
        .limit(100)

      const { data: alertsData } = await supabase
        .from('sensor_alerts')
        .select('id, alert_type, message, severity, triggered_at')
        .eq('sensor_id', sensor.id)
        .order('triggered_at', { ascending: false })
        .limit(20)

      const { data: sensorData } = await supabase
        .from('sensors')
        .select('api_key')
        .eq('id', sensor.id)
        .single()

      setReadings((readingsData || []).reverse())
      setAlerts(alertsData || [])
      setApiKey(sensorData?.api_key || '')
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const chartData = readings.map((r) => ({
    time: new Date(r.timestamp).toLocaleTimeString(),
    value: r.value,
  }))

  return (
    <div className={styles.details}>
      <div className={styles.header}>
        <button className={styles.backButton} onClick={onBack}>
          ← Back
        </button>
        <h2>{sensor.name}</h2>
      </div>

      <div className={styles.grid}>
        <div className={styles.infoCard}>
          <h3>Sensor Information</h3>
          <div className={styles.infoGrid}>
            <div>
              <span className={styles.label}>Device ID</span>
              <code>{sensor.device_id}</code>
            </div>
            <div>
              <span className={styles.label}>Type</span>
              <span>{sensor.sensor_type}</span>
            </div>
            <div>
              <span className={styles.label}>Location</span>
              <span>{sensor.location || 'Not specified'}</span>
            </div>
            <div>
              <span className={styles.label}>Status</span>
              <span style={{ color: sensor.status === 'active' ? '#10b981' : '#f59e0b' }}>
                {sensor.status}
              </span>
            </div>
          </div>

          <div className={styles.apiKeySection}>
            <h4>API Key</h4>
            <div className={styles.apiKeyBox}>
              <code>{showApiKey ? apiKey : '••••••••••••••••'}</code>
              <button
                className={styles.toggleButton}
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>
        </div>

        <div className={styles.chartCard}>
          <h3>Recent Readings</h3>
          {loading ? (
            <div className={styles.loading}>Loading...</div>
          ) : readings.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid stroke="#e5e7eb" />
                <XAxis dataKey="time" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#667eea"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className={styles.noData}>No readings yet</p>
          )}
        </div>
      </div>

      {alerts.length > 0 && (
        <div className={styles.alertsCard}>
          <h3>Recent Alerts</h3>
          <div className={styles.alertsList}>
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={styles.alertItem}
                style={{
                  borderLeftColor:
                    alert.severity === 'critical' ? '#ef4444' :
                    alert.severity === 'warning' ? '#f59e0b' : '#10b981',
                }}
              >
                <div>
                  <span className={styles.alertType}>{alert.alert_type}</span>
                  <p>{alert.message}</p>
                  <span className={styles.alertTime}>
                    {new Date(alert.triggered_at).toLocaleString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <div className={styles.error}>{error}</div>}
    </div>
  )
}
