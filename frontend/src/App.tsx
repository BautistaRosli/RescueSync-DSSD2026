import { useEffect, useState } from 'react'

function App() {
  const [backendStatus, setBackendStatus] = useState<string>('Conectando...')

  useEffect(() => {
    fetch('http://localhost:8000/')
      .then((res) => res.json())
      .then((data) => setBackendStatus(data.message))
      .catch(() => setBackendStatus('Error conectando al backend'))
  }, [])

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 text-white p-6">
      <div className="rounded-xl bg-slate-800 p-8 shadow-2xl border border-slate-700 text-center max-w-md">
        <h1 className="text-3xl font-bold tracking-tight text-cyan-400 mb-4">
          Template de index
        </h1>
        <p className="text-slate-300 mb-4">
          Usando la locura de <span className="font-semibold text-sky-400">Tailwind CSS</span>
        </p>
        <div className="rounded-lg bg-slate-900 p-4 border border-slate-700 text-sm">
          <p className="text-slate-400">Estado de FastAPI:</p>
          <p className="font-mono text-emerald-400 mt-1">{backendStatus}</p>
          <p className="size-sm  mt-2 text-slate-400">aca dice si anda el backend o si pudo conectarse a bonita</p>
        </div>
      </div>
    </div>
  )
}

export default App