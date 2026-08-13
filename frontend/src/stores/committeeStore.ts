import { create } from "zustand";

export interface CommitteeActivity {
  id: string;
  type: "analyst_output" | "ic_decision" | "cio_proposal" | "risk_assessment";
  workflow_run_id?: string;
  agent?: string;
  decision?: string;
  confidence?: number;
  timestamp: string;
}

interface CommitteeState {
  activities: CommitteeActivity[];
}

interface CommitteeActions {
  appendActivity: (activity: CommitteeActivity) => void;
  getActivities: () => CommitteeActivity[];
  getActivitiesByType: (type: CommitteeActivity["type"]) => CommitteeActivity[];
}

const MAX_ACTIVITIES = 500;

export const useCommitteeStore = create<CommitteeState & CommitteeActions>((set, get) => ({
  activities: [],

  appendActivity: (activity) => {
    set((state) => ({
      activities: [...state.activities, activity].slice(-MAX_ACTIVITIES),
    }));
  },

  getActivities: () => get().activities,

  getActivitiesByType: (type) => get().activities.filter((activity) => activity.type === type),
}));
