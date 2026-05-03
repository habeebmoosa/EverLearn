import { useState, useEffect } from 'react';

export default function TaskForm({ pipelines, selectedPipelineId, onSubmit }) {
  const [label, setLabel] = useState('');
  const [inputs, setInputs] = useState({});
  const [dataSourcesText, setDataSourcesText] = useState('');
  const [depth, setDepth] = useState('standard');
  const [webSearch, setWebSearch] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Reset form when pipeline changes
  useEffect(() => {
    setLabel('');
    setInputs({});
    setDataSourcesText('');
  }, [selectedPipelineId]);

  const activePipeline = pipelines.find(p => p.id === selectedPipelineId);
  const schema = activePipeline?.input_schema?.properties || {};
  const config = activePipeline?.display_config || {};

  const handleInputChange = (key, value) => {
    setInputs(prev => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!label.trim() || isSubmitting) return;

    setIsSubmitting(true);
    
    // Parse data sources
    const dataSources = [];
    if (dataSourcesText.trim()) {
      const isUrl = /^(https?:\/\/)/i.test(dataSourcesText.trim());
      dataSources.push({
        type: isUrl ? 'url' : 'text',
        content: dataSourcesText.trim(),
        label: isUrl ? 'Source URL' : 'Provided Text'
      });
    }

    const payload = {
      pipeline_id: selectedPipelineId,
      label: label.trim(),
      inputs: {
        ...inputs,
        enable_web_search: webSearch
      },
      data_sources: dataSources,
      config: {
        depth: depth,
        max_iterations: config.max_iterations_default || 5,
        max_iteration_timeout: 180
      }
    };

    try {
      await onSubmit(payload);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto w-full pt-12 pb-24 px-6 animate-fade-in">
      <div className="text-center mb-10">
        <div className="inline-block p-4 rounded-2xl bg-surface-2 border border-surface-4 mb-4 shadow-lg">
          <svg className="w-10 h-10 text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <h1 className="text-4xl font-bold text-white mb-3 tracking-tight">
          {activePipeline ? activePipeline.name : 'Select an Agent'}
        </h1>
        <p className="text-ink-2 text-lg">
          {activePipeline ? activePipeline.description || 'Configure and start a new task.' : 'Please select an agent from the sidebar.'}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">

        {activePipeline && (
          <div className="bg-surface-2 border border-surface-4 rounded-xl p-6 space-y-6 animate-slide-up">
            
            {/* Primary Input (Label) */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">
                {schema.label?.title || 'Task Description'}
              </label>
              <textarea
                value={label}
                onChange={e => setLabel(e.target.value)}
                placeholder={config.label_placeholder || 'Describe what you want the agent to do...'}
                className="w-full bg-surface-1 border border-surface-4 rounded-lg p-4 text-white placeholder-ink-3 focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500 transition-all resize-none min-h-[100px]"
                required
              />
            </div>

            {/* Dynamic Inputs from Schema */}
            {Object.entries(schema).filter(([key]) => key !== 'label').length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-surface-4">
                {Object.entries(schema).filter(([key]) => key !== 'label').map(([key, field]) => (
                  <div key={key} className="space-y-2">
                    <label className="block text-sm font-medium text-white">{field.title || key}</label>
                    {field.enum ? (
                      <select
                        value={inputs[key] || field.default || ''}
                        onChange={e => handleInputChange(key, e.target.value)}
                        className="w-full bg-surface-1 border border-surface-4 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500 outline-none appearance-none"
                      >
                        {field.enum.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={inputs[key] || field.default || ''}
                        onChange={e => handleInputChange(key, e.target.value)}
                        placeholder={field.description || ''}
                        className="w-full bg-surface-1 border border-surface-4 rounded-lg px-4 py-2.5 text-white placeholder-ink-3 focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500 outline-none"
                      />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Data Sources (if configured) */}
            {config.show_data_sources !== false && (
              <div className="space-y-2 pt-4 border-t border-surface-4">
                <label className="block text-sm font-medium text-white">Provide Reference Material (Optional)</label>
                <textarea
                  value={dataSourcesText}
                  onChange={e => setDataSourcesText(e.target.value)}
                  placeholder="Paste context, code, URLs, or reference material here..."
                  className="w-full bg-surface-1 border border-surface-4 rounded-lg p-4 text-white placeholder-ink-3 focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500 transition-all resize-y min-h-[100px] font-mono text-sm"
                />
              </div>
            )}

            {/* Config & Submission */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-6 border-t border-surface-4">
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <label className="text-sm font-medium text-ink-2">Depth</label>
                  <select
                    value={depth}
                    onChange={e => setDepth(e.target.value)}
                    className="bg-surface-1 border border-surface-4 rounded-md px-2 py-1 text-sm text-white focus:ring-1 focus:ring-brand-500 outline-none"
                  >
                    {(config.depth_options || ['quick', 'standard', 'deep']).map(opt => (
                      <option key={opt} value={opt}>{opt.charAt(0).toUpperCase() + opt.slice(1)}</option>
                    ))}
                  </select>
                </div>
                
                {config.show_web_search !== false && (
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={webSearch}
                      onChange={e => setWebSearch(e.target.checked)}
                      className="sr-only"
                    />
                    <div className={`w-10 h-5 rounded-full transition-colors relative ${webSearch ? 'bg-brand-500' : 'bg-surface-4'}`}>
                      <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${webSearch ? 'translate-x-5' : 'translate-x-0'}`} />
                    </div>
                    <span className="text-sm font-medium text-ink-2 group-hover:text-white transition-colors">Web Search</span>
                  </label>
                )}
              </div>

              <button
                type="submit"
                disabled={!label.trim() || isSubmitting}
                className="bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-8 rounded-lg shadow-lg shadow-brand-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-95 flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                    <span>Starting...</span>
                  </>
                ) : (
                  <>
                    <span>Start Agent</span>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                  </>
                )}
              </button>
            </div>

          </div>
        )}
      </form>
    </div>
  );
}
