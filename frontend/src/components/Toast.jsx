import { createContext, useCallback, useContext, useState } from 'react'

const ToastContext = createContext(() => {})

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const show = useCallback((text) => {
    const id = Math.random().toString(36).slice(2)
    setItems((t) => [...t, { id, text }])
    setTimeout(() => setItems((t) => t.filter((x) => x.id !== id)), 2600)
  }, [])
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => <div key={t.id} className="toast">{t.text}</div>)}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
