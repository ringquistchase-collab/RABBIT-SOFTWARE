import React, { useEffect, useState } from 'react'
import { useSpectrumStore } from './lib/store'
import { supabase } from './lib/supabase'
import { SpectrumChart } from './components/SpectrumChart'
import { LiveControl } from './components/LiveControl'
import { FrequencyFilter } from './components/FrequencyFilter'
import { SignalTable } from './components/SignalTable'
import styles from './App.module.css'

function App() {
  const { liveReadings, frequencyFilter } = useSpectrumStore()
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.onAuthStateChange((event, session) => {
      setUser(session?.user || null)
      setLoading(false)
    })
  }, [])

  const filteredReadings = liveReadings.filter(
    (r) => r.frequency_mhz >= frequencyFilter.min && r.frequency_mhz <= frequencyFilter.max
  )

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading...</div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className={styles.container}>
        <div className={styles.authPrompt}>
          <h1>SDR Spectrum Analyzer</h1>
          <p>Sign in to get started</p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div>
            <h1>SDR Spectrum Analyzer</h1>
            <p className={styles.subtitle}>Real-time RF signal analysis and visualization</p>
          </div>
          <div className={styles.userInfo}>
            <span>{user.email}</span>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <LiveControl />
        {liveReadings.length > 0 && (
          <>
            <SpectrumChart data={filteredReadings} />
            <div className={styles.gridLayout}>
              <FrequencyFilter />
              <SignalTable />
            </div>
          </>
        )}
        {liveReadings.length === 0 && (
          <div className={styles.placeholder}>
            <h2>No Data Yet</h2>
            <p>Start listening to begin collecting RF signal data</p>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
