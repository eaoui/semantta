# Installation

Semantta is distributed as a self-contained desktop application. The packaged application includes the runtime components required to run Semantta, so users do not need to separately install Python, Node.js, Java, or Apache Jena Fuseki.

Download the latest release from the [GitHub Releases](https://github.com/eaoui/semantta/releases) page.

## Supported Packages

| Platform | Architecture | Package                 |
| -------- | ------------ | ----------------------- |
| Linux    | x64          | AppImage                |
| Linux    | x64          | Debian package (`.deb`) |
| Windows  | x64          | NSIS installer (`.exe`) |
| macOS    | arm64        | DMG                     |
| macOS    | arm64        | ZIP                     |
| macOS    | x64          | DMG                     |
| macOS    | x64          | ZIP                     |

## Linux

### AppImage

Download the AppImage and make it executable:

```bash
chmod +x Semantta-<version>-linux-x64.AppImage
```

Then run it:

```bash
./Semantta-<version>-linux-x64.AppImage
```

The AppImage does not require a separate installation step.

### Debian package

Install the `.deb` package with:

```bash
sudo apt install ./Semantta-<version>-linux-x64.deb
```

Semantta will then be available as a normal installed application.

APT and Arch/Pacman repository distribution are planned for a future release.

## Windows

Download the Windows `.exe` installer and run it.

Follow the installation process shown by the installer.

The current Windows build is not code-signed, so Windows may display a security warning.

## macOS

Download either the DMG or ZIP package.

### DMG

1. Open the DMG file.
2. Copy `Semantta.app` to the Applications directory.
3. Launch Semantta.

### ZIP

1. Extract the ZIP archive.
2. Move `Semantta.app` to the Applications directory.
3. Launch Semantta.

The current macOS builds are not signed or notarized, so macOS may display a security warning.

## Verifying Downloads

Each GitHub Release includes a `SHA256SUMS` file containing SHA-256 checksums for all distributable packages.

### Linux

```bash
sha256sum -c SHA256SUMS
```

### macOS

```bash
shasum -a 256 -c SHA256SUMS
```

### Windows PowerShell

Calculate the checksum of the downloaded installer:

```powershell
Get-FileHash .\Semantta-<version>-win-x64.exe -Algorithm SHA256
```

Compare the resulting hash with the corresponding value in `SHA256SUMS`.

## User Data

Semantta stores user data separately from the application installation directory.

This includes, where applicable:

* ontologies
* metadata
* database data
* plugins
* themes
* settings and preferences
* cache
* logs

Updating or replacing the application does not intentionally remove this user data.

## Updating

Install a newer Semantta release using the normal installation method for your platform.

User data is stored separately from the application installation and is intended to survive application updates and replacement.

## Security and Code Signing

The current Semantta Windows, Linux, and macOS release packages are not distributed with commercial code-signing certificates.

Windows code signing, macOS Developer ID signing, and macOS notarization are planned for a later stage.

Linux package-manager repository signing will be implemented when APT and Arch/Pacman repositories are introduced.
