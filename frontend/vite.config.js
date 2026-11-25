import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The app calls /api on its own origin; in development that is proxied to FastAPI.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
