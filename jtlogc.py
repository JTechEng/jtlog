#!/usr/bin/python3
# Copyright © 2020 - J-Tech Engineering, Ltd.
#
# jtlogc.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
            
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Now that that's out of the way...
#
# A curses-based app for reading several different temperature sensors 
# based on the Microchip MCP3421 18-bit Delta Sigma converter. The 
# ti2c.py module contains the definition for the tempsensor class.
# Import the module as shown below. 
# Built-in functions:
#   tempsensor(address,mode) - create an object of class tempsensor
#       address: there are 8 possible addresses, numbered 0-7.
#       mode: the ADC has four possible conversion modes (0-3): 12, 14, 16 & 18-bit.                      
#
# Constants used in mapping temperature (by mode, not by individual sensor):
#
# If individual sensor calibration data is available, program the values
# as follows (it's a line: y = mx + b):
#   tempsensor.set_slope(m)
#   tempsensor.set_intercept(b)
#
# The following slope,intercept pairs are default values, based on perfect
# conditions, i.e. 0% tolerance on resistors, 0% error in the Platinum RTD
# sensor, 0V offset in the sensor amplifiers, error-free ADC conversion:
#
# resolution |    slope    | intercept
#    12 bits | 62.85027E-3 | 70.64385
#    14 bits | 15.71257E-3 | 70.64385
#    16 bits | 3.928142E-3 | 70.64385
#    18 bits | 982.0354E-6 | 70.64385
#
# The default values can produce reasonably accurate results, but calibrated
# values will reduce errors to a minimum. 
#
# Note also that the main loop sleeps for the amount of time until a fresh sample
# is expected, but does not account for how long it takes to process it; therefore, 
# it's running slightly slower than it would appear. Possible solutions include
# either adjusting the sleep time, or converting to an exception-based system in
# which an expiring timer triggers a device read.
#
# This is an adaptation of the cli tool, jtlog.py, to use curses for a more 
# menu-driven approach. It has similar features, but is equipped with a more 
# sophisticated display. It also moves away from continuous sampling; the menu 
# driven version is meant to log data, and supports much longer sample periods.
#
# Implementation details:
# -curses is used to manage the window header row, the pull-down menus, and all
#  child windows for entering data.
#
# -json is used to maintain configuration information such as calibration info. 
#  on each sensor, desired precision, system-wide sample period, start and stop
#  times for sample recording, log-file base name, etc.
#
# -threading and queues are used to manage all sensors. There are a lot of them.
#  Each sensor is broken into a front-end and a back-end; the front end displays
#  data on the screen, while the back-end issues commands to the sensors, and
#  retrieves data from them. There are two additional threads: one for writing
#  log data to file, and one for triggering system-wide sample conversions.
#  each back-end thread puts data in one queue for the front-end, and one queue
#  for storage to file. The back-end thread also has a message queue, which is 
#  used primarily for ending the thread on exit.
#  The front-end threads each receive sample data from a back-end queue, and
#  also receive supervisory requests from a message queue. The logging thread
#  receives information from all back-end sensors, one queue per sensor, and
#  receives supervisory commands from a separate message queue. The primary 
#  purpose of the message queue, as stated above is to instruct the thread to 
#  stop writing sample data to file, update the time of file closure, close 
#  the file, and end. The global triggering thread monitors only a messaging
#  queue for run, halt, and quit functions. Other than this, it simply issues
#  a global trigger command to all connected sensors, so they trigger
#  simultaneously, and sleep in between conversions.
#
# Threads & Curses: Any curses object can be called from any thread, with one
#  exception: curses.doupdate() (and more generally, window.refresh()) must 
#  never ever be called from a thread, other than the main thread. Note that 
#  window.refresh() actually calls curses.doupdate(), so it really is one 
#  exception.


import sys,os
import time             # timers for event coordination
import curses           # display
import curses.textpad   # user input
import json             # config file
import threading,queue  # sample sensors using threads.
import webbrowser       # allow opening company website in preferred browser.

from ti2c import tempsensorglobal
from ti2c import tempsensor     # sensors

