# Nanome - Vault

### A Nanome plugin that creates a web interface to upload files and make them available in Nanome

Nanome Vault will start a web server. Other people can upload molecules or other files to it, and they will appear in Nanome. This works for both Nanome & Nanome Curie (Quest edition).

Nanome Vault currently supports:

- Workspaces: .nanome
- Macros: .lua
- Molecules: .pdb, .cif, .sdf
- Presentations: .pptx, .ppt, .odp
- Documents: .pdf
- Images: .png .jpg

### Installation

```sh
$ pip3 install nanome-vault --version
```

In order to load non-molecular files with Nanome Vault, the following applications/packages should be installed on the computer running the plugin:

- ImageMagick
- LibreOffice
- Ghostscript

For Windows especially, make sure that these applications are in the PATH environment variable (the folder containing simpress.exe should be in PATH for LibreOffice)

On Ubuntu, a security policy might prevent ImageMagick from converting PDF to images.
It can be removed by running:

```sh
$ sudo mv /etc/ImageMagick-6/policy.xml /etc/ImageMagick-6/policy.xmlout
```

See this answer on AskUbuntu for more information: https://askubuntu.com/a/1081907

### Usage

To start the plugin:

```sh
$ nanome-vault -a <plugin_server_address>
```

On Linux, you might have to start using `sudo nanome-vault` to listen on port 80.

#### Optional arguments:

- `-w port`

  The port to use for the Web UI. Example: `-w 8080`

  Some OSes prevent the default port `80` from being used without elevated permissions, so this option may be used to change to an allowed port.

- `-s ssl-certificate`

  SSL certificate to be used for HTTPS. If port is not set, port will default to 443. Example: `-s ./cert.pem`

  To generate a self signed certificate to use for local HTTPS:\
  `openssl req -new -x509 -keyout cert.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'`

- `-k days`

  Automatically delete files that haven't been accessed in a given number of days. Example: to delete untouched files after 2 weeks: `-k 14`

- `-u url`

  The url to display in the plugin for accessing the Web UI. Example: `-u vault.example.com`

In Nanome:

- Activate Plugin
- Click Run
- Open your web browser, go to "127.0.0.1" (or your computer's IP address from another computer), and add supported files. Your files will appear in Nanome.

### Development

Ensure you have the latest `nanome` lib installed with:

```sh
$ pip3 install nanome --upgrade
```

Run the plugin and web server:

```sh
$ python -m nanome_vault.Vault -a <plugin_server_address> [optional args]
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
