import React from 'react'
import { useSpectrumStore } from '../lib/store'
import styles from './FrequencyFilter.module.css'

export const FrequencyFilter: React.FC = () => {
  const { frequencyFilter, setFrequencyFilter, liveReadings } = useSpectrumStore()

  const handleMinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const min = Math.min(Number(e.target.value), frequencyFilter.max)
    setFrequencyFilter({ ...frequencyFilter, min })
  }

  const handleMaxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const max = Math.max(Number(e.target.value), frequencyFilter.min)
    setFrequencyFilter({ ...frequencyFilter, max })
  }

  const filteredReadings = liveReadings.filter(
    (r) => r.frequency_mhz >= frequencyFilter.min && r.frequency_mhz <= frequencyFilter.max
  )

  const stats = {
    min:
      filteredReadings.length > 0
        ? Math.min(...filteredReadings.map((r) => r.power_dbm)).toFixed(1)
        : 'N/A',
    max:
      filteredReadings.length > 0
        ? Math.max(...filteredReadings.map((r) => r.power_dbm)).toFixed(1)
        : 'N/A',
    avg:
      filteredReadings.length > 0
        ? (filteredReadings.reduce((sum, r) => sum + r.power_dbm, 0) / filteredReadings.length).toFixed(1)
        : 'N/A',
  }

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Frequency Filter</h3>
      <div className={styles.filterGroup}>
        <div className={styles.inputGroup}>
          <label>Min Frequency (MHz)</label>
          <input
            type="number"
            value={frequencyFilter.min}
            onChange={handleMinChange}
            step="10"
            min="0"
          />
        </div>
        <div className={styles.inputGroup}>
          <label>Max Frequency (MHz)</label>
          <input
            type="number"
            value={frequencyFilter.max}
            onChange={handleMaxChange}
            step="10"
            min={frequencyFilter.min}
          />
        </div>
      </div>
      <div className={styles.analyticsGrid}>
        <div className={styles.analyticsCard}>
          <span className={styles.analyticsLabel}>Min Power (dBm)</span>
          <span className={styles.analyticsValue}>{stats.min}</span>
        </div>
        <div className={styles.analyticsCard}>
          <span className={styles.analyticsLabel}>Max Power (dBm)</span>
          <span className={styles.analyticsValue}>{stats.max}</span>
        </div>
        <div className={styles.analyticsCard}>
          <span className={styles.analyticsLabel}>Avg Power (dBm)</span>
          <span className={styles.analyticsValue}>{stats.avg}</span>
        </div>
        <div className={styles.analyticsCard}>
          <span className={styles.analyticsLabel}>In Range</span>
          <span className={styles.analyticsValue}>{filteredReadings.length}</span>
        </div>
      </div>
    </div>
  )
}
