'''
SVNPlotBase implementation. Common base class various ploting functions. Stores common settings as well
'''

__revision__ = '$Revision:$'
__date__     = '$Date:$'

import matplotlib.pyplot as plt
from matplotlib.dates import YearLocator, MonthLocator, DateFormatter
from matplotlib.ticker import FixedLocator, FormatStrFormatter
from matplotlib.font_manager import FontProperties
import sqlite3
import os.path, sys
import string
import operator
import logging

def dirname(searchpath, path, depth):
    assert(searchpath != None and searchpath != "")
    #replace the search path and then compare the depth
    path = path.replace(searchpath, "", 1)
    #first split the path and remove the filename
    pathcomp = os.path.dirname(path).split('/')
    #now join the split path upto given depth only
    dirpath = '/'.join(pathcomp[0:depth])
    #Now add the dirpath to searchpath to get the final directory path
    dirpath = searchpath+dirpath
    #print "%s : [%s]" %(path, dirpath)
    return(dirpath)

def filetype(path):
    (root, ext) = os.path.splitext(path)
    return(ext)
    
class SVNPlotBase:
    def __init__(self, svndbpath, dpi=100,format='png'):
        self.svndbpath = svndbpath
        self.dpi = dpi
        self.format = format
        self.reponame = ""
        self.verbose = False
        self.clrlist = ['b', 'g', 'r', 'c', 'm', 'y', 'k']
        self.__searchpath = '/%'
        self.dbcon = sqlite3.connect(self.svndbpath, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        #self.dbcon.row_factory = sqlite3.Row
        # Create the function "regexp" for the REGEXP operator of SQLite
        self.dbcon.create_function("dirname", 3, dirname)
        self.dbcon.create_function("filetype", 1, filetype)        
        self.cur = self.dbcon.cursor() 
    
    def __del__(self):
        self.cur.close()
        self.dbcon.close()

    def SetRepoName(self, reponame):
        self.reponame = reponame
        
    def SetVerbose(self, verbose):       
        self.verbose = verbose

    def SetSearchPath(self, searchpath = '/'):
        '''
        Set the path for searching the repository data.
        Default value is '/%' which searches all paths in the repository.
        Use self.SetSearchPath('/trunk/%') for searching inside the 'trunk' folder only
        '''
        if(searchpath != None and len(searchpath) > 0):
            self.__searchpath = searchpath
        if( self.__searchpath.endswith('%')==True):
            self.__searchpath = self.__searchpath[:-1]
        self._printProgress("Set the search path to %s" % self.__searchpath)

    @property
    def searchpath(self):
        return(self.__searchpath)

    @property    
    def sqlsearchpath(self):
        '''
        return the sql regex search path (e.g. '/trunk/' will be returned as '/trunk/%'
        '''
        return(self.__searchpath + '%')
    
    def _printProgress(self, msg):
        if( self.verbose == True):
            print msg
                                                
    def _getAuthorList(self, numAuthors=None):
        #Find out the unique developers and their number of commit sorted in 'descending' order
        self.cur.execute("select author, count(*) as commitcount from SVNLog group by author order by commitcount desc")
        
        #get the auhor list (ignore commitcount) and store it. Since LogGraphLineByDev also does an sql query. It will otherwise
        # get overwritten
        authList = [author for author,commitcount in self.cur]
        #Keep only top 'numAuthors'
        if( numAuthors != None):
            authList = authList[:numAuthors]
        
        #if there is an empty string in author list, replace it by "unknown"
        authListFinal = []
        for author in authList:
            if( author == ""):
                author='unknown'
            authListFinal.append(author)
        return(authListFinal)

    def _getLegendFont(self):
        legendfont = FontProperties(size='x-small')
        return(legendfont)
    
    def _addFigureLegend(self, ax, labels, loc="lower center", ncol=4):
        fig = ax.figure
        legendfont = self._getLegendFont()
        assert(len(labels) > 0)
        lnhandles =ax.get_lines()
        assert(len(lnhandles) > 0)
        #Fix for a bug in matplotlib 0.98.5.2. If the len(labels) < ncol,
        # then i get an error "range() step argument must not be zero" on line 542 in legend.py
        if( len(labels) < ncol):
           ncol = len(labels)
        fig.legend(lnhandles, labels, loc=loc, ncol=ncol, prop=legendfont)
                    
    def _drawBarGraph(self, data, labels, barwid):
        #create dummy locations based on the number of items in data values
        xlocations = [x*2*barwid+barwid for x in range(len(data))]
        xtickloc = [x+barwid/2.0 for x in xlocations]
        xtickloc.append(xtickloc[-1]+barwid)
        
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.bar(xlocations, data, width=barwid)
        ax.set_xticks(xtickloc)
        ax.set_xticklabels(labels)
        
        return(ax)

    def _drawHBarGraph(self, datalist, labels, barwid):
        assert(len(datalist) > 0)
        numDataItems = len(datalist)
        #create dummy locations based on the number of items in data values
        ymin = 0.0        
        ylocations = [y*barwid*2+barwid/2 for y in range(numDataItems)]
        ymax = ylocations[-1]+2.0*barwid
        ytickloc = [y+barwid/2.0 for y in ylocations]
        ytickloc.append(ytickloc[-1]+barwid)
        
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.set_color_cycle(self.clrlist)
        ax.set_yticks(ytickloc)
        ax.set_yticklabels(labels)
        
        clridx = 0
        maxclridx = len(self.clrlist)
        ax.barh(ylocations, datalist, height=barwid, color=self.clrlist[clridx])
        ax.set_ybound(ymin, ymax)
        return(ax)
    
    def _drawStackedHBarGraph(self, dataList, labels, legendlist, barwid):
        assert(len(dataList) > 0)
        numDataItems = len(dataList[0])
        #create dummy locations based on the number of items in data values
        ymin = 0.0        
        ylocations = [y*barwid*2+barwid/2 for y in range(numDataItems)]
        ymax = ylocations[-1]+2.0*barwid
        ytickloc = [y+barwid/2.0 for y in ylocations]
        ytickloc.append(ytickloc[-1]+barwid)
        
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.set_color_cycle(self.clrlist)
        ax.set_yticks(ytickloc)
        ax.set_yticklabels(labels)
        
        clridx = 0
        maxclridx = len(self.clrlist)
        ax.barh(ylocations, dataList[0], height=barwid, color=self.clrlist[clridx], label=legendlist[0])
        leftlist = [0 for x in range(0, numDataItems)]
        
        for i in range(1, len(dataList)):
            clridx=clridx+1
            if( clridx >= maxclridx):
                clridx = 0
            leftlist = [x+y for x,y in zip(leftlist, dataList[i-1])]
            ax.barh(ylocations, dataList[i], left=leftlist, height=barwid,
                    color=self.clrlist[clridx], label=legendlist[i])
            
        ax.legend(loc='lower center',ncol=3)        
        ax.set_ybound(ymin, ymax)
        
        return(ax)
    
    def _drawScatterPlot(self,dates, values, plotidx, plotcount, title, refaxs):
        if( refaxs == None):
            logging.debug("initializing scatter plot")
            fig = plt.figure()
            #1 inch height for each author graph. So recalculate with height. Else y-scale get mixed.
            figHt = float(self.commitGraphHtPerAuthor*plotcount)
            fig.set_figheight(figHt)
            #since figureheight is in inches, set around maximum of 0.75 inches margin on top.
            topmarginfrac = min(0.15, 0.85/figHt)
            logging.debug("top/bottom margin fraction is %f" % topmarginfrac)
            fig.subplots_adjust(bottom=topmarginfrac, top=1.0-topmarginfrac, left=0.05, right=0.95)
        else:
            fig = refaxs.figure
            
        axs = fig.add_subplot(plotcount, 1, plotidx,sharex=refaxs,sharey=refaxs)
        axs.grid(True)
        axs.plot_date(dates, values, marker='.', xdate=True, ydate=False)
        axs.autoscale_view()
        
        #Pass None as 'handles' since I want to display just the titles
        axs.set_title(title, fontsize='small',fontstyle='italic')
        
        self._setXAxisDateFormatter(axs)        
        plt.setp( axs.get_xmajorticklabels(), visible=False)
        plt.setp( axs.get_xminorticklabels(), visible=False)
                    
        return(axs)
    
    def _closeScatterPlot(self, refaxs, filename,title):
        #Do not autoscale. It will reset the limits on the x and y axis
        #refaxs.autoscale_view()

        fig = refaxs.figure
        #Update the font size for all subplots y-axis
        for axs in fig.get_axes():
            plt.setp( axs.get_yticklabels(), fontsize='x-small')
                
        fig.suptitle(title)        
        fig.savefig(filename, dpi=self.dpi, format=self.format)
        
    def _drawPieGraph(self, slicesizes, slicelabels):
        fig = plt.figure()
        axs = fig.add_subplot(111, aspect='equal')        
        (patches, labeltext, autotexts) = axs.pie(slicesizes, labels=slicelabels, autopct='%1.1f%%')
        #Turn off the labels displayed on the Piechart. 
        plt.setp(labeltext, visible=False)
        plt.setp(autotexts, visible=False)
        axs.autoscale_view()
        #Reposition the pie chart so that we can place a legend on the right
        bbox = axs.get_position()        
        (x,y, wid, ht) = bbox.bounds
        wid = wid*0.8
        bbox.bounds = (0, y, wid, ht)
        axs.set_position(bbox)
        #Now create a legend and place it on the right of the box.        
        legendtext=[]
        for slabel, ssize in zip(slicelabels, autotexts):
           legendtext.append("%s : %s" % (slabel, ssize.get_text()))

        fontprop = self._getLegendFont()
        legend = axs.legend(patches, legendtext, loc=(1, y), prop=fontprop)
        
        return(axs)

    def _setXAxisDateFormatter(self, ax):
##        years    = YearLocator()   # every year
##        months   = MonthLocator(interval=3)  # every 3 month
##        yearsFmt = DateFormatter('%Y')
##        monthsFmt = DateFormatter('%b')
        # format the ticks
##        ax.xaxis.set_major_locator(years)
##        ax.xaxis.set_major_formatter(yearsFmt)
##        ax.xaxis.set_minor_locator(months)
##        ax.xaxis.set_minor_formatter(monthsFmt)
        plt.setp( ax.get_xmajorticklabels(), fontsize='small')
        plt.setp( ax.get_xminorticklabels(), fontsize='x-small')
        
    def _closeDateLineGraph(self, ax, filename):
        assert(ax != None)
        ax.autoscale_view()
        self._setXAxisDateFormatter(ax)
        ax.grid(True)
        ax.set_xlabel('Date')
        fig = ax.figure
        fig.savefig(filename, dpi=self.dpi, format=self.format)        
        
    def _drawDateLineGraph(self, dates, values, axs= None):
        if( axs == None):
            fig = plt.figure()            
            axs = fig.add_subplot(111)
            axs.set_color_cycle(self.clrlist)
            
        axs.plot_date(dates, values, '-', xdate=True, ydate=False)
        
        return(axs)
    