# Nanome - Vault

### A Nanome plugin that creates a web interface to upload files and make them available in Nanome

Nanome Vault will start a web server. Other people can upload molecules or other files to it, and they will appear in Nanome. This works for both Nanome & Nanome Curie (Quest edition).

Nanome Vault currently supports:

- Molecules: .pdb, .cif, .sdf
- Presentations: .pptx, .ppt, .odp
- Documents: .pdf
- Images: .png .jpg

### Installation

```sh
$ pip install nanome-vault
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

- `-k days`

  Automatically delete files that haven't been accessed in a given number of days. Example: to delete untouched files after 2 weeks: `-k 14`

- `-u url`

  The url to display in the plugin for accessing the Web UI. Example: `-u vault.example.com`

In Nanome:

- Activate Plugin
- Click Run
- Open your web browser, go to "127.0.0.1" (or your computer's IP address from another computer), and add supported files. Your files will appear in Nanome.

### License

MIT
