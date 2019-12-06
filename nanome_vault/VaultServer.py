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

enable_logs = False

# Format, MIME type, Binary
Types = {
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
    try:
        return Types[format]
    except:
        return Types[""]

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
    def _send_list(self, folder=None):
        if VaultServer.instance.keep_files_days > 0:
            self.file_cleanup()

        path = VaultManager.get_vault_path(folder)
        if path is None:
            return self._send_json_error(404, 'File not found')

        response = VaultManager.list_path(path)
        response['success'] = True

        self._set_headers(200, 'application/json')
        self._write(json.dumps(response).encode("utf-8"))

    # Standard GET case: get a file
    def _try_get_resource(self, base_dir, path):
        path = os.path.join(base_dir, path)
        if not VaultManager.is_safe_path(path, base_dir):
            return self._send_json_error(404, 'File not found')

        try:
            ext = path.split(".")[-1]
            (mime, is_binary) = get_type(ext)
            f = open(path, 'rb' if is_binary else 'r')
        except:
            self._set_headers(404)
            return

        file = f.read()
        data = file if is_binary else file.encode("utf-8")

        self._set_headers(200, mime)
        self._write(data)
        f.close()

    # Called on GET request
    def do_GET(self):
        path = self._parse_path()
        base_dir = SERVER_DIR
        is_file = re.search(r'\.[^/]+$', path) is not None

        # path in vault
        if path.startswith('/files'):
            path = path[7:]

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

        content_len = int(self.headers.get('Content-Length'))
        folder = os.path.join(VaultManager.FILES_DIR, path[7:])

        # no files provided, create folders
        if not content_len:
            if os.path.exists(folder):
                self._send_json_error(400, "Name already exists")
            else:
                os.makedirs(folder)
                self._send_json_success()
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={'REQUEST_METHOD':'POST'})

        for file in form['file']:
            file_name = file.filename

            if not VaultServer.file_filter(file_name):
                self._send_json_error(400, file_name + " format not supported")
                return

            # create folder paths
            subfolder = os.path.join(folder, os.path.dirname(file_name))
            if not os.path.exists(subfolder):
                os.makedirs(subfolder)

            file_path = os.path.join(folder, file_name)

            # rename on duplicates: file.txt -> file (n).txt
            reg = r'(.+/)([^/]+?)(?: \((\d+)\))?(\.\w+)'
            (path, name, copy, ext) = re.search(reg, file_path).groups()
            copy = 1 if copy is None else int(copy)

            while os.path.isfile(file_path):
                copy += 1
                file_path = '%s%s (%d)%s' % (path, name, copy, ext)

            # Create file
            with open(file_path, "wb") as f:
                f.write(file.file.read())

        self._send_json_success()

    # Called on DELETE request
    def do_DELETE(self):
        path = self._parse_path()
        if not path.startswith('/files') or not path[7:]:
            self._send_json_error(403, "Forbidden")
            return

        path = os.path.join(VaultManager.FILES_DIR, path[7:])

        try:
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
        except:
            self._send_json_error(500, "Error deleting " + path)
            return

        self._send_json_success()

    # Override to prevent HTTP server from logging every request if enable_logs is False
    def log_message(self, format, *args):
        if enable_logs:
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
