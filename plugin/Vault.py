import argparse
import os
import socket
import tempfile

import nanome
from nanome.util import async_callback, Logs
from nanome.util.enums import Integrations, NotificationTypes

from .menus import VaultMenu
from .OBJLoader import OBJLoader
from .SceneViewer import SceneViewer
from .VaultManager import VaultManager
from . import WorkspaceSerializer

EXPORT_LOCATIONS = ['Workspaces', 'Structures', 'Recordings', 'Pictures', 'Browse']


class Vault(nanome.AsyncPluginInstance):

    def start(self):
        self.integration.import_file = lambda _: self.on_run()
        self.integration.export_locations = lambda req: req.send_response(EXPORT_LOCATIONS)
        self.integration.export_file = self.on_export_integration

        self.set_plugin_list_button(self.PluginListButtonType.run, 'Open')

        # set to empty string to read/write macros in Macros folder
        nanome.api.macro.Macro.set_plugin_identifier('')

        self.account = 'user-00000000'
        self.org = None

        external_url = self.custom_data[0]
        api_key = self.custom_data[1]
        internal_url = self.custom_data[2]

        self.menu = VaultMenu(self, external_url)
        self.vault = VaultManager(api_key, internal_url)
        self.obj_loader = OBJLoader(self)
        self.scene_viewer = SceneViewer(self)
        self.extensions = self.vault.get_extensions()

    def on_run(self):
        self.on_presenter_change()
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
        in_account = self.account in self.menu.path
        in_org = self.org and self.org in self.menu.path
        if in_account or in_org:
            self.menu.path = '.'

        info = await self.request_presenter_info()
        if not info.account_id:
            return

        self.account = info.account_id
        self.vault.create_path(self.account)

        if info.has_org:
            self.org = f'org-{info.org_id}'
            self.vault.create_path(self.org)
        else:
            self.org = None

        if not self.menu.menu.enabled:
            return

        self.menu.open_folder('.')

    def on_complex_list_changed(self):
        self.scene_viewer.on_scene_changed()

    async def load_or_queue_file(self, temp_dir, name, out_queue):
        item_name, extension = name.rsplit('.', 1)

        path = os.path.join(self.menu.path, name)
        key = self.menu.folder_key

        file_path = os.path.join(temp_dir.name, name)
        self.vault.get_file(path, key, file_path)

        msg = None

        # workspace
        if extension == 'nanome':
            try:
                with open(file_path, 'rb') as f:
                    workspace = WorkspaceSerializer.workspace_from_data(f.read())
                    await self.update_workspace(workspace)
                msg = f'Workspace "{item_name}" loaded'
            except Exception:
                out_queue.append(file_path)

        # scene viewer
        elif extension == 'nanoscenes':
            try:
                with open(file_path, 'rb') as f:
                    scenes = WorkspaceSerializer.scenes_from_data(f.read())
                self.scene_viewer.load(item_name, scenes)
                msg = f'Scenes "{item_name}" loaded'
            except Exception as e:
                error = f'Scenes: {item_name}" failed to load'
                self.send_notification(NotificationTypes.error, error)
                Logs.warning(e)

        # macro
        elif extension == 'lua':
            with open(file_path, 'r') as f:
                macro = nanome.api.macro.Macro()
                macro.title = item_name
                macro.logic = f.read()
                macro.save()
            msg = f'Macro "{item_name}" added'

        elif extension == 'obj':
            tex_path = None
            for ext in ['.png', '.jpg', '.jpeg']:
                tex_name = f'{item_name}{ext}'
                tex_in = os.path.join(self.menu.path, tex_name)
                tex_out = os.path.join(temp_dir.name, tex_name)
                if self.vault.get_file(tex_in, key, tex_out):
                    tex_path = tex_out
                    break
            try:
                await self.obj_loader.load(item_name, file_path, tex_path)
                msg = f'OBJ "{item_name}" loaded'
            except Exception as e:
                error = f'OBJ "{item_name}" failed to load'
                self.send_notification(NotificationTypes.error, error)
                Logs.warning(e)

        elif extension in self.extensions['supported'] + self.extensions['extras']:
            out_queue.append(file_path)

        else:
            error = f'Extension not yet supported: {extension}'
            self.send_notification(NotificationTypes.error, error)
            Logs.warning(error)

        if msg is not None:
            self.send_notification(NotificationTypes.success, msg)

    async def load_files(self, names):
        temp = tempfile.TemporaryDirectory()
        send_files = []

        for name in names:
            await self.load_or_queue_file(temp, name, send_files)

        if send_files:
            self.send_files_to_load(send_files)

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

        temp.close()  # unsure if needed
        os.remove(temp.name)


def create_parser():
    """Create command line parser For Vault Plugin.

    rtype: argsparser: args parser
    """
    parser = argparse.ArgumentParser(description='Parse Arguments to set up Vault Plugin and related Services.')
    plugin_group = parser.add_argument_group('Base Arguments')
    vault_group = parser.add_argument_group('Vault Arguments')

    # Add arguments from shared Plugin argparser, so that --help will show all possible arguments you can pass.
    base_parser = nanome.Plugin.create_parser()
    for action in base_parser._actions:
        if action.dest == 'help':
            continue
        plugin_group._add_action(action)

    # Add Vault specific arguments
    vault_group.add_argument(
        '--api-key',
        dest='api_key',
        default=os.environ.get("API_KEY", ""),
        help=argparse.SUPPRESS,
        required=False)
    vault_group.add_argument(
        '-s', '--https', '--ssl-cert',
        dest='https',
        action='store_true',
        default=os.environ.get("HTTPS", None),
        help='Enable HTTPS on the Vault Web UI')
    vault_group.add_argument(
        '-u', '--url', '--external_url',
        dest='external_url',
        type=str,
        default=os.environ.get("VAULT_URL", None),
        help='Vault Web UI URL. If omitted, IP address will be shown in plugin menu.')
    vault_group.add_argument(
        '--internal-url',
        dest='internal_url',
        type=str,
        default=os.environ.get('INTERNAL_URL', 'http://vault-server'),
        help='URL used for inter-container communication between vault and vault-server')
    vault_group.add_argument(
        '-w', '--web-port',
        dest='web_port',
        type=int,
        default=os.environ.get('VAULT_WEB_PORT', None),
        help='Custom port for connecting to Vault Web UI.',
        required=False)
    return parser


def get_default_url():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        url = s.getsockname()[0]
    except:
        url = 'localhost'
    finally:
        s.close()
    return url


def main():
    # Plugin server (for Web)
    parser = create_parser()
    args, _ = parser.parse_known_args()

    api_key = args.api_key
    https = args.https
    port = args.web_port
    external_url = args.external_url
    internal_url = args.internal_url

    if external_url is None:
        external_url = get_default_url()
    if https and not external_url.startswith('https://'):
        external_url = f'https://{external_url}'
    if port:
        external_url = f'{external_url}:{port}'

    # Plugin
    integrations = [
        Integrations.import_file,
        Integrations.export_locations,
        Integrations.export_file,
    ]
    plugin = nanome.Plugin('Vault', 'Use your browser to upload files and folders to make them available in Nanome.', 'Files', False, integrations=integrations)
    plugin.set_plugin_class(Vault)
    plugin.set_custom_data(external_url, api_key, internal_url)
    plugin.run()


if __name__ == '__main__':
    main()
