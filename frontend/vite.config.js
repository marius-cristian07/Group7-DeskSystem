// Vite reads this when starting the development server or building the frontend.
// The React plugin enables JSX files and component updates while developing.
// The backend address is configured separately through VITE_API_BASE_URL.

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  // Enable JSX and update React components while the dev server is running.
  plugins: [react()],
});
