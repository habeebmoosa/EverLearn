import { useState } from 'react';

export default function Sidebar({ sessions, currentSessionId, onSelectSession, onNewTask }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={`flex flex-col border-r border-surface-4 bg-surface-1 transition-all duration-300 ${collapsed ? 'w-16' : 'w-64'}`}>
      <div className="flex items-center justify-between p-4 border-b border-surface-4">
        {!collapsed && <h1 className="text-xl font-bold tracking-tight text-white">EverLearn</h1>}
        <button 
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-md text-ink-2 hover:bg-surface-3 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>

      <div className="p-3">
        <button
          onClick={onNewTask}
          className={`flex items-center justify-center gap-2 w-full py-2.5 bg-surface-3 hover:bg-surface-4 text-white rounded-md transition-colors border border-surface-5 ${collapsed ? 'px-2' : 'px-4'}`}
          title="New Task"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {!collapsed && <span className="font-medium text-sm">New Task</span>}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        {!collapsed && <h2 className="px-3 py-2 text-xs font-semibold tracking-wider text-ink-3 uppercase">Sessions</h2>}
        
        {sessions.map(session => (
          <button
            key={session.session_id}
            onClick={() => onSelectSession(session.session_id)}
            className={`w-full text-left px-3 py-2 rounded-md transition-colors flex items-center gap-3 text-sm group
              ${currentSessionId === session.session_id ? 'bg-surface-3 text-white' : 'text-ink-2 hover:bg-surface-2 hover:text-white'}`}
          >
            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${session.status === 'running' ? 'bg-status-running animate-pulse' : session.status === 'failed' ? 'bg-status-failed' : 'bg-status-completed'}`} />
            
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <div className="truncate font-medium">{session.topic}</div>
                <div className="text-xs text-ink-3 truncate mt-0.5">
                  <span className="inline-block px-1.5 py-0.5 bg-brand-500/10 text-brand-400 rounded text-[10px] uppercase font-bold mr-2">
                    {session.pipeline_id || 'Task'}
                  </span>
                  {new Date(session.created_at).toLocaleDateString()}
                </div>
              </div>
            )}
          </button>
        ))}
      </div>
      
      <div className="p-4 border-t border-surface-4 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
          U
        </div>
        {!collapsed && (
          <div className="text-sm">
            <div className="text-white font-medium">User</div>
            <div className="text-ink-3 text-xs">Local Environment</div>
          </div>
        )}
      </div>
    </div>
  );
}
