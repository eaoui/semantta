const {
  app,
  BrowserWindow,
  dialog,
  net: electronNet,
  protocol,
} = require('electron')

const path = require('node:path')
const fs = require('node:fs')
const os = require('node:os')

const { spawn } = require('node:child_process')
const http = require('node:http')
const net = require('node:net')

const DEV_SERVER_URL = 'http://localhost:3000'
const APP_SCHEME = 'semantta'
const APP_HOST = 'bundle'

const BACKEND_HOST = '127.0.0.1'
const FUSEKI_HOST = '127.0.0.1'
const FUSEKI_DATASET_NAME = 'obmms'

const BACKEND_STARTUP_TIMEOUT = 30000
const FUSEKI_STARTUP_TIMEOUT = 30000

const MAX_SERVICE_START_ATTEMPTS = 5

const IS_SMOKE_TEST = process.argv.includes(
  '--smoke-test',
)

if (IS_SMOKE_TEST) {
  app.commandLine.appendSwitch('no-sandbox')
}

let backendPort = null
let fusekiPort = null

let backendBaseUrl = null
let fusekiBaseUrl = null

let mainWindow = null
let backendProcess = null

function getElectronLogFile() {
  return path.join(
    getSemanttaDataDir(),
    'logs',
    'electron.log',
  )
}

function getFusekiBaseDir() {
  return path.join(
    getSemanttaDataDir(),
    'database',
    'fuseki',
    'runtime',
  )
}


function getFusekiDatabaseDir() {
  return path.join(
    getSemanttaDataDir(),
    'database',
    'fuseki',
    'tdb2',
  )
}

function log(message) {
  const timestamp =
    new Date().toISOString()

  const line =
    `${timestamp} | ${message}\n`

  console.log(line.trim())

  try {
    const logFile =
      getElectronLogFile()

    fs.mkdirSync(
      path.dirname(logFile),
      {
        recursive: true,
      },
    )

    fs.appendFileSync(
      logFile,
      line,
      'utf8',
    )
  } catch (error) {
    console.error(
      'Failed to write Electron log:',
      error,
    )
  }
}

function getSemanttaDataDir() {
  const home = os.homedir()

  let base

  if (process.platform === 'win32') {
    base =
      process.env.APPDATA ||
      path.join(
        home,
        'AppData',
        'Roaming',
      )
  } else if (process.platform === 'darwin') {
    base = path.join(
      home,
      'Library',
      'Application Support',
    )
  } else {
    base =
      process.env.XDG_DATA_HOME ||
      path.join(
        home,
        '.local',
        'share',
      )
  }

  return path.join(
    base,
    'Semantta',
  )
}

function getFusekiExecutable() {
  if (process.platform === 'win32') {
    return path.join(
      process.resourcesPath,
      'runtime',
      'fuseki',
      'fuseki-server.bat',
    )
  }

  return path.join(
    process.resourcesPath,
    'runtime',
    'fuseki',
    'fuseki-server',
  )
}

function getJavaHome() {
  return path.join(
    process.resourcesPath,
    'runtime',
    'java',
  )
}

let fusekiProcess = null

