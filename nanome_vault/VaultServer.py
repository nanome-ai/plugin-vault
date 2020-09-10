import cgi
import json
import os
import re
import requests
import sys
import traceback
import urllib
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from multiprocessing import Process
from socketserver import ThreadingMixIn
from threading import Thread
from time import sleep

import nanome
from nanome.util import Logs

from . import AESCipher, VaultManager

ENABLE_LOGS = False

# Format, MIME type, Binary
TYPES = {
    'ico': ('image/x-icon', True),
    'html': ('text/html; charset=utf-8', False),
    'css': ('text/css', False),
    'js': ('text/javascript', False),
    'png': ('image/png', True),
    'jpg': ('image/jpeg', True),
    '': ('application/octet-stream', True) # Default
}

# Utility to get type specs tuple
def get_type(format):
    return TYPES.get(format, TYPES[''])

POST_REQS = {
    'upload': ['files'],
    'rename': ['name'],
    'encrypt': ['key'],
    'verify': ['key'],
    'decrypt': ['key']
}

EXTENSIONS = {
    'supported': ['pdb', 'sdf', 'cif', 'pdf', 'png', 'jpg', 'nanome', 'lua'],
    'extras': ['ccp4', 'dcd', 'dsn6', 'dx', 'gro', 'mae', 'moe', 'mol2', 'pqr', 'pse', 'psf', 'smiles', 'trr', 'xtc', 'xyz'],
    'converted': ['ppt', 'pptx', 'doc', 'docx', 'txt', 'rtf', 'odt', 'odp']
}

SERVER_DIR = os.path.join(os.path.dirname(__file__), 'WebUI/dist')

