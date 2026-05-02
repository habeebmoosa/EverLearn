import { useState, useEffect } from 'react';
import { api } from './api';
import Sidebar from './components/Sidebar';
import TaskForm from './components/TaskForm';
import SessionView from './components/SessionView';

function App() {
  const [pipelines, setPipelines] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [currentSession, setCurrentSession] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Initial data load
  useEffect(() => {
    const loadData = async () => {
      try {
        const [pipelinesData, sessionsData] = await Promise.all([
          api.getPipelines(),
          api.getSessions()
        ]);
        setPipelines(pipelinesData.pipelines || []);
        setSessions(sessionsData.sessions || []);
      } catch (err) {
        console.error('Failed to load initial data:', err);
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, []);

  // Poll for active session updates
  useEffect(() => {
    let intervalId;
    
    const pollSession = async () => {
      if (!currentSessionId) return;
      
      try {
        const data = await api.getSession(currentSessionId);
        setCurrentSession(data);
        
        // Update session in the sidebar list too
        setSessions(prev => prev.map(s => 
          s.session_id === currentSessionId ? { ...s, status: data.status, topic: data.topic } : s
        ));

        // Stop polling if done or failed
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(intervalId);
        }
      } catch (err) {
        console.error('Polling error:', err);
        clearInterval(intervalId);
      }
    };

    if (currentSessionId && (!currentSession || currentSession.status === 'running')) {
      pollSession(); // Immediate fetch
      intervalId = setInterval(pollSession, 2000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [currentSessionId, currentSession?.status]);

  const handleSelectSession = (id) => {
    setCurrentSessionId(id);
    setCurrentSession(null); // Clear while loading
  };

  const handleNewTask = () => {
    setCurrentSessionId(null);
    setCurrentSession(null);
  };

  const handleSubmitTask = async (payload) => {
    try {
      const data = await api.startTask(payload);
      
      // Add immediately to sidebar
      const newSessionMeta = {
        session_id: data.session_id,
        topic: payload.label,
        status: 'running',
        pipeline_id: payload.pipeline_id,
        created_at: new Date().toISOString()
      };
      
      setSessions(prev => [newSessionMeta, ...prev]);
      setCurrentSessionId(data.session_id);
      
    } catch (err) {
      console.error('Failed to start task:', err);
      alert('Failed to start task. See console for details.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-surface-0">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
          <p className="text-ink-2 font-medium tracking-wide text-sm">Initializing EverLearn...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface-0">
      <Sidebar 
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewTask={handleNewTask}
      />
      
      <main className="flex-1 overflow-hidden relative">
        {!currentSessionId ? (
          <div className="h-full overflow-y-auto">
            <TaskForm pipelines={pipelines} onSubmit={handleSubmitTask} />
          </div>
        ) : (
          <div className="h-full relative">
            {!currentSession ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
              </div>
            ) : (
              <SessionView session={currentSession} />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