function startFuseki() {
  if (!fusekiPort) {
    throw new Error(
      'Fuseki port has not been allocated.',
    )
  }

  const fusekiExecutable =
    getFusekiExecutable()

  const javaHome =
    getJavaHome()

  const fusekiBaseDir =
    getFusekiBaseDir()

  const databaseDir =
    getFusekiDatabaseDir()

  fs.mkdirSync(
    fusekiBaseDir,
    {
      recursive: true,
    },
  )

  fs.mkdirSync(
    databaseDir,
    {
      recursive: true,
    },
  )

  const args = [
    '--tdb2',
    `--loc=${databaseDir}`,
    '--update',
    '--localhost',
    `--port=${fusekiPort}`,
    `/${FUSEKI_DATASET_NAME}`,
  ]

  const env = {
    ...process.env,

    JAVA_HOME: javaHome,

    FUSEKI_HOME:
      path.dirname(fusekiExecutable),

    FUSEKI_BASE:
      fusekiBaseDir,

    PATH: [
      path.join(
        javaHome,
        'bin',
      ),
      process.env.PATH || '',
    ].join(
      process.platform === 'win32'
        ? ';'
        : ':',
    ),
  }

  const options = {
    cwd: path.dirname(
      fusekiExecutable,
    ),
    env,
    windowsHide: true,
    stdio: [
      'ignore',
      'pipe',
      'pipe',
    ],
  }

  if (
    process.platform === 'win32'
  ) {
    options.shell = true
  } else {
    options.detached = true
  }

  fusekiProcess = spawn(
    fusekiExecutable,
    args,
    options,
  )

  fusekiProcess.stdout.on(
    'data',
    (data) => {
      log(
        `[Fuseki] ${data.toString().trim()}`,
      )
    },
  )

  fusekiProcess.stderr.on(
    'data',
    (data) => {
      log(
        `[Fuseki] ${data.toString().trim()}`,
      )
    },
  )

  fusekiProcess.on(
    'error',
    (error) => {
      console.error(
        'Failed to start Fuseki:',
        error,
      )
    },
  )

  fusekiProcess.on(
    'exit',
    (code, signal) => {
      console.log(
        `Fuseki exited: code=${code}, signal=${signal}`,
      )

      fusekiProcess = null
    },
  )
}

function waitForFuseki() {
  const startedAt = Date.now()
  const process = fusekiProcess

  return new Promise(
    (resolve, reject) => {
      let settled = false

      const cleanup = () => {
        if (process) {
          process.off(
            'exit',
            onExit,
          )
        }
      }

      const finish = (callback, value) => {
        if (settled) {
          return
        }

        settled = true
        cleanup()
        callback(value)
      }

      const onExit = (code, signal) => {
        finish(
          reject,
          new Error(
            `Fuseki exited before becoming ready ` +
            `(code=${code}, signal=${signal}).`,
          ),
        )
      }

      if (process) {
        process.once(
          'exit',
          onExit,
        )
      }

      const check = () => {
        if (settled) {
          return
        }

        if (
          Date.now() - startedAt >
          FUSEKI_STARTUP_TIMEOUT
        ) {
          finish(
            reject,
            new Error(
              'Timed out waiting for Fuseki.',
            ),
          )

          return
        }

        const request = http.get(
          `${fusekiBaseUrl}/$/ping`,
          (response) => {
            response.resume()

            if (
              response.statusCode === 200
            ) {
              finish(resolve)
              return
            }

            setTimeout(
              check,
              250,
            )
          },
        )

        request.on(
          'error',
          () => {
            setTimeout(
              check,
              250,
            )
          },
        )

        request.setTimeout(
          1000,
          () => {
            request.destroy()

            setTimeout(
              check,
              250,
            )
          },
        )
      }

      check()
    },
  )
}

function stopFuseki() {
  if (!fusekiProcess) {
    return
  }

  log('Stopping Fuseki.')

  const pid = fusekiProcess.pid

  if (
    process.platform === 'win32'
  ) {
    require('node:child_process').spawn(
      'taskkill',
      [
        '/pid',
        String(pid),
        '/t',
        '/f',
      ],
      {
        windowsHide: true,
        stdio: 'ignore',
      },
    )
  } else if (pid) {
    try {
      process.kill(
        -pid,
        'SIGTERM',
      )
    } catch {
      try {
        fusekiProcess.kill(
          'SIGTERM',
        )
      } catch {
        // Already stopped.
      }
    }
  }

  fusekiProcess = null
}

protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      allowServiceWorkers: true,
      corsEnabled: true,
      stream: true,
    },
  },
])


function getFrontendDist() {
  return path.join(
    app.getAppPath(),
    '.output',
    'public',
  )
}


