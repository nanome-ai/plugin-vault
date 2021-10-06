import argparse
import os
import socket
import tempfile

import nanome
from nanome.util import async_callback, Logs
from nanome.util.enums import Integrations, NotificationTypes

from .menus import VaultMenu
from .VaultManager import VaultManager
from . import Workspace

DEFAULT_WEB_PORT = 80
HTTPS_PORT = 443
EXPORT_LOCATIONS = ['Workspaces', 'Structures', 'Recordings', 'Pictures', 'Browse']

# Plugin instance (for Nanome)
class Vault(nanome.AsyncPluginInstance):
    def start(self):
        self.integration.import_file = lambda _: self.on_run()
        self.integration.export_locations = lambda req: req.send_response(EXPORT_LOCATIONS)
        self.integration.export_file = self.on_export_integration

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

    @async_callback
    async def on_export_integration(self, request):
        await self.on_presenter_change()
        (location, filename, data) = request.get_args()

        if location == 'Browse':
            self.menu.open_for_integration(request)
        else:
            path = os.path.join(self.account, location)
            r = self.vault.add_file(path, filename, data)
            request.send_response(r.ok)

    @async_callback
    async def on_presenter_change(self):
        info = await self.request_presenter_info()
        if not info.account_id:
            return

        in_account = self.account in self.menu.path
        self.account = info.account_id
        self.vault.create_path(self.account)

        if not self.menu.menu.enabled:
            return

        if in_account:
            self.menu.path = '.'
            self.menu.open_folder('.')
        else:
            self.menu.update()

    async def load_file(self, name):
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
                await self.send_files_to_load(file_path)

        # macro
        elif extension == 'lua':
            with open(file_path, 'r') as f:
                macro = nanome.api.macro.Macro()
                macro.title = item_name
                macro.logic = f.read()
                macro.save()
            msg = f'Macro "{item_name}" added'

        elif extension in self.extensions['supported'] + self.extensions['extras']:
            await self.send_files_to_load(file_path)

        else:
            error = f'Extension not yet supported: {extension}'
            self.send_notification(NotificationTypes.error, error)
            Logs.warning(error)

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

            r = self.vault.add_file(path, file_name, f.read(), key)
            if r.ok:
                self.send_notification(NotificationTypes.success, f'"{file_name}" saved')
            else:
                self.send_notification(NotificationTypes.error, r.json()['error']['message'])

        temp.close() # unsure if needed
        os.remove(temp.name)

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
            if port == HTTPS_PORT:
                url = 'https://' + url
            else:
                url += ':' + str(port)
        return url


def create_parser():
    """Create command line parser For Plugin.

    rtype: argsparser: args parser
    """
    parser = argparse.ArgumentParser(description='Parse Arguments to set up Vault Plugin and related Services.')
    parser.add_argument('--api-key', dest='api_key', help='Key for connecting to Vault Manager API', required=False)
    parser.add_argument('-s', '--https', '--ssl-cert', dest='https', action='store_true', help='connect to Vault Server via HTTPS')
    parser.add_argument('-u', '--url', dest='url', type=str, help='Url pointing to Vault Server.')
    parser.add_argument('-w', '--web-port', dest='web_port', type=int, help='Custom port for connecting to Vault Server.', required=False)
    return parser


def main():
    # Plugin server (for Web)

    parser = create_parser()
    args, _ = parser.parse_known_args()
    
    # args = None
    https = args.https
    url = args.url
    port = args.web_port
    api_key = args.api_key

    if port is None:
        port = HTTPS_PORT if https else DEFAULT_WEB_PORT

    # Plugin
    integrations = [
        Integrations.import_file,
        Integrations.export_locations,
        Integrations.export_file,
    ]
    plugin = nanome.Plugin('Vault', 'Use your browser to upload files and folders to make them available in Nanome.', 'Files', False, integrations=integrations)
    plugin.set_plugin_class(Vault)
    plugin.set_custom_data(url, port, api_key)
    plugin.run()

if __name__ == '__main__':
    main()
