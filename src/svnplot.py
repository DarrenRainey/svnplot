'''
Generate various graphs from the Subversion log data in the sqlite database.
It assumes that the sqlite file is generated using the 'svnlog2sqlite.py' script.

Graph types to be supported
1. Activity by hour of day bar graph (commits vs hour of day) -- Done
2. Activity by day of week bar graph (commits vs day of week) -- Done
3. Author Activity horizontal bar graph (author vs adding+commiting percentage) -- Done
4. Commit activity for each developer - scatter plot (hour of day vs date) -- Done
5. Contributed lines of code line graph (loc vs dates). Using different colour line
   for each developer -- Done
6. total loc line graph (loc vs dates) -- Done
7. file count vs dates line graph -- Done
8. average file size vs date line graph -- Done
9. directory size vs date line graph. Using different coloured lines for each directory
10. directory size pie chart (latest status)
11. Loc and Churn graph (loc vs date, churn vs date)- Churn is number of lines touched
	(i.e. lines added + lines deleted + lines modified)
12. Repository heatmap (treemap)

--- Nitin Bhide (nitinbhide@gmail.com)

Part of 'svnplot' project
Available on google code at http://code.google.com/p/svnplot/
Licensed under the 'New BSD License'

To use copy the file in Python 'site-packages' directory Setup is not available
yet.
'''

import matplotlib.pyplot as plt
from matplotlib.dates import YearLocator, MonthLocator, DateFormatter
import sqlite3
import calendar, datetime
import os.path

def dirname(path, depth):
    #first split the path and remove the filename
    pathcomp = os.path.dirname(path).split('/')
    #now join the split path upto given depth only
    #since path starts with '/' and slice ignores the endindex, to get the appropriate
    #depth, slice has to be [0:depth+1]
    dirpath = '/'.join(pathcomp[0:depth+1])
    return(dirpath)
    