function registerFrontendProtocol() {
  protocol.handle(
    APP_SCHEME,
    async (request) => {
      const requestUrl = new URL(request.url)

      if (
        requestUrl.host === APP_HOST &&
        requestUrl.pathname.startsWith('/api/')
      ) {
        const backendUrl =
          `${backendBaseUrl}${requestUrl.pathname}${requestUrl.search}`

        const headers = new Headers(request.headers)

        headers.delete('host')
        headers.delete('content-length')
        headers.delete('origin')
        headers.delete('referer')

        let body

        if (
          request.method !== 'GET' &&
          request.method !== 'HEAD'
        ) {
          body = Buffer.from(
            await request.arrayBuffer(),
          )
        }

        return electronNet.fetch(
          backendUrl,
          {
            method: request.method,
            headers,
            body,
          },
        )
      }

      if (requestUrl.host !== APP_HOST) {
        return new Response('Not found', {
          status: 404,
        })
      }

      let relativePath

      try {
        relativePath = decodeURIComponent(
          requestUrl.pathname,
        )
      } catch {
        return new Response('Bad request', {
          status: 400,
        })
      }

      relativePath = relativePath.replace(/^\/+/, '')

      const frontendRoot = path.resolve(
        getFrontendDist(),
      )

      const requestedPath = path.resolve(
        frontendRoot,
        relativePath,
      )

      const relativeToRoot = path.relative(
        frontendRoot,
        requestedPath,
      )

      const isInsideRoot =
        relativeToRoot !== '..' &&
        !relativeToRoot.startsWith(`..${path.sep}`) &&
        !path.isAbsolute(relativeToRoot)

      if (!isInsideRoot) {
        return new Response('Forbidden', {
          status: 403,
        })
      }

      let filePath = requestedPath

      try {
        const stat = require('node:fs').statSync(
          filePath,
        )

        if (stat.isDirectory()) {
          filePath = path.join(
            filePath,
            'index.html',
          )
        }
      } catch {
        const acceptsHtml =
          request.headers.get('accept')?.includes(
            'text/html',
          ) ?? false

        if (acceptsHtml) {
          filePath = path.join(
            frontendRoot,
            'index.html',
          )
        } else {
          return new Response('Not found', {
            status: 404,
          })
        }
      }

      try {
        return await electronNet.fetch(
          require('node:url').pathToFileURL(
            filePath,
          ).toString(),
        )
      } catch {
        return new Response('Not found', {
          status: 404,
        })
      }
    },
  )
}


function getBackendExecutable() {
  const executableName =
    process.platform === 'win32'
      ? 'SemanttaBackend.exe'
      : 'SemanttaBackend'

  return path.join(
    process.resourcesPath,
    'backend',
    executableName,
  )
}

function findFreePort(host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = net.createServer()

    server.unref()

    server.on('error', reject)

    server.listen(
      {
        host,
        port: 0,
      },
      () => {
        const address = server.address()

        if (
          !address ||
          typeof address === 'string'
        ) {
          server.close()
          reject(
            new Error(
              'Could not determine the allocated port.',
            ),
          )
          return
        }

        const port = address.port

        server.close((error) => {
          if (error) {
            reject(error)
            return
          }

          resolve(port)
        })
      },
    )
  })
}

async function allocateFusekiPort() {
  fusekiPort = await findFreePort(
    FUSEKI_HOST,
  )

  fusekiBaseUrl =
    `http://${FUSEKI_HOST}:${fusekiPort}`

  log(
    `Allocated Fuseki port: ${fusekiPort}`,
  )
}


