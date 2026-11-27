import { useEffect, useState } from 'react'
import { auth, desk, startDesk, DEMO } from './api'

export function useDesk() {
  const [state, setState] = useState(null)
  useEffect(() => {
    // startDesk idempoten (real: ditunda saat belum auth; demo: guard timer)
    startDesk()
    return desk.subscribe(setState)
  }, [])
  return state
}

export function useTick() {
  const [tick, setTick] = useState(null)
  useEffect(() => auth.onTick(setTick), [])
  return tick
}

export { DEMO }
