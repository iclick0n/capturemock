from .capturepython import interceptPython
from .capturecommand import interceptCommand
from .config import CaptureMockReplayError, RECORD, REPLAY, REPLAY_OLD_RECORD_NEW
from . import config, cmdlineutils
import os, sys, shutil, filecmp, subprocess, tempfile, types
from functools import wraps
from glob import glob
from collections import namedtuple
from datetime import datetime

class CaptureMockManager:
    fileContents = "import capturemock; capturemock.interceptCommand()\n"
    def __init__(self):
        self.serverProcess = None
        self.serverAddress = None

    def startServer(self,
                    mode,
                    recordFile,
                    replayFile=None,
                    recordEditDir=None,
                    replayEditDir=None,
                    rcFiles=[],
                    interceptDir=None,
                    sutDirectory=os.getcwd(),
                    environment=os.environ,
                    stderrFn=None):
        if config.isActive(mode, replayFile):
            # Environment which the server should get
            environment["CAPTUREMOCK_MODE"] = str(mode)
            environment["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            rcHandler = config.RcFileHandler(rcFiles)
            commands = rcHandler.getIntercepts("command line")
            for var in [ "CAPTUREMOCK_PROCESS_START", "CAPTUREMOCK_SERVER" ]:
                if var in environment:
                    del environment[var]

            from . import server
            self.serverProcess = server.startServer(rcFiles,
                                                    mode,
                                                    replayFile,
                                                    replayEditDir,
                                                    recordFile,
                                                    recordEditDir,
                                                    sutDirectory,
                                                    environment, 
                                                    stderrFn)
            self.serverAddress = self.serverProcess.stdout.readline().strip()
            self.serverProtocol = rcHandler.get("server_protocol", [ "general" ], "classic")

            # And environment it shouldn't get...
            environment["CAPTUREMOCK_SERVER"] = self.serverAddress
            if self.makePathIntercepts(commands, interceptDir, replayFile, mode):
                environment["PATH"] = interceptDir + os.pathsep + environment.get("PATH", "")
            return True
        else:
            return False

    def makeWindowsIntercept(self, interceptName):
        destFile = interceptName + ".exe"
        if sys.version_info.major == 3: # python 3, uses pyinstaller
            sourceFile = os.path.join(os.path.dirname(__file__), "capturemock_intercept.exe")
            if not os.path.isfile(sourceFile) and getattr(sys, 'frozen', False): # from exe file, likely TextTest
                sourceFile = os.path.join(os.path.dirname(sys.executable), "capturemock_intercept.exe")
        else: # python2, uses old exemaker executable
            file = open(interceptName + ".py", "w")
            file.write("#!python.exe\nimport site\n")
            file.write(self.fileContents)
            file.close()
            sourceFile = os.path.join(os.path.dirname(__file__), "python_script.exe")
        shutil.copy(sourceFile, destFile)

    def makePosixIntercept(self, interceptName):
        file = open(interceptName, "w")
        file.write("#!" + sys.executable + "\n")
        file.write(self.fileContents)
        file.close()
        os.chmod(interceptName, 0o775) # make executable

    def makePathIntercept(self, cmd, interceptDir):
        if not os.path.isdir(interceptDir):
            os.makedirs(interceptDir)
        interceptName = os.path.join(interceptDir, cmd)
        if os.name == "nt":
            self.makeWindowsIntercept(interceptName)
        else:
            self.makePosixIntercept(interceptName)

    def filterAbsolute(self, commands):
        relativeCmds = []
        for cmd in commands:
            if os.path.isabs(cmd):
                sys.stderr.write("WARNING: Ignoring requested intercept of command " + repr(cmd) + ".\n" +
                                 "CaptureMock intercepts commands via PATH and cannot do anything with absolute paths.\n")
            else:
                relativeCmds.append(cmd)
        return relativeCmds

    def makePathIntercepts(self, commands, interceptDir, replayFile, mode):
        commands = self.filterAbsolute(commands)
        if replayFile and mode == config.REPLAY:
            from . import replayinfo
            commands = replayinfo.filterCommands(commands, replayFile)
        for command in commands:
            self.makePathIntercept(command, interceptDir)
        return len(commands) > 0

    def terminate(self):
        if self.serverProcess:
            if self.serverAddress:
                from .server import stopServer
                stopServer(self.serverAddress, self.serverProtocol)
            self.writeServerErrors()
            self.serverProcess = None

    def writeServerErrors(self):
        out, err = self.serverProcess.communicate()
        if out:
            sys.stdout.write("Output from CaptureMock Server :\n" + out)
        if err:
            sys.stderr.write("Error from CaptureMock Server :\n" + err)


def setUpPython(mode, recordFile, replayFile=None,
                rcFiles=[], pythonAttrs=[], environment=os.environ):
    if config.isActive(mode, replayFile):
        # Environment which the server should get
        environment["CAPTUREMOCK_MODE"] = str(mode)
        if replayFile and mode != RECORD:
            environment["CAPTUREMOCK_REPLAY_FILE"] = replayFile
        environment["CAPTUREMOCK_RECORD_FILE"] = recordFile
        environment["CAPTUREMOCK_PROCESS_START"] = ",".join(rcFiles)
        environment["CAPTUREMOCK_PYTHON"] = ",".join(pythonAttrs)
        return True
    else:
        return False


def process_startup():
    rcFileStr = os.getenv("CAPTUREMOCK_PROCESS_START")
    if rcFileStr:
        rcFiles = rcFileStr.split(",")
        replayFile = os.getenv("CAPTUREMOCK_REPLAY_FILE")
        recordFile = os.getenv("CAPTUREMOCK_RECORD_FILE")
        mode = int(os.getenv("CAPTUREMOCK_MODE"))
        pythonAttrStr = os.getenv("CAPTUREMOCK_PYTHON")
        if pythonAttrStr:
            pythonAttrs = pythonAttrStr.split(",")
        else:
            pythonAttrs = []
        interceptPython(mode, recordFile, replayFile, rcFiles, pythonAttrs)


manager = None
def setUpServer(*args, **kw):
    global manager
    manager = CaptureMockManager()
    return manager.startServer(*args, **kw)


def terminate():
    if manager:
        manager.terminate()

def commandline():
    parser = cmdlineutils.create_option_parser()
    parser.disable_interspersed_args()
    options, args = parser.parse_args()
    if len(args) == 0:
        return parser.print_help()
    interceptDir = tempfile.mkdtemp()
    rcFiles = []
    if options.rcfiles:
        rcFiles = options.rcfiles.split(",")
    mode = options.mode
    if mode == REPLAY and options.replay is None:
        mode = RECORD
    # Start with a fresh file
    if options.record and os.path.isfile(options.record):
        os.remove(options.record)

    setUpServer(mode, options.record, options.replay,
                recordEditDir=options.record_file_edits, replayEditDir=options.replay_file_edits,
                rcFiles=rcFiles, interceptDir=interceptDir)
    subprocess.call(args)
    if os.path.exists(interceptDir):
        shutil.rmtree(interceptDir)
    terminate()

def replay_for_server(rcFile, replayFile, recordFile=None, serverAddress=None, **kw):
    ReplayOptions = namedtuple("ReplayOptions", "mode replay record rcfiles")
    options = ReplayOptions(mode=RECORD, replay=replayFile, record=recordFile, rcfiles=rcFile)
    from .server import ServerDispatcherBase
    dispatcher = ServerDispatcherBase(options)
    if serverAddress:
        from .clientservertraffic import ClientSocketTraffic
        ClientSocketTraffic.setServerLocation(serverAddress, True)
    dispatcher.replay_all(**kw)

def add_timestamp_data(data_by_timestamp, ts, fn, currText):
    tsdict = data_by_timestamp.setdefault(ts, {})
    if fn in tsdict:
        tsdict[fn] += currText
    else:
        tsdict[fn] = currText

class PrefixContext:
    def __init__(self, parseFn=None):
        self.parseFn = parseFn
        self.fns = {}

    def sort_clients(self, fns):
        if len(fns) < 2:
            return
            
        newFns = [ newFn for newFn, _, _ in fns.values() ]
        baseIndex = int(newFns[0][:2])
        without_prefix = [ fn[2:] for fn in newFns ]
        without_prefix.sort()
        for fn in newFns:
            tail = fn[2:]
            index = without_prefix.index(tail) + baseIndex
            newName = str(index).zfill(2) + tail
            os.rename(fn, newName)
            
    def remove_non_matching(self, item, ix):
        removed = {}
        for fn, info in self.fns.items():
            if info[ix] != item:
                removed[fn] = info
        for fn, info in removed.items():
            del self.fns[fn]
        return removed

    def all_same_server(self):
        servers = set()
        for _, _, server in self.fns.values():
            servers.add(server)
        return len(servers) == 1

    def add(self, fn, newFn):
        client, server = None, None
        if self.parseFn:
            client, server, _ = self.parseFn(fn)
            currClient, currServer = None, None
            if len(self.fns) > 0:
                _, currClient, currServer = list(self.fns.values())[-1]
            if client == currClient:
                self.remove_non_matching(client, 1)
            elif server == currServer:
                removed = self.remove_non_matching(server, 2)
                self.sort_clients(removed)
            else:
                if self.all_same_server():
                    self.sort_clients(self.fns)
                self.fns.clear()
            
        self.fns[fn] = newFn, client, server
        
    def get(self, fn):
        info = self.fns.get(fn)
        if info is not None:
            return info[0]

class DefaultTimestamper:
    def __init__(self):
        self.index = 1
        
    def stamp(self):
        ts = datetime.fromordinal(self.index).isoformat()
        self.index += 1
        return ts

# utility for sorting multiple Capturemock recordings so they can be replayed in the right order
# writes to current working directory
# Anything without timestamps is assumed to come first
def add_prefix_by_timestamp(recorded_files, ignoredIndicesIn=None, sep="-", ext=None, parseFn=None):
    ignoredIndices = ignoredIndicesIn or set()
    timestampPrefix = "--TIM:"
    data_by_timestamp = {}
    default_stamper = DefaultTimestamper()
    for fn in recorded_files:
        currText = ""
        curr_timestamp = None
        with open(fn) as f:
            for line in f:
                if line.startswith("<-"):
                    if currText:
                        ts = curr_timestamp or default_stamper.stamp()
                        add_timestamp_data(data_by_timestamp, ts, fn, currText)
                    currText = line
                    curr_timestamp = None
                elif line.startswith(timestampPrefix):
                    curr_timestamp = line[len(timestampPrefix):].strip()
                else:
                    currText += line
        ts = curr_timestamp or default_stamper.stamp()
        add_timestamp_data(data_by_timestamp, ts, fn, currText)
    currIndex = 0
    currContext = PrefixContext(parseFn)
    new_files = []
    for timestamp in sorted(data_by_timestamp.keys()):
        timestamp_data = data_by_timestamp.get(timestamp)
        timestamp_filenames = list(timestamp_data.keys())
        for fn in timestamp_filenames:
            currText = timestamp_data.get(fn)
            newFn = currContext.get(fn)
            if newFn is None:
                currIndex += 1
                while currIndex in ignoredIndices:
                    currIndex += 1
                # original file might already have a prefix, drop it if so
                newPrefix = str(currIndex).zfill(2) + sep
                if fn[2] == "-" and fn[1].isdigit():
                    newFn = newPrefix + fn[3:]
                else:
                    newFn = newPrefix + fn
                if ext:
                    stem = newFn.rsplit(".", 1)[0]
                    newFn = stem + "." + ext
                if newFn == fn:
                    os.rename(fn, fn + ".orig")
                new_files.append(newFn)
                currContext.add(fn, newFn)
            with open(newFn, "a") as currFile:
                currFile.write(currText)
    if currFile:
        currFile.close()
    return new_files


def capturemock(pythonAttrsOrFunc=[], *args, **kw):
    if isinstance(pythonAttrsOrFunc, types.FunctionType):
        return CaptureMockDecorator(stackDistance=2)(pythonAttrsOrFunc)
    else:
        return CaptureMockDecorator(pythonAttrsOrFunc, *args, **kw)


# For use as a decorator in coded tests
class CaptureMockDecorator(object):
    defaultMode = int(os.getenv("CAPTUREMOCK_MODE", "0"))
    defaultPythonAttrs = []
    defaultRcFiles = list(filter(os.path.isfile, [".capturemockrc"]))
    @classmethod
    def set_defaults(cls, pythonAttrs=[], mode=None, rcFiles=[]):
        if rcFiles:
            cls.defaultRcFiles = rcFiles
        cls.defaultPythonAttrs = pythonAttrs
        if mode is not None:
            cls.defaultMode = mode

    def __init__(self, pythonAttrs=[], mode=None, rcFiles=[], stackDistance=1):
        if mode is not None:
            self.mode = mode
        else:
            self.mode = self.defaultMode
        self.pythonAttrs = pythonAttrs or self.defaultPythonAttrs
        if not isinstance(self.pythonAttrs, list):
            self.pythonAttrs = [ self.pythonAttrs ]
        self.rcFiles = rcFiles or self.defaultRcFiles
        self.stackDistance = stackDistance

    def __call__(self, func):
        from inspect import stack
        callingFile = stack()[self.stackDistance][1]
        fileNameRoot = self.getFileNameRoot(func.__name__, callingFile)
        replayFile = None if self.mode == config.RECORD else fileNameRoot
        if not config.isActive(self.mode, replayFile):
            return func
        recordFile = tempfile.mktemp()
        @wraps(func)
        def wrapped_func(*funcargs, **funckw):
            interceptor = None
            try:
                setUpPython(self.mode, recordFile, replayFile, self.rcFiles, self.pythonAttrs)
                interceptor = interceptPython(self.mode, recordFile, replayFile, self.rcFiles, self.pythonAttrs)
                result = func(*funcargs, **funckw)
                if self.mode == config.REPLAY:
                    self.checkMatching(recordFile, replayFile)
                elif os.path.isfile(recordFile):
                    shutil.move(recordFile, fileNameRoot)
                return result
            finally:
                if interceptor:
                    interceptor.resetIntercepts()
                if os.path.isfile(recordFile):
                    os.remove(recordFile)
                terminate()
        return wrapped_func

    def fileContentsEqual(self, fn1, fn2):
        bufsize = 8*1024
        # copied from filecmp.py, adding universal line ending support
        with open(fn1, newline=None) as fp1, open(fn2, newline=None) as fp2:
            while True:
                b1 = fp1.read(bufsize)
                b2 = fp2.read(bufsize)
                if b1 != b2:
                    return False
                if not b1:
                    return True

    def checkMatching(self, recordFile, replayFile):
        if os.path.isfile(recordFile):
            if self.fileContentsEqual(recordFile, replayFile):
                os.remove(recordFile)
            else:
                # files don't match
                shutil.move(recordFile, replayFile + ".tmp")
                raise CaptureMockReplayError("Replayed calls do not match those recorded. " +
                                             "Either rerun with capturemock in record mode " +
                                             "or update the stored mock file by hand.")

    def getFileNameRoot(self, funcName, callingFile):
        dirName = os.path.join(os.path.dirname(callingFile), "capturemock")
        if not os.path.isdir(dirName):
            os.makedirs(dirName)
        return os.path.join(dirName, funcName.replace("test_", "") + ".mock")

set_defaults = CaptureMockDecorator.set_defaults
