import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle, XCircle, X } from 'lucide-react';

const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const show = useCallback((message, type = 'success') => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
  }, []);

  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => (
          <div key={t.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg border pointer-events-auto max-w-sm
              ${t.type === 'success' ? 'bg-white border-green-200 text-green-800' : 'bg-white border-red-200 text-red-800'}`}>
            {t.type === 'success'
              ? <CheckCircle size={18} className="text-green-500 flex-shrink-0" />
              : <XCircle size={18} className="text-red-500 flex-shrink-0" />}
            <span className="text-sm font-medium">{t.message}</span>
            <button onClick={() => setToasts(p => p.filter(x => x.id !== t.id))} className="ml-auto text-gray-400 hover:text-gray-600">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
};
