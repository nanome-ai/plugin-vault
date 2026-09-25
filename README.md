# Nanome - Vault

### A Nanome Plugin that creates a web interface to upload files and make them available in Nanome

Nanome Vault will start a web server. Other people can upload molecules or other files to it, and they will appear in Nanome. This works for both Nanome & Nanome Curie (Quest edition).

Supports Nanome v1.16 and up. For previous versions, please check out [Vault v1.2.1](https://github.com/nanome-ai/plugin-vault/tree/v1.2.1)

### Files Supported

Vault natively supports:

- Molecules: `.cif` `.mol2` `.pdb` `.sdf` `.smiles` `.xyz`
- 3rd party files: `.ccp4` `.dsn6` `.dx` `.mae` `.moe` `.pqr` `.pse` `.psf`
- Documents: `.pdf`
- Trajectories: `.dcd` `.gro` `.trr` `.xtc`
- Images: `.png` `.jpg`
- Spatial Recordings: `.nanosr`
- Workspaces: `.nanome`
- Macros: `.lua`

Using [Gotenberg](https://github.com/thecodingmachine/gotenberg), the following are converted to PDF:

- Documents: `.doc` `.docx` `.txt` `.rtf` `.odt`
- Presentations: `.ppt` `.pptx` `.odp`

### Web UI

- **Select** files and folders with a click, ctrl/cmd-click, shift-click, the checkboxes, or ctrl/cmd+A. Esc or a click on empty space clears the selection.
- **Download** a file with a double-click or its right-click menu. A folder downloads as a zip from its right-click menu, and a selection of several items downloads as one zip from the toolbar or the right-click menu. Files in an encrypted folder are decrypted with its key. Encrypted folders inside a selection need their own key, so they are left out and named after the download starts.
- **Open in Nanome 2** is in the right-click menu of files Nanome 2 can use, for one file or a selection:
  - Structure files (`.pdb` `.pqr` `.cif` `.mmcif` `.sdf` `.mol2` `.xyz`) load into a new Nanome 2 workspace, or into an existing one picked from a list of the user's workspaces (most recently opened first). Each file is loaded with its default representations, as the Nanome 2 web app does, into the workspace's first scene.
  - v1 sessions (`.nanome` `.nanoscenes`) are converted with the Nanome v1 Session Importer tool on the Nanome 2 web app (MARA) into a new workspace each, which is read back and checked. The import code comes from [nanome-ai/open-in-nanome-2](https://github.com/nanome-ai/open-in-nanome-2) (`server/ui/src/nanome2/pipeline.js`, copied without its references to private source files), which also documents each step and its limits.

  Both use the Vault login, so they ask for one first. Progress and a link to the workspace show in a card at the bottom left. The work runs in the page, so the tab has to stay open until it finishes; converting a large session can take several minutes. A banner at the top of the page points Classic users to Nanome 2 whenever this is enabled.

## Usage

To run Vault in a Docker container:

```sh
$ cd docker
$ ./build.sh
$ ./deploy.sh -a <plugin_server_address> [optional args]
```

### Optional arguments:

- `-c url` or `--converter-url url`

  The url of the Gotenberg service to use for conversion. Defaults to `http://vault-converter:3000` for use inside Docker. Example: `-c http://localhost:3000`

- `--enable-auth`

  Enables enforced authentication, preventing users from accessing files in the Web UI unless they are logged in.

- `--disable-nanome2`

  Hide Open in Nanome 2 and the Nanome 2 banner, for example when browsers using this Vault cannot reach the Nanome 2 web app.

- `--https`

  Enable HTTPS using a self-signed certificate. If port is not set, port will default to 443.

- `--keep-files-days days`

  Automatically delete files that haven't been accessed in a given number of days. Example: to delete untouched files after 2 weeks: `--keep-files-days 14`

- `--nanome2-url url`

  The Nanome 2 web app that Open in Nanome 2 uses. Defaults to `https://app.nanome.ai`.

- `--nanome2-tool-id id`

  The id of the Nanome v1 Session Importer tool on that web app. Defaults to `01M32ZZKF3RPH80EBW73T2VVKZ`.

- `--ui-message message`

  Add a custom message to the web UI, appearing right under the "Nanome Vault" at the top of the page. There is an issue with spaces in the message and passing the arg to docker, so instead replace any space in the message with an underscore and it will be converted back into a space. Example `--ui-message "Hello,_Vault!"`

- `-u url` or `--url url`

  The url to display in the plugin for accessing the Web UI. Example: `-u vault.example.com`

- `--user-storage size`

  The size of the user storage, defaults to unlimited. Supports suffixes: `k`, `m`, `g`. Example: `--user-storage 1g`. When user storage is exceeded, new files will fail to upload and a message will be displayed.

- `-w port` or `--web-port port`

  The port to use for the Web UI. Example: `-w 8080`

  Some OSes prevent the default port `80` from being used without elevated permissions, so this option may be used to change to an allowed port.

In Nanome:

- Activate Plugin
- Click Run
- Open your web browser, go to "127.0.0.1" (or your computer's IP address from another computer), and add supported files. Your files will appear in Nanome.

## Development

To run Vault plugin with autoreload:

```sh
$ python3 -m pip install -r requirements.txt
$ python3 run.py -r -a <plugin_server_address> [optional args]
```

---

To run Vault server with autoreload:

```sh
$ cd server
$ yarn install
$ yarn run dev
```

Note: when running outside of Docker, you will need to replace "vault-server" in VaultManager.py with "localhost".

---

To run the WebUI with autoreload:

```sh
$ cd server/ui
$ yarn install
$ yarn run serve
```

Note: this proxies API requests to a Vault server on `http://localhost`. For a server on another port, set `VAULT_SERVER`, e.g. `VAULT_SERVER=http://localhost:8420 yarn run serve`.

The UI build (Vue CLI 3, webpack 4) needs Node 16, the version in `docker/server.Dockerfile`.

---

To run the tests (Node 16 or newer):

```sh
$ cd server && yarn test
$ cd server/ui && yarn test
```

## License

MIT
