import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawn, spawnSync } from 'node:child_process'
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

function getApplicationRoot(executable) {
  if (process.platform === 'win32') {
    return path.join(outDir, 'win-unpacked')
  }

  if (process.platform === 'darwin') {
    const marker = `${path.sep}Contents${path.sep}MacOS${path.sep}`
    const markerIndex = executable.indexOf(marker)

    if (markerIndex === -1) {
      throw new Error(
        `Could not determine macOS application bundle from: ${executable}`
      )
    }

    return executable.slice(0, markerIndex)
  }

  return path.dirname(executable)
}

function createSmokeEnvironment() {
  const smokeRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), 'semantta-smoke-')
  )

  const env = {
    ...process.env,
  }

  if (process.platform === 'win32') {
    env.APPDATA = path.join(smokeRoot, 'AppData')
  } else if (process.platform === 'darwin') {
    env.HOME = path.join(smokeRoot, 'Home')
  } else {
    env.XDG_DATA_HOME = path.join(smokeRoot, 'XDG')
  }

  return {
    root: smokeRoot,
    env,
  }
}

function getUserDataDir(env) {
  if (process.platform === 'win32') {
    if (!env.APPDATA) {
      throw new Error('APPDATA is not defined.')
    }

    return path.join(env.APPDATA, 'Semantta')
  }

  if (process.platform === 'darwin') {
    if (!env.HOME) {
      throw new Error('HOME is not defined.')
    }

    return path.join(
      env.HOME,
      'Library',
      'Application Support',
      'Semantta'
    )
  }

  const dataHome =
    env.XDG_DATA_HOME ||
    path.join(
      env.HOME || os.homedir(),
      '.local',
      'share'
    )

  return path.join(dataHome, 'Semantta')
}

function assertUserDataOutsideApplication(
  userDataDir,
  applicationRoot
) {
  const userData = path.resolve(userDataDir)
  const application = path.resolve(applicationRoot)

  const relative = path.relative(application, userData)

  const isInsideApplication =
    relative === '' ||
    (
      !path.isAbsolute(relative) &&
      relative !== '..' &&
      !relative.startsWith(`..${path.sep}`)
    )

  if (isInsideApplication) {
    throw new Error(
      `User data is inside the application installation directory.\n` +
      `User data: ${userData}\n` +
      `Application: ${application}`
    )
  }
}

function runSmokeTest(executable, env) {
  return new Promise((resolve, reject) => {
    const smokeArgs = process.platform === 'linux'
      ? ['--no-sandbox', '--smoke-test']
      : ['--smoke-test']

    console.log(`Launching packaged application: ${executable}`)

    const child = spawn(executable, smokeArgs, {
      stdio: 'inherit',
      env,
    })

    child.on('error', (error) => {
      reject(
        new Error(
          `Failed to start packaged application: ${error.message}`
        )
      )
    })

    child.on('exit', (code, signal) => {
      if (signal) {
        reject(
          new Error(
            `Packaged application smoke test failed: signal=${signal}`
          )
        )
        return
      }

      if (code !== 0) {
        reject(
          new Error(
            `Packaged application smoke test failed: code=${code}`
          )
        )
        return
      }

      resolve()
    })
  })
}

function createReplacementInstallation(
  executable,
  applicationRoot,
  tempRoot
) {
  const replacementApplicationRoot = path.join(
    tempRoot,
    path.basename(applicationRoot)
  )

  if (process.platform === 'darwin') {
    const result = spawnSync(
      'ditto',
      [
        applicationRoot,
        replacementApplicationRoot,
      ],
      {
        stdio: 'inherit',
      }
    )

    if (result.error) {
      throw new Error(
        `Failed to copy macOS application bundle: ${result.error.message}`
      )
    }

    if (result.status !== 0) {
      throw new Error(
        `ditto failed while copying macOS application bundle: ${result.status}`
      )
    }
  } else {
    fs.cpSync(
      applicationRoot,
      replacementApplicationRoot,
      {
        recursive: true,
      }
    )
  }

  const relativeExecutable = path.relative(
    applicationRoot,
    executable
  )

  return path.join(
    replacementApplicationRoot,
    relativeExecutable
  )
}

async function verifyDataPreservation(
  executable,
  applicationRoot,
  smokeEnv
) {
  const userDataDir = getUserDataDir(smokeEnv)

  assertUserDataOutsideApplication(
    userDataDir,
    applicationRoot
  )

  fs.mkdirSync(userDataDir, {
    recursive: true,
  })

  const sentinel = path.join(
    userDataDir,
    'p3.9-upgrade-preservation-test.txt'
  )

  const marker =
    'Semantta P3.9 data-preservation test\n'

  fs.writeFileSync(
    sentinel,
    marker,
    'utf8'
  )

  const temporaryRoot = fs.mkdtempSync(
    path.join(
      os.tmpdir(),
      'semantta-upgrade-'
    )
  )

  try {
    const replacementExecutable =
      createReplacementInstallation(
        executable,
        applicationRoot,
        temporaryRoot
      )

    console.log(
      `Launching replacement installation: ${replacementExecutable}`
    )

    await runSmokeTest(
      replacementExecutable,
      smokeEnv
    )

    if (!fs.existsSync(sentinel)) {
      throw new Error(
        `User-data sentinel was deleted during upgrade test: ${sentinel}`
      )
    }

    const preserved = fs.readFileSync(
      sentinel,
      'utf8'
    )

    if (preserved !== marker) {
      throw new Error(
        'User-data sentinel was modified during upgrade test.'
      )
    }

    console.log(
      'P3.9 data-preservation test passed.'
    )
  } finally {
    removeTemporaryDirectory(temporaryRoot)
  }
}

function removeTemporaryDirectory(directory) {
  fs.rmSync(
    directory,
    {
      recursive: true,
      force: true,
      maxRetries: 20,
      retryDelay: 500,
    }
  )
}

async function main() {
  console.log(
    `Looking for packaged application under: ${outDir}`
  )

  const executable =
    findPackagedExecutable()

  if (!executable) {
    throw new Error(
      `Could not find packaged Semantta executable under ${outDir}`
    )
  }

  const applicationRoot =
    getApplicationRoot(executable)

  console.log(
    `Packaged executable: ${executable}`
  )

  console.log(
    `Application root: ${applicationRoot}`
  )

  const smokeEnvironment =
    createSmokeEnvironment()

  try {
    console.log(
      'Running packaged application smoke test...'
    )

    await runSmokeTest(
      executable,
      smokeEnvironment.env
    )

    console.log(
      'Packaged application smoke test passed.'
    )

    console.log(
      'Running P3.9 data-preservation test...'
    )

    await verifyDataPreservation(
      executable,
      applicationRoot,
      smokeEnvironment.env
    )
  } finally {
    removeTemporaryDirectory(
      smokeEnvironment.root
    )
  }

  console.log(
    'All packaged application tests passed.'
  )
}

main().catch((error) => {
  console.error(error.message)
  process.exit(1)
})