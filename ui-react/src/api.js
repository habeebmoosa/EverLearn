const API_BASE = '/api';

export const api = {
  // Pipelines
  getPipelines: async () => {
    const res = await fetch(`${API_BASE}/pipelines`);
    if (!res.ok) throw new Error('Failed to fetch pipelines');
    return res.json();
  },

  // Sessions
  getSessions: async () => {
    const res = await fetch(`${API_BASE}/research/sessions/list`);
    if (!res.ok) throw new Error('Failed to fetch sessions');
    return res.json();
  },

  getSession: async (id) => {
    const res = await fetch(`${API_BASE}/research/sessions/${id}`);
    if (!res.ok) throw new Error('Failed to fetch session');
    return res.json();
  },

  // Tasks
  startTask: async (payload) => {
    const res = await fetch(`${API_BASE}/tasks/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to start task');
    return res.json();
  }
};
