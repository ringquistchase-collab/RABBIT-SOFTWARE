import styles from './SensorCard.module.css'

interface Sensor {
  id: string
  device_id: string
  name: string
  location: string
  sensor_type: string
  status: string
  last_reading: string | null
}

interface Props {
  sensor: Sensor
  onSelect: () => void
}

export function SensorCard({ sensor, onSelect }: Props) {
  const lastReadingTime = sensor.last_reading
    ? new Date(sensor.last_reading).toLocaleString()
    : 'Never'

  const statusColor = sensor.status === 'active' ? '#10b981' :
                      sensor.status === 'inactive' ? '#f59e0b' : '#ef4444'

  return (
    <div className={styles.card} onClick={onSelect}>
      <div className={styles.header}>
        <div>
          <h3>{sensor.name}</h3>
          <p className={styles.deviceId}>{sensor.device_id}</p>
        </div>
        <div className={styles.status} style={{ backgroundColor: statusColor }}>
          {sensor.status}
        </div>
      </div>

      <div className={styles.content}>
        <div className={styles.item}>
          <span className={styles.label}>Type</span>
          <span className={styles.value}>{sensor.sensor_type}</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>Location</span>
          <span className={styles.value}>{sensor.location || 'Not specified'}</span>
        </div>
        <div className={styles.item}>
          <span className={styles.label}>Last Reading</span>
          <span className={styles.value}>{lastReadingTime}</span>
        </div>
      </div>

      <div className={styles.footer}>
        <button className={styles.viewButton}>View Details →</button>
      </div>
    </div>
  )
}
