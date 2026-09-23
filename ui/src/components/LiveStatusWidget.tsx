import React, { useState } from 'react';
import { GripHorizontal, ChevronDown, ChevronUp, EyeOff } from 'lucide-react';
import { WidgetConfig, LiveState } from '../types';

interface LiveStatusWidgetProps {
  config: WidgetConfig;
  live: LiveState;
  onUpdateConfig: (newConfig: Partial<WidgetConfig>) => void;
}

export const LiveStatusWidget: React.FC<LiveStatusWidgetProps> = ({
  config,
  live,
  onUpdateConfig,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  if (!config.enabled || !config.visible) return null;

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragOffset({
      x: e.clientX - config.x,
      y: e.clientY - config.y,
    });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      onUpdateConfig({
        x: Math.max(10, e.clientX - dragOffset.x),
        y: Math.max(10, e.clientY - dragOffset.y),
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const getBadgeColor = () => {
    switch (live.status_category) {
      case 'good':
        return 'bg-emerald-500 text-white';
      case 'warning':
        return 'bg-amber-500 text-slate-900';
      case 'paused':
        return 'bg-blue-500 text-white';
      default:
        return 'bg-slate-600 text-white';
    }
  };

  return (
    <div
      style={{
        left: `${config.x}px`,
        top: `${config.y}px`,
        opacity: config.opacity,
      }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      className={`fixed z-50 select-none backdrop-blur-md border rounded-xl shadow-2xl transition-opacity ${
        live.status_category === 'warning'
          ? 'border-amber-500/50 bg-slate-900/90'
          : 'border-slate-700 bg-slate-900/90'
      }`}
    >
      {/* Drag handle / Titlebar */}
      <div
        onMouseDown={handleMouseDown}
        className="px-3 py-1.5 bg-slate-800/80 rounded-t-xl cursor-move flex items-center justify-between border-b border-slate-700/50"
      >
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-300">
          <GripHorizontal className="w-3.5 h-3.5 text-slate-400" />
          <span>DeskSense Widget</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onUpdateConfig({ collapsed: !config.collapsed })}
            className="p-0.5 hover:bg-slate-700 rounded text-slate-400 hover:text-slate-200"
            title={config.collapsed ? 'Expand' : 'Collapse'}
          >
            {config.collapsed ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
          </button>
          <button
            onClick={() => onUpdateConfig({ visible: false })}
            className="p-0.5 hover:bg-slate-700 rounded text-slate-400 hover:text-slate-200"
            title="Hide widget"
          >
            <EyeOff className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Widget Body */}
      <div className="p-3">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${getBadgeColor()}`} />
          <span className="text-xs font-bold text-white tracking-tight">
            {live.status_label}
          </span>
        </div>

        {!config.collapsed && (
          <div className="mt-2 text-[11px] text-slate-300 space-y-1 font-mono">
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Session:</span>
              <span>{live.session_duration_formatted}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Attention:</span>
              <span>{live.attention}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
