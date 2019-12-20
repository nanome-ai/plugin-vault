import nanome
from nanome.util import Logs

import os
import tempfile
import traceback
import subprocess
from sys import platform

class PPTConverter(object):
    def __init__(self, file_name):
        self.running = False
        self.done = False
        self.error = None
        self._tmp_dir = None
        self._base_name = ""
        self.result = []

        self._ppt_file = file_name
        self._base_name = tempfile.NamedTemporaryFile().name

        if platform == "win32" and file_name.endswith((".pptx", ".ppt", ".odp")):
            self._tmp_dir = tempfile.TemporaryDirectory()
            self._step = 1
        else:
            self._step = 2

        self.done_delegates = []
        self.error_delegates = []

    def Convert(self, done_delegate, error_delegate = None):
        if self.done:
            Logs.debug("Using Cached convert")
            done_delegate(self.result)
            return
        else:
            Logs.debug("Adding to existing convert")
            self.done_delegates.append(done_delegate)
            self.error_delegates.append(error_delegate)

        if not self.running:
            self._start_conversion()

    def __del__(self):
        Logs.debug("Cleaning up temp resources.")
        try:
            os.remove(self._tmp_dir)
        except:
            pass
        if self._base_name != "":
            for image in self.result:
                try:
                    Logs.debug("Removing", image)
                    os.remove(image)
                    Logs.debug("Success", image)
                except:
                    pass

    ### Conversion Process ###

    def update(self):
        if not self.running:
            return
        if self._check_conversion():
            Logs.debug("Conversion done")
            self._conversion_finished()

    def _start_conversion(self):
        Logs.debug("Starting conversion on file: " + self._base_name)
        if platform in ["linux", "linux2", "darwin"]:
            args = ['convert', '-density', '288', self._ppt_file, self._base_name + '-pptreader-%d.jpg']
        elif platform == "win32":
            if self._step == 1:
                args = ['simpress.exe', '--headless', '--invisible', '--convert-to', 'pdf', '--outdir', self._tmp_dir.name, self._ppt_file]
            else:
                if self._tmp_dir != None:
                    input = os.path.join(self._tmp_dir.name, '*.pdf')
                else:
                    input = self._ppt_file
                args = ['magick', '-density', '288', input, self._base_name + '-pptreader-%d.jpg']

        Logs.debug("Starting conversion with args:", args)
        try:
            self._process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except:
            Logs.error("Couldn't convert:", traceback.format_exc())
            #ERROR
            self.finished(False)
        self.running = True

    def _check_conversion(self):
        return self._process.poll() != None

    def _conversion_finished(self):
        if platform == "win32" and self._step == 1:
            self._step = 2
            self._start_conversion()
            return

        try:
            (results, errors) = self._process.communicate()
            if len(errors) == 0:
                for result in results:
                    for line in result.split('\n'):
                        Logs.debug(line)
            else:
                for line in errors.splitlines():
                    Logs.error(line.decode("utf-8"))

                #ERROR
                self.finished(False)
                return
        except:
            pass

        images = []
        i = 0
        is_file = True
        while is_file:
            file_name = self._base_name + '-pptreader-' + str(i) + '.jpg'
            is_file = os.path.isfile(file_name)
            if is_file:
                images.append(file_name)
                i += 1

        if i == 0:
            Logs.error("No file generated by conversion")
            #ERROR
            self.finished(False)
            return

        self.finished(True, images)

    def finished(self, success=True, results=None):
        self.done = success
        self.running = False
        self.result = results
        if success:
            for done_delegate in self.done_delegates:
                done_delegate(results)
        else:
            for error_delegate in self.error_delegates:
                error_delegate()
        self.done_delegates.clear()
        self.error_delegates.clear()