# Class handling HTTP requests
class RequestHandler(BaseHTTPRequestHandler):
    def _parse_path(self):
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            return urllib.parse.unquote(parsed_url.path)
        except:
            Logs.error('Error parsing path:\n', traceback.format_exc())

    def _is_auth_valid(self, path):
        if not VaultServer.enable_auth:
            return True

        auth = self.headers.get('authorization')
        if auth is None:
            return False

        token = auth.split(' ')[-1]
        cached = VaultServer.auth_cache.get(token, None)

        if cached is None:
            try:
                headers = {'authorization': auth}
                r = requests.get('https://api.nanome.ai/user/session', headers=headers, timeout=10)
                r.raise_for_status()
                if r.status_code == 200:
                    json = r.json()
                    cached = {'user': json['results']['user']['unique']}
                    VaultServer.auth_cache[token] = cached
            except:
                return False

        user = None
        if cached:
            user = cached['user']
            cached['access'] = datetime.now()

        search = re.search(r'^user-[0-9a-f]{8}', path)
        if search is not None:
            return user == search[0]

        return user is not None

    # Utility function to set response header
    def _set_headers(self, code, type='text/html; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-type', type)
        self.end_headers()

    def _write(self, message):
        try:
            self.wfile.write(message)
        except:
            Logs.warning('Connection reset while responding', self.client_address)

    def _send_json(self, code=200, error=None, data=None):
        self._set_headers(code, 'application/json')
        response = {'success': code < 400}
        if error: response['error'] = error
        if data: response.update(data)
        self._write(json.dumps(response).encode('utf-8'))

    # Standard GET case: get a file
    def _try_get_resource(self, base_dir, path, key=None):
        path = os.path.join(base_dir, path)
        if not VaultManager.is_safe_path(path, base_dir):
            self._set_headers(404)
            return

        try:
            ext = path.split('.')[-1]
            (mime, is_binary) = get_type(ext)

            with open(path, 'rb' if is_binary else 'r') as f:
                data = f.read()

            if key is not None:
                data = AESCipher.decrypt(data, key)

            self._set_headers(200, mime)
            self._write(data if is_binary else data.encode('utf-8'))
        except:
            Logs.warning('Server error:\n', traceback.format_exc())
            self._send_json(500, error='Server error')

    # Called on GET request
    def do_GET(self):
        path = self._parse_path()
        if not path: return

        # get supported extensions info
        if path == '/info':
            self._send_json(data={'extensions': EXTENSIONS})
            return

        base_dir = SERVER_DIR
        is_file = re.search(r'\.[^/]+$', path) is not None
        key = None

        # path in vault
        if path.startswith('/files'):
            path = path[7:]

            if not self._is_auth_valid(path):
                self._send_json(401, error='Unauthorized')
                return

            key = self.headers.get('vault-key')
            if not VaultManager.is_key_valid(path, key):
                self._send_json(403, error='Forbidden')
                return

            if not is_file:
                try:
                    response = VaultManager.list_path(path)
                    self._send_json(data=response)
                except VaultManager.InvalidPathError:
                    self._send_json(404, error='Not found')
                return

            base_dir = VaultManager.FILES_DIR

        # if path doesn't contain extension, serve index
        if not is_file:
            path = 'index.html'
        if path.startswith('/'):
            path = path[1:]

        self._try_get_resource(base_dir, path, key)

    # Called on POST request
    def do_POST(self):
        path = self._parse_path()
        if not path: return

        if not path.startswith('/files'):
            self._send_json(403, error='Forbidden')
            return
        path = path[7:]

        if not self._is_auth_valid(path):
            self._send_json(401, error='Unauthorized')
            return

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST'})
        except:
            Logs.error('Error parsing form data:\n', traceback.format_exc())
            return

        if 'command' not in form:
            self._send_json(400, error='Invalid command')
            return

        # commands: create, delete, upload, encrypt, decrypt
        command = form['command'].value

        # check if missing any required form data
        missing = [req for req in POST_REQS.get(command, []) if req not in form]
        if missing:
            self._send_json(400, error=f'Missing required values: {", ".join(missing)}')
            return

        def check_auth(path, form):
            if VaultManager.is_path_locked(path):
                if 'key' not in form or not VaultManager.is_key_valid(path, form['key'].value):
                    self._send_json(403, error='Forbidden')
                    return False
            return True

        def check_error(success, error_message, error_code=500):
            if success:
                self._send_json(code=200)
            else:
                self._send_json(error_code, error=error_message)

        try:
            if command == 'create':
                if not check_auth(path, form): return
                success = VaultManager.create_path(path)
                check_error(success, 'Path already exists', 400)

            elif command == 'delete':
                if not path or path == 'shared':
                    self._send_json(403, error='Forbidden')
                    return

                if not check_auth(path, form): return
                success = VaultManager.delete_path(path)
                check_error(success, f'Error deleting {path}')

            elif command == 'rename':
                if not check_auth(path, form): return
                success = VaultManager.rename_path(path, form['name'].value)
                check_error(success, f'Error renaming {path}')

            elif command == 'upload':
                if not check_auth(path, form): return
                key = form['key'].value if 'key' in form else None

                files = form['files']
                if not isinstance(files, list):
                    files = [files]

                unsupported = [file.filename for file in files if not VaultServer.file_filter(file.filename)]
                if unsupported:
                    self._send_json(400, error=f'Format not supported: {", ".join(unsupported)}')
                    return

                failed = []
                for file in files:
                    name = file.filename
                    base, ext = name.rsplit('.', 1)
                    if ext in EXTENSIONS['converted']:
                        r = requests.post(VaultServer.converter_url + '/convert/office', files={name: file.file})
                        if r.status_code == 200:
                            name = base + '.pdf'
                            content = r.content
                        else:
                            failed.append(name)
                            continue
                    else:
                        content = file.file.read()
                    VaultManager.add_file(path, name, content, key)

                data = {'failed': failed} if failed else {}
                self._send_json(code=200, data=data)
                return

            elif command == 'encrypt':
                success = VaultManager.encrypt_folder(path, form['key'].value)
                check_error(success, 'Path contains an encrypted folder', 400)

            elif command == 'verify':
                success = VaultManager.is_key_valid(path, form['key'].value)
                self._send_json(data={'success': success})
                return

            elif command == 'decrypt':
                success = VaultManager.decrypt_folder(path, form['key'].value)
                check_error(success, 'Forbidden', 403)

            else:
                self._send_json(400, error='Invalid command')
                return

        except VaultManager.InvalidPathError:
            self._send_json(404, error='Not found')

        except:
            Logs.warning('Server error:\n', traceback.format_exc())
            self._send_json(500, error='Server error')

    # Override to prevent HTTP server from logging every request if ENABLE_LOGS is False
    def log_message(self, format, *args):
        if ENABLE_LOGS:
            BaseHTTPRequestHandler.log_message(self, format, *args)
            sys.stdout.flush()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def finish_request(self, request, client_address):
        request.settimeout(60)
        HTTPServer.finish_request(self, request, client_address)