class appconfig(object):
    cfgfile = 'config.json'
    cfgpath = '~/.jtlogc'
    logfilebasename = 'jtlog'
    logfileloc = '~/jtlogs'            # assume data stores in run-from location.
    def __init__(self,statwin):
        """appconfig __init__: load system parameters from a config file, or generate a default one (json); delete config.json to regen."""
        self.statwin = statwin
        # if the config file exists already, open & read it; else,
        #   create and fill it with a list of dictionaries containing
        #   sensible values.
        self.cfgpath = os.path.expanduser(self.cfgpath) # if a '~' was in the pathname, expand it.
        try:
            self.load()
        except:
            self.__gendefaultcfg()

    def __gendefaultcfg(self):
        """appconfig __gendefaultcfg: generate a json config file with sensible default values."""
        # create a template dictionary for sensors, and add one key/value pair per sensor.
        self.statwin.message('Generating default config...')
        sensordefaults = {}
        for i in range(len(tempsensor.i2caddress)):
            sensordefaults.update({str(i) : {
                'address' : -1,
                'modeind' : tempsensor.mode,
                'slope' : tempsensor.slope_intercept[tempsensor.mode][0],
                'intercept' : tempsensor.slope_intercept[tempsensor.mode][1],
                'units' : 0}})
        self.sensorcfg = {'sensors' : sensordefaults}

        # add a logging dictionary; e.g. start & stop times, default sample rates, etc.
        self.sensorcfg.update({'logging' : {
            'start time' : time.strftime('%Y:%m:%d:%H:%M:%S'),
            'stop time' : time.strftime('%Y:%m:%d:%H:%M:%S',time.localtime(time.clock_gettime(time.CLOCK_REALTIME)+3600)),
            'sample period' : 1,
            'logfile' : self.logfilebasename,
            'logloc' : self.logfileloc}})

        # create the config directory if it doesn't exist:
        if not os.path.exists(self.cfgpath):
            try:
                os.mkdir(self.cfgpath)
                self.statwin.message('{} directory created.'.format(self.cfgpath))
            except:
                sys.stderr.write('error: invalid path {}; cannot create directory.')
                exit(1)
        # assume we have the directory now:
        #self.cfgfile = '{}/{}'.format(self.cfgpath,self.cfgfile)
        self.save(self.sensorcfg)
        self.createlogdir(self.logfileloc)          # if generating default setup, ensure the log directory exists.

    def createlogdir(self,logfileloc):
        """ create the log directory if it does not exist. """
        logfileloc = os.path.expanduser(logfileloc) # if a '~' was in the pathname, expand it.
        if not os.path.exists(logfileloc):          # full path to log directory does not exist.
            try:
                os.mkdir(logfileloc)
                self.sensorcfg['logging']['logloc'] = logfileloc
                self.save(self.sensorcfg)
                self.statwin.message('new log directory {} created; configuration saved.'.format(self.sensorcfg['logging']['logloc']))
            except:
                self.statwin.message('error: invalid path {}; cannot create directory; using existing: {}.'.format(logfileloc,
                                                                                                                   self.sensorcfg['logging']['logloc']))
        else:
            self.statwin.message('using existing log path: {}.'.format(self.sensorcfg['logging']['logloc']))

    def checksensor(self,sensor):
        """ verify sensor corresponds to a physical device. """
        if sensor['address'] == -1: # if there's no sensor, still valid, even though it's technically not there.
            return True
        try:
            tempsensor(sensor['address'],sensor['modeind'],sensor['units']).write_config()    # write to the ti2c module; will fail if no sensor.
            return True
        except:
            return False

    def load(self):
        """appconfig load: load system parameters from json file; returns a dictionary."""
        with open('{}/{}'.format(self.cfgpath,self.cfgfile),'r') as f:
            self.sensorcfg = json.load(f)
        return self.sensorcfg

    def save(self,sensorcfg):
        """appconfig save: save system parameters to json file; takes the dictionary as a parameter."""
        self.sensorcfg = sensorcfg
        with open('{}/{}'.format(self.cfgpath,self.cfgfile),'w') as f:
            json.dump(self.sensorcfg,f,indent=4)

    def gensensorframework(self):
        """create all sensor, triggering, logging, and displaying objects, message queues, and threads."""
        # instantiate active sensors:
        self.sensor = []
        self.sensorno = []
        for s in sorted(self.sensorcfg['sensors']):
            if self.sensorcfg['sensors'][s]['address'] != -1:
                self.sensorno.append(int(s)) # maps active sensors to sequential list.

                # create the object:
                self.sensor.append(tempsensor(self.sensorcfg['sensors'][s]['address'],
                                              self.sensorcfg['sensors'][s]['modeind'],
                                              self.sensorcfg['sensors'][s]['units']))
                # load calibration info:
                self.sensor[int(s)].set_slope(self.sensorcfg['sensors'][s]['slope'])
                self.sensor[int(s)].set_intercept(self.sensorcfg['sensors'][s]['intercept'])
                
        # queues:
        # qfileio is a list of queues; a thread object of class datalogger gets data from each qfilio queue.
        # the last member of the qfileio list is associated with the global triggering thread, and is used for timestamps.
        # the datalogger uses this to record sample times.
        self.qfileio = []
        [self.qfileio.append(queue.Queue(100)) for _ in range(len(self.sensor)+1)]

        # queues used by display objects; each display object gets data from a queue associated with a sensor thread.
        self.qdisplay = []
        [self.qdisplay.append(queue.Queue(1000)) for _ in range(len(self.sensor))]

        # control queues: threads have a message queue for receiving instructions, pause/run/quit, etc:
        #   qmsg[0..n-1]    - sensorread threads;
        #   qmsg[n..2n-1]   - sensordisp threads;
        #   qmsg[2n]        - datalogger thread;
        #   qmsg[2n+1]      - global trigger thread.
        self.qmsg = []
        [self.qmsg.append(queue.Queue(10)) for _ in range(len(self.sensor)*2+2)]

        # threads:
        # sensor read & display objects (note these create threads and must know which message queues to get/put data from/to):
        self.globalsampleperiod = self.sensorcfg['logging']['sample period']
        self.sensorread = []
        self.sensordisp = []
        for i in range(len(self.sensor)):
            self.sensorread.append(sensorbackend(self.sensor[i],i,
                                                 self.qdisplay[i],self.qfileio[i],self.qmsg[i],
                                                 self.statwin))
            self.sensordisp.append(sensorfrontend(self.sensor[i],self.sensorno[i],i,len(self.sensor),self.globalsampleperiod,
                                                  self.qdisplay[i],self.qmsg[len(self.sensor)+i],
                                                  self.statwin))

        self.logger = datalogger(self.qfileio,self.qmsg[len(self.sensor)*2],self.globalsampleperiod,
                                 self.sensorcfg['logging']['logloc']+'/'+self.sensorcfg['logging']['logfile'],self.statwin)

        self.trigger = sensorglobaltrigger(self.globalsampleperiod,self.qfileio[len(self.sensor)],self.qmsg[len(self.sensor)*2+1],self.statwin)

        # initial samples from sensor are corrupt, so force a trigger now to overwrite whatever is there.
        self.trigger.trigger()
        time.sleep(0.267)       # must wait for conversion to complete before returning. 
        
    def startsensors(self):
        '''send all threads a run message & show them'''
        for q in self.qmsg:
            q.put('r')
        # show the sensor data:
        [sd.windowrefresh() for sd in self.sensordisp]
        self.statwin.message('sensors started')

    def stopsensors(self):
        '''send all threads a halt message; this is like pause, not quit'''
        for q in self.qmsg:
            q.put('h')          # halt the threads functions; do not kill them.
        #self.qmsg[len(self.sensor)*2+1].put('h')   # halt the trigger.

    def pausedisplayupdates(self):
        '''send all display threads a halt message, pausing them; the threads are still running, just not updating'''
        for q in range(len(self.sensor),len(self.sensor)*2):
            self.qmsg[q].put('h')
        #time.sleep(self.globalsampleperiod)    # wait a little so the display threads can stop.
        time.sleep(0.1)                         # if the sample period is long, the program will sit here for far too long.

    def resumedisplayupdates(self):
        '''resume display updates by queueing run commands to the display threads'''
        for q in range(len(self.sensor),len(self.sensor)*2):
            self.qmsg[q].put('r')
        [sd.windowrefresh() for sd in self.sensordisp]
        
    def endsensorframework(self):
        '''send a quit command to each thread; this will make them complete and end'''
        # end datalogger thread; will close log file on exit;
        self.qmsg[len(self.sensor)*2].put('q')
        # datalogger thread blocks on other threads, which may have extremely long 
        # sleep times. Push dummy data onto the sensor back-end threads to force the 
        # threads to unblock, receive the quit command from its message queue, and 
        # finally, mercifully, die.
        # But wait, there's a possibility of confusion if the datalogger queues have data in them:
        while True:
            allempty = True
            for i in range(len(self.sensor)):
                if not self.qfileio[i].empty():
                    allempty = False
            if not self.qfileio[len(self.sensor)].empty():
                allempty = False
            if allempty:
                break
                
        [self.qfileio[i].put((0,0,0.0)) for i in range(len(self.sensor))]   # dump 0 into each sensor backend queue
        self.qfileio[len(self.sensor)].put(time.time()) # dump time into time queue to wake the thread up.
        #self.statwin.message('endsensorframework: awaiting datalogger thread exit.')
        curses.doupdate()
        self.logger.tl.join()
        
        # end sensor front end threads:
        for q in range(len(self.sensor),len(self.sensor)*2):
            self.qmsg[q].put('q')
        for q in range(len(self.sensor)):       # threads block on data; so unblock them.
            self.qdisplay[q].put(0) # raw
            self.qdisplay[q].put(0) # cooked
        #self.statwin.message('endsensorframework: awaiting frontends.')
        curses.doupdate()
        for sd in self.sensordisp:
            sd.td.join()
        
        # end sensor backend threads:
        for q in range(len(self.sensor)):
            self.qmsg[q].put('q')
        #self.statwin.message('endsensorframework: awaiting backends')
        curses.doupdate()
        for sr in self.sensorread:
            sr.ts.join()
        
        # end trigger thread:
        self.qmsg[len(self.sensor)*2+1].put('q')
        #self.statwin.message('endsensorframework: awaiting trigger thread exit.')
        curses.doupdate()
        self.trigger.tgt.join()
        
        # wipe out the queues
        del self.qfileio
        del self.qdisplay
        del self.qmsg

    def regensensorframework(self):
        self.endsensorframework()
        self.gensensorframework()

class thetime(object):
    ysize = 1
    xsize = 20 # yyyy:mm:dd:hh:mm:ss
    xloc = 1 + 12 # (1 to not write on the border, 12 is the length of the string 'local time: ')
    def __init__(self):
        self.yloc = curses.LINES - 5 - 4    # a priori knowledge: status window is 5 lines, border is 1 line, pos. above start/stop times.
        self.win= curses.newwin(self.ysize,self.xsize,self.yloc,self.xloc)
        self.win.bkgd(' ',curses.color_pair(1))

        self.qmsg = queue.Queue(2)
        self.tloctime = threading.Thread(target=self.__syslocaltimetask,name='t-rtc',args=())
        self.tloctime.start()

    def move(self):
        self.yloc = curses.LINES - 5 - 4
        self.win.mvwin(self.yloc,self.xloc)

    def __syslocaltimetask(self):
        msg = 'r'
        while(True):
            if msg == 'r':
                with threading.Lock():
                    self.win.addstr(0,0,time.strftime('%Y:%m:%d:%H:%M:%S'))
                    self.win.noutrefresh()
            elif msg == 'q':
                break

            if not self.qmsg.empty():                               # only processes when data received.
                msg = self.qmsg.get()

            time.sleep(1)
            
        #sys.stderr.write('thread: {} ended.\n'.format(threading.current_thread().name))
        # end thread

    def endthetime(self):
        self.qmsg.put('q')
        self.tloctime.join()
        del self.qmsg
        del self.win


