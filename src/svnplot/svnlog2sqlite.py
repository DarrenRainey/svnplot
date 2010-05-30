'''
svnlog2sqlite.py
Copyright (C) 2009 Nitin Bhide (nitinbhide@gmail.com)

This module is part of SVNPlot (http://code.google.com/p/svnplot) and is released under
the New BSD License: http://www.opensource.org/licenses/bsd-license.php
--------------------------------------------------------------------------------------

python script to convert the Subversion log into an sqlite database
The idea is to use the generated SQLite database as input to Matplot lib for
creating various graphs and analysis. The graphs are inspired from graphs
generated by StatSVN/StatCVS.
'''

import sys,os
import datetime
import sqlite3
import logging
import traceback
from optparse import OptionParser

import svnlogiter

BINARYFILEXT = [ 'doc', 'xls', 'ppt', 'docx', 'xlsx', 'pptx', 'dot', 'dotx', 'ods', 'odm', 'odt', 'ott', 'pdf',
                 'o', 'a', 'obj', 'lib', 'dll', 'so', 'exe',
                 'jar', 'zip', 'z', 'gz', 'tar', 'rar','7z',
                 'pdb', 'idb', 'ilk', 'bsc', 'ncb', 'sbr', 'pch', 'ilk',
                 'bmp', 'dib', 'jpg', 'jpeg', 'png', 'gif', 'ico', 'pcd', 'wmf', 'emf', 'xcf', 'tiff', 'xpm',
                 'gho', 'mp3', 'wma', 'wmv','wav','avi'
                 ]

