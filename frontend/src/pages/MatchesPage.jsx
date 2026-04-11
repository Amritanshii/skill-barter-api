import React, { useEffect, useState } from 'react';
import { matchesAPI } from '../api/client';
import { useToast } from '../components/Toast';
import SkillBadge from '../components/SkillBadge';
import { Loader2, RefreshCw, ArrowLeftRight, CheckCircle, XCircle, Trophy } from 'lucide-react';
import { Link } from 'react-router-dom';

const FILTERS = ['ALL', 'PENDING', 'ACCEPTED', 'COMPLETED', 'REJECTED'];

const STATUS_STYLES = {
  PENDING:   { dot: 'bg-amber-400', badge: 'bg-amber-50 text-amber-700 border-amber-200', label: '⏳ Pending' },
  ACCEPTED:  { dot: 'bg-green-400', badge: 'bg-green-50 text-green-700 border-green-200', label: '✅ Connected' },
  REJECTED:  { dot: 'bg-gray-400', badge: 'bg-gray-50 text-gray-500 border-gray-200', label: '❌ Passed' },
  COMPLETED: { dot: 'bg-blue-400', badge: 'bg-blue-50 text-blue-700 border-blue-200', label: '🏆 Completed' },
};

function MatchRow({ match, onAction }) {
  const [loading, setLoading] = useState(null);
  const toast = useToast();
  const status = match.match_status?.toUpperCase() || 'PENDING';
  const stStyle = STATUS_STYLES[status] || STATUS_STYLES.PENDING;

  const act = async (newStatus) => {
    if (!match.match_id) { toast('Match ID not available yet', 'error'); return; }
    setLoading(newStatus);
    try {
      await matchesAPI.updateStatus(match.match_id, newStatus.toLowerCase());
      toast(newStatus === 'ACCEPTED' ? '🤝 Connected!' : '👋 Passed');
      onAction(match.other_user_id, newStatus);
    } catch (err) {
      toast(err.response?.data?.detail || 'Could not update match', 'error');
    } finally { setLoading(null); }
  };

  return (
    <div className="card p-5">
      <div className="flex items-center gap-4 flex-wrap">
        {/* Avatar */}
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-400 to-pink-400 flex items-center justify-center text-white font-bold text-xl flex-shrink-0">
          {match.other_username?.[0]?.toUpperCase()}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-gray-800">{match.other_full_name || match.other_username}</span>
            <span className="text-gray-400 text-sm">@{match.other_username}</span>
            {match.other_college && <span className="text-xs text-violet-600 font-medium">🎓 {match.other_college}</span>}
          </div>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <SkillBadge name={match.skill_i_offer_name} category={match.skill_i_offer_category} size="sm" />
            <ArrowLeftRight size={14} className="text-gray-400 flex-shrink-0" />
            <SkillBadge name={match.skill_they_offer_name} category={match.skill_they_offer_category} size="sm" />
          </div>
        </div>

        {/* Score */}
        <div className="text-right flex-shrink-0">
          <div className="text-2xl font-black text-violet-600">{Math.round((match.match_score || 0) * 100)}%</div>
          <div className="text-xs text-gray-400">match</div>
        </div>

        {/* Status + actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${stStyle.badge}`}>
            {stStyle.label}
          </span>
          {status === 'PENDING' && (
            <div className="flex gap-2">
              <button onClick={() => act('ACCEPTED')} disabled={!!loading}
                className="flex items-center gap-1 bg-green-500 text-white text-xs font-bold px-3 py-2 rounded-xl hover:bg-green-600 transition-all disabled:opacity-50">
                {loading === 'ACCEPTED' ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={14} />}
                Connect
              </button>
              <button onClick={() => act('REJECTED')} disabled={!!loading}
                className="flex items-center gap-1 bg-gray-100 text-gray-600 text-xs font-bold px-3 py-2 rounded-xl hover:bg-gray-200 transition-all disabled:opacity-50">
                {loading === 'REJECTED' ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={14} />}
                Pass
              </button>
            </div>
          )}
          {status === 'ACCEPTED' && (
            <button onClick={() => act('COMPLETED')} disabled={!!loading}
              className="flex items-center gap-1 bg-blue-500 text-white text-xs font-bold px-3 py-2 rounded-xl hover:bg-blue-600 transition-all disabled:opacity-50">
              {loading === 'COMPLETED' ? <Loader2 size={12} className="animate-spin" /> : <Trophy size={14} />}
              Mark Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function MatchesPage() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('ALL');
  const toast = useToast();

  const load = async (refresh = false) => {
    setLoading(true);
    try {
      const r = await matchesAPI.getMatches(refresh);
      setMatches(r.data.matches || []);
    } catch { toast('Failed to load matches', 'error'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleAction = (userId, newStatus) => {
    setMatches(prev => prev.map(m =>
      m.other_user_id === userId ? { ...m, match_status: newStatus } : m
    ));
  };

  const filtered = filter === 'ALL' ? matches
    : matches.filter(m => (m.match_status || 'PENDING').toUpperCase() === filter);

  const counts = FILTERS.reduce((acc, f) => {
    acc[f] = f === 'ALL' ? matches.length
      : matches.filter(m => (m.match_status || 'PENDING').toUpperCase() === f).length;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black gradient-text">My Matches ✨</h1>
          <p className="text-gray-500 mt-1">Connect, barter, and mark exchanges complete.</p>
        </div>
        <button onClick={() => load(true)} disabled={loading}
          className="btn-secondary flex items-center gap-2 text-sm">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {FILTERS.map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold transition-all border ${
              filter === f ? 'bg-violet-600 text-white border-violet-600' : 'bg-white text-gray-600 border-gray-200 hover:border-violet-300'
            }`}>
            {f} {counts[f] > 0 && <span className={`text-xs px-1.5 py-0.5 rounded-full ${filter === f ? 'bg-white/20 text-white' : 'bg-violet-100 text-violet-700'}`}>{counts[f]}</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><Loader2 size={36} className="animate-spin text-violet-400" /></div>
      ) : filtered.length === 0 ? (
        <div className="card p-16 text-center">
          <div className="text-5xl mb-3">{filter === 'ALL' ? '🔍' : filter === 'ACCEPTED' ? '🤝' : '😶'}</div>
          <h3 className="text-xl font-bold text-gray-700 mb-2">
            {filter === 'ALL' ? 'No matches yet' : `No ${filter.toLowerCase()} matches`}
          </h3>
          <p className="text-gray-500 mb-6">
            {filter === 'ALL'
              ? 'Add skills to your profile and check the Discover page.'
              : 'Try a different filter or refresh your matches.'}
          </p>
          {filter === 'ALL' && (
            <Link to="/discover" className="btn-primary inline-flex items-center gap-2">🔍 Discover Matches</Link>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((m, i) => (
            <MatchRow key={m.other_user_id || i} match={m} onAction={handleAction} />
          ))}
        </div>
      )}
    </div>
  );
}
