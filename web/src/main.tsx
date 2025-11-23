import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ZeroProvider } from './contexts/ZeroContext'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  // StrictMode temporarily disabled for WebSocket development
  // <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ZeroProvider>
        <App />
      </ZeroProvider>
    </QueryClientProvider>
  // </React.StrictMode>,
)