class SVNLog2Sqlite:
    def __init__(self, svnrepopath, sqlitedbpath,verbose=False,username=None, password=None):
        self.svnclient = svnlogiter.SVNLogClient(svnrepopath,BINARYFILEXT,username=username, password=password)
        self.dbpath =sqlitedbpath
        self.dbcon =None
        self.verbose = verbose
        
    def convert(self, bUpdLineCount=True, maxtrycount=3):
        #First check if this a full conversion or a partial conversion
        self.initdb()
        self.CreateTables()
        for trycount in range(0, maxtrycount):
            try:
                laststoredrev = self.getLastStoredRev()
                rootUrl = self.svnclient.getRootUrl()
                self.printVerbose("Root url found : %s" % rootUrl)
                (startrevno, endrevno) = self.svnclient.findStartEndRev()
                self.printVerbose("Start-End Rev no : %d-%d" % (startrevno, endrevno))
                startrevno = max(startrevno,laststoredrev+1) 
                self.ConvertRevs(startrevno, endrevno, bUpdLineCount, maxtrycount)
            except Exception, expinst:
                logging.error("Error %s" % expinst)
                print "Error %s" % expinst
                traceback.print_exc()
                print "Trying again (%d)" % (trycount+1)
            finally:                        
                self.dbcon.commit()
                
        self.closedb()
        
    def initdb(self):
        self.dbcon = sqlite3.connect(self.dbpath, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        #self.dbcon.row_factory = sqlite3.Row

    def closedb(self):
        self.dbcon.commit()
        self.dbcon.close()
        
    def getLastStoredRev(self):
        cur = self.dbcon.cursor()
        cur.execute("select max(revno) from svnlog")
        lastStoreRev = 0
        
        row = cur.fetchone()
        if( row != None and len(row) > 0 and row[0] != None):
            lastStoreRev = int(row[0])
        cur.close()
        return(lastStoreRev)

    def getFilePathId(self, filepath, updcur):
        '''
        update the filepath id if required.
        '''
        id = None
        if( filepath ):
            querycur=self.dbcon.cursor()
            querycur.execute('select id from SVNPaths where path = ?', (filepath,))
            resultrow = querycur.fetchone()
            if( resultrow == None):
                updcur.execute('INSERT INTO SVNPaths(path) values(?)', (filepath,))
                querycur.execute('select id from SVNPaths where path = ?', (filepath,))
                resultrow = querycur.fetchone()
            id = resultrow[0]
            querycur.close()
            
        return(id)
    
    def ConvertRevs(self, startrev, endrev, bUpdLineCount, maxtrycount=3):
        if( startrev < endrev):
            querycur = self.dbcon.cursor()
            updcur = self.dbcon.cursor()
            svnloglist = svnlogiter.SVNRevLogIter(self.svnclient, startrev, endrev)
            revcount = 0
            lc_updated = 'N'
            if( bUpdLineCount == True):
                lc_updated = 'Y'
            lastrevno = 0
            for revlog in svnloglist:                
##                logging.debug("Revision author:%s" % revlog.author)
##                logging.debug("Revision date:%s" % revlog.date)
##                logging.debug("Revision msg:%s" % revlog.message)
                revcount = revcount+1
                addedfiles, changedfiles, deletedfiles = revlog.changedFileCount()                
                if( revlog.isvalid() == True):
                    updcur.execute("INSERT into SVNLog(revno, commitdate, author, msg, addedfiles, changedfiles, deletedfiles) \
                                values(?, ?, ?, ?,?, ?, ?)",
                                (revlog.revno, revlog.date, revlog.author, revlog.message, addedfiles, changedfiles, deletedfiles))
                    for change in revlog.getDiffLineCount(bUpdLineCount):
                        filename = change.filepath_unicode()
                        changetype = change.change_type()
                        linesadded = change.lc_added()
                        linesdeleted = change.lc_deleted()
                        copyfrompath,copyfromrev = change.copyfrom()
                        entry_type = 'R' #Real log entry.
                        pathtype = change.pathtype()
                        changepathid = self.getFilePathId(filename, updcur)
                        copyfromid = self.getFilePathId(copyfrompath,updcur)
                        updcur.execute("INSERT into SVNLogDetail(revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                            linesadded, linesdeleted, lc_updated, pathtype, entrytype) \
                                    values(?, ?, ?, ?,?,?, ?,?,?,?)", (revlog.revno, changepathid, changetype, copyfromid, copyfromrev, \
                                            linesadded, linesdeleted, lc_updated, pathtype, entry_type))

                        if( bUpdLineCount == True):
                            #dummy entries may add additional added/deleted file entries.
                            (addedfiles1, deletedfiles1) = self.addDummyLogDetail(change,querycur,updcur)
                            addedfiles = addedfiles+addedfiles1
                            deletedfiles = deletedfiles+deletedfiles1
                            updcur.execute("UPDATE SVNLog SET addedfiles=?, deletedfiles=? where revno=?",(addedfiles,deletedfiles,revlog.revno))
                            
                        #print "%d : %s : %s : %d : %d " % (revlog.revno, filename, changetype, linesadded, linesdeleted)
                    lastrevno = revlog.revno
                    #commit after every change
                logging.debug("Number revisions converted : %d (Rev no : %d)" % (revcount, lastrevno))
                self.printVerbose("Number revisions converted : %d (Rev no : %d)" % (revcount, lastrevno))

            if( self.verbose == False):            
                print "Number revisions converted : %d (Rev no : %d)" % (revcount, lastrevno)
            querycur.close()
            updcur.close()

    def addDummyLogDetail(self,change,querycur, updcur):
        '''
        add dummy log detail entries for getting the correct line count data in case of tagging/branching and deleting the directories.
        '''
        changetype = change.change_type()
        entry_type = 'D'
        lc_updated = 'Y'
        addedfiles = 0
        deletedfiles = 0
        if( changetype == 'D' or changetype=='A'):
            #since we may have to query the existing data. Commit the changes first.
            self.dbcon.commit()
            
            copyfrompath, copyfromrev = change.copyfrom()            
            path_type = 'U' #set path type to unknown
            if(changetype == 'A' and copyfrompath != None):
                #the data is copied from an existing source path.
                querycur.execute("select changedpath, sum(linesadded), sum(linesdeleted) from SVNLogDetailVw where changedpath LIKE ? and revno < ? \
                                group by changedpath",("%s%%"%copyfrompath, copyfromrev))

                for row in querycur:
                    #set lines added to current line count
                    lc_added = row[1]-row[2]
                    if( lc_added < 0):
                        lc_added = 0
                    #set the lines deleted = 0
                    lc_deleted = 0

                    filename = row[0].replace(copyfrompath, change.filepath_unicode(), 1)
                    pathtype = 'F'
                    if(filename.endswith('/')):
                       pathtype = 'D'
                    changedpathid = self.getFilePathId(filename, updcur)
                    copyfrompathid = self.getFilePathId(row[0], updcur)
                    updcur.execute("INSERT into SVNLogDetail(revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                            linesadded, linesdeleted, entrytype, pathtype, lc_updated) \
                                    values(?, ?, ?, ?,?,?, ?,?,?,?)", (change.revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                            lc_added, lc_deleted, entry_type,path_type,lc_updated))
                    addedfiles = addedfiles+1
                        
                    #print row
            elif( changetype == 'D' and change.lc_added()== 0 and change.lc_deleted() == 0):                
                #data is deleted and possibly original path is a copied from another source.
                filename = change.filepath_unicode()

                sqlquery = "select changedpath, sum(linesadded), sum(linesdeleted) from SVNLogDetailVw where changedpath LIKE '%s' and revno < %d \
                                group by changedpath" % ("%s%%"%filename, change.revno)
                querycur.execute('select changedpath, sum(linesadded), sum(linesdeleted) from SVNLogDetailVw where changedpath LIKE ? and revno < ? \
                                group by changedpath',("%s%%"%filename, change.revno))
                
                for row in querycur:
                    #set lines deleted to current line count
                    lc_deleted = row[1]-row[2]
                    if( lc_deleted < 0):
                        lc_deleted = 0
                    #set lines added to 0
                    lc_added = 0
                    pathtype = 'F'
                    if(row[0].endswith('/')):
                       pathtype = 'D'                    
                    changedpathid = self.getFilePathId(row[0], updcur)
                    copyfrompathid = self.getFilePathId(copyfrompath, updcur)
                    updcur.execute("INSERT into SVNLogDetail(revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                            linesadded, linesdeleted, entrytype, pathtype, lc_updated) \
                                    values(?, ?, ?, ?,?,?, ?,?,?,?)", (change.revno, changedpathid, changetype, copyfrompathid, copyfromrev, \
                                            lc_added, lc_deleted, entry_type,path_type,lc_updated))
                    deletedfiles = deletedfiles+1
                    
        return(addedfiles, deletedfiles)
            
    def UpdateLineCountData(self):
        self.initdb()
        try:        
            self.__updateLineCountData()
        except Exception, expinst:            
            logging.error("Error %s" % expinst)
            print "Error %s" % expinst            
        self.closedb()
        
    def __updateLineCountData(self):
        '''Update the line count data in SVNLogDetail where lc_update flag is 'N'.
        This function is to be used with incremental update of only 'line count' data.
        '''
        #first create temporary table from SVNLogDetail where only the lc_updated status is 'N'
        #Set the autocommit on so that update cursor inside the another cursor loop works.
        self.dbcon.isolation_level = None
        cur = self.dbcon.cursor()        
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS LCUpdateStatus \
                    as select revno, changedpath, changetype from SVNLogDetail where lc_updated='N'")
        self.dbcon.commit()
        cur.execute("select revno, changedpath, changetype from LCUpdateStatus")
                
        for revno, changedpath, changetype in cur:
            linesadded =0
            linesdeleted = 0
            self.printVerbose("getting diff count for %d:%s" % (revno, changedpath))
            
            linesadded, linesdeleted = self.svnclient.getDiffLineCountForPath(revno, changedpath, changetype)
            sqlquery = "Update SVNLogDetail Set linesadded=%d, linesdeleted=%d, lc_updated='Y' \
                    where revno=%d and changedpath='%s'" %(linesadded,linesdeleted, revno,changedpath)
            self.dbcon.execute(sqlquery)            
        
        cur.close()
        self.dbcon.commit()
        
    def CreateTables(self):
        cur = self.dbcon.cursor()
        cur.execute("create table if not exists SVNLog(revno integer, commitdate timestamp, author text, msg text, \
                            addedfiles integer, changedfiles integer, deletedfiles integer)")
        cur.execute("create table if not exists SVNLogDetail(revno integer, changedpathid integer, changetype text, copyfrompathid integer, copyfromrev integer, \
                    pathtype text, linesadded integer, linesdeleted integer, lc_updated char, entrytype char)")
        cur.execute("CREATE TABLE IF NOT EXISTS SVNPaths(id INTEGER PRIMARY KEY AUTOINCREMENT, path text)")
        try:
                #create VIEW IF NOT EXISTS was not supported in default sqlite version with Python 2.5
                cur.execute("CREATE VIEW SVNLogDetailVw AS select SVNLogDetail.*, ChangedPaths.path as changedpath, CopyFromPaths.path as copyfrompath \
                    from SVNLogDetail LEFT JOIN SVNPaths as ChangedPaths on SVNLogDetail.changedpathid=ChangedPaths.id \
                    LEFT JOIN SVNPaths as CopyFromPaths on SVNLogDetail.copyfrompathid=CopyFromPaths.id")
        except:
                #you will get an exception if the view exists. In that case nothing to do. Just continue.
                pass
        #lc_updated - Y means line count data is updated.
        #lc_updated - N means line count data is not updated. This flag can be used to update
        #line count data later        
        cur.execute("CREATE INDEX if not exists svnlogrevnoidx ON SVNLog (revno ASC)")
        cur.execute("CREATE INDEX if not exists svnlogdtlrevnoidx ON SVNLogDetail (revno ASC)")
        cur.execute("CREATE INDEX IF NOT EXISTS svnpathidx ON SVNPaths (path ASC)")
        self.dbcon.commit()
        
        #Table structure is changed slightly. I have added a new column in SVNLogDetail table.
        #Use the following sql to alter the old tables
        #ALTER TABLE SVNLogDetail ADD COLUMN lc_updated char
        #update SVNLogDetail set lc_updated ='Y' ## Use 'Y' or 'N' as appropriate.
        
    def printVerbose(self, msg):
        logging.debug(msg)
        if( self.verbose==True):
            print msg            
                    
def getLogfileName(sqlitedbpath):
    '''
    create log file in using the directory path from the sqlitedbpath
    '''
    dir, file = os.path.split(sqlitedbpath)
    logfile = os.path.join(dir, 'svnlog2sqlite.log')
    return(logfile)
    
def RunMain():
    usage = "usage: %prog [options] <svnrepo root url> <sqlitedbpath>"
    parser = OptionParser(usage)
    parser.set_defaults(updlinecount=False)

    parser.add_option("-l", "--linecount", action="store_true", dest="updlinecount", default=False,
                      help="update changed line count (True/False). Default is False")
    parser.add_option("-g", "--log", action="store_true", dest="enablelogging", default=False,
                      help="Enable logging during the execution(True/False). Name of generate logfile is svnlog2sqlite.log.")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False,
                      help="Enable verbose output. Default is False")
    parser.add_option("-u", "--username", dest="username",default=None, action="store", type="string",
                      help="username to be used for repository authentication")
    parser.add_option("-p", "--password", dest="password",default=None, action="store", type="string",
                      help="password to be used for repository authentication")
    (options, args) = parser.parse_args()
    
    if( len(args) < 2):
        print "Invalid number of arguments. Use svnlog2sqlite.py --help to see the details."    
    else:
        svnrepopath = args[0]
        sqlitedbpath = args[1]


        try:
            print "Updating the subversion log"
            print "Repository : %s" % svnrepopath
            print "Log database filepath : %s" % sqlitedbpath
            print "Update Changed Line Count : %s" % options.updlinecount
            
            if(options.enablelogging==True):
                logfile = getLogfileName(sqlitedbpath)
                logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s %(message)s',
                        filename=logfile,
                        filemode='w')
                print "Logging to file %s" % logfile

            conv = None            
            conv = SVNLog2Sqlite(svnrepopath, sqlitedbpath,verbose=options.verbose, username=options.username, password=options.password)
            conv.convert(options.updlinecount)
        except Exception, expinst:
            print "Error "
            print expinst
            del conv            
        
if( __name__ == "__main__"):
    RunMain()
    
    