import { create } from 'zustand'

export interface SignalReading {
  id: string
  frequency_mhz: number
  power_dbm: number
  bandwidth_mhz?: number
  timestamp: string
  signal_type: string
}

export interface SpectrumSession {
  id: string
  name: string
  description?: string
  start_time: string
  end_time?: string
  recording_count: number
}

interface SpectrumStore {
  isLive: boolean
  setIsLive: (value: boolean) => void
  currentSession: SpectrumSession | null
  setCurrentSession: (session: SpectrumSession | null) => void
  liveReadings: SignalReading[]
  addLiveReading: (reading: SignalReading) => void
  clearLiveReadings: () => void
  frequencyFilter: { min: number; max: number }
  setFrequencyFilter: (filter: { min: number; max: number }) => void
}

export const useSpectrumStore = create<SpectrumStore>((set) => ({
  isLive: false,
  setIsLive: (value) => set({ isLive: value }),
  currentSession: null,
  setCurrentSession: (session) => set({ currentSession: session }),
  liveReadings: [],
  addLiveReading: (reading) =>
    set((state) => ({
      liveReadings: [...state.liveReadings.slice(-99), reading],
    })),
  clearLiveReadings: () => set({ liveReadings: [] }),
  frequencyFilter: { min: 0, max: 6000 },
  setFrequencyFilter: (filter) => set({ frequencyFilter: filter }),
}))
