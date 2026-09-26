import { useState } from 'react'
import { LoginPage, RegistroPage } from './pages'

type Vista = 'login' | 'registro'

function App() {
  const [vista, setVista] = useState<Vista>('login')

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <header className="border-b border-slate-700 bg-slate-800/60">
        <div className="mx-auto max-w-md px-4 py-6">
          <h1 className="text-3xl font-bold tracking-tight text-cyan-400">
            RescueSync
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Coordinación de rescates en emergencias.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-md px-4 py-8">
        {vista === 'login' ? (
          <LoginPage onIrARegistro={() => setVista('registro')} />
        ) : (
          <RegistroPage onIrALogin={() => setVista('login')} />
        )}
      </main>
    </div>
  )
}

export default App
