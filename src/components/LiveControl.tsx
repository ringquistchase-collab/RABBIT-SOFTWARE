import React, { useState, useEffect } from 'react'
import { useSpectrumStore } from '../lib/store'
import styles from './LiveControl.module.css'

export const LiveControl: React.FC = () => {
  const { isLive, setIsLive, liveReadings, addLiveReading, clearLiveReadings } = useSpectrumStore()
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>(
    'disconnected'
  )

  const handleToggleLive = async () => {
    if (!isLive) {
      setConnectionStatus('connecting')
      setIsLive(true)
      clearLiveReadings()
      setConnectionStatus('connected')

      // Simulate live RF signal readings
      const interval = setInterval(() => {
        const frequency = Math.random() * 5000 + 100
        const power = Math.random() * 40 - 80
        const bandwidth = Math.random() * 50 + 1

        addLiveReading({
          id: `reading-${Date.now()}-${Math.random()}`,
          frequency_mhz: frequency,
          power_dbm: power,
          bandwidth_mhz: bandwidth,
          timestamp: new Date().toISOString(),
          signal_type: power > -60 ? 'strong' : power > -70 ? 'medium' : 'weak',
        })
      }, 1000)

      // Store interval ID for cleanup
      ;(window as any).spectrumInterval = interval
    } else {
      setIsLive(false)
      setConnectionStatus('disconnected')
      if ((window as any).spectrumInterval) {
        clearInterval((window as any).spectrumInterval)
      }
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.controls}>
        <button
          onClick={handleToggleLive}
          className={`${styles.button} ${isLive ? styles.active : ''}`}
        >
          {isLive ? '◼ Stop' : '▶ Start'} Listening
        </button>
        <div className={styles.status}>
          <span
            className={`${styles.indicator} ${styles[connectionStatus]}`}
          ></span>
          <span className={styles.statusText}>{connectionStatus.toUpperCase()}</span>
        </div>
      </div>
      <div className={styles.stats}>
        <div className={styles.stat}>
          <span className={styles.label}>Readings</span>
          <span className={styles.value}>{liveReadings.length}</span>
        </div>
        {liveReadings.length > 0 && (
          <>
            <div className={styles.stat}>
              <span className={styles.label}>Latest Frequency</span>
              <span className={styles.value}>{liveReadings[liveReadings.length - 1].frequency_mhz.toFixed(1)} MHz</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Latest Power</span>
              <span className={styles.value}>{liveReadings[liveReadings.length - 1].power_dbm.toFixed(1)} dBm</span>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
