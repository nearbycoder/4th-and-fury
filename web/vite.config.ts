import { defineConfig } from 'vite';

// The game is served from /<repo>/play/ on GitHub Pages; FURY_BASE overrides it for other hosts.
export default defineConfig({
  base: process.env.FURY_BASE ?? './',
  build: {
    outDir: 'dist',
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 1500,
  },
  server: { port: 5199, strictPort: true },
});
