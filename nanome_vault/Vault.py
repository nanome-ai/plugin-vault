import sys
import os
import socket
import tempfile
from functools import partial

import nanome
from nanome.util import Logs
from nanome.util.enums import NotificationTypes
from nanome.api.structure import Complex

from .VaultServer import VaultServer, EXTENSIONS
from .menus import VaultMenu
from . import VaultManager, Workspace

DEFAULT_WEB_PORT = 80
DEFAULT_CONVERTER_URL = 'http://vault-converter:3000'
DEFAULT_KEEP_FILES_DAYS = 0

# Plugin instance (for Nanome)
class Vault(nanome.PluginInstance):
    def start(self):
        self.set_plugin_list_button(self.PluginListButtonType.run, 'Open')

        # set to empty string to read/write macros in Macros folder
        nanome.api.macro.Macro.set_plugin_identifier('')

        self.account = 'user-00000000'
        self.menu = VaultMenu(self, self.get_server_url())
        self.on_run()

    def on_run(self):
        self.on_presenter_change()
        self.menu.open_folder('.')
        self.menu.show_menu()

    def on_presenter_change(self):
        self.request_presenter_info(self.update_account)

    def update_account(self, info):
        if not info.account_id:
            return

        self.account = info.account_id
        VaultManager.create_path(self.account)
        self.menu.update()

    def load_file(self, name, callback):
        item_name, extension = name.rsplit('.', 1)

        path = self.menu.path
        file_path = VaultManager.get_vault_path(os.path.join(path, name))

        temp = None
        if self.menu.locked_path:
            key = self.menu.folder_key
            temp = tempfile.TemporaryDirectory()
            temp_path = os.path.join(temp.name, name)
            VaultManager.decrypt_file(file_path, key, temp_path)
            file_path = temp_path

        msg = None

        # workspace
        if extension == 'nanome':
            try:
                with open(file_path, 'rb') as f:
                    workspace = Workspace.from_data(f.read())
                    self.update_workspace(workspace)
                msg = f'Workspace "{item_name}" loaded'
            except:
                self.send_files_to_load(file_path)
            finally:
                callback()

        # macro
        elif extension == 'lua':
            with open(file_path, 'r') as f:
                macro = nanome.api.macro.Macro()
                macro.title = item_name
                macro.logic = f.read()
                macro.save()
            msg = f'Macro "{item_name}" added'
            callback()

        elif extension in EXTENSIONS['supported'] + EXTENSIONS['extras']:
            self.send_files_to_load(file_path, lambda _: callback())

        else:
            error = f'Extension not yet supported: {extension}'
            self.send_notification(NotificationTypes.error, error)
            Logs.warning(error)
            callback()

        if msg is not None:
            self.send_notification(NotificationTypes.success, msg)

        if temp:
            temp.cleanup()

    def save_file(self, item, name, extension):
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)

        # structures / workspace
        if extension in ['pdb', 'sdf', 'cif', 'lua', 'nanome']:
            mode = 'wb' if extension == 'nanome' else 'w'
            with open(temp.name, mode) as f:
                f.write(item)

        with open(temp.name, 'rb') as f:
            path = VaultManager.get_vault_path(self.menu.path)
            key = self.menu.folder_key
            file_name = f'{name}.{extension}'

            VaultManager.add_file(path, file_name, f.read(), key)
            self.send_notification(NotificationTypes.success, f'"{file_name}" saved')

        temp.close() # unsure if needed
        os.remove(temp.name)

    def send_complexes(self, complexes, callback):
        self.add_to_workspace(complexes)
        self.send_notification(NotificationTypes.success, f'"{complexes[0].name}" loaded')
        callback()

    def get_server_url(self):
        url, port = self.custom_data
        if url is not None:
            return url

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            url = s.getsockname()[0]
        except:
            url = '127.0.0.1'
        finally:
            s.close()

        if port != DEFAULT_WEB_PORT:
            url += ':' + str(port)
        return url

def main():
    # Plugin server (for Web)
    converter_url = DEFAULT_CONVERTER_URL
    enable_auth = False
    keep_files_days = DEFAULT_KEEP_FILES_DAYS
    ssl_cert = None
    url = None
    port = DEFAULT_WEB_PORT

    try:
        for i, arg in enumerate(sys.argv):
            if arg in ['-c', '--converter-url']:
                converter_url = sys.argv[i + 1]
            elif arg in ['--enable-auth']:
                enable_auth = True
            elif arg in ['--keep-files-days']:
                keep_files_days = int(sys.argv[i + 1])
            elif arg in ['-s', '--ssl-cert']:
                ssl_cert = sys.argv[i + 1]
            elif arg in ['-u', '--url']:
                url = sys.argv[i + 1]
            elif arg in ['-w', '--web-port']:
                port = int(sys.argv[i + 1])
    except:
        pass

    if ssl_cert is not None and port == DEFAULT_WEB_PORT:
        port = 443

    server = None
    def pre_run():
        nonlocal server
        server = VaultServer(port, ssl_cert, keep_files_days, converter_url, enable_auth)
        server.start()
    def post_run():
        server.stop()

    # Plugin
    plugin = nanome.Plugin('Vault', 'Use your browser to upload files and folders to make them available in Nanome.', 'Files', False)
    plugin.set_plugin_class(Vault)
    plugin.set_custom_data(url, port)
    plugin.pre_run = pre_run
    plugin.post_run = post_run
    plugin.run('127.0.0.1', 8888)

if __name__ == '__main__':
    main()
