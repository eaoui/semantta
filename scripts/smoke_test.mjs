import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const projectDir = path.join(__dirname, '..')
const outDir = path.join(projectDir, 'frontend', 'out')

function findExecutable(dir, predicate) {
  if (!fs.existsSync(dir)) {
    return null
  }

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name)

    if (entry.isDirectory()) {
      const result = findExecutable(fullPath, predicate)
      if (result) {
        return result
      }
    } else if (predicate(fullPath, entry.name)) {
      return fullPath
    }
  }

  return null
}

function findPackagedExecutable() {
  if (process.platform === 'win32') {
    const windowsUnpackedDir = path.join(outDir, 'win-unpacked')

    return findExecutable(
      windowsUnpackedDir,
      (_fullPath, name) => name.toLowerCase() === 'semantta.exe'
    )
  }

  if (process.platform === 'darwin') {
    return findExecutable(
      outDir,
      (fullPath, name) =>
        name === 'Semantta' &&
        fullPath.includes('.app/Contents/MacOS/')
    )
  }

  return findExecutable(
    outDir,
    (_fullPath, name) => name === 'semantta'
  )
}

console.log(`Looking for packaged application under: ${outDir}`)

const executable = findPackagedExecutable()

if (!executable) {
  console.error(
    `Could not find packaged Semantta executable under ${outDir}`
  )
  process.exit(1)
}

console.log(`Launching packaged application: ${executable}`)

const smokeArgs = process.platform === 'linux'
  ? ['--no-sandbox', '--smoke-test']
  : ['--smoke-test']

const child = spawn(executable, smokeArgs, {
  stdio: 'inherit',
  env: {
    ...process.env,
  },
})

child.on('error', (error) => {
  console.error('Failed to start packaged application:', error)
  process.exit(1)
})

child.on('exit', (code, signal) => {
  if (signal) {
    console.error(`Packaged application smoke test failed: signal=${signal}`)
    process.exit(1)
  }

  if (code !== 0) {
    console.error(`Packaged application smoke test failed: code=${code}`)
    process.exit(code ?? 1)
  }

  console.log('Packaged application smoke test passed.')
  process.exit(0)
})