class datalogger(object):
    def __init__(self,qfileio,qmsg,sampleperiod,logfileprefix,statwin):     # note qfileio is an array of queues
        self.qfileio = qfileio
        self.qmsg = qmsg
        self.sampleperiod = sampleperiod
        self.logfileprefix = logfileprefix      # path and prefix of log file; time stamp and csv suffix added in-thread
        self.statwin = statwin
    
        self.tl = threading.Thread(target=self.__logwriter,name='t-datalogger',args=())
        self.tl.start()

    # the sensor task will queue the sensor address, calculated temperature, and raw adc sample,
    # instead of maintaining a column of data, just write addr,raw,cooked,,addr,raw,cooked,,adr,raw,cooked...
    # this way the sensor doesn't need to know its number, and the log function doesn't need to care, but 
    # the cost is more data being queued.
    # the task will block waiting for data from the queue while running, but if halted will check every sample period 
    # for supervisory queue messages, such as either 'r' or 'q'.

    def __logwriter(self):
        # open a file for writing sample data
        log = time.strftime(self.logfileprefix + '%Y%m%d%H%M%S.csv')
        datalog = open(log,'w')
        header = 'Filename: ' + log + '\n'
        endstamp = len(header)
        datalog.write(header)
        header = 'Start time: ' + time.asctime() + '\n'
        endstamp += len(header)
        datalog.write(header)
        datalog.write('dnE time: ' + time.asctime() + '\n') # thread will overwrite this when terminating.
        datalog.write('Sample period: ' + str(self.sampleperiod) + ' seconds.\n')

        # adapt the list size to suit the # of sensors.
        valsensor = []
        [valsensor.append(0) for _ in range(len(self.qfileio)-1)]

        msg = 'r'               # initial state is running.

        while True:
            if msg == 'r':
                #sys.stderr.write('{}: awaiting timestamp.\n'.format(threading.current_thread().name))
                with threading.Lock():
                    timestamp = self.qfileio[len(self.qfileio)-1].get()  # a float
                for i in range(len(self.qfileio)-1):    # all queues have tuples, except the time stamp
                    #sys.stderr.write('{}: awaiting q[{}].\n'.format(threading.current_thread().name,str(i)))
                    with threading.Lock():
                        valsensor[i] = self.qfileio[i].get()    # a tuple: (sensor address, raw sample, cooked temp)
                if valsensor[0][0] != 0:   # if the address entry of the tuple is 0, this is end of file, so don't write.
                    datalog.write(time.strftime('%Y/%m/%d %H:%M:%S.{:03},'.format(int(timestamp % 1 * 1000)),time.localtime(timestamp)))
                    for d in valsensor:
                        datalog.write(',{:#4x},{:#7x},{:#7.3f},'.format(d[0],d[1],d[2]))
                    datalog.seek(datalog.tell()-1)               # move back a character; overwrite the comma with a \n.
                    datalog.write('\n')
            else:
                time.sleep(self.sampleperiod)

            # check for supervisor message:
            if self.qmsg.empty() == False:
                msg = self.qmsg.get()
                #self.statwin.message('thread: {} received {}.'.format(threading.current_thread().name,msg))
                #sys.stderr.write('{}: received {}.\n'.format(threading.current_thread().name,msg))
                if msg == 'q':
                    break

        datalog.seek(endstamp)
        datalog.write('End time: ' + time.asctime())
        datalog.close()
        #self.statwin.message('thread: {} ended.'.format(threading.current_thread().name))
        #sys.stderr.write('thread: {} ended.\n'.format(threading.current_thread().name))
        # end thread.

class sensorglobaltrigger(object):
    def __init__(self,triggertime,qfileio,qmsg,statwin):
        self.triggertime = triggertime
        self.qfileio = qfileio
        self.qmsg = qmsg
        self.statwin = statwin
        self.sensors = tempsensorglobal()
        self.sensors.reset()

        self.tgt = threading.Thread(target=self.__trigger,name='t-trig',args=())
        self.tgt.start()

    def trigger(self):
        with threading.Lock():
            self.sensors.trigger()

    # method will trigger all devices to convert simultaneously; min. time = 266.67mS.
    # messages retrieved from qmsg:
    # 'r' = run; q = end function; anythinge else = halt.
    def __trigger(self):
        msg = 'h'
        tnext = time.perf_counter() + self.triggertime
        while(True):
            if msg == 'r':
                if tnext > time.perf_counter():
                    time.sleep(tnext - time.perf_counter())
                tnext += self.triggertime
                with threading.Lock():
                    self.sensors.trigger()
                    self.qfileio.put(time.time())  # in a raspian system, returns a float with fractional seconds.
                #self.statwin.message('thread: {} triggered.'.format(threading.current_thread().name))
            while(tnext - time.perf_counter() > 0.25 or msg != 'r'):
                if not self.qmsg.empty():
                    msg = self.qmsg.get()
                    #self.statwin.message('thread: {} received {}.'.format(threading.current_thread().name,msg))
                    if msg == 'r':
                        tnext = time.perf_counter()
                        break
                    if msg == 'q': 
                        break
                time.sleep(0.15)
            if msg == 'q':
                break
        #self.statwin.message('thread: {} ended.'.format(threading.current_thread().name))
        #sys.stderr.write('thread: {} ended.\n'.format(threading.current_thread().name))
        # end thread

class sensorbackend(object):
    # creates a thread, retrieves data from one of up to eight i2c devices,
    # posts data to one queue for display, & a second queue for logging;
    # listens to a third for instructions on whether it should continue running.
    # note that the physical device is triggered by the global trigger thread,
    # so there's little need to start/stop the sensor back-end; to stop it from 
    # sampling, halt the global trigger function.
    def __init__(self,sensor,sensorno,qdisplay,qfileio,qmsg,statwin):
        self.sensor = sensor        # an existing sensor object
        self.sensorno = sensorno
        self.qdisplay = qdisplay
        self.qfileio = qfileio
        self.qmsg = qmsg
        self.statwin = statwin
        
        try:
            self.sensor.stop_sampling() # Don't let the sensor run initially, or it will fill up the queue with data!
            self.statwin.message('sensordevice: sensor = {:#04x}; mode = {}; cfg = {:#04x}.'.format(self.sensor.address,self.sensor.mode,self.sensor.cfgbyte))
            self.ts = threading.Thread(target=self.__sensoroneshottask,name='t-sensor{}'.format(self.sensorno),args=())
            self.ts.start()
        except:
            self.statwin.message('sensordevice: sensor @ ' + hex(self.sensor.address) + ' not found.')
       
        # initial value from sensor seems to be corrupt; do an immediate trigger of the specific sensor,
        # but don't bother collecting the data.
        #with threading.Lock():
        #    self.sensor.trigger()   # note this is not a global trigger.
        #time.sleep(0.467)           # don't return from init until initial corrupt trigger has expired.

    def __sensortask(self):
        while(True):
            with threading.Lock():
                if self.sensor.read_status() and self.sensor.status & 0x10: # sensor status bit 4 will be 1 if in continuous mode.
                    raw = self.sensor.get_tempraw()
                    cooked = self.sensor.get_tempcooked()
                    self.qfileio.put((self.sensor.address,raw,cooked))
                    self.qdisplay.put(raw)
                    self.qdisplay.put(cooked)
            time.sleep(0.8 / self.sensor.get_samplerate())
            if self.qmsg.empty() == False:
                msg = self.qmsg.get()
                if msg == 'q':
                    break
                elif msg == 'r':
                    self.sensor.start_sampling()
                elif msg == 'h':
                    self.sensor.stop_sampling()
            #self.statwin.message('thread: {}\tqdisplay: {}\tqfileio: {}.'.format(threading.current_thread().name,self.qdisplay.qsize(),self.qfileio.qsize()))
            
    # The read_status method will return true only when it is not converting; will return false during conversion.
    # For this reason, once the data is read, await a False condition before expecting new data. Rather than using
    # some sort of message system to indicate a conversion is underway, we poll the device itself to see if a
    # conversion has been triggered. The global trigger function above will initiate a conversion on all devices at once.
    # initial sample is garbage; not sure why.
    def __sensoroneshottask(self):
        data_ready = False
        while(not data_ready):
            data_ready = self.sensor.read_status()
            time.sleep(0.050)
        triggered = False
        while(True):
            with threading.Lock():
                data_ready = self.sensor.read_status()
            if not triggered and not data_ready:
                triggered = True
            if triggered and data_ready:
                triggered = False
                with threading.Lock():
                    raw = self.sensor.get_tempraw()
                    cooked = self.sensor.get_tempcooked()
                    self.qfileio.put((self.sensor.address,raw,cooked))
                    self.qdisplay.put(raw)
                    self.qdisplay.put(cooked)
                #self.statwin.message('thread: {}\tqdisplay: {}\tqfileio: {}.'.format(threading.current_thread().name,self.qdisplay.qsize(),self.qfileio.qsize()))
            if self.qmsg.empty() == False:
                msg = self.qmsg.get()
                if msg == 'q':
                    break
            time.sleep(0.200) # conversion takes ~267mS, so check more frequently than that.
        #self.statwin.message('thread: {} ended.'.format(threading.current_thread().name))
        #sys.stderr.write('thread: {} ended.\n'.format(threading.current_thread().name))
        # end thread