async function allocateBackendPort() {
  backendPort = await findFreePort(
    BACKEND_HOST,
  )

  backendBaseUrl =
    `http://${BACKEND_HOST}:${backendPort}`

  log(
    `Allocated FastAPI port: ${backendPort}`,
  )
}
function startBackend() {
  const executablePath = getBackendExecutable()

  backendProcess = spawn(
    executablePath,
    [],
    {
      cwd: path.dirname(executablePath),
      env: {
        ...process.env,
        SEMANTTA_HOST: BACKEND_HOST,
        SEMANTTA_PORT: String(backendPort),
        FUSEKI_DATASET_URL:
          `${fusekiBaseUrl}/${FUSEKI_DATASET_NAME}`,
      },
      windowsHide: true,
      stdio: 'ignore',
    },
  )

  backendProcess.on('error', (error) => {
    console.error(
      'Failed to start Semantta backend:',
      error,
    )
  })

  backendProcess.on('exit', (code, signal) => {
    console.log(
      `Semantta backend exited: code=${code}, signal=${signal}`,
    )

    backendProcess = null
  })
}


function waitForBackend() {
  const startedAt = Date.now()
  const process = backendProcess

  return new Promise(
    (resolve, reject) => {
      let settled = false

      const cleanup = () => {
        if (process) {
          process.off(
            'exit',
            onExit,
          )
        }
      }

      const finish = (callback, value) => {
        if (settled) {
          return
        }

        settled = true
        cleanup()
        callback(value)
      }

      const onExit = (code, signal) => {
        finish(
          reject,
          new Error(
            `Semantta backend exited before becoming ready ` +
            `(code=${code}, signal=${signal}).`,
          ),
        )
      }

      if (process) {
        process.once(
          'exit',
          onExit,
        )
      }

      const check = () => {
        if (settled) {
          return
        }

        if (
          Date.now() - startedAt >
          BACKEND_STARTUP_TIMEOUT
        ) {
          finish(
            reject,
            new Error(
              'Timed out waiting for the Semantta backend.',
            ),
          )

          return
        }

        const request = http.get(
          `${backendBaseUrl}/api/health`,
          (response) => {
            response.resume()

            if (
              response.statusCode === 200 ||
              response.statusCode === 503
            ) {
              finish(resolve)
              return
            }

            setTimeout(
              check,
              250,
            )
          },
        )

        request.on(
          'error',
          () => {
            setTimeout(
              check,
              250,
            )
          },
        )

        request.setTimeout(
          1000,
          () => {
            request.destroy()

            setTimeout(
              check,
              250,
            )
          },
        )
      }

      check()
    },
  )
}

async function startServices() {
  let lastError = null

  for (
    let attempt = 1;
    attempt <= MAX_SERVICE_START_ATTEMPTS;
    attempt += 1
  ) {
    try {
      log(
        `Starting Semantta services ` +
        `(attempt ${attempt}/${MAX_SERVICE_START_ATTEMPTS}).`,
      )

      await allocateFusekiPort()
      startFuseki()
      await waitForFuseki()

      log(
        `Fuseki is ready at ${fusekiBaseUrl}.`,
      )

      await allocateBackendPort()
      startBackend()
      await waitForBackend()

      log(
        `FastAPI is ready at ${backendBaseUrl}.`,
      )

      return
    } catch (error) {
      lastError =
        error instanceof Error
          ? error
          : new Error(
            String(error),
          )

      log(
        `Service startup attempt ${attempt} failed: ` +
        `${lastError.message}`,
      )

      stopBackend()
      stopFuseki()

      if (
        attempt <
        MAX_SERVICE_START_ATTEMPTS
      ) {
        log(
          'Retrying with new service ports.',
        )
      }
    }
  }

  throw lastError ||
  new Error(
    'Semantta services could not be started.',
  )
}

function stopBackend() {
  if (!backendProcess) {
    return
  }

  log('Stopping FastAPI backend.')

  backendProcess.kill()
  backendProcess = null
}

