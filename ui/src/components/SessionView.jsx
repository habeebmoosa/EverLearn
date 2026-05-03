import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function SessionView({ session }) {
  const bottomRef = useRef(null);

  // Auto-scroll to bottom of content when running
  useEffect(() => {
    if (session?.status === 'running') {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [session?.report, session?.iterations, session?.status]);

  if (!session) return null;

  const progress = Math.min(100, Math.round((session.current_iteration / session.max_iterations) * 100));

  return (
    <div className="flex flex-col h-full bg-surface-0">
      
      {/* Header */}
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur-xl border-b border-surface-4 px-8 py-5 flex items-center justify-between">
        <div className="min-w-0 flex-1 pr-4">
          <div className="flex items-center gap-3 mb-1">
            <span className="px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider bg-brand-500/10 text-brand-400 border border-brand-500/20">
              {session.pipeline_id || 'Task'}
            </span>
            <span className={`flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider
              ${session.status === 'running' ? 'text-status-running' : session.status === 'failed' ? 'text-status-failed' : 'text-status-completed'}`}>
              {session.status === 'running' && <span className="w-1.5 h-1.5 rounded-full bg-status-running animate-pulse" />}
              {session.status}
            </span>
          </div>
          <h2 className="text-xl font-bold text-white truncate" title={session.topic}>{session.topic}</h2>
        </div>
        
        {/* Stats */}
        <div className="flex items-center gap-6 shrink-0 bg-surface-1 px-4 py-2 rounded-lg border border-surface-4">
          <div className="text-center">
            <div className="text-[10px] uppercase text-ink-3 font-semibold tracking-wider">Iteration</div>
            <div className="text-white font-medium text-sm">{session.current_iteration} / {session.max_iterations}</div>
          </div>
          <div className="w-px h-6 bg-surface-4" />
          <div className="text-center">
            <div className="text-[10px] uppercase text-ink-3 font-semibold tracking-wider">Best Score</div>
            <div className="text-brand-400 font-bold text-sm">{session.best_score || 0}</div>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto w-full px-6 py-8">
          
          {/* Active Progress State */}
          {session.status === 'running' && (
            <div className="mb-10 p-5 rounded-xl border border-brand-500/30 bg-brand-500/5 animate-pulse-dot">
              <div className="flex justify-between text-sm mb-2 font-medium">
                <span className="text-brand-400">{session.current_step || 'Agent is working...'}</span>
                <span className="text-white">{progress}%</span>
              </div>
              <div className="w-full bg-surface-3 rounded-full h-1.5 overflow-hidden">
                <div 
                  className="bg-brand-500 h-1.5 rounded-full transition-all duration-500 ease-out" 
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Render iterations history */}
          {session.iterations && session.iterations.length > 0 && (
            <div className="space-y-6 mb-10">
              <h3 className="text-sm font-semibold text-ink-3 uppercase tracking-wider border-b border-surface-4 pb-2">Iteration History</h3>
              {session.iterations.map((iter, idx) => (
                <div key={idx} className="bg-surface-1 border border-surface-4 rounded-lg p-4 flex gap-4">
                  <div className="w-10 h-10 rounded-lg bg-surface-3 flex items-center justify-center font-bold text-ink-2 shrink-0">
                    {iter.iteration}
                  </div>
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <span className={`text-sm font-semibold ${iter.kept ? 'text-status-completed' : 'text-ink-2'}`}>
                        Score: {iter.quality_score}
                      </span>
                      {iter.kept && <span className="px-1.5 py-0.5 rounded text-[10px] bg-status-completed/10 text-status-completed border border-status-completed/20 font-bold uppercase tracking-wider">Kept</span>}
                    </div>
                    <p className="text-sm text-ink-2 leading-relaxed">{iter.summary}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Error Message */}
          {session.error && (
            <div className="mb-8 p-4 bg-status-failed/10 border border-status-failed/20 rounded-lg">
              <h3 className="text-status-failed font-semibold mb-1 flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                Task Failed
              </h3>
              <p className="text-white text-sm whitespace-pre-wrap">{session.error}</p>
            </div>
          )}

          {/* Markdown Output */}
          {(session.report || session.artifact) && (
            <div className="bg-surface-1 border border-surface-4 rounded-xl overflow-hidden shadow-xl">
              <div className="bg-surface-2 px-6 py-3 border-b border-surface-4 flex items-center justify-between">
                <h3 className="font-semibold text-white">Final Output</h3>
              </div>
              <div className="p-8">
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {session.artifact || session.report}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} className="h-4" />
        </div>
      </div>
    </div>
  );
}
