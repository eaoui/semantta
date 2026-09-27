import { spawnSync } from 'node:child_process'

const command =
  process.platform === 'win32'
    ? 'npx.cmd'
    : 'npx'

const result = spawnSync(
  command,
  ['nuxt', 'generate'],
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