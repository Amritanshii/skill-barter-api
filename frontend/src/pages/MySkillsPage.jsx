import React, { useEffect, useState, useRef } from 'react';
import { usersAPI, skillsAPI } from '../api/client';
import { useToast } from '../components/Toast';
import SkillBadge from '../components/SkillBadge';
import { Plus, Trash2, Loader2, ChevronDown } from 'lucide-react';

const PROFICIENCY = ['beginner', 'intermediate', 'expert'];
const URGENCY = ['low', 'medium', 'high'];
const PROF_EMOJI = { beginner: '🌱', intermediate: '⚡', expert: '🔥' };
const URG_EMOJI = { low: '😌', medium: '🙏', high: '🚨' };

const CATEGORIES = ['programming','design','music','languages','mathematics','science','sports','cooking','arts','writing','marketing','finance','other'];

function SkillAutocomplete({ onSelect, placeholder }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newCategory, setNewCategory] = useState('other');
  const [showCreate, setShowCreate] = useState(false);
  const ref = useRef();
  const toast = useToast();

  useEffect(() => {
    if (query.length < 1) { setResults([]); setShowCreate(false); return; }
    setLoading(true);
    const t = setTimeout(() => {
      skillsAPI.autocomplete(query)
        .then(r => {
          setResults(r.data || []);
          setShowCreate(r.data?.length === 0);
          setOpen(true);
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const res = await skillsAPI.create({ name: query, category: newCategory });
      onSelect(res.data);
      toast(`Created new skill: ${query} ✨`);
      setOpen(false); setShowCreate(false);
    } catch (err) {
      toast(err.response?.data?.detail || 'Could not create skill', 'error');
    } finally { setCreating(false); }
  };

  return (
    <div className="relative" ref={ref}>
      <div className="relative">
        <input className="input-field pr-10" placeholder={placeholder} value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => query && setOpen(true)} />
        {loading
          ? <Loader2 size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-violet-400 animate-spin" />
          : <ChevronDown size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400" />
        }
      </div>
      {open && (results.length > 0 || showCreate) && (
        <div className="absolute z-20 w-full mt-1 bg-white border border-violet-100 rounded-xl shadow-lg overflow-hidden">
          {results.map(skill => (
            <button key={skill.id} type="button"
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-violet-50 text-left transition-colors"
              onMouseDown={() => { onSelect(skill); setQuery(skill.name); setOpen(false); }}>
              <SkillBadge name={skill.name} category={skill.category} size="sm" />
            </button>
          ))}
          {showCreate && query.length > 1 && (
            <div className="border-t border-violet-100 p-3 space-y-2">
              <p className="text-xs text-gray-500 font-medium">No results — create <span className="text-violet-600 font-bold">"{query}"</span> as a new skill:</p>
              <select value={newCategory} onChange={e => setNewCategory(e.target.value)}
                className="w-full text-sm border border-violet-100 rounded-lg px-3 py-1.5 outline-none focus:border-violet-400">
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <button type="button" onMouseDown={handleCreate} disabled={creating}
                className="w-full bg-violet-600 text-white text-sm font-semibold py-2 rounded-lg hover:bg-violet-700 transition-all flex items-center justify-center gap-2 disabled:opacity-50">
                {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                {creating ? 'Creating…' : `Create "${query}"`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AddOfferedForm({ onAdded }) {
  const [skill, setSkill] = useState(null);
  const [proficiency, setProficiency] = useState('intermediate');
  const [years, setYears] = useState('');
  const [desc, setDesc] = useState('');
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!skill) { toast('Pick a skill first', 'error'); return; }
    setLoading(true);
    try {
      await usersAPI.addOffered({ skill_id: skill.id, proficiency_level: proficiency, years_experience: years ? parseFloat(years) : null, description: desc || null });
      toast(`Added ${skill.name} to your teaching skills! 🎓`);
      setSkill(null); setYears(''); setDesc(''); setProficiency('intermediate');
      onAdded();
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to add skill', 'error');
    } finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="card p-5 space-y-4 border-2 border-dashed border-violet-200 bg-violet-50/30">
      <h3 className="font-bold text-gray-700 flex items-center gap-2"><Plus size={18} className="text-violet-500"/>Add a skill I can teach</h3>
      <SkillAutocomplete onSelect={setSkill} placeholder="Type to search skills… e.g. Python" />
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-gray-500 mb-1.5">Proficiency</label>
          <div className="flex gap-2">
            {PROFICIENCY.map(p => (
              <button key={p} type="button" onClick={() => setProficiency(p)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-all ${proficiency === p ? 'bg-violet-600 text-white border-violet-600' : 'bg-white text-gray-600 border-gray-200 hover:border-violet-300'}`}>
                {PROF_EMOJI[p]}
              </button>
            ))}
          </div>
          <div className="text-center text-xs text-gray-500 mt-1 capitalize">{PROF_EMOJI[proficiency]} {proficiency}</div>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-500 mb-1.5">Years experience</label>
          <input type="number" step="0.5" min="0" max="50" placeholder="e.g. 2" value={years}
            onChange={e => setYears(e.target.value)} className="input-field text-sm py-2" />
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1.5">Description (optional)</label>
        <input className="input-field text-sm py-2" placeholder="e.g. 3 years Django, 5 deployed projects" value={desc} onChange={e => setDesc(e.target.value)} />
      </div>
      <button type="submit" disabled={!skill || loading} className="btn-primary w-full flex items-center justify-center gap-2 text-sm">
        {loading ? <><Loader2 size={16} className="animate-spin"/>Adding…</> : '✨ Add Skill'}
      </button>
    </form>
  );
}

function AddWantedForm({ onAdded }) {
  const [skill, setSkill] = useState(null);
  const [urgency, setUrgency] = useState('medium');
  const [desc, setDesc] = useState('');
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!skill) { toast('Pick a skill first', 'error'); return; }
    setLoading(true);
    try {
      await usersAPI.addWanted({ skill_id: skill.id, urgency, description: desc || null });
      toast(`Added ${skill.name} to your learning goals! 📚`);
      setSkill(null); setDesc(''); setUrgency('medium');
      onAdded();
    } catch (err) {
      toast(err.response?.data?.detail || 'Failed to add skill', 'error');
    } finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="card p-5 space-y-4 border-2 border-dashed border-pink-200 bg-pink-50/30">
      <h3 className="font-bold text-gray-700 flex items-center gap-2"><Plus size={18} className="text-pink-500"/>Add a skill I want to learn</h3>
      <SkillAutocomplete onSelect={setSkill} placeholder="Type to search… e.g. Figma" />
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1.5">Urgency</label>
        <div className="flex gap-2">
          {URGENCY.map(u => (
            <button key={u} type="button" onClick={() => setUrgency(u)}
              className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-all capitalize ${urgency === u ? 'bg-pink-500 text-white border-pink-500' : 'bg-white text-gray-600 border-gray-200 hover:border-pink-300'}`}>
              {URG_EMOJI[u]} {u}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-gray-500 mb-1.5">Why you want it (optional)</label>
        <input className="input-field text-sm py-2" placeholder="e.g. Need React for my final year project" value={desc} onChange={e => setDesc(e.target.value)} />
      </div>
      <button type="submit" disabled={!skill || loading} className="btn-primary w-full flex items-center justify-center gap-2 text-sm" style={{background:'linear-gradient(to right,#ec4899,#f97316)'}}>
        {loading ? <><Loader2 size={16} className="animate-spin"/>Adding…</> : '🎯 Add Goal'}
      </button>
    </form>
  );
}

export default function MySkillsPage() {
  const [offered, setOffered] = useState([]);
  const [wanted, setWanted] = useState([]);
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState(null);
  const toast = useToast();

  const loadSkills = async () => {
    try {
      const [o, w] = await Promise.all([usersAPI.getOffered(), usersAPI.getWanted()]);
      setOffered(o.data || []);
      setWanted(w.data || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { loadSkills(); }, []);

  const removeOffered = async (id) => {
    setRemovingId(id);
    try {
      await usersAPI.removeOffered(id);
      setOffered(p => p.filter(s => s.id !== id));
      toast('Skill removed');
    } catch { toast('Failed to remove skill', 'error'); }
    finally { setRemovingId(null); }
  };

  const removeWanted = async (id) => {
    setRemovingId(id);
    try {
      await usersAPI.removeWanted(id);
      setWanted(p => p.filter(s => s.id !== id));
      toast('Goal removed');
    } catch { toast('Failed to remove goal', 'error'); }
    finally { setRemovingId(null); }
  };

  if (loading) return (
    <div className="flex justify-center py-24"><Loader2 size={36} className="animate-spin text-violet-400" /></div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black gradient-text">My Skills 🎒</h1>
        <p className="text-gray-500 mt-1">Manage what you teach and what you want to learn.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* I Teach */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-500 flex items-center justify-center text-white text-sm">🎓</div>
            <h2 className="text-xl font-black text-gray-800">Skills I Can Teach</h2>
            <span className="bg-violet-100 text-violet-700 text-xs font-bold px-2 py-0.5 rounded-full">{offered.length}</span>
          </div>

          <AddOfferedForm onAdded={loadSkills} />

          <div className="space-y-3">
            {offered.length === 0 ? (
              <div className="card p-8 text-center text-gray-400">
                <div className="text-4xl mb-2">🤷</div>
                <p className="text-sm">No teaching skills yet. Add one above!</p>
              </div>
            ) : offered.map(s => (
              <div key={s.id} className="card p-4 flex items-center gap-3">
                <SkillBadge name={s.skill.name} category={s.skill.category} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-500 capitalize">
                      {PROF_EMOJI[s.proficiency_level?.toLowerCase()]} {s.proficiency_level?.toLowerCase()}
                    </span>
                    {s.years_experience && (
                      <span className="text-xs text-gray-400">· {s.years_experience}y</span>
                    )}
                  </div>
                  {s.description && <div className="text-xs text-gray-400 truncate mt-0.5">{s.description}</div>}
                </div>
                <button onClick={() => removeOffered(s.id)} disabled={removingId === s.id}
                  className="text-gray-300 hover:text-red-500 transition-colors flex-shrink-0 p-1 rounded-lg hover:bg-red-50 disabled:opacity-50">
                  {removingId === s.id ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* I Want to Learn */}
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-pink-500 to-orange-400 flex items-center justify-center text-white text-sm">📚</div>
            <h2 className="text-xl font-black text-gray-800">Skills I Want to Learn</h2>
            <span className="bg-pink-100 text-pink-700 text-xs font-bold px-2 py-0.5 rounded-full">{wanted.length}</span>
          </div>

          <AddWantedForm onAdded={loadSkills} />

          <div className="space-y-3">
            {wanted.length === 0 ? (
              <div className="card p-8 text-center text-gray-400">
                <div className="text-4xl mb-2">🌟</div>
                <p className="text-sm">No learning goals yet. What do you want to learn?</p>
              </div>
            ) : wanted.map(s => (
              <div key={s.id} className="card p-4 flex items-center gap-3">
                <SkillBadge name={s.skill.name} category={s.skill.category} />
                <div className="flex-1 min-w-0">
                  <span className="text-xs font-medium text-gray-500 capitalize">
                    {URG_EMOJI[s.urgency?.toLowerCase()]} {s.urgency?.toLowerCase()} urgency
                  </span>
                  {s.description && <div className="text-xs text-gray-400 truncate mt-0.5">{s.description}</div>}
                </div>
                <button onClick={() => removeWanted(s.id)} disabled={removingId === s.id}
                  className="text-gray-300 hover:text-red-500 transition-colors flex-shrink-0 p-1 rounded-lg hover:bg-red-50 disabled:opacity-50">
                  {removingId === s.id ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
