// State kill-switch bersama + label mode.
//
// Dipisah ke modul non-komponen supaya file komponen tetap hanya mengekspor
// komponen (aturan Fast Refresh), dan supaya kartu (KillSwitchCard) serta chip
// header (terminal/KillSwitchControl) membaca state yang SAMA dari desk store
// tanpa menduplikasi fetch.
import { useDesk } from '../../lib/useDesk'

export const MODE_LABEL = {
  STOP_NEW_ORDERS: 'order baru diblokir',
  STOP_AND_FLATTEN: 'semua posisi di-flatten',
  PAUSE_STRATEGY: 'strategi dijeda',
  GLOBAL_HALT: 'halt global',
}

// Satu sumber kebenaran status halt: store desk (diisi /kill-switch + SSE),
// dengan fallback `state.halted` untuk kompatibilitas.
export function useKillState() {
  const state = useDesk()
  const ks = state?.killSwitch
  const armed = !!(ks?.state?.active ?? state?.halted)
  return {
    ks,
    armed,
    mode: ks?.state?.mode,
    strategy: ks?.state?.strategy,
    reason: ks?.state?.reason,
    paused: ks?.paused_strategies || [],
    checklist: ks?.recovery_checklist || [],
  }
}