class SVNPlot:
    def __init__(self, svndbpath, dpi=100, format='png'):
        self.svndbpath = svndbpath
        self.dpi = dpi
        self.format = format
        self.clrlist = ['b', 'g', 'r', 'c', 'm', 'y', 'k']
        self.dbcon = sqlite3.connect(self.svndbpath, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        #self.dbcon.row_factory = sqlite3.Row
        # Create the function "regexp" for the REGEXP operator of SQLite
        self.dbcon.create_function("dirname", 2, dirname)
        
        self.cur = self.dbcon.cursor()        

    def __del__(self):
        self.cur = None
        self.dbcon.close()

    def AllGraphs(self, path):
        self.ActivityByWeekday(os.path.join(path, "actbyweekday.png"));
        self.ActivityByTimeOfDay(os.path.join(path, "actbytimeofday.png"));
        self.LocGraph(os.path.join(path, "loc.png"));
        self.FileCountGraph(os.path.join(path, "filecount.png"));
        self.LocGraphAllDev(os.path.join(path, "locbydev.png"));
        self.AvgFileLocGraph(os.path.join(path, "avgloc.png"));
        self.AuthorActivityGraph(os.path.join(path, "authactivity.png"));
        self.CommitActivityGraph(os.path.join(path, "commitactivity.png"));
        self.DirectorySizePieGraph(os.path.join(path, "dirsizepie.png"));
                               
    def ActivityByWeekday(self, filename):
        self.cur.execute("select strftime('%w', commitdate), count(revno) from SVNLog group by strftime('%w', commitdate)")
        labels =[]
        data = []
        for dayofweek, commitcount in self.cur:
           data.append(commitcount)           
           labels.append(calendar.day_abbr[int(dayofweek)])

        ax = self._drawBarGraph(data, labels,0.5)
        ax.set_ylabel('Commits')
        ax.set_xlabel('Day of Week')
        ax.set_title('Activity By Day of Week')

        fig = ax.figure                        
        fig.savefig(filename, dpi=self.dpi, format=self.format)        

    def ActivityByTimeOfDay(self, filename):
        self.cur.execute("select strftime('%H', commitdate), count(revno) from SVNLog group by strftime('%H', commitdate)")
        labels =[]
        data = []
        for hourofday, commitcount in self.cur:
           data.append(commitcount)           
           labels.append(int(hourofday))

        ax = self._drawBarGraph(data, labels,0.5)
        ax.set_ylabel('Commits')
        ax.set_xlabel('Hour of Day')
        ax.set_title('Activity By Hour of Day')

        fig = ax.figure                        
        fig.savefig(filename, dpi=self.dpi, format=self.format)        
        
    def LocGraph(self, filename, inpath='/%'):        
        self.cur.execute("select strftime('%%Y', SVNLog.commitdate), strftime('%%m', SVNLog.commitdate),\
                         strftime('%%d', SVNLog.commitdate), sum(SVNLogDetail.linesadded), sum(SVNLogDetail.linesdeleted) \
                         from SVNLog, SVNLogDetail \
                         where SVNLog.revno = SVNLogDetail.revno and SVNLogDetail.changedpath like '%s'\
                         group by date(SVNLog.commitdate)" % inpath)
        dates = []
        loc = []
        tocalloc = 0
        for year, month, day, locadded, locdeleted in self.cur:
            dates.append(datetime.date(int(year), int(month), int(day)))
            tocalloc = tocalloc + locadded-locdeleted
            loc.append(float(tocalloc))
            
        ax = self._drawDateLineGraph(dates, loc)
        ax.set_title('Lines of Code')
        ax.set_ylabel('Lines')
        
        self._closeDateLineGraph(ax, filename)

    def LocGraphAllDev(self, filename, inpath='/%'):        
        ax = None
        authList = self._getAuthorList()
        for author in authList:
            ax = self._drawlocGraphLineByDev(author, inpath,  ax)
            
        ax.legend(authList, loc='upper left')
            
        ax.set_title('Contributed Lines of Code')
        ax.set_ylabel('Lines')        
        self._closeDateLineGraph(ax, filename)
        
    def LocGraphByDev(self, filename, devname, inpath='/%'):
        ax = self._drawlocGraphLineByDev(devname, inpath)
        ax.set_title('Contributed LoC by %s' % devname)
        ax.set_ylabel('Line Count')
        self._closeDateLineGraph(ax, filename)
            
    def FileCountGraph(self, filename, inpath='/%'): 
        self.cur.execute("select strftime('%%Y', SVNLog.commitdate), strftime('%%m', SVNLog.commitdate),\
                         strftime('%%d', SVNLog.commitdate), sum(SVNLog.addedfiles), sum(SVNLog.deletedfiles) \
                         from SVNLog, SVNLogDetail \
                         where SVNLog.revno = SVNLogDetail.revno and SVNLogDetail.changedpath like '%s'\
                         group by date(SVNLog.commitdate)" % inpath)
        dates = []
        fc = []
        totalfiles = 0
        for year, month, day, fadded,fdeleted in self.cur:
            dates.append(datetime.date(int(year), int(month), int(day)))
            totalfiles = totalfiles + fadded-fdeleted
            fc.append(float(totalfiles))
        
        ax = self._drawDateLineGraph(dates, fc)
        ax.set_title('File Count')
        ax.set_ylabel('Files')
        self._closeDateLineGraph(ax, filename)

    def AvgFileLocGraph(self, filename, inpath='/%'): 
        self.cur.execute("select strftime('%%Y', SVNLog.commitdate), strftime('%%m', SVNLog.commitdate),\
                         strftime('%%d', SVNLog.commitdate), sum(SVNLogDetail.linesadded), sum(SVNLogDetail.linesdeleted), \
                         sum(SVNLog.addedfiles), sum(SVNLog.deletedfiles) \
                         from SVNLog, SVNLogDetail \
                         where SVNLog.revno = SVNLogDetail.revno and SVNLogDetail.changedpath like '%s'\
                         group by date(SVNLog.commitdate)" % inpath)
        dates = []
        avgloclist = []
        avgloc = 0
        totalFileCnt = 0
        totalLoc = 0
        for year, month, day, locadded, locdeleted, filesadded, filesdeleted in self.cur:
            dates.append(datetime.date(int(year), int(month), int(day)))
            totalLoc = totalLoc + locadded-locdeleted
            totalFileCnt = totalFileCnt + filesadded - filesdeleted
            avgloclist.append(float(totalLoc)/float(totalFileCnt))
            
        ax = self._drawDateLineGraph(dates, avgloclist)
        ax.set_title('Average File Size (Lines)')
        ax.set_ylabel('LoC/Files')
        
        self._closeDateLineGraph(ax, filename)

    def AuthorActivityGraph(self, filename, inpath='/%'):
        self.cur.execute("select SVNLog.author, sum(SVNLog.addedfiles), sum(SVNLog.changedfiles), sum(SVNLog.deletedfiles) \
                         from SVNLog, SVNLogDetail \
                         where SVNLog.revno = SVNLogDetail.revno and SVNLogDetail.changedpath like '%s'\
                         group by SVNLog.author" % inpath)

        authlist = []
        addfraclist = []
        changefraclist=[]
        delfraclist = []
        
        for author, filesadded, fileschanged, filesdeleted in self.cur:
            authlist.append(author)            
            activitytotal = float(filesadded+fileschanged+filesdeleted)
            addfraclist.append(float(filesadded)/activitytotal*100)
            changefraclist.append(float(fileschanged)/activitytotal*100)
            delfraclist.append(float(filesdeleted)/activitytotal*100)

        dataList = [addfraclist, changefraclist, delfraclist]
        
        barwid = 0.5
        legendlist = ["Adding", "Modifying", "Deleting"]
        ax = self._drawStackedHBarGraph(dataList, authlist, legendlist, barwid)
        ax.set_title('Author Activity')
        fig = ax.figure
        fig.savefig(filename, dpi=self.dpi, format=self.format)
        
    def CommitActivityGraph(self, filename, inpath='/%'):
        authList = self._getAuthorList()
        authCount = len(authList)

        authIdx = 1
        refaxs = None
        for author in authList:
            axs = self._drawCommitActivityGraphByAuthor(authCount, authIdx, author, inpath, refaxs)
            if( refaxs == None):
                refaxs = axs
            authIdx = authIdx+1
            
        #Set the x axis label on the last graph
        axs.set_xlabel('Date')
        #Turn on the xtick display only on the last graph
        plt.setp( axs.get_xticklabels(), visible=True)
        
        self._closeScatterPlot(refaxs, filename, 'Commit Activity')
        
    def DirectorySizePieGraph(self, filename, depth=2, inpath='/%'):
        sqlQuery = "select dirname(SVNLogDetail.changedpath, %d), sum(SVNLogDetail.linesadded), sum(SVNLogDetail.linesdeleted) \
                         from SVNLog, SVNLogDetail \
                         where SVNLog.revno = SVNLogDetail.revno and SVNLogDetail.changedpath like '%s' \
                         group by dirname(SVNLogDetail.changedpath, %d)" % (depth, inpath, depth)
        self.cur.execute(sqlQuery)
            
        dirlist = []
        dirsizelist = []
        for dirname, linesadded, linesdeleted in self.cur:
            dsize = linesadded-linesdeleted
            if( dsize > 0):
                dirlist.append(dirname)
                dirsizelist.append(dsize)
        
        axs = self._drawPieGraph(dirsizelist, dirlist)
        axs.set_title('Directory Sizes')        
        fig = axs.figure
        fig.savefig(filename, dpi=self.dpi, format=self.format)
        
    def _getAuthorList(self):
        #Find out the unique developers
        self.cur.execute("select author from SVNLog group by author")
        #get the auhor list and store it. Since LogGraphLineByDev also does an sql query. It will otherwise
        # get overwritten
        authList = [author for author, in self.cur]
        return(authList)
        
    def _drawCommitActivityGraphByAuthor(self, authIdx, authCount, author, inpath='/%', axs=None):
        sqlQuery = "select strftime('%%H', commitdate), strftime('%%Y', SVNLog.commitdate), strftime('%%m', SVNLog.commitdate), \
                         strftime('%%d', SVNLog.commitdate) from SVNLog where author='%s' \
                            group by date(commitdate)" % author
        self.cur.execute(sqlQuery)

        dates = []
        committimelist = []
        for hr, year, month, day in self.cur:
            dates.append(datetime.date(int(year), int(month), int(day)))
            committimelist.append(hr)
        axs = self._drawScatterPlot(dates, committimelist, authCount, authIdx, author, axs)
        
        return(axs)
            
    def _drawlocGraphLineByDev(self, devname, inpath='/%', ax=None):
        sqlQuery = "select strftime('%%Y', SVNLog.commitdate), strftime('%%m', SVNLog.commitdate),\
                         strftime('%%d', SVNLog.commitdate), sum(SVNLogDetail.linesadded), sum(SVNLogDetail.linesdeleted) \
                         from SVNLog, SVNLogDetail \
                         where SVNLog.revno = SVNLogDetail.revno and SVNLogDetail.changedpath like '%s' and SVNLog.author='%s' \
                         group by date(SVNLog.commitdate)" % (inpath, devname)
        self.cur.execute(sqlQuery)
        dates = []
        loc = []
        tocalloc = 0
        for year, month, day, locadded, locdeleted in self.cur:
            dates.append(datetime.date(int(year), int(month), int(day)))
            tocalloc = tocalloc + locadded-locdeleted
            loc.append(float(tocalloc))
            
        ax = self._drawDateLineGraph(dates, loc, ax)
        return(ax)
    
    def _drawBarGraph(self, data, labels, barwid):
        #create dummy locations based on the number of items in data values
        xlocations = [x*barwid*2+barwid for x in range(len(data))]
        xtickloc = [x+barwid/2.0 for x in xlocations]
        xtickloc.append(xtickloc[-1]+barwid)
        
        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.set_xticks(xtickloc)
        ax.set_xticklabels(labels)
        ax.bar(xlocations, data, width=barwid)
        ax.autoscale_view()
        
        return(ax)

    def _drawStackedHBarGraph(self, dataList, labels, legendlist, barwid):
        assert(len(dataList) > 0)
        numDataItems = len(dataList[0])
        #create dummy locations based on the number of items in data values
        ylocations = [y*barwid*2+barwid for y in range(numDataItems)]
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
            
        ax.legend(loc='lower left')        
        ax.autoscale_view()
        
        return(ax)
    
    def _drawScatterPlot(self,dates, values, plotidx, plotcount, title, refaxs):
        if( refaxs == None):
            fig = plt.figure()
        else:
            fig = refaxs.figure
            
        axs = fig.add_subplot(plotcount, 1, plotidx,sharex=refaxs,sharey=refaxs)
        axs.grid(True)
        axs.plot_date(dates, values, marker='o', xdate=True, ydate=False)

        #Pass None has 'handles' since I want to display just the titles
        axs.legend([None], [title], loc='upper center')
        plt.setp( axs.get_xticklabels(), visible=False)
        
        if( refaxs != None):
            xmin, xmax = axs.get_xbound()
            #set the yaxis limits to (0-24) hours
            corners = (xmin,0),(xmax,24)            
            refaxs.update_datalim(corners)
            axs.update_datalim(corners)
            
        return(axs)
    
    def _closeScatterPlot(self, refaxs, filename,title):
        years    = YearLocator()   # every year
        months   = MonthLocator(3)  # every 3 month
        yearsFmt = DateFormatter('%Y')
        # format the ticks
        refaxs.xaxis.set_major_locator(years)
        refaxs.xaxis.set_major_formatter(yearsFmt)
        refaxs.xaxis.set_minor_locator(months)
        refaxs.autoscale_view()

        fig = refaxs.figure
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
        legend = axs.legend(patches, legendtext, loc=(1, y))
        plt.setp(legend.get_texts(), fontsize='x-small')
        
        return(axs)
        
    def _closeDateLineGraph(self, ax, filename):
        assert(ax != None)
        ax.autoscale_view()
        years    = YearLocator()   # every year
        months   = MonthLocator(3)  # every 3 month
        months   = MonthLocator(3)  # every 3 month
        yearsFmt = DateFormatter('%Y')
        # format the ticks
        ax.xaxis.set_major_locator(years)
        ax.xaxis.set_major_formatter(yearsFmt)
        ax.xaxis.set_minor_locator(months)
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

if(__name__ == "__main__"):
    #testing
    svndbpath = "D:\\nitinb\\SoftwareSources\\SVNPlot\\svnrepo.db"
    graphfile = "D:\\nitinb\\SoftwareSources\\SVNPlot\\graph.png"
    svnplot = SVNPlot(svndbpath)
    #svnplot.ActivityByTimeOfDay(graphfile)
    #svnplot.LocGraph(graphfile)
    #svnplot.DirectorySizePieGraph(graphfile)    
    svnplot.AllGraphs("D:\\nitinb\\SoftwareSources\\SVNPlot\\")
    