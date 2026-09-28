import {
  existsSync,
  readdirSync,
  statSync,
} from 'node:fs'

import path from 'node:path'
import { spawn } from 'node:child_process'
import process from 'node:process'


const projectRoot =
  path.resolve(
    new URL(
      '..',
      import.meta.url,
    ).pathname,
  )

const outputDir =
  path.join(
    projectRoot,
    'frontend',
    'out',
  )


function findExecutable(
  directory,
) {
  if (!existsSync(directory)) {
    return null
  }

  for (
    const entry of readdirSync(
      directory,
      {
        withFileTypes: true,
      },
    )
  ) {
    const fullPath =
      path.join(
        directory,
        entry.name,
      )

    if (entry.isDirectory()) {
      const result =
        findExecutable(
          fullPath,
        )

      if (result) {
        return result
      }

      continue
    }

    if (
      process.platform === 'win32' &&
      entry.name.toLowerCase() ===
      'semantta.exe'
    ) {
      return fullPath
    }

    if (
      process.platform === 'linux' &&
      entry.name === 'semantta' &&
      statSync(fullPath).isFile()
    ) {
      return fullPath
    }

    if (
      process.platform === 'darwin' &&
      entry.name === 'Semantta' &&
      fullPath.includes(
        `${path.sep}Contents${path.sep}MacOS${path.sep}`,
      )
    ) {
      return fullPath
    }
  }

  return null
}


const executable =
  findExecutable(outputDir)

if (!executable) {
  console.error(
    `Could not find packaged Semantta executable under ${outputDir}`,
  )

  process.exit(1)
}

console.log(
  `Launching packaged application: ${executable}`,
)

const child =
  spawn(
    executable,
    ['--smoke-test'],
    {
      cwd:
        path.dirname(executable),
      stdio: 'inherit',
      env: {
        ...process.env,
      },
    },
  )

child.on(
  'error',
  (error) => {
    console.error(
      'Failed to launch packaged application:',
      error,
    )

    process.exit(1)
  },
)

child.on(
  'exit',
  (code, signal) => {
    if (
      code === 0 &&
      !signal
    ) {
      console.log(
        'Packaged application smoke test passed.',
      )

      process.exit(0)
    }

    console.error(
      `Packaged application smoke test failed: ` +
      `code=${code}, signal=${signal}`,
    )

    process.exit(
      typeof code === 'number'
        ? code
        : 1,
    )
  },
)