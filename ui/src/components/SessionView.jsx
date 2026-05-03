import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceDot } from 'recharts';

export default function SessionView({ session }) {
  const bottomRef = useRef(null);
  const [isHistoryExpanded, setIsHistoryExpanded] = useState(false);

  const chartData = session?.iterations?.map(iter => ({
    iteration: iter.iteration,
    name: `Iter ${iter.iteration}`,
    score: iter.quality_score || 0,
    kept: iter.kept
  })) || [];

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
      <div className="sticky top-0 z-10 bg-surface-0/80 backdrop-blur-xl border-b border-surface-4 px-8 h-20 flex items-center justify-between shrink-0">
        {/* Left: Title only */}
        <h2 className="text-xl font-bold text-white truncate min-w-0 flex-1 pr-4" title={session.topic}>
          {session.topic}
        </h2>

        {/* Right: Status + Iterations + Best Score */}
        <div className="flex items-center gap-5 shrink-0 bg-surface-1 px-5 py-2.5 rounded-xl border border-surface-4">
          <div className="text-center">
            <div className="text-[10px] uppercase text-ink-3 font-semibold tracking-wider mb-0.5">Status</div>
            <div className={`flex items-center gap-1.5 text-sm font-semibold capitalize
              ${session.status === 'running' ? 'text-status-running' : session.status === 'failed' ? 'text-status-failed' : 'text-status-completed'}`}>
              {session.status === 'running' && <span className="w-1.5 h-1.5 rounded-full bg-status-running animate-pulse" />}
              {session.status === 'failed' && <span className="w-1.5 h-1.5 rounded-full bg-status-failed" />}
              {session.status === 'completed' && <span className="w-1.5 h-1.5 rounded-full bg-status-completed" />}
              {session.status}
            </div>
          </div>
          <div className="w-px h-8 bg-surface-4" />
          <div className="text-center">
            <div className="text-[10px] uppercase text-ink-3 font-semibold tracking-wider mb-0.5">Iteration</div>
            <div className="text-white font-medium text-sm">{session.current_iteration} / {session.max_iterations}</div>
          </div>
          <div className="w-px h-8 bg-surface-4" />
          <div className="text-center">
            <div className="text-[10px] uppercase text-ink-3 font-semibold tracking-wider mb-0.5">Best Score</div>
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

          {/* Dashboard Summary */}
          {/* <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
            <div className="bg-surface-1 border border-surface-4 rounded-xl p-5 shadow-sm">
              <div className="text-ink-3 text-xs font-bold uppercase tracking-wider mb-1">Status</div>
              <div className="text-white font-medium text-lg capitalize flex items-center gap-2">
                {session.status === 'running' && <span className="w-2 h-2 rounded-full bg-status-running animate-pulse" />}
                {session.status === 'failed' && <span className="w-2 h-2 rounded-full bg-status-failed" />}
                {session.status === 'completed' && <span className="w-2 h-2 rounded-full bg-status-completed" />}
                {session.status}
              </div>
            </div>
            <div className="bg-surface-1 border border-surface-4 rounded-xl p-5 shadow-sm">
              <div className="text-ink-3 text-xs font-bold uppercase tracking-wider mb-1">Iterations</div>
              <div className="text-white font-medium text-lg">
                {session.current_iteration} <span className="text-ink-3 text-sm font-normal">/ {session.max_iterations}</span>
              </div>
            </div>
            <div className="bg-surface-1 border border-surface-4 rounded-xl p-5 shadow-sm">
              <div className="text-ink-3 text-xs font-bold uppercase tracking-wider mb-1">Best Quality Score</div>
              <div className="text-brand-400 font-bold text-lg">{session.best_score || '0.0'}</div>
            </div>
          </div> */}

          {/* Expandable Iterations Section */}
          {session.iterations && session.iterations.length > 0 && (
            <div className="mb-10 bg-surface-1 border border-surface-4 rounded-xl overflow-hidden shadow-sm">
              <button 
                onClick={() => setIsHistoryExpanded(!isHistoryExpanded)}
                className="w-full px-6 py-4 flex items-center justify-between bg-surface-2 hover:bg-surface-3 transition-colors text-left"
              >
                <div>
                  <h3 className="font-semibold text-white">Iteration Analysis</h3>
                  <p className="text-xs text-ink-3 mt-0.5">View quality scores and step history</p>
                </div>
                <div className="text-ink-3 bg-surface-4 rounded-full p-1.5">
                  <svg 
                    className={`w-5 h-5 transition-transform duration-300 ${isHistoryExpanded ? 'rotate-180' : ''}`} 
                    fill="none" viewBox="0 0 24 24" stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>
              
              {isHistoryExpanded && (
                <div className="p-6 border-t border-surface-4 animate-slide-up">
                  {/* Iteration Graph */}
                  <div className="h-64 w-full mb-8">
                    <h4 className="text-xs font-bold text-ink-3 uppercase tracking-wider mb-4">Quality Score Trajectory</h4>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#2A2A2A" vertical={false} />
                        <XAxis dataKey="name" stroke="#666" tick={{ fill: '#666', fontSize: 12 }} />
                        <YAxis stroke="#666" tick={{ fill: '#666', fontSize: 12 }} domain={[0, 'dataMax + 10']} />
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#1A1A1A', borderColor: '#333', borderRadius: '8px' }}
                          itemStyle={{ color: '#E0E0E0' }}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="score" 
                          stroke="#3B82F6" 
                          strokeWidth={2}
                          dot={(props) => {
                            const { cx, cy, payload } = props;
                            return (
                              <circle 
                                cx={cx} cy={cy} r={4} 
                                fill={payload.kept ? '#10B981' : '#3B82F6'} 
                                stroke="#1A1A1A" strokeWidth={2} 
                                key={`dot-${payload.iteration}`}
                              />
                            );
                          }}
                          activeDot={{ r: 6, fill: '#3B82F6' }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Iteration History List */}
                  <div className="space-y-4">
                    <h4 className="text-xs font-bold text-ink-3 uppercase tracking-wider mb-4">Detailed History</h4>
                    {session.iterations.map((iter, idx) => (
                      <div key={idx} className="bg-surface-0 border border-surface-4 rounded-lg p-4 flex gap-4">
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
                </div>
              )}
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
