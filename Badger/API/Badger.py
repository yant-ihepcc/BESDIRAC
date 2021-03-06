#!/usr/bin/env python

import os,sys,time
from DIRAC.Core.Base import Script
Script.initialize()
from DIRAC.DataManagementSystem.Client.FileCatalogClientCLI import FileCatalogClientCLI
from DIRAC.Resources.Catalog.FileCatalogClient import FileCatalogClient
from DIRAC.Resources.Storage.StorageElement import StorageElement

from DIRAC.Interfaces.API.Dirac import Dirac
from DIRAC import gLogger,S_OK,S_ERROR

from BESDIRAC.Badger.DataLoader.DFC.readAttributes import DataAll,Others
from BESDIRAC.Badger.DataLoader.DFC.judgeType import judgeType
"""This is the public API for BADGER, the BESIII Advanced Data ManaGER.

   BADGER wraps the DIRAC File Catalog and related DIRAC methods for 
   use in the BESIII distributed computing environment.


"""

class Badger:

    def __init__(self, fcClient = False):
        """Internal initialization of Badger API.
        """       
        if not fcClient:
            _fcType = 'DataManagement/FileCatalog'
            self.client = FileCatalogClient(_fcType)
        else:
            self.client = fcClient
        self.besclient = FileCatalogClient('DataManagement/DatasetFileCatalog')
    def __getFilenamesByLocaldir(self,localDir):
        """ get all files under the given dir
        example:__getFilenamesByLocaldir("/bes3fs/offline/data/663-1/4260/dst/121215/")
        result = [/bes3fs/offline/data/663-1/4260/dst/121215/filename1,
                  /bes3fs/offline/data/663-1/4260/dst/121215/filename2,
                  ...
                  ] 
        """
        fileList = []
        for rootdir,subdirs,files in os.walk(localDir):
          for name in files:
            fullPath = os.path.join(rootdir,name)
            fileList.append(fullPath)

        return fileList
    def __getFileAttributes(self,fullPath):
        """ get all attributes of the given file,return a attribute dict.
        """
        if os.path.exists(fullPath):
          type = judgeType(fullPath)
          if type=="all":
            obj = DataAll(fullPath)
          elif type=="others":
            obj = Others(fullPath)
          elif type==None:
            errorMes= "name if %s is not correct"%fullPath
            print "cannot get attributes of %s"%fullPath
            return S_ERROR(errorMes)
          attributes = obj.getAttributes()
          attributes['date'] = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime())

        return attributes

    def testFunction(self):
        result = self.__getFilenamesByLocaldir('/besfs2/offline/data/664-1/jpsi/dst')
        for item in result:
          print item
        print len(result)

    def __registerDir(self,dir):
        """Internal function to register a new directory in DFC .
           Returns True for success, False for failure.
        """
        fc = self.client
        result = fc.createDirectory(dir)
        if result['OK']:
            if result['Value']['Successful']:
                if result['Value']['Successful'].has_key(dir):
                    return S_OK() 
                elif result['Value']['Failed']:
                    if result['Value']['Failed'].has_key(dir):
                        print 'Failed to create directory %s:%s'%(dir,result['Value']['Failed'][dir])
                        return S_ERROR() 
        else:
            print 'Failed to create directory %s:%s'%(dir,result['Message'])
            return S_ERROR() 
    def __registerFileMetadata(self,lfn,attributes):
        """Internal function to set metadata values on a given lfn. 
          Returns True for success, False for failure.
        """
        metadataDict = {}
        metadataDict['dataType'] = attributes['dataType']
        metadataDict['runL'] = attributes['runL']
        metadataDict['runH'] = attributes['runH']
        metadataDict['status'] = attributes['status']
        metadataDict['description'] = attributes['description']
        metadataDict['date'] = attributes['date']
        metadataDict['LFN'] = attributes['LFN']
        metadataDict['PFN'] = attributes['PFN']
        metadataDict['eventNum'] = attributes['eventNum']
        metadataDict['fileSize'] = attributes['fileSize']
        result = self.client.setMetadata(lfn,metadataDict)
        if not result['OK']:
          return S_ERROR() 
        else:
          return S_OK() 

    def __registerDirMetadata(self,dir,metaDict):
        """Internal function to set metadata to a directory
           Returns True for success, False for failure.
        """
        fc = self.client
        result = fc.setMetadata(dir,metaDict)
        if result['OK']:
            return S_OK() 
        else:
            print ("Error for setting metadata %s to %s: %s" %(metaDict,dir,result['Message']))
            return S_ERROR(result['Message']) 
        
    def __dirExists(self,dir,parentDir):
        """ Internal function to check whether 'dir' is the subdirectory of 'parentDir'
            Returns 1 for Yes, 0 for NO
        """
        fc = self.client
        dir_exists = 0
        result = fc.listDirectory(parentDir)
        if result['OK']:
            for i,v in enumerate(result['Value']['Successful'][parentDir]['SubDirs']):
                if v == dir: 
                    dir_exists = 1
                    break
        else:
            print 'Failed to list subdirectories of %s:%s'%(parentDir,result['Message'])
        
        return dir_exists

    def __registerSubDirs(self,dirs_dict,dirs_meta):
        """Internal function to create directories in dirs_dict
           Returns True for sucess, False for failure
        """
        creation_ok = True
        
        for dir in dirs_dict:
            if (dir != 'dir_file')&(dir !='dir_data_mc' ):
                if self.__registerDir(dirs_meta[dir][0])['OK']:
                    result = self.__registerDirMetadata(dirs_meta[dir][0],{dir.split('_')[1]:dirs_meta[dir][1]})
                    if not result['OK']:
                        creation_ok = False
                        break
                else:
                    print 'Failed to create %s'%dir
                    creation_ok = False
                    break
            else:
                if not self.__registerDir(dirs_meta[dir])['OK']:
                    print 'Failed to create %s'%dir
                    creation_ok = False
                    break

        return creation_ok
            
    def registerHierarchicalDir(self,metaDict,rootDir='/bes'):
        """
           Create a hierarchical directory according the metadata dictionary
           Return created directory  for sucess,if this directory has been created, return this existing directory .

           Structure of the hierarchical directory:
           for real data:/bes/File/resonance/boss version/data/eventType/round
           for mc data:/bes/File/resonance/boss version/mc/eventType/round/streamId
           The eventType of all real datas is all. 

           Example:
           >>>metaDict = {'dataType': 'dst', 'eventType': 'all', 'streamId': 'stream0','resonance': 'psipp', 'round':'round01','bossVer': '6.6.1'}
           
           >>>badger.registerHierarchicalDir(metaDic)
           1
        """
        #Save about 20 lines compared with last one
        fc = self.client
        
        dir_exists = 0
        #0 for failure,1 for success,2 for existing directory
        creation_OK = 0
        lastDirMetaDict = {'dataType':metaDict['dataType'],'streamId':metaDict['streamId']}

        dir_file = rootDir + '/File'
        dir_resonance = dir_file + '/' + metaDict['resonance']
        dir_bossVer = dir_resonance + '/' + metaDict['bossVer']

        if metaDict['streamId'] == 'stream0':
            dir_data_mc = dir_bossVer + '/data'
        else:
            dir_data_mc = dir_bossVer + '/mc'
        dir_eventType = dir_data_mc + '/' +metaDict['eventType']
        dir_round = dir_eventType + '/' + metaDict['round']
        dir_streamId = dir_round + '/' + metaDict['streamId']

        # if dir_round has been created,create_round=1 
        create_round = 0

        dirs_dict = ['dir_file','dir_resonance','dir_bossVer','dir_data_mc','dir_eventType','dir_round']
        dirs_meta = {'dir_file':dir_file,'dir_data_mc':dir_data_mc,'dir_resonance':[dir_resonance,metaDict['resonance']],'dir_bossVer':[dir_bossVer,metaDict['bossVer']],'dir_eventType':[dir_eventType,metaDict['eventType']],'dir_round':[dir_round,metaDict['round']]}

        dir_exists = self.__dirExists(dir_file,rootDir)
        if not dir_exists:
            result = self.__registerSubDirs(dirs_dict,dirs_meta)
            if result:
                create_round = 1
        else:
            dir_exists = self.__dirExists(dir_resonance,dir_file)
            if not dir_exists:
                dirs_dict = dirs_dict[1:]
                result = self.__registerSubDirs(dirs_dict,dirs_meta)
                if result:
                    create_round = 1
            else:
                dir_exists = self.__dirExists(dir_bossVer,dir_resonance)
                if not dir_exists:
                    dirs_dict = dirs_dict[2:]
                    result = self.__registerSubDirs(dirs_dict,dirs_meta)
                    if result:
                        create_round = 1
                else:
                    dir_exists = self.__dirExists(dir_data_mc,dir_bossVer)
                    if not dir_exists:
                        dirs_dict = dirs_dict[3:]
                        result = self.__registerSubDirs(dirs_dict,dirs_meta)
                        if result:
                            create_round = 1
                    else:
                        dir_exists = self.__dirExists(dir_eventType,dir_data_mc)
                        if not dir_exists:
                            dirs_dict = dirs_dict[4:]
                            result = self.__registerSubDirs(dirs_dict,dirs_meta)
                            if result:
                                create_round = 1
                        else:
                            dir_exists = self.__dirExists(dir_round,dir_eventType)
                            if not dir_exists:
                                dirs_dict = dirs_dict[5:]
                                result = self.__registerSubDirs(dirs_dict,dirs_meta)
                                if result:
                                    create_round = 1
                            else:
                                create_round = 1
        
        if create_round:
            if metaDict['streamId'] != "stream0":
                dir_exists = self.__dirExists(dir_streamId,dir_round)
                if not dir_exists:
                    if self.__registerDir(dir_streamId)['OK']:
                        result = self.__registerDirMetadata(dir_streamId,{'streamId':metaDict['streamId']})
                        if result['OK']:
                            result = self.__registerDirMetadata(dir_streamId,lastDirMetaDict)
                            if result['OK']:
                                creation_OK = 1
                else:
                    creation_OK = 2
            else:
                result = self.__registerDirMetadata(dir_round,lastDirMetaDict)
                if result['OK']:
                    creation_OK = 1
    
        if (creation_OK==1)|(creation_OK==2):
            if metaDict['streamId'] == "stream0":
                return dir_round
            else:   
                return dir_streamId
    def removeDir(self,dir):
        """remove the dir include files and subdirs
        """
        result = self.client.listDirectory(dir)
        if result['OK']:
            if not result['Value']['Successful'][dir]['Files'] and not result['Value']['Successful'][dir]['SubDirs']:
                print 'no file and subDirs in this dir'
                self.client.removeDirectory(dir)
                return S_OK()
            else:
                if result['Value']['Successful'][dir]['Files']:
                    for file in result['Value']['Successful'][dir]['Files']:
                        self.client.removeFile(file)
                else:
                    for subdir in result['Value']['Successful'][dir]['SubDirs']:
                        self.removeDir(subdir)
                    self.removeDir(dir)

    def registerFileMetadata(self,lfn,metaDict):

        """Add file level metadata to an entry
           True for success, False for failure
           (maybe used to registerNewMetadata
           Example:
           >>>lfn = '/bes/File/psipp/6.6.1/data/all/exp1/run_0011414_All_file001_SFO-1'
           >>>entryDict = {'runL':1000,'runH':898898}
           >>>badger.registerFileMetadata(lfn,entryDict)
           True
        """
        fc = self.client
        result = fc.setMetadata(lfn,metaDict)
        if result['OK']:
            return S_OK() 
        else:
            print 'Error:%s'%(result['Message'])
            return S_ERROR(result['Message'])
    #################################################################################
    # meta fields operations
    #
    def addNewFields(self,fieldName,fieldType,metaType='-d'):
      """add new fields,if metaType is '-f',add file field,
        fileType is datatpye in MySQL notation
      """
      result = self.client.addMetadataField(fieldName,fieldType,metaType)
      if not result['OK']:
        return S_ERROR(result)
      else:
        return S_OK()

    def deleteMetaField(self,fieldName):
      """delete a exist metafield"""
      result = self.client.deleteMetadataField(fieldName)
      if not result['OK']:
        return S_ERROR(result)
      else:
        return S_OK()

    def getAllFields(self):
        """get all meta fields,include file metafield and dir metafield.
        """
        result = self.client.getMetadataFields()
        if not result['OK']:
          return S_ERROR(result['Message'])
        else:
          return result['Value']
    #####################################################################

    def registerFile(self,lfn,dfcAttrDict):
        """Register a new file in the DFC.
        
        """
        #TODO:need more tests,if directory of file doesn't exist,
        #addFile will create it without setting any metadata(lin lei)
        #need to check whether directory of file exists in dfc?(lin lei) 
        #pass
        fc = self.client
        result = fc.addFile({lfn:dfcAttrDict})
        if result['OK']:
            if result['Value']['Successful']:
                if result['Value']['Successful'].has_key(lfn):
                    return S_OK()
            elif result['Value']['Failed']:
                if result['Value']['Failed'].has_key(lfn):
                    print 'Failed to add this file:',result['Value']['Failed'][lfn]
                    return S_ERROR()
        else:
            print 'Failed to add this file :',result['Message']
            return S_ERROR()
        # need to register file (inc. creating appropriate directory
        # if it doesn't already exist; and register metadata for that
        # file / directory
        # Q: how / where to pass the metadata?
    
    def removeFile(self,lfn):
        """remove file on DFC
        """
        result = self.client.removeFile(lfn)
        if not result['OK']:
          return S_ERROR(result)
        else:
          return S_OK()

    def uploadAndRegisterFiles(self,localDir,SE='IHEP-USER',guid=None):
        """upload a set of files to SE and register it in DFC.
        user input the directory of localfile.
        we can treat localDir as a kind of datasetName.
        """          

        result_OK = 1
        errorList = []
        fileList = self.__getFilenamesByLocaldir(localDir)
        for fullpath in fileList[:50]:
          #get the attributes of the file
          print fullpath
          fileAttr = self.__getFileAttributes(fullpath)
          #create dir and set dirMetadata to associated dir
          metaDict = {}
          metaDict['dataType'] = fileAttr['dataType']
          metaDict['eventType'] = fileAttr['eventType']
          metaDict['streamId'] = fileAttr['streamId']
          metaDict['resonance'] = fileAttr['resonance']
          metaDict['round'] = fileAttr['round']
          metaDict['bossVer'] = fileAttr['bossVer']
          lastDir = self.registerHierarchicalDir(metaDict,rootDir='/zhanggang_test')
          lfn = lastDir + os.sep+fileAttr['LFN']
          fileAttr['LFN'] = lfn
          #upload and register file. 
          dirac = Dirac()
          result = dirac.addFile(lfn,fullpath,SE,guid,printOutput=True)
          #register file metadata
          if not result['OK']:
            print 'ERROR %s'%(result['Message'])
            #return S_ERROR(result['Message']) 
            errorList.append(fullpath)
            result_OK = 0
          else:
            #get the truely PFN 
            storageElement = StorageElement(SE)
            res = storageElement.getPfnForLfn( lfn )
            destPfn = res['Value']
            fileAttr['PFN'] = destPfn
            result = self.__registerFileMetadata(lfn,fileAttr)
            if not result['OK']:
              result_OK = 0
              print "failed to register file metadata"
        if result_OK:
          return S_OK()
        else:
          return S_ERROR(errorList)

    ####################################################################
    # dataset functions
    #
    def registerDataset(self, dataset_name, conditions):
        """Register a new dataset in DFC. Takes dataset name and string with
           conditions for new dataset as arguments.
           datasetname format:  
           "resonance_BossVer_eventtype_round_runL_runH_stream0_datatype
           example:psip_655_all_round01_8093_9025_stream0_dst
           resonance_BossVer_eventtype_round_runL_runH_streamID_datatype
           example:psip_655_inc_round01_8093_9025_stream1_dst
           example:psipp_655_user1_round01_11414_13988_stream1_dst"
        """
        pass
        # need to think about how datasets are defined
        # format for passing the dataset conditions?
        
        fc = self.client
        setDict = {}
        for cond in conditions:
            key, value = cond.split('=')
            setDict[key] = value
        result = fc.addMetadataSet(dataset_name, setDict)
        if not result['OK']:
            print ("Error: %s" % result['Message'])
        else:
            print "Added dataset %s with conditions %s" % (dataset_name, conditions)
        

    def getFilesByDatasetName(self, dataset_name):
        """Return a list of LFNs in the given dataset.
           
           Example usage:
           >>> badger.getFilesByDatasetName('psipp_661_data_all_exp2')
           ['/bes/File/psipp/6.6.1/data/all/exp2/file1', .....]
        """

        fc = self.client
        #sfc = self.besclient
        result = fc.getMetadataSet(dataset_name, True)
        if result['Value']:
            metadataDict = result['Value']
            result=fc.findFilesByMetadata(metadataDict,'/')
            lfns = result['Value']
            lfns.sort()
            dirs = fc.findDirectoriesByMetadata(metadataDict)
            return lfns
        else:
            print "ERROR: Dataset", dataset_name," not found"
            return S_ERROR(result)
            
    def getFilesByMetadataQuery(self, query):
        """Return a list of LFNs satisfying given query conditions.

           Example usage:
           >>> badger.getFilesByMetadataQuery('resonance=jpsi bossVer=6.5.5 round=exp1')
           ['/bes/File/jpsi/6.5.5/data/all/exp1/file1', .....]

        """
        #TODO: checking of output, error catching


        fc = self.client
        #TODO: calling the FileCatalog CLI object and its private method
        # is not a good way of doing this! but use it to allow construction of
        # the query meantime, until createQuery is made a public method
        cli = FileCatalogClientCLI(fc)
        metadataDict = cli._FileCatalogClientCLI__createQuery(query)
        result = fc.findFilesByMetadata(metadataDict,'/')
        if result['OK']:
            lfns = fc.findFilesByMetadata(metadataDict,'/')['Value']
            lfns.sort()
            return lfns
        else:
            print "ERROR: No files found which match query conditions."
            return None
  

    def getDatasetDescription(self, dataset_name):
        """Return a string containing a description of metadata with which 
           the given dataset was defined.
           
           Example usage:
           >>> result = badger.getDatasetDescription('psipp_661_data_all_exp2')
           >>> print result
           Dataset psipp_661_data_all_exp2 was defined with the following metadata conditions:
               round : exp2
               bossVer : 6.6.1
               resonance : psipp
        """
        #TODO: keep this as separate method, or just return description with LFNs?
        fc = self.client
        result = fc.getMetadataSet(dataset_name, True)
        if result['Value']:
            metadataDict = result['Value']
            # give user a reminder of what this dataset's definition is
            dataset_desc = ''
            dataset_desc += \
                'Dataset %s was defined with the following metadata conditions: \n ' \
                % dataset_name
            for key in metadataDict:
                dataset_desc += '%s : %s \n' % (key, metadataDict[key])
        else:
            dataset_desc = 'Error: dataset %s is not defined.' % dataset_name
        return dataset_desc


    def listDatasets(self):
        """list the exist dataset"""
        result = self.besclient.listMetadataSets()
        if not result['OK']:
          return S_ERROR(result)
        else:
          return result['Value']
          

    def downloadFilesByDatasetName(self,dataset_name):
        """downLoad a set of files form SE.
        use getFilesByDatasetName() get a list of lfns and download these files.

           Example usage:
           >>>badger.downloadFilesByDatasetName('psipp_661_data_all_exp2')i
        """
        dirac = Dirac()
        fileList = self.getFilesByDatasetName(dataset_name)
        result = dirac.getFile(fileList,printOutput = True)
        if not result['OK']:
          print 'ERROR %s'%(result['Message'])
          return S_ERROR(result['Message']) 
        else:
          return S_OK() 


    def checkDatasetIntegrity():
        pass


