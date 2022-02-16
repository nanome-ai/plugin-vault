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

- `--https`

  Enable HTTPS using a self-signed certificate. If port is not set, port will default to 443.

- `--keep-files-days days`

  Automatically delete files that haven't been accessed in a given number of days. Example: to delete untouched files after 2 weeks: `--keep-files-days 14`

- `--ui-message message`

  Add a custom message to the web UI, appearing right under the "Nanome Vault" at the top of the page. Example `--ui-message "Hello, Vault!"`

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

Note: this will only work if the Vault server is running on the default port (without using the `-w` option). To work with a non-default port, change the proxy settings in `vue.config.js`.

## License

MIT
