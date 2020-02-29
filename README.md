# Nanome - Vault

### A Nanome plugin that creates a web interface to upload files and make them available in Nanome

Nanome Vault will start a web server. Other people can upload molecules or other files to it, and they will appear in Nanome. This works for both Nanome & Nanome Curie (Quest edition).

Supports Nanome v1.16 and up. For previous versions, please check out [Vault v1.2.1](https://github.com/nanome-ai/plugin-vault/tree/v1.2.1)

### Files Supported

Vault natively supports:

- Molecules: `.pdb` `.sdf` `.cif`
- Documents: `.pdf`
- Images: `.png` `.jpg`
- Workspaces: `.nanome`
- Macros: `.lua`

Using [Gotenberg](https://github.com/thecodingmachine/gotenberg), the following are converted to PDF:

- Documents: `.doc` `.docx` `.txt` `.rtf` `.odt`
- Presentations: `.ppt` `.pptx` `.odp`

### Installation

It is highly recommended to run Vault in Docker; please see the Docker Usage section.

```sh
$ pip3 install nanome-vault --upgrade
```

### Usage

To start the plugin:

```sh
$ nanome-vault -a <plugin_server_address> [optional args]
```

On Linux, you might have to start using `sudo nanome-vault` to listen on port 80.

To utilize file conversion (to support files like `.ppt` and `.doc`), launch Gotenberg:

```sh
$ docker run --rm -p 3000:3000 thecodingmachine/gotenberg:6
```

and add `-c http://localhost:3000` as an argument when you start the plugin.

#### Optional arguments:

- `-c url` or `--converter-url url`

  The url of the Gotenberg service to use for conversion. Defaults to `http://vault-converter:3000` for use inside Docker. Example: `-c http://localhost:3000`

- `-k days` or `--keep-files-days days`

  Automatically delete files that haven't been accessed in a given number of days. Example: to delete untouched files after 2 weeks: `-k 14`

- `-s certfile` or `--ssl-cert certfile`

  SSL certificate to be used for HTTPS. If port is not set, port will default to 443. Example: `-s ./cert.pem`

  To generate a self signed certificate to use for local HTTPS:\
  `openssl req -new -x509 -keyout cert.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'`

- `-u url` or `--url url`

  The url to display in the plugin for accessing the Web UI. Example: `-u vault.example.com`

- `-w port` or `--web-port port`

  The port to use for the Web UI. Example: `-w 8080`

  Some OSes prevent the default port `80` from being used without elevated permissions, so this option may be used to change to an allowed port.

In Nanome:

- Activate Plugin
- Click Run
- Open your web browser, go to "127.0.0.1" (or your computer's IP address from another computer), and add supported files. Your files will appear in Nanome.

### Docker Usage

To run with Docker including Gotenberg:

```sh
$ cd docker
$ ./build.sh
$ ./deploy.sh -a <plugin_server_address> [optional args]
```

### Development

Ensure you have the latest `nanome` lib installed with:

```sh
$ pip3 install nanome --upgrade
```

Run the plugin and web server:

```sh
$ python run.py -a <plugin_server_address> [optional args]
```

#### Web UI Development

Run the Vue.js dev server in another terminal while plugin is running:

```sh
$ cd nanome_vault/WebUI
$ yarn install
$ yarn run serve
```

Note: this will only work if the plugin's web server is started on the default port (without using the `-w` option). To work with a non-default port, change the proxy settings in `vue.config.js`.

### License

MIT