class sensorfrontend(object):
    ybuffer = 18    # need a way of determining this automagically; # of rows to exclude from window height calc.
    xsize = 12
    def __init__(self,sensor,sensorno,displaypos,maxwindows,period,qdisplay,qmsg,statwin):
        # way too many parameters!!!
        self.sensor = sensor            # sensor details.
        self.sensorno = sensorno+1      # sensor number + 1 from the json config file.
        self.displaypos = displaypos    # sensor window display position (0-7).
        self.maxwindows = maxwindows    # used to be fixed at 8, but caused trouble; actual # of configured sensors.
        self.period = period
        self.statwin = statwin
        self.qdisplay = qdisplay
        self.qmsg = qmsg

        winperrow = int((curses.COLS - 2) / (self.xsize + 1))    # # of windows that can fit on a single row.
        winrows = int(self.maxwindows / winperrow)               # # of rows of sensor windows; always round up! 8/3 = 2.666, meaning 3 rows, etc.
        if (self.maxwindows % winperrow) > 0:
            winrows += 1
        winrow = int(self.displaypos/winperrow)
        self.ysize = int((curses.LINES - self.ybuffer - (winrows - 1)) / winrows) # total # of available lines
        
        yloc = 3 + int(self.displaypos/winperrow) * (self.ysize + 1) * winrow
        xloc = 1 + (self.displaypos - (winrow * winperrow)) * (self.xsize + 1)
   
        self.sensorwin = curses.newwin(self.ysize,self.xsize,yloc,xloc)
        self.sensorwin.bkgd(' ',curses.color_pair(1))
        self.sensorwin.border()
        self.banner = str(' sensor ' + str(self.sensorno) + ' ')
        self.sensorwin.addstr(0,int((self.xsize - len(self.banner))/2),self.banner,curses.A_BOLD)

        self.raw = [0 for i in range(self.ysize - 3)]  # holds values for display in scrolling window
        self.cookedhist = [0 for i in range(self.ysize - 3)]  # holds values for display in scrolling window
        self.ind = 0 # raw data index.
        
        self.td = threading.Thread(target=self.__sensordisplaytask,name='t-disp{}'.format(self.sensorno),args=())
        self.td.start()

        # show the window right away.
        self.windowrefresh()

    def displaycooked(self):
        self.sensorwin.addstr(self.ysize-2,1,str('%7.3f' % self.cooked + self.sensor.unit[self.sensor.units]).rjust(self.xsize-2),curses.A_BOLD)

    def displayhist(self,fmt):
        # write the whole raw list to the upper part of the sensor window.
        if self.ind == 0:
            j = self.ysize - 4
        else:
            j = self.ind - 1

        for i in range(self.ysize - 3,0,-1):
            if fmt == True:
                self.sensorwin.addstr(i,1,str('%7.3f' % self.cookedhist[j] + self.sensor.unit[self.sensor.units]).rjust(self.xsize-2))
            else:
                self.sensorwin.addstr(i,1,str('{:#07x}'.format(self.raw[j])).rjust(self.xsize-3))
            j -= 1
            if j < 0:
                j = self.ysize - 4

    def windowrefresh(self):
        self.sensorwin.border()
        self.sensorwin.addstr(0,int((self.xsize - len(self.banner))/2),self.banner,curses.A_BOLD)
        self.displayhist(True)                          # make parm false to see raw sensor data
        self.displaycooked()
        self.sensorwin.noutrefresh()

    def __sensordisplaytask(self):
        self.cooked = 0
        msg = 'h'                                                   # run, but there's no data initially.
        while(True):
            if msg == 'r':
                while(not self.qdisplay.empty()):
                    with threading.Lock():
                        self.raw[self.ind] = self.qdisplay.get()    # will block while awaiting data.
                        self.cookedhist[self.ind] = self.cooked     # keep a history of cooked values too.
                        self.cooked = self.qdisplay.get()
                    # advance the object's list index:        
                    self.ind += 1
                    if self.ind >= self.ysize - 3:
                        self.ind = 0
                    if self.qdisplay.empty():                       # only refresh once, regardless of how many entries.
                        self.windowrefresh()
            elif msg == 'q':
                break
            else:   # not run == halt!
                while(not self.qdisplay.empty()):
                    with threading.Lock():
                        dummy = self.qdisplay.get()                 # discard raw.
                        dummy = self.qdisplay.get()                 # discard cooked.
            time.sleep(0.25)
            if not self.qmsg.empty():
                msg = self.qmsg.get()

            #self.statwin.message('thread: {}\tqdisplay: {}.'.format(threading.current_thread().name,self.qdisplay.qsize()))
        #self.statwin.message('thread: {} ended.'.format(threading.current_thread().name))
        #sys.stderr.write('thread: {} ended.\n'.format(threading.current_thread().name))
        # end thread

class mainwindow(object):
    appname = ' Sigma Delta ADC Analyser & Logger '
    copyright = ' (c)2020 - J-Tech Engineering, Ltd. '
    def __init__(self,stdscr,settings):

        self.stdscr = stdscr
        self.settings = settings
        
        self.y = curses.LINES
        self.x = curses.COLS

        if curses.has_colors() == True:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1,curses.COLOR_GREEN,curses.COLOR_BLUE)
            curses.init_pair(2,curses.COLOR_WHITE,curses.COLOR_RED)
            curses.init_pair(3,curses.COLOR_GREEN,curses.COLOR_BLACK)
            curses.init_pair(4,curses.COLOR_MAGENTA,curses.COLOR_BLUE)
            curses.init_pair(5,curses.COLOR_MAGENTA,curses.COLOR_BLACK)      # debug window
            self.stdscr.bkgd(' ',curses.color_pair(1))

        self.refresh()

    def refresh(self):
        '''redraw the main window'''
        if curses.is_term_resized(self.y,self.x):
            self.__resize()
        self.dresswin()
        self.stdscr.noutrefresh()

    def __resize(self):
        '''update all display variables; called by refresh'''
        curses.update_lines_cols()
        self.y=curses.LINES
        self.x=curses.COLS
        curses.resizeterm(self.y,self.x)
        self.stdscr.resize(self.y,self.x)
        self.stdscr.clear()

    def dresswin(self):
        '''put all of the logging details on the main window'''
        self.stdscr.erase()
        self.stdscr.border()
        self.stdscr.addstr(0,int((curses.COLS - len(self.appname))/2),self.appname,curses.A_BOLD | curses.color_pair(1))
        self.stdscr.addstr(curses.LINES-1,int((curses.COLS - len(self.copyright))/2),self.copyright,curses.color_pair(1))
        
        self.stdscr.addstr(curses.LINES - 5 - 4,1,'local time: ')
        self.stdscr.addstr(curses.LINES - 5 - 3,1,'start time: {}'.format(self.settings.sensorcfg['logging']['start time']))
        self.stdscr.addstr(curses.LINES - 5 - 2,1,'stop time:  {}'.format(self.settings.sensorcfg['logging']['stop time']))
        
        # note the datalogger object fills in the date & time for the log file when it's opened; so just give the concept of the file name:
        logfileinfo = str('log file: {}/{}yyyymmddhhmmss.csv'.format(self.settings.sensorcfg['logging']['logloc'],
                                                                     self.settings.sensorcfg['logging']['logfile'])).rjust(curses.COLS - 34)
        sampleperiodinfo = str('sample period: {} s'.format(self.settings.sensorcfg['logging']['sample period'])).rjust(curses.COLS - 34)
        self.stdscr.addstr(curses.LINES - 5 - 4,33,sampleperiodinfo)
        self.stdscr.addstr(curses.LINES - 5 - 2,33,logfileinfo)

        # display each sensor's configured state; note i is the sequence of defined sensors, and not neccessarily contiguous:
        j=0 # Use j to correctly locate the sensor configuration blocks: left-justified, no gaps!
        for i in sorted(self.settings.sensorcfg['sensors']):
            if self.settings.sensorcfg['sensors'][i]['address'] != -1 and int(j+1)*13 < curses.COLS-2:
                self.stdscr.addstr(curses.LINES - 15,2 + 13 * int(j),
                                   '~sensor #{}~'.format(int(i)+1),curses.A_BOLD)
                self.stdscr.addstr(curses.LINES - 14,2 + 13 * int(j),
                                   'addr: {:#05x}'.format(self.settings.sensorcfg['sensors'][i]['address']))
                self.stdscr.addstr(curses.LINES - 13,2 + 13 * int(j),
                                   'sr: {} bits'.format(tempsensor.mcp3421[self.settings.sensorcfg['sensors'][i]['modeind']][0]))
                self.stdscr.addstr(curses.LINES - 12,2 + 13 * int(j),
                                   'm: {:#3.6f}'.format(self.settings.sensorcfg['sensors'][i]['slope']))
                self.stdscr.addstr(curses.LINES - 11,2 + 13 * int(j),
                                   'b: {:#5.5f}'.format(self.settings.sensorcfg['sensors'][i]['intercept']))
                j+=1
    
    def centremessage(self,verbiage):
        '''put a bold one liner in the centre of the main window'''
        verbiage = ' {} '.format(verbiage)
        pad = ' ' * len(verbiage)
        self.stdscr.addstr(int(curses.LINES/2)-1,int((curses.COLS-len(pad))/2),pad)
        self.stdscr.addstr(int(curses.LINES/2),int((curses.COLS-len(verbiage))/2),
                           verbiage,curses.color_pair(4) | curses.A_BOLD)
        self.stdscr.addstr(int(curses.LINES/2)+1,int((curses.COLS-len(pad))/2),pad)