class VaultServer():
    is_running = False
    last_auth_cleanup = None
    last_file_cleanup = None

    converter_url = None
    enable_auth = False
    keep_files_days = None

    auth_cache = {}

    def __init__(self, port, ssl_cert, keep_files_days, converter_url, enable_auth):
        self.__process = Process(target=VaultServer.start_process, args=(port, ssl_cert, keep_files_days, converter_url, enable_auth))

    def start(self):
        self.__process.start()

    def stop(self):
        self.__process.kill()

    @staticmethod
    def file_filter(name):
        ext = name.split('.')[-1]
        return ext in sum(EXTENSIONS.values(), [])

    @classmethod
    def start_process(cls, port, ssl_cert, keep_files_days, converter_url, enable_auth):
        VaultServer.is_running = True
        VaultServer.last_auth_cleanup = datetime.now()
        VaultServer.last_file_cleanup = datetime.now()

        VaultServer.converter_url = converter_url
        VaultServer.enable_auth = enable_auth
        VaultServer.keep_files_days = keep_files_days

        server = ThreadedHTTPServer(('', port), RequestHandler)

        if ssl_cert is not None:
            import ssl
            server.socket = ssl.wrap_socket(server.socket, certfile=ssl_cert, server_side=True)

        auth_cleanup_thread = None
        if VaultServer.enable_auth:
            auth_cleanup_thread = Thread(target=VaultServer.auth_cleanup)
            auth_cleanup_thread.start()

        file_cleanup_thread = None
        if VaultServer.keep_files_days:
            file_cleanup_thread = Thread(target=VaultServer.file_cleanup)
            file_cleanup_thread.start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.socket.close()
        except:
            Logs.error('Error in serve_forever', traceback.format_exc())

        VaultServer.is_running = False

        if auth_cleanup_thread:
            auth_cleanup_thread.join()

        if file_cleanup_thread:
            file_cleanup_thread.join()

    @staticmethod
    def auth_cleanup():
        while VaultServer.is_running:
            sleep(1)
            now = datetime.now()

            # only run auth cleanup every 10 minutes
            if now - VaultServer.last_auth_cleanup < timedelta(minutes=10):
                continue

            VaultServer.last_auth_cleanup = now
            expiry_time = now - timedelta(hours=1)

            # check token last accessed time and remove those older than 1 hour
            for token in list(VaultServer.auth_cache):
                if VaultServer.auth_cache[token]['access'] < expiry_time:
                    del VaultServer.auth_cache[token]

    @staticmethod
    def file_cleanup():
        while VaultServer.is_running:
            sleep(1)
            now = datetime.now()

            # only run file cleanup every 5 minutes
            if now - VaultServer.last_file_cleanup < timedelta(minutes=5):
                continue

            VaultServer.last_file_cleanup = now
            expiry_date = now - timedelta(days=VaultServer.keep_files_days)

            # check file last accessed time and remove those older than keep_files_days
            for root, _, files in os.walk(VaultManager.FILES_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    last_accessed = datetime.fromtimestamp(os.path.getatime(file_path))

                    if last_accessed < expiry_date:
                        os.remove(file_path)
