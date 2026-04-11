import React from 'react';

export const CATEGORY_CONFIG = {
  programming:  { emoji: '💻', color: 'bg-indigo-100 text-indigo-700 border-indigo-200' },
  design:       { emoji: '🎨', color: 'bg-pink-100 text-pink-700 border-pink-200' },
  music:        { emoji: '🎵', color: 'bg-orange-100 text-orange-700 border-orange-200' },
  languages:    { emoji: '🗣️', color: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  mathematics:  { emoji: '🔢', color: 'bg-violet-100 text-violet-700 border-violet-200' },
  science:      { emoji: '🔬', color: 'bg-teal-100 text-teal-700 border-teal-200' },
  sports:       { emoji: '⚽', color: 'bg-green-100 text-green-700 border-green-200' },
  cooking:      { emoji: '🍳', color: 'bg-amber-100 text-amber-700 border-amber-200' },
  arts:         { emoji: '🖼️', color: 'bg-rose-100 text-rose-700 border-rose-200' },
  writing:      { emoji: '✍️', color: 'bg-blue-100 text-blue-700 border-blue-200' },
  marketing:    { emoji: '📢', color: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  finance:      { emoji: '💰', color: 'bg-lime-100 text-lime-700 border-lime-200' },
  other:        { emoji: '✨', color: 'bg-gray-100 text-gray-700 border-gray-200' },
};

export default function SkillBadge({ name, category, size = 'md' }) {
  const cfg = CATEGORY_CONFIG[category?.toLowerCase()] || CATEGORY_CONFIG.other;
  const sz = size === 'sm' ? 'text-xs px-2 py-0.5' : size === 'lg' ? 'text-base px-4 py-2' : 'text-sm px-3 py-1';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${cfg.color} ${sz}`}>
      <span>{cfg.emoji}</span>{name}
    </span>
  );
}