class msgwin(object):
    y = 5            # # of lines in status window.
    def __init__(self):
        self.ind = 0
        self.spew = ['' for i in range(self.y)]
        #if curses.COLS > 79:
        #    self.x = 78
        #else:
        #    self.x = curses.COLS - 2
        self.x = curses.COLS - 2
        self.win = curses.newwin(self.y,self.x,curses.LINES - self.y - 1,curses.COLS - self.x - 1)
        self.win.bkgd(' ',curses.color_pair(5))
        self.message('status messages will appear here')

    def resize(self):
        self.x = curses.COLS - 2
        self.win.resize(self.y,self.x)
        self.win.mvwin(curses.LINES - self.y - 1,curses.COLS - self.x - 1)
        self.message('status window resized &/or moved')

    def refreshvirtual(self):        # if the main window is refreshed, the message window must be redrawn.
        self.win.touchwin()
        self.win.noutrefresh()

    def message(self,text):
        text = text.replace('\n','<cr>')
        text = text.replace('\x1b','<esc>')
        self.spew[self.ind] = text.strip()[:self.x - 1]
        self.win.erase()
        j = self.ind
        for i in range(self.y):
            j += 1
            if j >= self.y:
                j = 0
            self.win.addstr(i,0,self.spew[j])
        self.ind += 1
        if self.ind >= self.y:
            self.ind = 0
        self.win.noutrefresh()

class menuheader(object):
    menurow = 1
    def __init__(self,header):
        self.header = header
        self.__getmwidth()
        self.mheader = []
        for i in range(0,len(header)):
            self.mheader.append(curses.newwin(self.menurow,self.menuwidth,self.menurow,1 + (1 + self.menuwidth) * i))
            self.mheader[i].addstr(0,int((self.menuwidth - len(header[i]))/2),header[i])

    def refreshmenu(self,menu):
        for i in range(0,len(self.mheader)):
            if i == menu:
                self.mheader[i].bkgd(' ',curses.color_pair(3))
            else:
                self.mheader[i].bkgd(' ',curses.color_pair(2))                  # what happens if we don't have colour?
            self.mheader[i].noutrefresh()

    def resize(self):
        self.__getmwidth()
        for i in range(0,len(self.mheader)):
            self.mheader[i].resize(self.menurow,self.menuwidth)
            self.mheader[i].mvwin(self.menurow,1 + (1 + self.menuwidth) * i)
            self.mheader[i].erase()
            self.mheader[i].addstr(0,int((self.menuwidth - len(self.header[i]))/2),self.header[i])
            self.mheader[i].noutrefresh()
        self.refreshmenu(None)

    def __getmwidth(self):
        self.menuwidth = int((curses.COLS - len(self.header) - 2 + 1)/len(self.header))   # the extra -2 is to accommodate the border around the screen.

class menu(object):
    menus = 4
    def __init__(self,menunum,choices,statwin):
        self.choices = choices
        self.choices.append('cancel')
        self.selection = 0
        if menunum < 0:
            self.menunum = 0
        elif menunum >= self.menus:
            self.menunum = self.menus - 1
        else:
            self.menunum = menunum
        self.itemcount = len(self.choices)
        self.menuwidth = int((curses.COLS - self.menus - 2 + 1)/self.menus)         # the extra -2 is to accommodate the border around the screen.
        self.y = 2                                                                  # always right below the menu line at the top of the window.
        self.x = 1 + (1 + self.menuwidth) * self.menunum
        self.statwin = statwin

    def __nav(self,delta):
        if delta >= ord('0') and delta <= ord('9'):
            self.selection = int(chr(delta)) - 1
        elif delta == 1 or delta == -1:
            self.selection += delta
        if self.selection >= self.itemcount:
            self.selection = 0
        elif self.selection < 0:
            self.selection = self.itemcount - 1

    def display(self):
        ddmenu = curses.newwin(self.itemcount,self.menuwidth,self.y,self.x)
        ddmenu.bkgd(' ',curses.color_pair(2))
        ddmenu.keypad(True)
        
        selection_existing = self.selection
        
        key = curses.ERR
        while True:
            for i,choice in enumerate(self.choices):
                if i == self.selection:
                    textattr = curses.color_pair(3)
                else:
                    textattr = curses.color_pair(2)
                ddmenu.addstr(i,1,choice,textattr)
            ddmenu.noutrefresh()
            curses.doupdate()

            key = ddmenu.getch()
            if key != curses.ERR:
                if key == curses.KEY_UP:
                    self.__nav(-1)
                elif key == curses.KEY_DOWN:
                    self.__nav(1)
                elif key >= ord('0') and key <= ord('9'):
                    self.__nav(key)
                #elif key in [ord('\x09'),curses.KEY_BTAB,curses.KEY_LEFT,curses.KEY_RIGHT]:     # allow menu switching.
                #    self.selection = self.itemcount
                #    curses.ungetch(key)
                #    break
                elif key == ord('\x1b'):                 # discard changes on escape.
                    self.selection = self.itemcount
                    break
                elif key in [curses.KEY_ENTER, ord('\n'),ord(' ')]:
                    #self.statwin.message('\'' + chr(key) + '\'' + ' - received, ' + str(self.selection + 1) + ' chosen.')
                    break                       # stay in loop until user has selected
                elif key in (curses.KEY_LEFT,curses.KEY_BTAB):    # left,right,tab,btab keys allow menu switching.
                    self.selection = self.itemcount + 1
                    break
                elif key in (curses.KEY_RIGHT,ord('\x09')):
                    self.selection = self.itemcount + 2
                    break
        del ddmenu
        return self.selection

class single_item_entry(object):
    # initialize with the title, name of the field.
    # return the string so the calling function can deal with it.
    # things it needs to take: start time, run time, file location, file name, sample rate.
    # this is entirely for the logging menu. The action menu is more for start/stop operations. Maybe these should be 
    # other quick key operations with a banner on the bottom saying start/stop, etc?
    # use the text pad feature to get the data. Don't convert it!
    # for file location, the path could end up being quite long, so do we want to use a different method here?
    # How about a window driven file manager for selection? Or just create a log directory and name the file. That would be much easier.
    # in this case it's only for time entry: start time; duration, or start stop. Why do I need stop if I have duration? duration if I have stop?
    # this is really only needed for time entry:
    def __init__(self,title,sampledata,statwin):
        self.title = title
        self.sampledata = sampledata
        self.statwin = statwin
        self.ybegin = 5
        self.y = 4
        self.x = 40

        # build the window:
        self.uiwin = curses.newwin(self.y,self.x,self.ybegin,int((curses.COLS - self.x)/2))
        self.uiwin.bkgd(' ',curses.color_pair(2))
        self.uiwin.border()
        self.uiwin.addstr(0,int((self.x - len(self.title))/2),self.title)
        self.uiwin.move(2,int(self.x/2))

    def __terminate_entry(self,ch):
        if ch in (9,10,11,12,13,27,curses.KEY_BTAB):   # return ctrl-g for any of these; terminate the window.
            return 7
        else:
            return ch

    def get_userinput(self):
        windowpadding = 3
        windowlength = self.x - 2 * windowpadding
        
        entrywin = self.uiwin.derwin(1,windowlength,2,windowpadding)
        entrywin.bkgd(' ',curses.color_pair(3))
        entrywin.addstr(0,0,self.sampledata.ljust(windowlength-1),curses.color_pair(3))
        entrywin.move(0,len(self.sampledata))
        curses.curs_set(2)
        self.refresh()
        
        entryfield = curses.textpad.Textbox(entrywin)
        ch = ''
        entryfield.edit(self.__terminate_entry)
        entry = entryfield.gather()

        curses.curs_set(0)
        del entryfield
        del entrywin
        entry = entry.strip()   # remove leading & trailing whitespace
        self.statwin.message('single_item_entry: ->'+entry+'<-')
        return entry
    
    def refresh(self):
        self.uiwin.noutrefresh()
        curses.doupdate()

