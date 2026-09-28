import { spawnSync } from 'node:child_process'

const isWindows = process.platform === 'win32'

const command = isWindows
  ? (process.env.ComSpec || 'cmd.exe')
  : 'npx'

const args = isWindows
  ? ['/d', '/s', '/c', 'npx.cmd nuxt generate']
  : ['nuxt', 'generate']

const result = spawnSync(
  command,
  args,
  {
    stdio: 'inherit',
    env: {
      ...process.env,
      NUXT_PUBLIC_API_BASE: 'semantta://bundle',
    },
  },
)

if (result.error) {
  console.error(
    'Failed to run Nuxt generate:',
    result.error,
  )
  process.exit(1)
}

process.exit(
  typeof result.status === 'number'
    ? result.status
    : 1,
)