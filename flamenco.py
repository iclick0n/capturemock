import carmen, os, plugins

def getConfig(optionMap):
    return FlamencoConfig(optionMap)

class FlamencoConfig(carmen.CarmenConfig):
    def interpretBinary(self, binaryString):
        os.system(os.path.join(os.environ["CARMSYS"], "CONFIG"))
        return binaryString.replace("ARCHITECTURE", carmen.architecture)
    def getTestCollator(self):
        return plugins.CompositeAction([ carmen.CarmenConfig.getTestCollator(self), MakeSQLErrorFile() ])

class MakeSQLErrorFile(plugins.Action):
    def __call__(self, test):
        sqlfile = test.getTmpFileName("sqlerr", "w")
        if os.path.isfile("sqlnet.log"):
            os.rename("sqlnet.log", sqlfile)
        else:
            file = open(sqlfile, "w")
            file.write("NO ERROR" + os.linesep)
    