class sensorcfgwin(object):
    instructions = ' tab to move between fields; arrows to choose; n|p to switch sensor '
    pendingaction = ('save','next','prev')
    maxsensors = 8
    
    def __init__(self,sensor,sensorno,statwin):
        self.ycfg = 10
        if curses.COLS > 79:
            self.xcfg = 78
        else:
            self.xcfg = curses.COLS - 2
        
        self.sensorno = sensorno    # specific sensor (0-7; displayed as 1-8)
        #self.sensors = sensor # dictionary corresponding to all sensors.
        #self.sensor = self.sensors[str(self.sensorno)]
        self.sensor = sensor
        #self.__banner()
        self.banner = ' sensor #' + str(self.sensorno + 1) + ' configuration '
        self.statwin = statwin

        self.nefld = ((0,int((self.xcfg - len(self.banner))/2),self.banner),
                      (1,2,'address:'),
                      (3,2,'mode (0..3):'),
                      (4,2,'resolution:       bits'),
                      (5,2,'max. rate:          Hz'),
                      (7,2,'units(C|K|F):'),
                      (3,int(self.xcfg/2),'~~~~~~~ calibration ~~~~~~~'),
                      (5,int(self.xcfg/2),'slope:'),
                      (7,int(self.xcfg/2),'intercept:'),
                      (9,int((self.xcfg-len(self.instructions))/2),self.instructions))
    
        self.efld = ((1,16,'    ',curses.color_pair(3)),
                     (3,16,' ',curses.color_pair(3)),
                     (4,16,'    ',curses.color_pair(2)),
                     (5,16,'     ',curses.color_pair(2)),
                     (7,16,'  ',curses.color_pair(3)),
                     (5,int(self.xcfg/2)+12,'               ',curses.color_pair(3)),
                     (7,int(self.xcfg/2)+12,'               ',curses.color_pair(3)))

        # instantiate a curses window object
        self.child = curses.newwin(self.ycfg,self.xcfg,3,int((curses.COLS - self.xcfg)/2))
        self.child.border()
        self.child.keypad(True)   # receive chars from the rest of the keyboard.

    #def __banner(self):
    #    self.banner = ' sensor #' + str(self.sensorno + 1) + ' configuration '
        
    def __drawwin(self):
        # construct the window with prompts & fields:
        self.child.bkgd(' ',curses.color_pair(2))
        for i in self.nefld:
            self.child.addstr(i[0],i[1],i[2])
        # load the editable fields up with different background.
        for i in self.efld:
            self.child.addstr(i[0],i[1],i[2],i[3])
        self.child.noutrefresh()
        curses.doupdate()

    def __updatewin(self,field):
        # fetch all current field values:
        if self.sensor['address'] == -1:
            fieldvalue = []
            for i in range(len(self.efld)):
                fieldvalue.append(self.efld[i][2])
        else:
            fieldvalue = [hex(self.sensor['address']),
                          str(self.sensor['modeind']),
                          str(tempsensor.mcp3421[self.sensor['modeind']][0]),
                          str(tempsensor.mcp3421[self.sensor['modeind']][1]),
                          tempsensor.unit[self.sensor['units']],
                          str(self.sensor['slope']).ljust(15),
                          str(self.sensor['intercept']).ljust(15)]
        # invert the colours on the active one:
        for i in range(len(fieldvalue)):
            if i == field:
                attr = curses.A_REVERSE
            else:
                attr = curses.A_NORMAL
            self.child.addstr(self.efld[i][0],self.efld[i][1],fieldvalue[i],self.efld[i][3] | attr)
        self.child.noutrefresh()
        curses.doupdate()

    # serve two masters: the field to be edited, and the indexed item list being scrolled within that field.
    # ...assuming the field holds a selection from a list; if it requires actual user input, that's a different method.
    def __nav(self,field,userinput):
        newfield = field
        delta = 0
        if self.sensor['address'] == -1:
            newfield = 0
        if userinput == curses.KEY_UP:
            delta = 1
        elif userinput == curses.KEY_DOWN:
             delta = -1
        elif userinput == curses.KEY_BTAB:
            newfield -= 1
            if newfield < 0:
                newfield = len(self.efld) - 1
            if newfield == 3:
                newfield = 1
        elif userinput == ord('\x09'):      # curses.KEY_TAB? Weird that this isn't in curses.
            newfield += 1
            if newfield > len(self.efld) - 1:
                newfield = 0
            if newfield == 2:
                newfield = 4
        elif userinput in [curses.KEY_ENTER, ord('\n'),0x1b]:
            newfield = -1                 # if the returned field is -1, save & exit.
        elif userinput in [ord('n'),ord('N')]:  # save & exit, but return a notification that thenext sensor should be loaded.
            newfield = -2
        elif userinput in [ord('p'),ord('P')]:  # same as above, but previous sensor.
            newfield = -3
        return newfield,delta
    
    def __terminate_entry(self,ch):
        if ch in (9,10,11,12,13,u'\u001b',27,curses.KEY_BTAB):   # carriage return will terminate the window.
            return 7
        else:
            return ch

    def __textfieldinput(self,field):
        editwindowobject = curses.newwin(1,15,3 + self.efld[field][0],int((curses.COLS - self.xcfg)/2) + self.efld[field][1])
        editwindowobject.bkgd(' ',curses.color_pair(3))
        valuewin = curses.textpad.Textbox(editwindowobject)
        if field == len(self.efld)-2:
            floatvalue = self.sensor['slope']
        else:
            floatvalue = self.sensor['intercept']
        while True:
            editwindowobject.bkgd(' ',curses.color_pair(3) | curses.A_REVERSE)
            editwindowobject.addstr(0,0,str(floatvalue),curses.A_REVERSE)
            editwindowobject.move(0,14)
            curses.curs_set(2)
            ch = ''
            valuewin.edit(self.__terminate_entry)
            value = valuewin.gather()
            curses.curs_set(0)
            editwindowobject.bkgd(' ',curses.color_pair(3) | curses.A_NORMAL)
            try:
                floatvalue = float(value)
                editwindowobject.clear()
                break
            except:
                if field == len(self.efld)-2:
                    floatvalue = self.sensor['slope']
                else:
                    floatvalue = self.sensor['intercept']
            editwindowobject.addstr(0,0,str(floatvalue).ljust(14),curses.A_NORMAL)
            editwindowobject.noutrefresh()
            with threading.Lock():
                curses.refresh()
        del valuewin
        del editwindowobject
        return floatvalue

    def gensetup(self):
        self.__drawwin()                # set up the fixed part of the window.
        field = 0
        if self.sensor['address'] in tempsensor.i2caddress:
            sensoraddrind = tempsensor.i2caddress.index(self.sensor['address'])
        else:
            sensoraddrind = -1
        #sensoraddrind = self.sensor['address'] #self.sensor[self.sensorno].i2caddrind  #i2caddress.index(self.sensor[self.sensorno].address)
        # retain the existing values in case user escapes out.
        existing_slope = self.sensor['slope']
        existing_intercept = self.sensor['intercept']
        while True:
            self.__updatewin(field)     # fill in the editable fields.
            key = self.child.getch()    # returns an int, not a char.
            if key != curses.ERR:
                # if user attempts to configure another sensor:
                #self.statwin.message('gensetup: key={},{}.'.format(chr(key),key))
                #if key == ord('n') or key == ord('p'): #in ['n','p']:
                #    if key == ord('n'):
                #        self.sensorno += 1
                #        if self.sensorno >= self.maxsensors:
                #            self.sensorno = 0
                #    if key == ord('p'):
                #        self.sensorno -= 1
                #        if self.sensorno < 0:
                #            self.sensorno = self.maxsensors - 1
                #    self.sensor = self.sensors[str(self.sensorno)]
                #    self.__banner()     # update the banner to reflect which sensor
                #    self.statwin.message('gensetup: sensorno={}.'.format(self.sensorno))

                field,delta = self.__nav(field,key)

                if field == 0:          # i2c address
                    sensoraddrind += delta
                    if sensoraddrind < -1:
                        sensoraddrind = 7
                    elif sensoraddrind > 7:
                        sensoraddrind = -1
                    if sensoraddrind == -1:
                        self.sensor['address'] = -1
                    else:
                        self.sensor['address'] = tempsensor.i2caddress[sensoraddrind] #self.sensor[self.sensorno].set_address(sensoraddrind)
                elif field == 1:        # mode
                    modeind = self.sensor['modeind'] + delta #self.sensor[self.sensorno].mode + delta
                    if modeind < 0:
                        modeind = 3
                    elif modeind >= 4:
                        modeind = 0
                    if delta != 0:
                        # slope & intercept change with mode, so switch to stock values if the user changes modes.
                        if modeind == self.sensor['modeind']:
                            self.sensor['slope'] = existing_slope
                            self.sensor['intercept'] = existing_intercept
                        else:
                            self.sensor['slope'] = tempsensor.slope_intercept[modeind][0]
                            self.sensor['intercept'] = tempsensor.slope_intercept[modeind][1]
                    self.sensor['modeind'] = modeind
                elif field == 4:        # units
                    units = self.sensor['units'] + delta
                    if units < 0:
                        units = 2
                    elif units >= 3:
                        units = 0
                    self.sensor['units'] = units
                elif field == 5:
                    self.__updatewin(field)     # fill in the editable fields.
                    slope = self.__textfieldinput(field)
                    self.sensor['slope'] = slope
                elif field == 6:
                    self.__updatewin(field)     # fill in the editable fields.
                    intercept = self.__textfieldinput(field)
                    self.sensor['intercept'] = intercept
                elif field in [-1,-2,-3]:
                    nextmove = self.pendingaction[-field - 1]
                    break
        return self.sensor,nextmove

