import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Home, Search, BookOpen, Sparkles, LogOut, Menu, X } from 'lucide-react';

const navItems = [
  { to: '/', icon: <Home size={17} />, label: 'Home', end: true },
  { to: '/discover', icon: <Search size={17} />, label: 'Discover' },
  { to: '/skills', icon: <BookOpen size={17} />, label: 'My Skills' },
  { to: '/matches', icon: <Sparkles size={17} />, label: 'Matches' },
];

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = () => { logout(); navigate('/login'); };
  const avatarLetter = user?.username?.[0]?.toUpperCase() || '?';

  return (
    <nav className="bg-white/80 backdrop-blur-md border-b border-violet-100 sticky top-0 z-50 shadow-sm">
      <div className="max-w-6xl mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <NavLink to="/" className="flex items-center gap-2 select-none">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-pink-500 flex items-center justify-center text-lg shadow-sm">
              🔄
            </div>
            <span className="font-extrabold text-xl gradient-text tracking-tight">SkillBarter</span>
          </NavLink>

          {/* Desktop links */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map(({ to, icon, label, end }) => (
              <NavLink key={to} to={to} end={end}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                    isActive ? 'bg-violet-100 text-violet-700' : 'text-gray-500 hover:bg-violet-50 hover:text-violet-600'
                  }`}
              >{icon}{label}</NavLink>
            ))}
          </div>

          {/* User pill */}
          <div className="hidden md:flex items-center gap-3">
            <div className="flex items-center gap-2 bg-violet-50 px-3 py-1.5 rounded-full border border-violet-100">
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-500 to-pink-400 flex items-center justify-center text-white text-xs font-bold">
                {avatarLetter}
              </div>
              <span className="text-sm font-semibold text-violet-800">{user?.username}</span>
            </div>
            <button onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-gray-400 hover:bg-red-50 hover:text-red-500 transition-all">
              <LogOut size={15} /> Out
            </button>
          </div>

          <button className="md:hidden p-2 rounded-lg text-gray-500 hover:bg-violet-50" onClick={() => setOpen(!open)}>
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {open && (
          <div className="md:hidden border-t border-violet-100 py-3 space-y-1">
            {navItems.map(({ to, icon, label, end }) => (
              <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium ${
                    isActive ? 'bg-violet-100 text-violet-700' : 'text-gray-600 hover:bg-violet-50'
                  }`}
              >{icon}{label}</NavLink>
            ))}
            <button onClick={handleLogout} className="flex items-center gap-3 px-4 py-3 text-sm text-red-500 hover:bg-red-50 w-full rounded-xl">
              <LogOut size={16} />Logout
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
