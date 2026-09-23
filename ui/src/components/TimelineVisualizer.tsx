import React, { useState } from 'react';
import { TimelineSegment } from '../types';

interface TimelineVisualizerProps {
  timeline?: TimelineSegment[];
}

export const TimelineVisualizer: React.FC<TimelineVisualizerProps> = ({ timeline = [] }) => {
  const [hoveredSegment, setHoveredSegment] = useState<TimelineSegment | null>(null);

  if (!timeline || timeline.length === 0) {
    return (
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 backdrop-blur-md mb-6 shadow-xl">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-2">Workday Timeline</h3>
        <p className="text-xs text-slate-500">No activity segments recorded yet for today.</p>
      </div>
    );
  }

  const totalDuration = timeline.reduce((acc, s) => acc + s.duration, 0) || 1;

  const formatSec = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    if (m >= 60) {
      const h = Math.floor(m / 60);
      return `${h}h ${m % 60}m`;
    }
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 backdrop-blur-md mb-6 shadow-xl">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Workday Ribbon Timeline</h3>
          <p className="text-xs text-slate-400">Continuous transitions between Deep Focus, Active Work, Phone, Breaks, and Away</p>
        </div>
        {hoveredSegment && (
          <div className="text-xs px-3 py-1 bg-slate-800/90 border border-slate-700 rounded-lg flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: hoveredSegment.color }} />
            <span className="font-semibold text-slate-200">{hoveredSegment.label}</span>
            <span className="text-slate-400">({hoveredSegment.start_time_str} - {hoveredSegment.end_time_str})</span>
            <span className="text-emerald-400 font-mono font-medium">{formatSec(hoveredSegment.duration)}</span>
          </div>
        )}
      </div>

      {/* Ribbon Bar */}
      <div className="relative w-full h-8 bg-slate-950 rounded-xl overflow-hidden flex border border-slate-800/80 shadow-inner">
        {timeline.map((seg, idx) => {
          const widthPct = Math.max(0.5, (seg.duration / totalDuration) * 100);
          return (
            <div
              key={idx}
              className="h-full cursor-pointer transition-opacity hover:opacity-80 relative group"
              style={{
                width: `${widthPct}%`,
                backgroundColor: seg.color,
              }}
              onMouseEnter={() => setHoveredSegment(seg)}
              onMouseLeave={() => setHoveredSegment(null)}
              tabIndex={0}
              role="button"
              aria-label={`${seg.label}: ${seg.start_time_str} to ${seg.end_time_str}`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 mt-3 pt-2 border-t border-slate-800/50 text-xs text-slate-400">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" />
          <span>Deep Focus</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#3b82f6]" />
          <span>Active Work</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]" />
          <span>Phone (Estimated)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#8b5cf6]" />
          <span>Break</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#64748b]" />
          <span>Away</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#94a3b8]" />
          <span>Idle</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#334155]" />
          <span>Unmonitored</span>
        </div>
      </div>
    </div>
  );
};
