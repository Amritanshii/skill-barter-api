import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { usersAPI, matchesAPI } from '../api/client';
import SkillBadge from '../components/SkillBadge';
import { Sparkles, BookOpen, Target, ArrowRight, Trophy, Zap } from 'lucide-react';

function StatCard({ icon, label, value, color }) {
  return (
    <div className={`card p-5 flex items-center gap-4 border-l-4 ${color}`}>
      <div className="text-3xl">{icon}</div>
      <div>
        <div className="text-3xl font-black text-gray-800">{value}</div>
        <div className="text-sm font-medium text-gray-500">{label}</div>
      </div>
    </div>
  );
}

function MatchPreviewCard({ match }) {
  const score = Math.round((match.match_score || 0) * 100);
  const scoreColor = score >= 70 ? 'text-green-600 bg-green-50 border-green-200'
    : score >= 40 ? 'text-amber-600 bg-amber-50 border-amber-200'
    : 'text-violet-600 bg-violet-50 border-violet-200';

  return (
    <div className="card p-4 flex items-center gap-4">
      <div className="w-11 h-11 rounded-full bg-gradient-to-br from-violet-400 to-pink-400 flex items-center justify-center text-white font-bold text-lg flex-shrink-0">
        {match.other_username?.[0]?.toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-gray-800 truncate">{match.other_full_name || match.other_username}</div>
        <div className="text-xs text-gray-500">{match.other_college}</div>
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          <SkillBadge name={match.skill_i_offer_name} category={match.skill_i_offer_category} size="sm" />
          <span className="text-gray-400 text-xs">↔</span>
          <SkillBadge name={match.skill_they_offer_name} category={match.skill_they_offer_category} size="sm" />
        </div>
      </div>
      <span className={`text-sm font-bold px-2.5 py-1 rounded-full border flex-shrink-0 ${scoreColor}`}>
        {score}%
      </span>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [matches, setMatches] = useState([]);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [loadingMatches, setLoadingMatches] = useState(true);

  useEffect(() => {
    usersAPI.getProfile()
      .then(r => setProfile(r.data))
      .finally(() => setLoadingProfile(false));
    matchesAPI.getMatches()
      .then(r => setMatches(r.data.matches || []))
      .finally(() => setLoadingMatches(false));
  }, []);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? '☀️ Good morning' : hour < 18 ? '👋 Hey' : '🌙 Good evening';
  const name = user?.full_name?.split(' ')[0] || user?.username || 'there';

  return (
    <div className="space-y-8">
      {/* Hero greeting */}
      <div className="bg-gradient-to-r from-violet-600 to-pink-500 rounded-3xl p-8 text-white relative overflow-hidden">
        <div className="absolute inset-0 opacity-10 text-9xl flex items-center justify-end pr-8 pointer-events-none">🔄</div>
        <h1 className="text-3xl font-black">{greeting}, {name}! 🎉</h1>
        <p className="mt-2 text-violet-100 text-lg">
          {matches.length > 0
            ? `You have ${matches.length} skill match${matches.length !== 1 ? 'es' : ''} waiting for you.`
            : 'Add skills to start discovering your matches.'}
        </p>
        <div className="mt-5 flex gap-3 flex-wrap">
          <Link to="/discover" className="flex items-center gap-2 bg-white text-violet-700 font-bold px-5 py-2.5 rounded-xl text-sm hover:bg-violet-50 transition-all shadow-md">
            <Sparkles size={16} /> Discover Matches
          </Link>
          <Link to="/skills" className="flex items-center gap-2 bg-white/20 text-white font-semibold px-5 py-2.5 rounded-xl text-sm hover:bg-white/30 transition-all border border-white/30">
            <BookOpen size={16} /> Manage Skills
          </Link>
        </div>
      </div>

      {/* Stats */}
      {!loadingProfile && profile && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard icon="🎯" label="Skill Matches" value={matches.length} color="border-violet-500" />
          <StatCard icon="🎓" label="Skills I Teach" value={profile.offered_skills?.length || 0} color="border-pink-500" />
          <StatCard icon="📚" label="Skills I Want" value={profile.wanted_skills?.length || 0} color="border-amber-500" />
        </div>
      )}

      {/* Skills summary */}
      {!loadingProfile && profile && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold text-gray-800 flex items-center gap-2"><Trophy size={18} className="text-amber-500"/>I Can Teach</h2>
              <Link to="/skills" className="text-sm text-violet-600 hover:text-violet-800 font-medium flex items-center gap-1">
                Edit <ArrowRight size={14}/>
              </Link>
            </div>
            {profile.offered_skills?.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {profile.offered_skills.map(s => (
                  <SkillBadge key={s.id} name={s.skill.name} category={s.skill.category} />
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-gray-400">
                <div className="text-4xl mb-2">🎓</div>
                <p className="text-sm">No skills added yet</p>
                <Link to="/skills" className="text-violet-600 text-sm font-medium hover:underline">Add your first skill →</Link>
              </div>
            )}
          </div>
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold text-gray-800 flex items-center gap-2"><Target size={18} className="text-violet-500"/>I Want to Learn</h2>
              <Link to="/skills" className="text-sm text-violet-600 hover:text-violet-800 font-medium flex items-center gap-1">
                Edit <ArrowRight size={14}/>
              </Link>
            </div>
            {profile.wanted_skills?.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {profile.wanted_skills.map(s => (
                  <SkillBadge key={s.id} name={s.skill.name} category={s.skill.category} />
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-gray-400">
                <div className="text-4xl mb-2">📚</div>
                <p className="text-sm">No learning goals yet</p>
                <Link to="/skills" className="text-violet-600 text-sm font-medium hover:underline">Add what you want to learn →</Link>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Recent matches preview */}
      {!loadingMatches && matches.length > 0 && (
        <div className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-gray-800 flex items-center gap-2"><Zap size={18} className="text-pink-500"/>Top Matches</h2>
            <Link to="/discover" className="text-sm text-violet-600 hover:text-violet-800 font-medium flex items-center gap-1">
              See all <ArrowRight size={14}/>
            </Link>
          </div>
          <div className="space-y-3">
            {matches.slice(0, 3).map((m, i) => <MatchPreviewCard key={i} match={m} />)}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loadingProfile && !loadingMatches && matches.length === 0 && profile && (
        <div className="card p-12 text-center">
          <div className="text-6xl mb-4">🔍</div>
          <h3 className="text-xl font-bold text-gray-700 mb-2">No matches yet!</h3>
          <p className="text-gray-500 mb-6">Add skills you can teach and skills you want to learn to find your perfect study buddies.</p>
          <Link to="/skills" className="btn-primary inline-flex items-center gap-2">
            <BookOpen size={18}/> Add Skills Now
          </Link>
        </div>
      )}
    </div>
  );
}
