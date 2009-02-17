#!/usr/bin/env python

import os, operator
from glob import glob
from copy import copy

def writeMods(newFile, mods, ext, prefix):
    for mod in mods:
        newFile.write("[" + mod + "]\n")
        newFile.write("Target: " + prefix + mod.replace(" ", "") + "." + ext + "\n")
        newFile.write("LogLevel: None\n\n")

def findDiagNames(location):
    result = []
    for fileName in glob(os.path.join(installationRoot, location, "*.py")):
        for line in open(fileName).xreadlines():
            if line.find("getDiagnostics") != -1:
                words = line.split('"')
                if len(words) > 1:
                    name = words[1].lower()
                    if not name in result:
                        result.append(name)
    result.sort()
    return result

def writeFile(fileName, coreDiagsIn, ext, prefix="", siteDiagsIn=[], defaultDiags=[]):
    coreDiags = copy(coreDiagsIn)
    siteDiags = copy(siteDiagsIn)
    newFileName = fileName + ".new"
    newFile = open(newFileName, "w")
    foundMarker = False
    for line in open(fileName).readlines():
        if line.find("TextTest") != -1:
            foundMarker = True
        if not line.startswith("#") and foundMarker:
            break
        else:
            newFile.write(line)
    newFile.write("\n")
    if len(defaultDiags) > 0:
        newFile.write("# The following diagnostics are on by default for the self-tests:\n")
        for mod, diagFile in defaultDiags:
            if mod in coreDiags:
                coreDiags.remove(mod)
            elif mod in siteDiags:
                siteDiags.remove(mod)
            else:
                continue
            newFile.write("[" + mod + "]\n")
            newFile.write("Target: " + diagFile + "." + ext + "\n")
            newFile.write("LogLevel: Normal\nFormat: %M\n\n")
        
    newFile.write("# The following diagnostics are available for the generic TextTest modules:\n")
    writeMods(newFile, coreDiags, ext, prefix)
    if len(siteDiags) > 0:
        newFile.write("# The following diagnostics are only relevant when using site-specific configuration modules:\n")
        writeMods(newFile, siteDiags, ext, prefix)
    newFile.close()
    os.remove(fileName)
    os.rename(newFileName, fileName)

installationRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
coreDiags = findDiagNames("lib")
coreDiagFile = os.path.join(installationRoot, "log/log4py.conf")
writeFile(coreDiagFile, coreDiags, "diag", prefix="$TEXTTEST_DIAGDIR/")

siteDiagFile = os.path.join(installationRoot, "site/log/log4py.conf")
if os.path.isfile(siteDiagFile):
    siteDiags = findDiagNames("site/lib")
    writeFile(siteDiagFile, coreDiags, "diag", "$TEXTTEST_DIAGDIR/", siteDiags)

selftestFile = os.path.join(os.getenv("TEXTTEST_HOME"), "texttest", "logging.texttest")
if not os.path.isfile(selftestFile):
    selftestFile = os.path.join(os.getenv("TEXTTEST_HOME"), "logging.texttest")

defaultDiags = [ ("static gui behaviour", "gui_log"), ("dynamic gui behaviour", "dynamic_gui_log"), \
                 ("use-case log", "usecase_log"), ("test graph", "gnuplot") ]

writeFile(selftestFile, coreDiags, "texttest", defaultDiags=defaultDiags)

selftestSiteFile = os.path.join(os.getenv("TEXTTEST_HOME"), "texttest", "site", "logging.texttest")
if not os.path.isfile(selftestFile):
   selftestSiteFile = os.path.join(os.getenv("TEXTTEST_HOME"), "site", "logging.texttest")

if os.path.isfile(selftestSiteFile):
    writeFile(selftestSiteFile, coreDiags, "texttest", siteDiagsIn=siteDiags, defaultDiags=defaultDiags)
    os.system("bzr tkdiff " + selftestSiteFile)