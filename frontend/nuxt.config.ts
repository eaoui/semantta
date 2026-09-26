import tailwindcss from '@tailwindcss/vite'
import fs from 'fs'
import path from 'path'

// ── Development-time active theme detection ───────────────────────────

const dataDir = path.resolve(__dirname, '..', 'data')

const activeThemeFile = path.join(
  dataDir,
  'active-theme.json',
)

let activeTheme = 'default'

try {
  const config = JSON.parse(
    fs.readFileSync(activeThemeFile, 'utf-8'),
  )

  activeTheme = config.active_theme || 'default'
} catch {
  // File not found or invalid: use the built-in default theme.
}

const themeLayers: string[] = []

if (activeTheme !== 'default') {
  const themePath = path.join(
    dataDir,
    'themes',
    activeTheme,
  )

  if (fs.existsSync(themePath)) {
    themeLayers.push(themePath)
  }
}

export default defineNuxtConfig({
  ssr: false,

  devtools: {
    enabled: process.env.NODE_ENV !== 'production',
  },

  modules: [
    '@pinia/nuxt',
    ['nuxt-phosphor-icons', { style: 'regular' }],
    '@vite-pwa/nuxt',
  ],

  css: [
    '~/assets/css/main.css',
    'vis-network/styles/vis-network.min.css',
  ],

  runtimeConfig: {
    public: {
      apiBase: (
        process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8000'
      ).replace(/\/+$/, ''),
    },
  },

  vite: {
    plugins: [
      tailwindcss(),
    ],

    server: {
      strictPort: true,
    },

    optimizeDeps: {
      include: [
        '@vue/devtools-core',
        '@vue/devtools-kit',
        'vue-sonner',
        'vis-network',
        'workbox-window',
      ],
    },
  },
  app: {
    head: {
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
        { rel: 'icon', type: 'image/png', href: '/favicon.png' }
      ],
      script: [
        {
          // Runs before any content is rendered – prevents flash of wrong theme
          innerHTML: `(function() {
            try {
              const theme = localStorage.getItem('theme') || 'system';
              if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                document.documentElement.classList.add('dark');
              } else {
                document.documentElement.classList.remove('dark');
              }
            } catch(e) {}
          })()`,
          type: 'text/javascript',
        },
      ],
    },
  },
  pwa: {
    registerType: 'autoUpdate',
    manifest: {
      name: 'Semantta',
      short_name: 'Semantta',
      description: 'Ontology‑Based Linked Data Management System',
      theme_color: '#3B82F6',    // matches tailwind's blue‑600
      background_color: '#ffffff',
      icons: [
        {
          src: 'pwa-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'any maskable',
        },
        {
          src: 'pwa-256.png',
          sizes: '256x256',
          type: 'image/png',
        },
        {
          src: 'pwa-128.png',
          sizes: '128x128',
          type: 'image/png',
        },
      ],
    },
    workbox: {
      // In development, Vite doesn't write matching files – skip precaching
      globPatterns: process.env.NODE_ENV === 'development' ? [] : ['_nuxt/**/*.{js,css,html,png,svg,ico}', '**/*.{png,svg,ico}'],
    },
    // Enable PWA in development (disabled by default)
    devOptions: {
      enabled: process.env.NODE_ENV !== 'production',
      type: 'module',
    },
  },
})