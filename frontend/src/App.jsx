import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './components/Toast';
import Navbar from './components/Navbar';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import DiscoverPage from './pages/DiscoverPage';
import MySkillsPage from './pages/MySkillsPage';
import MatchesPage from './pages/MatchesPage';

function Spinner() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-spin rounded-full h-12 w-12 border-4 border-violet-200 border-t-violet-600"></div>
    </div>
  );
}

function PrivateRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return user ? children : <Navigate to="/login" replace />;
}

function Layout({ children }) {
  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<PrivateRoute><Layout><DashboardPage /></Layout></PrivateRoute>} />
            <Route path="/discover" element={<PrivateRoute><Layout><DiscoverPage /></Layout></PrivateRoute>} />
            <Route path="/skills" element={<PrivateRoute><Layout><MySkillsPage /></Layout></PrivateRoute>} />
            <Route path="/matches" element={<PrivateRoute><Layout><MatchesPage /></Layout></PrivateRoute>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  );
}
