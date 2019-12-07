import urllib
import http.server
import socketserver
from multiprocessing import Process
import cgi
import os
import traceback
import re
import json
import shutil
from datetime import datetime, timedelta

import nanome
from nanome.util import Logs

from . import VaultManager

ENABLE_LOGS = False

# Format, MIME type, Binary
TYPES = {
    "ico" : ("image/x-icon", True),
    "html" : ("text/html; charset=utf-8", False),
    "css" : ("text/css", False),
    "js" : ("text/javascript", False),
    "png" : ("image/png", True),
    "jpg" : ("image/jpeg", True),
    "" : ("text/plain", False) # Default
}

# Utility to get type specs tuple
def get_type(format):
    return TYPES.get(format, TYPES[''])

POST_REQS = {
    'upload': ['files'],
    'encrypt': ['key'],
    'decrypt': ['key']
}

SERVER_DIR = os.path.join(os.path.dirname(__file__), 'WebUI/dist')

# Class handling HTTP requests
class RequestHandler(http.server.BaseHTTPRequestHandler):
    def _parse_path(self):
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            return urllib.parse.unquote(parsed_url.path)
        except:
            pass

    # Utility function to set response header
    def _set_headers(self, code, type='text/html; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-type', type)
        self.end_headers()

    def _write(self, message):
        try:
            self.wfile.write(message)
        except:
            Logs.warning("Connection reset while responding", self.client_address)

    def _send_json_success(self, code=200):
        self._set_headers(code, 'application/json')
        response = dict()
        response['success'] = True
        self._write(json.dumps(response).encode("utf-8"))

    def _send_json_error(self, code, message):
        response = dict()
        response['success'] = False
        response['error'] = message
        self._set_headers(code, 'application/json')
        self._write(json.dumps(response).encode("utf-8"))

    # Special GET case: get file list
    def _send_list(self, path=None):
        if VaultServer.instance.keep_files_days > 0:
            self.file_cleanup()

        try:
            response = VaultManager.list_path(path)
            response['success'] = True
            self._set_headers(200, 'application/json')
            self._write(json.dumps(response).encode("utf-8"))
        except VaultManager.InvalidPathError:
            self._send_json_error(404, 'Not found')

    # Standard GET case: get a file
    def _try_get_resource(self, base_dir, path):
        path = os.path.join(base_dir, path)
        if not VaultManager.is_safe_path(path, base_dir):
            self._set_headers(404)
            return

        try:
            ext = path.split(".")[-1]
            (mime, is_binary) = get_type(ext)
            with open(path, 'rb' if is_binary else 'r') as f:
                data = f.read()
            self._set_headers(200, mime)
            self._write(data if is_binary else data.encode("utf-8"))
        except:
            self._set_headers(404)

    # Called on GET request
    def do_GET(self):
        path = self._parse_path()
        base_dir = SERVER_DIR
        is_file = re.search(r'\.[^/]+$', path) is not None

        # path in vault
        if path.startswith('/files'):
            path = path[7:]

            key = self.headers.get('vault-key')
            if not VaultManager.is_key_valid(path, key):
                self._send_json_error(403, 'Forbidden')
                return

            if not is_file:
                self._send_list(path or None)
                return
            else:
                base_dir = VaultManager.FILES_DIR

        # if path doesn't contain extension, serve index
        if not is_file:
            path = 'index.html'
        if path.startswith('/'):
            path = path[1:]

        self._try_get_resource(base_dir, path)

    # Called on POST request
    def do_POST(self):
        path = self._parse_path()
        if not path.startswith('/files'):
            self._send_json_error(403, "Forbidden")
            return
        path = path[7:]

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={'REQUEST_METHOD': 'POST'})

        if 'command' not in form:
            self._send_json_error(400, "Invalid command")
            return

        # commands: create, delete, upload, encrypt, decrypt
        command = form['command'].value

        # check if missing any required form data
        missing = [req for req in POST_REQS.get(command, []) if req not in form]
        if missing:
            self._send_json_error(400, "Missing required values: %s" % ', '.join(missing))
            return

        try:
            if command == 'create':
                success = VaultManager.create_path(path)
                if not success:
                    self._send_json_error(400, "Path already exists")
                    return

            elif command == 'delete':
                if not path or path == 'shared':
                    self._send_json_error(403, "Forbidden")
                    return

                success = VaultManager.delete_path(path)
                if not success:
                    self._send_json_error(500, "Error deleting " + path)
                    return

            elif command == 'upload':
                files = form['files']
                if not isinstance(files, list):
                    files = [files]

                for file in files:
                    filename = file.filename

                    if not VaultServer.file_filter(filename):
                        self._send_json_error(400, filename + " format not supported")
                        return

                    VaultManager.add_file(path, filename, file.file.read())

            elif command == 'encrypt':
                success = VaultManager.encrypt_folder(path, form['key'].value)
                if not success:
                    self._send_json_error(400, "Path contains an encrypted folder")
                    return

            elif command == 'decrypt':
                success = VaultManager.decrypt_folder(path, form['key'].value)
                if not success:
                    self._send_json_error(403, "Forbidden")
                    return

            else:
                self._send_json_error(400, "Invalid command")
                return

            self._send_json_success()

        except VaultManager.InvalidPathError:
            self._send_json_error(404, "Not found")

        except:
            Logs.warning("Server error:\n", traceback.format_exc())
            self._send_json_error(500, "Server error")

    # Override to prevent HTTP server from logging every request if ENABLE_LOGS is False
    def log_message(self, format, *args):
        if ENABLE_LOGS:
            http.server.BaseHTTPRequestHandler.log_message(self, format, *args)

    # Check file last accessed time and remove those older than 28 days
    def file_cleanup(self):
        server = VaultServer.instance

        # don't execute more than once every 5 min
        if datetime.today() - server.last_cleanup < timedelta(minutes=5):
            return

        server.last_cleanup = datetime.today()
        expiry_date = datetime.today() - timedelta(days=server.keep_files_days)

        for (dirpath, _, filenames) in os.walk(VaultManager.FILES_DIR):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                last_accessed = datetime.fromtimestamp(os.path.getatime(file_path))

                if last_accessed < expiry_date:
                    os.remove(file_path)

class VaultServer():
    def __init__(self, url, port, keep_files_days):
        VaultServer.instance = self
        self.url = url
        self.port = port
        self.keep_files_days = keep_files_days
        self.last_cleanup = datetime.fromtimestamp(0)
        self.__process = Process(target=VaultServer._start_process, args=(port,))

    @staticmethod
    def file_filter(name):
        valid_ext = (".pdb", ".sdf", ".cif", ".ppt", ".pptx", ".odp", ".pdf", ".png", ".jpg")
        return name.endswith(valid_ext)

    def start(self):
        self.__process.start()

    @classmethod
    def _start_process(cls, port):
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("", port), RequestHandler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
