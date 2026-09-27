const {
  app,
  BrowserWindow,
  dialog,
  net,
  protocol,
} = require('electron')

const path = require('node:path')
const fs = require('node:fs')
const os = require('node:os')

const { spawn } = require('node:child_process')
const http = require('node:http')

const DEV_SERVER_URL = 'http://localhost:3000'
const APP_SCHEME = 'semantta'
const APP_HOST = 'bundle'

const BACKEND_HOST = '127.0.0.1'
const BACKEND_PORT = 8000
const BACKEND_BASE_URL =
  `http://${BACKEND_HOST}:${BACKEND_PORT}`

const BACKEND_STARTUP_TIMEOUT = 30000

const FUSEKI_HOST = '127.0.0.1'
const FUSEKI_PORT = 3030
const FUSEKI_DATASET_NAME = 'obmms'

let mainWindow = null
let backendProcess = null


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
  const fusekiExecutable = getFusekiExecutable()
  const javaHome = getJavaHome()

  const databaseDir = path.join(
    getSemanttaDataDir(),
    'database',
    'fuseki',
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
    `--port=${FUSEKI_PORT}`,
    `/${FUSEKI_DATASET_NAME}`,
  ]

  const env = {
    ...process.env,
    JAVA_HOME: javaHome,
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

  if (process.platform === 'win32') {
    fusekiProcess = spawn(
      fusekiExecutable,
      args,
      {
        cwd: path.dirname(
          fusekiExecutable,
        ),
        env,
        shell: true,
        windowsHide: true,
        stdio: 'ignore',
      },
    )
  } else {
    fusekiProcess = spawn(
      fusekiExecutable,
      args,
      {
        cwd: path.dirname(
          fusekiExecutable,
        ),
        env,
        detached: true,
        stdio: 'ignore',
      },
    )
  }

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

  return new Promise(
    (resolve, reject) => {
      const check = () => {
        if (
          Date.now() - startedAt >
          BACKEND_STARTUP_TIMEOUT
        ) {
          reject(
            new Error(
              'Timed out waiting for Fuseki.',
            ),
          )
          return
        }

        const request = http.get(
          `http://${FUSEKI_HOST}:${FUSEKI_PORT}/$/ping`,
          (response) => {
            response.resume()

            if (
              response.statusCode === 200
            ) {
              resolve()
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

  const pid =
    fusekiProcess.pid

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
        // Fuseki is already stopped.
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
          `${BACKEND_BASE_URL}${requestUrl.pathname}${requestUrl.search}`

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

        return net.fetch(
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
        return await net.fetch(
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
        SEMANTTA_PORT: String(BACKEND_PORT),
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

  return new Promise((resolve, reject) => {
    const check = () => {
      if (
        Date.now() - startedAt >
        BACKEND_STARTUP_TIMEOUT
      ) {
        reject(
          new Error(
            'Timed out waiting for the Semantta backend.',
          ),
        )
        return
      }

      const request = http.get(
        `http://${BACKEND_HOST}:${BACKEND_PORT}/api/health`,
        (response) => {
          response.resume()

          if (
            response.statusCode === 200 ||
            response.statusCode === 503
          ) {
            resolve()
            return
          }

          setTimeout(
            check,
            250,
          )
        },
      )

      request.on('error', () => {
        setTimeout(check, 250)
      })

      request.setTimeout(1000, () => {
        request.destroy()
        setTimeout(check, 250)
      })
    }

    check()
  })
}


function stopBackend() {
  if (!backendProcess) {
    return
  }

  backendProcess.kill()
  backendProcess = null
}


function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'Semantta',

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
}


app.whenReady().then(async () => {
  registerFrontendProtocol()

  if (app.isPackaged) {
    try {
      startFuseki()
      await waitForFuseki()

      startBackend()
      await waitForBackend()
    } catch (error) {
      console.error(
        'Unable to start Semantta services:',
        error,
      )

      dialog.showErrorBox(
        'Semantta Startup Error',
        'Semantta could not start its required backend services.',
      )

      stopBackend()
      stopFuseki()

      app.quit()
      return
    }
  }

  createMainWindow()

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