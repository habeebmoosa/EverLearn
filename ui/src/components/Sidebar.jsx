import { useState, useRef, useEffect } from 'react';

export default function Sidebar({ 
  sessions, 
  pipelines,
  selectedPipelineId,
  onSelectPipeline,
  currentSessionId, 
  onSelectSession, 
  onNewTask 
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedPipeline = pipelines.find(p => p.id === selectedPipelineId);

  return (
    <div className={`flex flex-col border-r border-surface-4 bg-surface-1 transition-all duration-300 ${collapsed ? 'w-16' : 'w-64'}`}>
      <div className="flex items-center justify-between h-20 px-4 border-b border-surface-4 shrink-0">
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

      <div className="p-3 pb-0">
        <button
          onClick={onNewTask}
          className={`flex items-center justify-center gap-2 w-full py-2.5 bg-brand-600 hover:bg-brand-500 text-white rounded-md transition-colors border border-brand-500/50 mb-4 shadow-sm ${collapsed ? 'px-2' : 'px-4'}`}
          title="New Task"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {!collapsed && <span className="font-medium text-sm">New Task</span>}
        </button>

        {!collapsed && (
          <div className="mb-2 relative" ref={dropdownRef}>
            <label className="block text-[10px] font-bold tracking-wider text-ink-3 uppercase mb-1.5 px-1">
              Select Agent
            </label>
            
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="w-full flex items-center justify-between bg-surface-2 border border-surface-4 hover:border-brand-500/50 text-white text-sm rounded-md py-2 px-3 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors shadow-sm"
            >
              <div className="flex items-center gap-2 truncate">
                {selectedPipeline ? (
                  <>
                    <div className="w-5 h-5 rounded flex items-center justify-center font-bold text-[10px] shrink-0 bg-brand-500 text-white shadow-[0_0_10px_rgba(168,85,247,0.4)]">
                      {selectedPipeline.id.charAt(0).toUpperCase()}
                    </div>
                    <span className="truncate font-medium">{selectedPipeline.name}</span>
                  </>
                ) : (
                  <span className="text-ink-3">Select an Agent...</span>
                )}
              </div>
              <svg className={`w-4 h-4 text-ink-3 shrink-0 transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {isDropdownOpen && (
              <div className="absolute z-50 w-full mt-1.5 bg-surface-2 border border-surface-4 rounded-lg shadow-xl overflow-hidden py-1 animate-slide-up origin-top">
                {pipelines.map(p => {
                  const isSelected = p.id === selectedPipelineId;
                  return (
                    <button
                      key={p.id}
                      onClick={() => {
                        onSelectPipeline(p.id);
                        setIsDropdownOpen(false);
                      }}
                      className={`w-full text-left px-3 py-2.5 flex items-center gap-3 hover:bg-surface-3 transition-colors ${isSelected ? 'bg-brand-500/10' : ''}`}
                    >
                      <div className={`w-6 h-6 rounded-md flex items-center justify-center font-bold text-xs shrink-0
                        ${isSelected ? 'bg-brand-500 text-white shadow-[0_0_10px_rgba(168,85,247,0.4)]' : 'bg-surface-4 text-ink-2'}`}>
                        {p.id.charAt(0).toUpperCase()}
                      </div>
                      <span className={`text-sm ${isSelected ? 'text-brand-400 font-semibold' : 'text-white'}`}>
                        {p.name}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        {!collapsed && <h2 className="px-3 py-2 text-xs font-semibold tracking-wider text-ink-3 uppercase mt-2">Recent Sessions</h2>}

        {sessions.filter(s => s.pipeline_id === selectedPipelineId || !selectedPipelineId).map(session => (
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
    </div>
  );
}
