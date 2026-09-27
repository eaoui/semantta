const {
  app,
  BrowserWindow,
  dialog,
  net,
  protocol,
} = require('electron')

const path = require('node:path')

const { spawn } = require('node:child_process')
const http = require('node:http')

const DEV_SERVER_URL = 'http://localhost:3000'
const APP_SCHEME = 'semantta'
const APP_HOST = 'bundle'

const BACKEND_HOST = '127.0.0.1'
const BACKEND_PORT = 8000
const BACKEND_STARTUP_TIMEOUT = 30000

let mainWindow = null
let backendProcess = null


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
          resolve()
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
      startBackend()
      await waitForBackend()
    } catch (error) {
      console.error(
        'Unable to start the Semantta backend:',
        error,
      )

      dialog.showErrorBox(
        'Semantta Backend Error',
        'Semantta could not start its backend service.',
      )

      stopBackend()
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
})


app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})