import { useEffect, useState } from 'react'
import { supabase } from './lib/supabase'
import styles from './App.module.css'
import { SensorDashboard } from './components/SensorDashboard'
import { SensorRegistration } from './components/SensorRegistration'
import { Auth } from './components/Auth'

function App() {
  const [session, setSession] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [showRegistration, setShowRegistration] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
      setLoading(false)
    })

    return () => subscription?.unsubscribe()
  }, [])

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading...</div>
      </div>
    )
  }

  if (!session) {
    return <Auth />
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1>IoT Sensor Data Platform</h1>
          <div className={styles.headerActions}>
            <button
              className={styles.primaryButton}
              onClick={() => setShowRegistration(!showRegistration)}
            >
              {showRegistration ? 'Close' : 'Register Sensor'}
            </button>
            <button
              className={styles.secondaryButton}
              onClick={() => supabase.auth.signOut()}
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {showRegistration && <SensorRegistration onSuccess={() => setShowRegistration(false)} />}
      <SensorDashboard />
    </div>
  )
}

export default App
