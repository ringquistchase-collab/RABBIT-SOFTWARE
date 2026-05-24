import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import { SensorCard } from './SensorCard'
import { SensorDetails } from './SensorDetails'
import styles from './SensorDashboard.module.css'

interface Sensor {
  id: string
  device_id: string
  name: string
  location: string
  sensor_type: string
  status: string
  last_reading: string | null
  created_at: string
}

export function SensorDashboard() {
  const [sensors, setSensors] = useState<Sensor[]>([])
  const [selectedSensor, setSelectedSensor] = useState<Sensor | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    loadSensors()
  }, [])

  const loadSensors = async () => {
    try {
      setLoading(true)
      const { data: session } = await supabase.auth.getSession()
      if (!session.session) throw new Error('Not authenticated')

      const apiUrl = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/sensor-management`
      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.session.access_token}`,
        },
      })

      if (!response.ok) throw new Error('Failed to load sensors')

      const data = await response.json()
      setSensors(data.sensors || [])
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sensors')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className={styles.dashboard}>
        <div className={styles.loading}>Loading sensors...</div>
      </div>
    )
  }

  if (error && sensors.length === 0) {
    return (
      <div className={styles.dashboard}>
        <div className={styles.error}>{error}</div>
      </div>
    )
  }

  if (selectedSensor) {
    return (
      <SensorDetails
        sensor={selectedSensor}
        onBack={() => setSelectedSensor(null)}
        onRefresh={loadSensors}
      />
    )
  }

  return (
    <div className={styles.dashboard}>
      <div className={styles.header}>
        <h2>Registered Sensors</h2>
        <span className={styles.count}>{sensors.length} total</span>
      </div>

      {sensors.length === 0 ? (
        <div className={styles.empty}>
          <p>No sensors registered yet.</p>
          <p>Register your first sensor to get started.</p>
        </div>
      ) : (
        <div className={styles.grid}>
          {sensors.map((sensor) => (
            <SensorCard
              key={sensor.id}
              sensor={sensor}
              onSelect={() => setSelectedSensor(sensor)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
