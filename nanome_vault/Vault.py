import sys
import os
import socket
import tempfile
from functools import partial

import nanome
from nanome.util import Logs
from nanome.util.enums import NotificationTypes
from nanome.api.structure import Complex

from .menus import VaultMenu
from .VaultManager import VaultManager
from . import Workspace

DEFAULT_WEB_PORT = 80
EXPORT_LOCATIONS = ['Workspaces', 'Structures', 'Recordings', 'Pictures']

# Plugin instance (for Nanome)
class Vault(nanome.PluginInstance):
    def start(self):
        self.integration.import_file = lambda _: self.on_run()
        self.integration.export_locations = lambda req: req.send_response(EXPORT_LOCATIONS)
        self.integration.export_file = self.on_export_file

        self.set_plugin_list_button(self.PluginListButtonType.run, 'Open')

        # set to empty string to read/write macros in Macros folder
        nanome.api.macro.Macro.set_plugin_identifier('')

        self.account = 'user-00000000'
        self.menu = VaultMenu(self, self.get_server_url())
        self.vault = VaultManager(self.custom_data[2])
        self.extensions = self.vault.get_extensions()

    def on_run(self):
        self.on_presenter_change()
        self.menu.open_folder('.')
        self.menu.show_menu()

    def on_presenter_change(self):
        self.request_presenter_info(self.update_account)

    def on_export_file(self, request):
        (location, filename, data) = request.get_args()
        path = os.path.join(self.account, location)
        self.vault.add_file(path, filename, data)
        request.send_response(True)

    def update_account(self, info):
        if not info.account_id:
            return

        self.account = info.account_id
        self.vault.create_path(self.account)
        self.menu.update()

    def load_file(self, name, callback):
        item_name, extension = name.rsplit('.', 1)

        path = os.path.join(self.menu.path, name)
        key = self.menu.folder_key

        temp = tempfile.TemporaryDirectory()
        file_path = os.path.join(temp.name, name)
        self.vault.get_file(path, key, file_path)

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

        elif extension in self.extensions['supported'] + self.extensions['extras']:
            self.send_files_to_load(file_path, lambda _: callback())

        else:
            error = f'Extension not yet supported: {extension}'
            self.send_notification(NotificationTypes.error, error)
            Logs.warning(error)
            callback()

        if msg is not None:
            self.send_notification(NotificationTypes.success, msg)

        temp.cleanup()

    def save_file(self, item, name, extension):
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)

        # structures / workspace
        if extension in ['pdb', 'sdf', 'cif', 'lua', 'nanome']:
            mode = 'wb' if extension == 'nanome' else 'w'
            with open(temp.name, mode) as f:
                f.write(item)

        with open(temp.name, 'rb') as f:
            path = self.menu.path
            key = self.menu.folder_key
            file_name = f'{name}.{extension}'

            self.vault.add_file(path, file_name, f.read(), key)
            self.send_notification(NotificationTypes.success, f'"{file_name}" saved')

        temp.close() # unsure if needed
        os.remove(temp.name)

    def send_complexes(self, complexes, callback):
        self.add_to_workspace(complexes)
        self.send_notification(NotificationTypes.success, f'"{complexes[0].name}" loaded')
        callback()

    def get_server_url(self):
        url, port, _ = self.custom_data
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
    api_key = None
    https = False
    url = None
    port = None

    try:
        for i, arg in enumerate(sys.argv):
            if arg == '--api-key':
                api_key = sys.argv[i + 1]
            elif arg in ['--https', '-s', '--ssl-cert']:
                https = True
            elif arg in ['-u', '--url']:
                url = sys.argv[i + 1]
            elif arg in ['-w', '--web-port']:
                port = int(sys.argv[i + 1])
    except:
        pass

    if port is None:
        port = 443 if https else DEFAULT_WEB_PORT

    # Plugin
    plugin = nanome.Plugin('Vault', 'Use your browser to upload files and folders to make them available in Nanome.', 'Files', False)
    plugin.set_plugin_class(Vault)
    plugin.set_custom_data(url, port, api_key)
    plugin.run()

if __name__ == '__main__':
    main()
