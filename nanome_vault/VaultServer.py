import cgi
import json
import os
import re
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
    "ico": ("image/x-icon", True),
    "html": ("text/html; charset=utf-8", False),
    "css": ("text/css", False),
    "js": ("text/javascript", False),
    "png": ("image/png", True),
    "jpg": ("image/jpeg", True),
    "": ("application/octet-stream", True) # Default
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

SERVER_DIR = os.path.join(os.path.dirname(__file__), 'WebUI/dist')

# Class handling HTTP requests
class RequestHandler(BaseHTTPRequestHandler):
    def _parse_path(self):
        try:
            parsed_url = urllib.parse.urlparse(self.path)
            return urllib.parse.unquote(parsed_url.path)
        except:
            Logs.error('Error parsing path:\n', traceback.format_exc())

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
        try:
            response = VaultManager.list_path(path)
            response['success'] = True
            self._set_headers(200, 'application/json')
            self._write(json.dumps(response).encode("utf-8"))
        except VaultManager.InvalidPathError:
            self._send_json_error(404, 'Not found')

    # Standard GET case: get a file
    def _try_get_resource(self, base_dir, path, key=None):
        path = os.path.join(base_dir, path)
        if not VaultManager.is_safe_path(path, base_dir):
            self._set_headers(404)
            return

        try:
            ext = path.split(".")[-1]
            (mime, is_binary) = get_type(ext)

            with open(path, 'rb' if is_binary else 'r') as f:
                data = f.read()

            if key is not None:
                data = AESCipher.decrypt(data, key)

            self._set_headers(200, mime)
            self._write(data if is_binary else data.encode("utf-8"))
        except:
            Logs.warning("Server error:\n", traceback.format_exc())
            self._send_json_error(500, "Server error")

    # Called on GET request
    def do_GET(self):
        path = self._parse_path()
        if not path: return

        base_dir = SERVER_DIR
        is_file = re.search(r'\.[^/]+$', path) is not None
        key = None

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

        self._try_get_resource(base_dir, path, key)

    # Called on POST request
    def do_POST(self):
        path = self._parse_path()
        if not path: return

        if not path.startswith('/files'):
            self._send_json_error(403, "Forbidden")
            return
        path = path[7:]

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST'})
        except:
            Logs.error('Error parsing form data:\n', traceback.format_exc())
            return

        if 'command' not in form:
            self._send_json_error(400, "Invalid command")
            return

        # commands: create, delete, upload, encrypt, decrypt
        command = form['command'].value

        # check if missing any required form data
        missing = [req for req in POST_REQS.get(command, []) if req not in form]
        if missing:
            self._send_json_error(400, f"Missing required values: {', '.join(missing)}")
            return

        def check_auth(path, form):
            if VaultManager.is_path_locked(path):
                if 'key' not in form or not VaultManager.is_key_valid(path, form['key'].value):
                    self._send_json_error(403, "Forbidden")
                    return False
            return True

        def check_error(success, error_message, error_code=500):
            if success:
                self._send_json_success()
            else:
                self._send_json_error(error_code, error_message)

        try:
            if command == 'create':
                if not check_auth(path, form): return
                success = VaultManager.create_path(path)
                check_error(success, "Path already exists", 400)

            elif command == 'delete':
                if not path or path == 'shared':
                    self._send_json_error(403, "Forbidden")
                    return

                if not check_auth(path, form): return
                success = VaultManager.delete_path(path)
                check_error(success, f"Error deleting {path}")

            elif command == 'rename':
                if not check_auth(path, form): return
                success = VaultManager.rename_path(path, form['name'].value)
                check_error(success, f"Error renaming {path}")

            elif command == 'upload':
                if not check_auth(path, form): return
                key = form['key'].value if 'key' in form else None

                files = form['files']
                if not isinstance(files, list):
                    files = [files]

                unsupported = [file.filename for file in files if not VaultServer.file_filter(file.filename)]
                if unsupported:
                    self._send_json_error(400, f"Format not supported: {', '.join(unsupported)}")
                    return

                for file in files:
                    VaultManager.add_file(path, file.filename, file.file.read(), key)

                self._send_json_success()
                return

            elif command == 'encrypt':
                success = VaultManager.encrypt_folder(path, form['key'].value)
                check_error(success, "Path contains an encrypted folder", 400)

            elif command == 'verify':
                success = VaultManager.is_key_valid(path, form['key'].value)
                response = { 'success': success }
                self._set_headers(200, 'application/json')
                self._write(json.dumps(response).encode("utf-8"))
                return

            elif command == 'decrypt':
                success = VaultManager.decrypt_folder(path, form['key'].value)
                check_error(success, "Forbidden", 403)

            else:
                self._send_json_error(400, "Invalid command")
                return

        except VaultManager.InvalidPathError:
            self._send_json_error(404, "Not found")

        except:
            Logs.warning("Server error:\n", traceback.format_exc())
            self._send_json_error(500, "Server error")

    # Override to prevent HTTP server from logging every request if ENABLE_LOGS is False
    def log_message(self, format, *args):
        if ENABLE_LOGS:
            BaseHTTPRequestHandler.log_message(self, format, *args)
            sys.stdout.flush()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

    def finish_request(self, request, client_address):
        request.settimeout(30)
        HTTPServer.finish_request(self, request, client_address)

class VaultServer():
    is_running = False
    keep_files_days = 0

    def __init__(self, port, ssl_cert, keep_files_days):
        self.__process = Process(target=VaultServer.start_process, args=(port, ssl_cert, keep_files_days))

    def start(self):
        self.__process.start()

    def stop(self):
        self.__process.kill()

    @staticmethod
    def file_filter(name):
        valid_ext = (".nanome", ".lua", ".pdb", ".sdf", ".cif", ".ppt", ".pptx", ".odp", ".pdf", ".png", ".jpg")
        return name.endswith(valid_ext)

    @classmethod
    def start_process(cls, port, ssl_cert, keep_files_days):
        VaultServer.is_running = True
        VaultServer.keep_files_days = keep_files_days

        server = ThreadedHTTPServer(("", port), RequestHandler)

        if ssl_cert is not None:
            import ssl
            server.socket = ssl.wrap_socket(server.socket, certfile=ssl_cert, server_side=True)

        cleanup_thread = None
        if VaultServer.keep_files_days:
            cleanup_thread = Thread(target=VaultServer.file_cleanup)
            cleanup_thread.start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.socket.close()
        except:
            Logs.error('Error in serve_forever', traceback.format_exc())

        VaultServer.is_running = False

        if cleanup_thread:
            cleanup_thread.join()

    @staticmethod
    def file_cleanup():
        while VaultServer.is_running:
            expiry_date = datetime.today() - timedelta(days=VaultServer.keep_files_days)

            # check file last accessed time and remove those older than keep_files_days
            for root, _, files in os.walk(VaultManager.FILES_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    last_accessed = datetime.fromtimestamp(os.path.getatime(file_path))

                    if last_accessed < expiry_date:
                        os.remove(file_path)

            # wait 5 minutes
            sleep(300)
