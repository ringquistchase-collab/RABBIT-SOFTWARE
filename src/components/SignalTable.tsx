import React from 'react'
import { SignalReading, useSpectrumStore } from '../lib/store'
import styles from './SignalTable.module.css'

export const SignalTable: React.FC = () => {
  const { liveReadings, frequencyFilter } = useSpectrumStore()

  const filteredReadings = liveReadings
    .filter((r) => r.frequency_mhz >= frequencyFilter.min && r.frequency_mhz <= frequencyFilter.max)
    .slice(-20)
    .reverse()

  const getPowerClass = (power: number) => {
    if (power > -60) return styles.strong
    if (power > -70) return styles.medium
    return styles.weak
  }

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Recent Signals</h3>
      <div className={styles.tableWrapper}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Frequency (MHz)</th>
              <th>Power (dBm)</th>
              <th>Bandwidth (MHz)</th>
              <th>Signal Type</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {filteredReadings.length === 0 ? (
              <tr>
                <td colSpan={5} className={styles.empty}>
                  No signals in selected frequency range
                </td>
              </tr>
            ) : (
              filteredReadings.map((reading) => (
                <tr key={reading.id}>
                  <td className={styles.mono}>{reading.frequency_mhz.toFixed(2)}</td>
                  <td className={`${styles.mono} ${getPowerClass(reading.power_dbm)}`}>
                    {reading.power_dbm.toFixed(2)}
                  </td>
                  <td className={styles.mono}>{(reading.bandwidth_mhz || 0).toFixed(2)}</td>
                  <td>
                    <span className={`${styles.badge} ${styles[reading.signal_type]}`}>
                      {reading.signal_type}
                    </span>
                  </td>
                  <td className={styles.mono}>{new Date(reading.timestamp).toLocaleTimeString()}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
