import React, { useEffect, useState } from 'react';
import { matchesAPI } from '../api/client';
import { useToast } from '../components/Toast';
import SkillBadge from '../components/SkillBadge';
import { RefreshCw, Loader2, Users, ArrowLeftRight } from 'lucide-react';

const STATUS_CONFIG = {
  PENDING:   { label: 'Connect', cls: 'btn-primary text-sm py-2 px-4', action: 'ACCEPTED' },
  ACCEPTED:  { label: '✅ Connected', cls: 'bg-green-100 text-green-700 border border-green-200 font-semibold py-2 px-4 rounded-xl text-sm', action: null },
  REJECTED:  { label: '❌ Passed', cls: 'bg-gray-100 text-gray-500 border border-gray-200 font-medium py-2 px-4 rounded-xl text-sm', action: null },
  COMPLETED: { label: '🏆 Done', cls: 'bg-amber-100 text-amber-700 border border-amber-200 font-semibold py-2 px-4 rounded-xl text-sm', action: null },
};

function MatchCard({ match, onStatusChange }) {
  const [loading, setLoading] = useState(false);
  const toast = useToast();
  const score = Math.round((match.match_score || 0) * 100);
  const status = match.match_status?.toUpperCase() || 'PENDING';
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.PENDING;

  const handleConnect = async () => {
    if (!match.match_id || !cfg.action) return;
    setLoading(true);
    try {
      await matchesAPI.updateStatus(match.match_id, cfg.action.toLowerCase());
      toast(`Connected with ${match.other_username}! 🎉`);
      onStatusChange(match.other_user_id, cfg.action);
    } catch (err) {
      toast(err.response?.data?.detail || 'Could not update match', 'error');
    } finally { setLoading(false); }
  };

  const scoreColor = score >= 70 ? 'from-green-400 to-emerald-500'
    : score >= 40 ? 'from-amber-400 to-orange-400'
    : 'from-violet-400 to-pink-400';

  return (
    <div className="card p-6 hover:scale-[1.01] transition-transform duration-200">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-400 to-pink-400 flex items-center justify-center text-white font-bold text-xl flex-shrink-0">
            {match.other_username?.[0]?.toUpperCase()}
          </div>
          <div>
            <div className="font-bold text-gray-900 text-base">{match.other_full_name || match.other_username}</div>
            <div className="text-sm text-gray-500">@{match.other_username}</div>
            {match.other_college && (
              <div className="text-xs text-violet-600 font-medium mt-0.5">🎓 {match.other_college}</div>
            )}
          </div>
        </div>
        {/* Score ring */}
        <div className={`flex-shrink-0 w-14 h-14 rounded-2xl bg-gradient-to-br ${scoreColor} flex flex-col items-center justify-center text-white shadow-md`}>
          <div className="text-lg font-black leading-none">{score}</div>
          <div className="text-xs opacity-80">match</div>
        </div>
      </div>

      {/* Skill exchange */}
      <div className="bg-gradient-to-r from-violet-50 to-pink-50 rounded-2xl p-4 mb-4 border border-violet-100">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">You teach</div>
            <SkillBadge name={match.skill_i_offer_name} category={match.skill_i_offer_category} />
          </div>
          <div className="flex-shrink-0">
            <ArrowLeftRight size={20} className="text-violet-400" />
          </div>
          <div className="flex-1 min-w-0 text-right">
            <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">They teach</div>
            <SkillBadge name={match.skill_they_offer_name} category={match.skill_they_offer_category} />
          </div>
        </div>
      </div>

      {/* Action */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">
          {match.match_id ? `ID: ${match.match_id.slice(0,8)}…` : 'Computing…'}
        </div>
        {cfg.action ? (
          <button onClick={handleConnect} disabled={loading || !match.match_id} className={cfg.cls + ' flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed'}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : '🤝'}
            {loading ? 'Connecting…' : cfg.label}
          </button>
        ) : (
          <span className={cfg.cls}>{cfg.label}</span>
        )}
      </div>
    </div>
  );
}

export default function DiscoverPage() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cached, setCached] = useState(false);
  const toast = useToast();

  const load = async (forceRefresh = false) => {
    forceRefresh ? setRefreshing(true) : setLoading(true);
    try {
      const r = await matchesAPI.getMatches(forceRefresh);
      setMatches(r.data.matches || []);
      setCached(r.data.cached);
      if (forceRefresh) toast('Matches refreshed! ✨');
    } catch {
      toast('Failed to load matches', 'error');
    } finally { setLoading(false); setRefreshing(false); }
  };

  useEffect(() => { load(); }, []);

  const handleStatusChange = (userId, newStatus) => {
    setMatches(prev => prev.map(m =>
      m.other_user_id === userId ? { ...m, match_status: newStatus } : m
    ));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black gradient-text">Discover Matches 🔍</h1>
          <p className="text-gray-500 mt-1">People who can teach you something — and want to learn from you too.</p>
        </div>
        <button onClick={() => load(true)} disabled={refreshing || loading}
          className="btn-secondary flex items-center gap-2 text-sm">
          <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Cache badge */}
      {!loading && (
        <div className="flex items-center gap-3">
          <span className={`text-xs px-3 py-1 rounded-full font-medium border ${cached ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-green-50 text-green-700 border-green-200'}`}>
            {cached ? '⚡ Cached results' : '🔄 Fresh results'}
          </span>
          <span className="text-sm text-gray-500">{matches.length} match{matches.length !== 1 ? 'es' : ''} found</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-center space-y-3">
            <Loader2 size={40} className="animate-spin text-violet-400 mx-auto" />
            <p className="text-gray-500">Computing your matches…</p>
          </div>
        </div>
      ) : matches.length === 0 ? (
        <div className="card p-16 text-center">
          <div className="text-6xl mb-4">🤔</div>
          <h3 className="text-xl font-bold text-gray-700 mb-2">No matches yet</h3>
          <p className="text-gray-500">Add more skills to your profile to find people to barter with.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-5">
          {matches.map((m, i) => (
            <MatchCard key={m.other_user_id || i} match={m} onStatusChange={handleStatusChange} />
          ))}
        </div>
      )}
    </div>
  );
}
