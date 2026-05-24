import { useState } from 'react'
import { supabase } from '../lib/supabase'
import styles from './SensorRegistration.module.css'

interface Props {
  onSuccess: () => void
}

export function SensorRegistration({ onSuccess }: Props) {
  const [deviceId, setDeviceId] = useState('')
  const [name, setName] = useState('')
  const [location, setLocation] = useState('')
  const [sensorType, setSensorType] = useState('RF_ANALYZER')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const { data: session } = await supabase.auth.getSession()
      if (!session.session) throw new Error('Not authenticated')

      const apiUrl = `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/sensor-management`
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.session.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          device_id: deviceId,
          name,
          location,
          sensor_type: sensorType,
          metadata: {},
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || 'Failed to register sensor')
      }

      setDeviceId('')
      setName('')
      setLocation('')
      setSensorType('RF_ANALYZER')
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.registration}>
      <div className={styles.box}>
        <h2>Register New Sensor</h2>
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.formGroup}>
            <label htmlFor="deviceId">Device ID</label>
            <input
              id="deviceId"
              type="text"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              placeholder="e.g., SDR-001"
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label htmlFor="name">Sensor Name</label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Lab RF Analyzer"
              required
            />
          </div>

          <div className={styles.formGroup}>
            <label htmlFor="location">Location</label>
            <input
              id="location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g., Building A, Floor 3"
            />
          </div>

          <div className={styles.formGroup}>
            <label htmlFor="sensorType">Sensor Type</label>
            <select
              id="sensorType"
              value={sensorType}
              onChange={(e) => setSensorType(e.target.value)}
            >
              <option value="RF_ANALYZER">RF Analyzer</option>
              <option value="TEMPERATURE">Temperature</option>
              <option value="HUMIDITY">Humidity</option>
              <option value="SIGNAL_STRENGTH">Signal Strength</option>
              <option value="CUSTOM">Custom</option>
            </select>
          </div>

          {error && <div className={styles.error}>{error}</div>}

          <button
            type="submit"
            disabled={loading}
            className={styles.submitButton}
          >
            {loading ? 'Registering...' : 'Register Sensor'}
          </button>
        </form>
      </div>
    </div>
  )
}
