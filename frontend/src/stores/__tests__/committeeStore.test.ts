import { describe, it, expect } from 'vitest';
import { useCommitteeStore } from '../committeeStore';

function makeActivity(id: string, type: 'analyst_output' | 'ic_decision') {
  return {
    id,
    type,
    workflow_run_id: 'run-1',
    agent: 'Macro Analyst',
    decision: 'BULLISH',
    confidence: 0.82,
    timestamp: new Date().toISOString(),
  };
}

describe('committeeStore', () => {
  it('appends and filters activities', () => {
    useCommitteeStore.getState().appendActivity(makeActivity('a1', 'analyst_output'));
    useCommitteeStore.getState().appendActivity(makeActivity('a2', 'ic_decision'));

    expect(useCommitteeStore.getState().getActivities()).toHaveLength(2);
    expect(useCommitteeStore.getState().getActivitiesByType('ic_decision')).toHaveLength(1);
  });

  it('trims activities to 500 entries', () => {
    for (let i = 0; i < 550; i++) {
      useCommitteeStore.getState().appendActivity(makeActivity(`a${i}`, 'analyst_output'));
    }

    expect(useCommitteeStore.getState().getActivities()).toHaveLength(500);
  });
});