function waitForRendererSmokeTest() {
  return new Promise((resolve, reject) => {
    if (!mainWindow) {
      reject(
        new Error(
          'Main window does not exist.',
        ),
      )
      return
    }

    const onFailedLoad = (
      _event,
      errorCode,
      errorDescription,
      validatedURL,
    ) => {
      reject(
        new Error(
          `Renderer failed to load: ` +
          `${errorCode} ${errorDescription} ` +
          `(${validatedURL})`,
        ),
      )
    }

    const onFinishedLoad = async () => {
      try {
        const result =
          await mainWindow.webContents.executeJavaScript(
            `
              (async () => {
                const response = await fetch(
                  '/api/health',
                  {
                    cache: 'no-store',
                  },
                )

                const body =
                  await response.json()

                return {
                  status: response.status,
                  body,
                  origin: window.location.origin,
                }
              })()
            `,
            true,
          )

        if (result.status !== 200) {
          throw new Error(
            `Health endpoint returned HTTP ` +
            `${result.status}.`,
          )
        }

        if (
          !result.body ||
          result.body.status !== 'ok' ||
          result.body.backend !== 'ok' ||
          result.body.fuseki !== 'ok'
        ) {
          throw new Error(
            `Unexpected health response: ` +
            `${JSON.stringify(result.body)}`,
          )
        }

        if (
          result.origin !==
          `${APP_SCHEME}://${APP_HOST}`
        ) {
          throw new Error(
            `Unexpected renderer origin: ` +
            `${result.origin}`,
          )
        }

        log(
          'Renderer smoke test succeeded.',
        )

        resolve()
      } catch (error) {
        reject(error)
      }
    }

    mainWindow.webContents.once(
      'did-fail-load',
      onFailedLoad,
    )

    mainWindow.webContents.once(
      'did-finish-load',
      onFinishedLoad,
    )
  })
}

async function createMainWindow() {
  const windowIcon = path.join(
    app.getAppPath(),
    '.output',
    'public',
    'pwa-512.png',
  )

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'Semantta',
    show: !IS_SMOKE_TEST,
    icon: windowIcon,

    webPreferences: {
      preload: path.join(
        __dirname,
        'preload.cjs',
      ),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  if (!app.isPackaged) {
    mainWindow.loadURL(DEV_SERVER_URL)
  } else {
    mainWindow.loadURL(
      `${APP_SCHEME}://${APP_HOST}/`,
    )
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  const rendererUrl = app.isPackaged
    ? `${APP_SCHEME}://${APP_HOST}/`
    : DEV_SERVER_URL

  if (IS_SMOKE_TEST) {
    const smokeTest =
      waitForRendererSmokeTest()

    await mainWindow.loadURL(
      rendererUrl,
    )

    await smokeTest
  } else {
    await mainWindow.loadURL(
      rendererUrl,
    )
  }
}

const gotSingleInstanceLock =
  app.requestSingleInstanceLock()

if (!gotSingleInstanceLock) {
  app.quit()
}

app.on(
  'second-instance',
  () => {
    if (mainWindow) {
      if (
        mainWindow.isMinimized()
      ) {
        mainWindow.restore()
      }

      mainWindow.focus()
    }
  },
)

app.whenReady().then(async () => {
  registerFrontendProtocol()

  if (app.isPackaged) {
    try {
      await startServices()
    } catch (error) {
      console.error(
        'Unable to start Semantta services:',
        error,
      )

      log(
        `Startup failed: ${error.message}`,
      )

      stopBackend()
      stopFuseki()

      if (IS_SMOKE_TEST) {
        app.exit(1)
        return
      }

      dialog.showErrorBox(
        'Semantta Startup Error',
        'Semantta could not start its required services.',
      )

      app.quit()
      return
    }
  }

  try {
    await createMainWindow()

    if (IS_SMOKE_TEST) {
      stopBackend()
      stopFuseki()

      log(
        'Semantta packaged smoke test completed successfully.',
      )

      app.exit(0)
      return
    }
  } catch (error) {
    console.error(
      'Semantta renderer failed:',
      error,
    )

    log(
      `Renderer startup failed: ${error.message}`,
    )

    stopBackend()
    stopFuseki()

    app.exit(1)
    return
  }

  app.on('activate', () => {
    if (
      BrowserWindow.getAllWindows().length === 0
    ) {
      createMainWindow()
    }
  })
})


app.on('before-quit', () => {
  stopBackend()
  stopFuseki()
})


app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})