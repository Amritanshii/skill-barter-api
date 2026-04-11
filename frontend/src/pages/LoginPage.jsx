import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Eye, EyeOff, Loader2 } from 'lucide-react';

const skills = ['Python 💻','Figma 🎨','Guitar 🎵','Spanish 🗣️','React ⚛️','Piano 🎹','Calculus 🔢','Photoshop 🖼️'];

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState('login');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [loginForm, setLoginForm] = useState({ identifier: '', password: '' });
  const [regForm, setRegForm] = useState({ email: '', username: '', password: '', full_name: '', college: '' });

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await login(loginForm.identifier, loginForm.password);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check your credentials.');
    } finally { setLoading(false); }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await register(regForm);
      navigate('/');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail[0]?.msg : (detail || 'Registration failed.'));
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left panel */}
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-gradient-to-br from-violet-600 via-purple-600 to-pink-500 p-12 text-white">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center text-2xl">🔄</div>
          <span className="text-2xl font-extrabold tracking-tight">SkillBarter</span>
        </div>
        <div className="space-y-6">
          <h1 className="text-5xl font-black leading-tight">
            Trade Skills,<br/>Not Money 🎉
          </h1>
          <p className="text-xl text-violet-100 leading-relaxed">
            Connect with students who have what you want to learn — and want what you can teach.
          </p>
          <div className="flex flex-wrap gap-2">
            {skills.map(s => (
              <span key={s} className="bg-white/20 backdrop-blur-sm px-3 py-1.5 rounded-full text-sm font-medium border border-white/20">
                {s}
              </span>
            ))}
          </div>
        </div>
        <p className="text-violet-200 text-sm">Built for college students. Free forever.</p>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-8 bg-gradient-to-br from-violet-50 to-pink-50">
        <div className="w-full max-w-md">
          <div className="card p-8">
            {/* Mobile logo */}
            <div className="lg:hidden flex items-center gap-2 mb-6">
              <div className="w-8 h-8 bg-gradient-to-br from-violet-600 to-pink-500 rounded-lg flex items-center justify-center text-lg">🔄</div>
              <span className="text-xl font-extrabold gradient-text">SkillBarter</span>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-violet-50 p-1 rounded-xl mb-6">
              {['login','register'].map(t => (
                <button key={t} onClick={() => { setTab(t); setError(''); }}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-all capitalize ${
                    tab === t ? 'bg-white text-violet-700 shadow-sm' : 'text-gray-500 hover:text-violet-600'}`}>
                  {t === 'login' ? '👋 Sign In' : '🚀 Sign Up'}
                </button>
              ))}
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-xl mb-4">
                {error}
              </div>
            )}

            {tab === 'login' ? (
              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">Email or Username</label>
                  <input className="input-field" placeholder="alice@uni.edu or alice_codes" value={loginForm.identifier}
                    onChange={e => setLoginForm(p => ({...p, identifier: e.target.value}))} required />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">Password</label>
                  <div className="relative">
                    <input className="input-field pr-12" type={showPwd ? 'text' : 'password'} placeholder="••••••••"
                      value={loginForm.password} onChange={e => setLoginForm(p => ({...p, password: e.target.value}))} required />
                    <button type="button" onClick={() => setShowPwd(!showPwd)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-violet-600">
                      {showPwd ? <EyeOff size={18}/> : <Eye size={18}/>}
                    </button>
                  </div>
                </div>
                <button type="submit" className="btn-primary w-full flex items-center justify-center gap-2 mt-2" disabled={loading}>
                  {loading ? <><Loader2 size={18} className="animate-spin"/>Signing in…</> : '✨ Sign In'}
                </button>
                <p className="text-center text-sm text-gray-500 mt-2">
                  Try demo: <span className="font-mono text-violet-600 text-xs">alice@university.edu / SeedPass1</span>
                </p>
              </form>
            ) : (
              <form onSubmit={handleRegister} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1.5">Full Name</label>
                    <input className="input-field" placeholder="Alice Smith" value={regForm.full_name}
                      onChange={e => setRegForm(p => ({...p, full_name: e.target.value}))} />
                  </div>
                  <div>
                    <label className="block text-sm font-semibold text-gray-700 mb-1.5">Username</label>
                    <input className="input-field" placeholder="alice_codes" value={regForm.username}
                      onChange={e => setRegForm(p => ({...p, username: e.target.value}))} required />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">Email</label>
                  <input className="input-field" type="email" placeholder="alice@university.edu" value={regForm.email}
                    onChange={e => setRegForm(p => ({...p, email: e.target.value}))} required />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">College / University</label>
                  <input className="input-field" placeholder="MIT" value={regForm.college}
                    onChange={e => setRegForm(p => ({...p, college: e.target.value}))} />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">Password</label>
                  <div className="relative">
                    <input className="input-field pr-12" type={showPwd ? 'text' : 'password'} placeholder="Min 8 chars with a number"
                      value={regForm.password} onChange={e => setRegForm(p => ({...p, password: e.target.value}))} required />
                    <button type="button" onClick={() => setShowPwd(!showPwd)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-violet-600">
                      {showPwd ? <EyeOff size={18}/> : <Eye size={18}/>}
                    </button>
                  </div>
                </div>
                <button type="submit" className="btn-primary w-full flex items-center justify-center gap-2 mt-2" disabled={loading}>
                  {loading ? <><Loader2 size={18} className="animate-spin"/>Creating account…</> : '🚀 Create Account'}
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
