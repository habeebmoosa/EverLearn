export default function PipelineCard({ pipeline, isActive, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`text-left p-4 rounded-xl border transition-all duration-200 flex flex-col gap-2 h-full
        ${isActive 
          ? 'bg-brand-500/10 border-brand-500 ring-1 ring-brand-500/50' 
          : 'bg-surface-2 border-surface-4 hover:border-brand-500/50 hover:bg-surface-3'
        }`}
    >
      <div className="flex items-center gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-semibold text-lg
          ${isActive ? 'bg-brand-500 text-white shadow-[0_0_15px_rgba(168,85,247,0.5)]' : 'bg-surface-4 text-ink-1'}`}>
          {pipeline.id.charAt(0).toUpperCase()}
        </div>
        <h3 className={`font-semibold ${isActive ? 'text-brand-400' : 'text-white'}`}>
          {pipeline.name}
        </h3>
      </div>
      <p className="text-sm text-ink-2 line-clamp-2 mt-1">
        {pipeline.description || 'No description available for this pipeline.'}
      </p>
    </button>
  );
}