# call this before calling the curses wrapper, or escape has a 1-second delay.
def shorten_esc_delay():
    os.environ.setdefault('ESCDELAY','200') # in mS; normally it's 1000

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def main(stdscr):
    # try to sort out drawing borders properly, instead of using +/-/| characters.
    #locale.setlocale(locale.LC_ALL,'')
    #code = locale.getpreferredencoding()
    # turns out the user's app window needs to be set up correctly; there's only so much this app can do.

    # direct actual statwin messages here:
    sys.stderr = open('err.txt','w')        # do this in a separate window: watch --interval 5 tail -70 err.txt

    #stdscr = curses.initscr()              # wrapper function handles this
    statwin = msgwin()                      # let's have a status window.
    settings = appconfig(statwin)           # load the setup from file.
    appwindow = mainwindow(stdscr,settings)
    ddheader = ('(s)ensor','(l)ogging','(a)ction','(h)elp')
    ddmenuheading = menuheader(ddheader)
    ddmenuheading.refreshmenu(None)
    statwin.refreshvirtual()
    curses.doupdate()
    
    curses.curs_set(0)                      # turn the cursor off.
    curses.noecho()
    curses.cbreak()
    stdscr.nodelay(True)                    # make getch() non-blocking.
    stdscr.keypad(True)                     # receive non-standard key messages.
    
    clockdisplay = thetime()                # show the current time above the message window.

    selection = 0                           # sensor selection (1-8 if a selection has been made)
    collectdata = False
    collectionalarm = False
    while True:
        key = stdscr.getch()
        if key == -1:
            # idle task is to verify there isn't an impending sample start & stop:
            if collectionalarm:
                starttime = time.mktime(time.strptime(settings.sensorcfg['logging']['start time'],'%Y:%m:%d:%H:%M:%S'))
                currenttime = time.time()
                if starttime > currenttime and collectdata == False:
                    delta = starttime - currenttime
                    if delta < 1:
                        #appwindow.centremessage('           preparing to sample           ')
                        appwindow.centremessage('                                         ')
                        #stdscr.noutrefresh()
                        #verbiage = '                   '
                        #stdscr.addstr(int(curses.LINES/2),int((curses.COLS-len(verbiage))/2),verbiage)
                        curses.doupdate()
                        settings.gensensorframework()           # create threads & queues, but don't start.
                        time.sleep(starttime - currenttime)
                        settings.startsensors()                 # issue run command to all threads.
                        collectdata = True
                    else:
                        # delta is in seconds:
                        verbiage = 'sampling in (days:hh:mm:ss): {:05}:{:02}:{:02}:{:02}'.format(int(delta/86400),
                                                                                                 int(delta%86400/3600),
                                                                                                 int(delta%3600/60),
                                                                                                 int(delta%60))
                        appwindow.centremessage(verbiage)
                        stdscr.noutrefresh()
                        curses.doupdate()
                stoptime = time.mktime(time.strptime(settings.sensorcfg['logging']['stop time'],'%Y:%m:%d:%H:%M:%S'))
                currenttime = time.time()
                if stoptime > currenttime and collectdata == True:
                    delta = stoptime - currenttime
                    if delta < 1:
                        appwindow.centremessage('    stopping sampling    ')
                        stdscr.noutrefresh()
                        curses.doupdate()
                        time.sleep(stoptime - currenttime)
                        settings.endsensorframework()           # destroy the sensor threads, and close the log file.
                        collectdata = False
                        appwindow.centremessage('                         ')
                        collectionalarm = False
                        appwindow.refresh()
                        ddmenuheading.refreshmenu(None)
                        statwin.refreshvirtual()
            curses.doupdate()
            time.sleep(0.050)

        # handle non-standard keys:
        if key == curses.ERR:
            key = ''                        # ignore the error thrown by getch() if no characters available.
        elif key == curses.KEY_RESIZE:
            appwindow.refresh()
            ddmenuheading.resize()
            clockdisplay.move()
            statwin.resize()
            with threading.Lock():
                curses.doupdate()
            key = ''
            stdscr.getch()                  # curses seems to be sending two resize messages; toss the 2nd one.
        else:
            key = chr(key)

        # handle user input:
        if key in ['q','Q','\x1b']:         # also allow escape key to exit.
            statwin.message('exiting...')
            appwindow.centremessage('press any key to exit')
            key = -1
            while key == -1:
                time.sleep(0.050)
                key = stdscr.getch()
            if key == ord('\x1b'):
                statwin.message('exit cancelled')
                appwindow.centremessage('                     ')
            else:
                if collectdata == True:
                    appwindow.centremessage('terminating threads')
                    settings.endsensorframework()
                clockdisplay.endthetime()
                break

        elif key in ['s','S']:
            statwin.message('sensor selection menu')
            if collectdata == True:
                settings.pausedisplayupdates()
            ddmenu = 0
            ddmenuheading.refreshmenu(ddmenu)
           
            # add addresses of configured sensors to the menu.
            menu_items = []
            for i in sorted(settings.sensorcfg['sensors']):
                if settings.sensorcfg['sensors'][i]['address'] == -1:
                    menu_items.append('sensor #{}'.format(int(i)+1))
                else:
                    menu_items.append('sensor #{} - {:#04x}'.format(int(i)+1,settings.sensorcfg['sensors'][i]['address']))

            sensorsel = menu(ddmenu,menu_items,statwin)
            selection = sensorsel.display()
            del sensorsel
            appwindow.refresh()

            # bit of a kluge... added direct sensor selection from within the sensor window here.
            action = ''                 # next action will be returned by sensorcfg
            while action != 'save':
                if selection < len(menu_items) - 1:
                    statwin.message('sensor #' + str(selection + 1) + ' selected.')
                    if collectdata == True:
                        collectdata = False
                        Collectionalarm = False             # don't restart if operation occurs during scheduled sampling.
                        settings.endsensorframework()       # wipe out all threads & queues; save & close the log file.
                    configwindow = sensorcfgwin(settings.sensorcfg['sensors'][str(selection)],selection,statwin)
                    settings.sensorcfg['sensors'][str(selection)],action = configwindow.gensetup()     # load the sensor config values
                   
                    if settings.checksensor(settings.sensorcfg['sensors'][str(selection)]) == True:    # meaning the sensor responded.
                        settings.save(settings.sensorcfg)       # update the config file.
                        statwin.message('sensor #' + str(selection + 1) + ' configured.')
                    else:
                        settings.load()                     # reload the sensor values from file.
                        statwin.message('>>> error: sensor #{} not found; config not updated. <<<'.format(selection + 1))

                    del configwindow                        # clear the configuration window.
                    appwindow.refresh()                     # remove the sensor config window.

                    if action == 'next':
                        selection += 1
                        if selection > sensorcfgwin.maxsensors - 1:
                            selection = 0
                    elif action == 'prev':
                        selection -= 1
                        if selection < 0:
                            selection = sensorcfgwin.maxsensors - 1
                else:
                    action = 'save' # should really be 'abort'
                    statwin.message('operation cancelled.')

            # move to next or previous window if user requests:
            if selection == len(menu_items) + 1:
                curses.ungetch('h')
            elif selection == len(menu_items) + 2:
                curses.ungetch('l')

            if collectdata == True:
                settings.resumedisplayupdates()
            
            appwindow.refresh()
            ddmenuheading.refreshmenu(None)
            statwin.refreshvirtual()
            curses.doupdate()
    
        elif key in ['l','L']:
            statwin.message('data logging menu')
            if collectdata == True:
                settings.pausedisplayupdates()
            ddmenu = 1
            ddmenuheading.refreshmenu(ddmenu)
            menu_items = ['start time','stop time','sample period (sec)','log file prefix','log file location']
            logsel = menu(ddmenu,menu_items,statwin)
            selection = logsel.display()
            del logsel
            appwindow.refresh()

            if selection < len(menu_items) - 1:
                statwin.message(menu_items[selection] + ' selected.')
                if selection == 0:
                    while(True):        # start time (loads time from config file)
                        userinput = single_item_entry(' ' + menu_items[selection] + ' ',settings.sensorcfg['logging']['start time'],statwin)
                        tstart = userinput.get_userinput()
                        tstop = settings.sensorcfg['logging']['stop time']
                        try:
                            time.strptime(tstart,'%Y:%m:%d:%H:%M:%S')
                            if tstop < tstart:       # make stop time = start time if stop time is before new start time.
                                tstop = tstart
                            settings.sensorcfg['logging']['start time'] = tstart
                            settings.sensorcfg['logging']['stop time'] = tstop
                            settings.save(settings.sensorcfg)
                            statwin.message('start time updated: ->'+tstart+'<-')
                            break
                        except:
                            statwin.message('invalid start time: ->'+tstart+'<-')
                elif selection == 1:    # stop time (loads time from config file)
                    while(True):
                        userinput = single_item_entry(' ' + menu_items[selection] + ' ',settings.sensorcfg['logging']['stop time'],statwin)
                        tstop = userinput.get_userinput()
                        tstart = settings.sensorcfg['logging']['start time']
                        try:
                            time.strptime(tstop,'%Y:%m:%d:%H:%M:%S')
                            if tstop < tstart:            # make start time = stop time if stop time is before new start time.
                                tstart = tstop
                            settings.sensorcfg['logging']['start time'] = tstart
                            settings.sensorcfg['logging']['stop time'] = tstop
                            settings.save(settings.sensorcfg)
                            statwin.message('stop time updated: ->'+tstop+'<-')
                            break
                        except:
                            statwin.message('invalid stop time: ->'+tstop+'<-')
                elif selection == 2:    # sample period
                    while(True):
                        sampletime = settings.sensorcfg['logging']['sample period']
                        userinput = single_item_entry(' ' + menu_items[selection] + ' ',str(sampletime),statwin)
                        sampletime = userinput.get_userinput()
                        try:
                            sampletime = float(sampletime)
                            if sampletime < 1/240:          # fastest sample rate at 12 bits.
                                sampletime = 1/240
                            settings.sensorcfg['logging']['sample period'] = sampletime
                            settings.save(settings.sensorcfg)
                            break
                        except:
                            statwin.message('invalid sample time: ->'+sampletime+'<-')
                elif selection == 3:    # log file name entry
                    suggestedlogfile = settings.sensorcfg['logging']['logfile']
                    userinput = single_item_entry(' ' + menu_items[selection] + ' ',suggestedlogfile,statwin)
                    logfile = userinput.get_userinput()
                    if logfile =='':
                        logfile = suggestedlogfile
                    settings.sensorcfg['logging']['logfile'] = logfile
                    settings.save(settings.sensorcfg)
                elif selection == 4:    # log file location
                    # prefill the path to the user's home directory...
                    logloc = settings.sensorcfg['logging']['logloc']
                    if logloc in ('','.'):
                        logloc = os.getcwd()   # assume saving to the current directory.
                    userinput = single_item_entry(' ' + menu_items[selection] + ' ',logloc,statwin)
                    logloc = userinput.get_userinput()
                    settings.createlogdir(logloc)
                del userinput
            else:
                statwin.message('operation cancelled.')

            # if user presses an arrow or tab/btab key, selection will return a menu number indicating which menu to switch to.
            if selection == len(menu_items) + 1:
                curses.ungetch('s')
            elif selection == len(menu_items) + 2:
                curses.ungetch('a')

            if collectdata == True:
                settings.resumedisplayupdates()
            
            appwindow.refresh()
            ddmenuheading.refreshmenu(None)
            statwin.refreshvirtual()
            curses.doupdate()
            
        elif key == 'a' or key == 'A':
            statwin.message('action menu')
            if collectdata == True:
                settings.pausedisplayupdates()
            ddmenu = 2
            ddmenuheading.refreshmenu(ddmenu)
            menu_items = ['start/stop','await start']
            if collectdata == True:
                menu_items[0] += ' *'
            if collectionalarm == True:
                menu_items[1] += ' *'
            actionsel = menu(ddmenu,menu_items,statwin)
            selection = actionsel.display()
            del actionsel

            appwindow.refresh()

            if selection < len(menu_items) - 1:
                statwin.message(menu_items[selection] + ' selected.')
                if selection == 0:      # start/stop - immediate - with logging - runs until stopped.
                    if collectdata == True:
                        statwin.message('stopping sensors.')
                        settings.resumedisplayupdates()     # must be running to stop. ;-)
                        settings.endsensorframework()
                        collectdata = False
                    else:
                        statwin.message('starting sensors.')
                        settings.gensensorframework()
                        collectdata = True
                elif selection == 1:    # start/stop at programmed time - with logging; will stop at stop time.
                    if collectionalarm == True:
                        collectionalarm = False
                        statwin.message('data collection not armed.')
                    else:
                        if time.time() < time.mktime(time.strptime(settings.sensorcfg['logging']['stop time'],'%Y:%m:%d:%H:%M:%S')):
                            collectionalarm = True
                            statwin.message(time.strftime('data collection starting at {}.'.format(settings.sensorcfg['logging']['start time'])))
                        else:
                            statwin.message(time.strftime('not starting; stop time {} has passed.'.format(settings.sensorcfg['logging']['stop time'])))
            else:
                statwin.message('operation cancelled.')

            # menu may return a value outside the range of menu options; this indicates the user
            # wants a different pull-down menu; pre-load a character into the buffer to facilitate switching.
            if selection == len(menu_items) + 1:
                curses.ungetch('l')
            elif selection == len(menu_items) + 2:
                curses.ungetch('h')
            
            # refresh the whole shebang:
            appwindow.refresh()
            ddmenuheading.refreshmenu(None)
            if collectdata == True:
                if selection != 0:
                    settings.resumedisplayupdates()
                else:
                    settings.startsensors()
            statwin.refreshvirtual()
            curses.doupdate()
        elif key == 'h' or key == 'H':
            statwin.message('help menu')
            if collectdata == True:
                settings.pausedisplayupdates()
            ddmenu = 3
            ddmenuheading.refreshmenu(ddmenu)
            menu_items = ['user manual','check for updates','about j-tech','web']
            helpsel = menu(ddmenu,menu_items,statwin)
            selection = helpsel.display()
            del helpsel
            appwindow.refresh()

            if selection < len(menu_items) - 1:
                #statwin.message(menu_items[selection] + ' selected.')
                if selection == 0:      # user manual
                    statwin.message('There isn\'t a manual viewer here, but there is a man page:')
                    statwin.message('type \'man jtlogc\' in your favourite shell.')
                    statwin.message('See README.md for further background information as well.')
                elif selection == 1:    # updates
                    webbrowser.open('https://github.com/JTechEng/jtlog',new=2,autoraise=True)
                    statwin.message('Updates:')
                    statwin.message('see https://github.com/JTechEng/jtlog for the latest release of this application.')
                elif selection == 2:    # about
                    statwin.message('About us:')
                    statwin.message('J-Tech Engineering, Ltd. - 11080 Bond Blvd - Delta BC - V4E 1M7')
                    statwin.message('Lawrence Johnson - lawrence@jtecheng.com - 604 802 7579 - @JTechEng')
                    statwin.message('see http://jtecheng.com/?page_id=74 for our bio.')
                elif selection == 3:    # url... doesn't work through ssh :-(
                    webbrowser.open('http://jtecheng.com',new=2,autoraise=True)
                    statwin.message('see http://jtecheng.com for the latest updates on sensors, software, and what\'s happening at our house.')
            else:
                statwin.message('operation cancelled.')

            if selection == len(menu_items) + 1:
                curses.ungetch('a')
            elif selection == len(menu_items) + 2:
                curses.ungetch('s')
            ddmenuheading.refreshmenu(None)
            if collectdata == True:
                settings.resumedisplayupdates()

            appwindow.refresh()
            ddmenuheading.refreshmenu(None)
            statwin.refreshvirtual()
            curses.doupdate()
        elif key != '':
            statwin.message('\'' + key + '\'' + ' - invalid key')
            key = ''
        #else:
            #if collectdata == 1:
            #with threading.Lock():
            # don't need threadlock, but do need to know if an update is required. We have the sensor devices all created;
            # to do: verify start without sensors configured; or trouble abounds;
            # semaphore? check sensorwin for required update.
        #    for i in sensorout:
                #i.updateraw()
                #i.displaycooked()
        #        i.refresh()

    #while stdscr.getch() == -1:
    #    curses.doupdate()
    #    time.sleep(0.050)
    #stdscr.keypad(False)
    curses.nocbreak()
    curses.echo()
    curses.endwin()

if(__name__ == '__main__'):
    shorten_esc_delay()             # Must happen BEFORE calling the wrapper, else the escape key has a 1 second delay after pressing.
    curses.wrapper(main)
    #main()
