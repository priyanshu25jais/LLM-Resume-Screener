import { createContext, useContext, useEffect, useState } from 'react'
import { api } from './api.js'

const AuthContext = createContext(null)

// user: undefined while checking, null when logged out, otherwise the account
export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined)

  useEffect(() => { api.me().then(setUser).catch(() => setUser(null)) }, [])
  useEffect(() => {
    const expired = () => setUser(null)
    window.addEventListener('auth-expired', expired)
    return () => window.removeEventListener('auth-expired', expired)
  }, [])

  const logout = async () => {
    try { await api.logout() } finally { setUser(null) }
  }
  return <AuthContext.Provider value={{ user, setUser, logout }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
