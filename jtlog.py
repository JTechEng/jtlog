#!/usr/bin/python3
# jtlog.py - an application for collecting and displaying data from 
#            sensors supplied by J-Tech Engineering, Ltd.
# Copyright © 2020 - J-Tech Engineering, Ltd.
# licensing & permissions {{{
# jtlog.py is free software: you can redistribute it and/or modify
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
# }}}
# grandiose description {{{
# A logger for reading several ti2c temperature sensors, based on the 
# Microchip MCP3421 18-bit Delta Sigma converter.
# The ti2c.py module contains the definition for the tempsensor class. Import the module 
# as below. 
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
# values will reduce the errors to a minimum. 
#
# Note also that the main loop sleeps for the amount of time until a fresh sample
# is expected, but does not account for how long it takes to process it; therefore, 
# it's running slightly slower than it would appear. Possible solutions include
# either adjusting the sleep time, or converting to an exception-based system in
# which an expiring timer triggers a device read.
# }}}

# modules {{{
import sys,os,getopt
import termios
import time
from ti2c import tempsensor
# }}}

# globals {{{
# number of samples to keep, and number to discard during settling period at start of logging:
maxduration = 31557600 # one year; no real reason for this; seems like enough.
duration = 0        # 0 means sample until you run out of storage space. 
discard = 0         # adjust to suit; # of samples to be discarded before logging.

# log file particulars:
logsubdir = 'jtlogs'
logfile = 'jtlog'
logfile_ext = '.csv'

# Specific variables to the ADC and amplifier stages on the sensor board:
maxsensors = 8      # I2C addresses are available from Microchip.
cfgmodes = 4        # config modes of adc
# }}}

# functions {{{1
# showhelp {{{2
# Explain how to use this program, then dump the user back to the command line:
def showhelp():
    print(sys.argv[0],' -h -s <mode-sensor#1> [-r] [-c] [-s <mode-sensor#2> ... <mode-sensor#{}>] [-d <duration>] [-f filename]\n'.format(maxsensors))
    print('-h,--help\n\tdisplay this message.\n')
    print('-s<mode>,--sensor-mode=<mode>\n\twhere <mode> is 0-4; up to 8 -s<mode> pairs can be supplied;')
    print('\n\t<mode> is one of:\n\t\t0 - no sensor')
    for i in range(cfgmodes):
        print('\t\t%d -' % (i + 1),'%d-bit samples,' % tempsensor.mcp3421[i][0], 'sample rate %.2f Hz' % tempsensor.mcp3421[i][1])
    print('\n\tmax. # of sensors: %d:' % maxsensors)
    for i in range(maxsensors):
        print('\t\tsensor %d' % i,'I2C addr: 0x%2x' % tempsensor.i2caddress[i])
    print('\n\tSensors must be specified in ascending order of address.\n',
            '\tIf a sensor is absent, use a 0 as a place holder. There\n',
            '\tis no need to pad remaining addresses with 0s after the\n',
            '\tlast sensor parameter.\n',sep='')
    print('-r,--raw\n\tInclude only raw ADC data in hex format in output to stdout & file.\n')
    print('-c,--cook\n\tInclude only cooked data in °C in output to stdout or file.\n')
    print('-d<duration>,--duration=<duration>\n\tduration of data collection in seconds; 0 means collect for one year.\n')
    print('-f<filename>,--logfile=<filename>\n\tPrefix of file name to which collected data will be written; csv')
    print('\tformat. All file output will be written to ~/jtlogs. If no filename\n',
          '\tis specified, the default log file name is \'jtlog_nnnn.csv\', where\n',
          '\tnnnn is a unique number depending on what files already exist. If\n',
          '\tfilename is specified, \'_nnnn.csv\' will be appended.\n')
#  }}}
# gen_log_name {{{2
# Create a unique log file name:
def gen_log_name(filename):
    # determine if a log path exists:
    logdir = os.path.expanduser('~') + '/' + logsubdir
    if not os.path.exists(logdir):
        os.mkdir(logdir)
    logfile = filename
    log = True
    j = 0
    # iterate until we have a unique log file name.
    while os.path.exists(log):
        j += 1
        log = str(logdir + '/' + logfile + '_' + str('%04d' % j) + logfile_ext)
    return log
# }}}
# get_cfg {{{2
def get_cfg(argv):
    '''Get configuration info from command line:'''
    try:
        opts,args=getopt.getopt(argv,'hrcs:d:f:',['help','raw','cook','sensor-mode=','duration=','logfile='])
    except getopt.GetoptError:
        print('Unspecified error. Perhaps command line arguments are not correct?\n\tTry: {} -h or {} --help.\nAborting...\n'.format(sys.argv[0],sys.argv[0]))
        sys.exit(2)
    
    raw = True      # default is to supply raw data to the log file.
    cooked = True   # default is to supply cooked data to the log file.
    sensor = []
    s = 0           # sensor index counter.
    duration = 0
    log = gen_log_name(logfile)
    for opt, arg in opts:
        if opt in ('-h','--help'):
            showhelp()
            exit(0)
        elif opt in ('-s','--sensor-mode'):
            if len(sensor) > maxsensors:
                print('>>> Error: maximum # of sensors is {}. Too many! <<<'.format(maxsensors))
                exit(1)
            if int(arg) in range(1,cfgmodes+1):
                sensor.append(tempsensor(s,int(arg)-1,0))   # the last field is units (0=C, 1=K, 2=F) affects get_tempcooked()
                try:
                    sensor[len(sensor)-1].write_config()    # write to the ti2c module; will fail if no sensor.
                except:
                    print('>>> Error: sensor #{} not found. <<<'.format(len(sensor-1)))
                    exit(3)
            elif int(arg) not in range(cfgmodes+1):
                print('>>> Error: invalid mode {}; range is 0-{}. <<<'.format(arg,cfgmodes))
                exit(1)
            s += 1
        elif opt in ('-d','--duration'):
            duration = int(arg)
            if duration < 0:
                duration = -duration
        elif opt in ('-f','--logfile'):
            log = gen_log_name(arg)
        elif opt in ('-r','--raw'):
            cooked = False
        elif opt in ('-c','--cook'):
            raw = False
   
    # user specified both raw and cooked data explicitly:
    if raw == False and cooked == False:
        raw = True
        cooked = True

    # can get here without any arguments supplied; if so, bail; also bail if no sensors configured.
    if len(opts) == 0: 
        print('No arguments supplied.\n\n\tTry: {} -h or {} --help.\n\nAborting...\n'.format(sys.argv[0],sys.argv[0]))
        exit(1)
    elif len(sensor) == 0:
        print('No sensors specified.\n\n\tTry: {} -h or {} --help.\n\nAborting...\n'.format(sys.argv[0],sys.argv[0]))
        exit(1)
        
    
    # duration is converted to a sample count; so make it the # of samples at the highest data rate
    # required to sample for the requested duration.
    modes = []
    [modes.append(s.mcp3421[s.get_mode()][1]) for s in sensor]
    if duration == 0:
        duration = maxduration
    samples = duration * max(sorted(modes))
    return sensor,duration,samples,log,raw,cooked
# }}}
# make_term_raw {{{2
# Reconfigure the terminal to allow reception of characters:
def make_term_raw(fd):
    orig_attr = termios.tcgetattr(fd)
    attr = termios.tcgetattr(fd)
    attr[3] &= ~termios.ICANON      # clear the canonical attribute
    attr[3] &= ~termios.ECHO        # turn off echoing.
    attr[6][termios.VMIN] = 0       # set min. # of chars to be returned to 0; note this means '\0' is returned if no characters available.
    attr[6][termios.VTIME] = 0      # set time to wait for a character to 0; just return if none available.
    termios.tcsetattr(fd,termios.TCSADRAIN,attr)
    return orig_attr 
# }}}
# }}}

# main {{{1
def main(argv):
    # introduction; get setup; test sensors {{{2
    print('J-Tech Engineering, Ltd. - Sigma Delta ADC Analyser & Logger\n')

    # determine what sensors are present, and what mode each will use:
    sensor,duration,samples,log,raw,cooked = get_cfg(argv)
    numsensors = len(sensor)
    # }}}
    # open a file for writing sample data {{{2
    datalog = open(log,"w")
    datalog.write('Filename: ' + log + '\n')
    datalog.write('Date: ' + time.asctime() + '\n')
    # }}}
    # confirm setup to both screen & log file: {{{2
    print('set up:')
    print('sample duration is {} seconds.'.format(duration))
    print('log file name = {}.'.format(log))
    for i in range(numsensors):
        sensor_config = str('Sensor #%d: ' % (i+1)) + str('addr=%#04x; ' % sensor[i].get_address()) + \
                        str('sample freq.=%3.2f Hz; ' % sensor[i].get_samplerate()) + str('resolution=%d bits; ' % sensor[i].get_resolution()) + \
                        str('slope=%e; ' % sensor[i].get_slope()) + str('intercept=%f.\n' %sensor[i].get_intercept())
        datalog.write(sensor_config)
        print(sensor_config,sep='',end='')
    print('\npress q to quit.\n')
    # }}}
    # determine highest conversion rate {{{2
    # Default device read rate will be the lowest resolution/highest conversion rate; 
    # sort through the list looking for the highest rate:
    sfreq = sensor[0].get_samplerate()
    for i in range(numsensors):
        if sfreq < sensor[i].get_samplerate():
            sfreq = sensor[i].get_samplerate()
    # }}}
    # Configure the relationship between sensor sample rates: {{{2
    # If one sensor is running 12-bits / 240Hz, & another is 18-bits / 3.75Hz,
    # read the slower sensor once every 64 passes through
    # the sensor loop, but the faster one every time.
    sdowncountini = []
    sdowncount = []
    for i in range(numsensors):
        sdowncountini.append(sfreq / sensor[i].get_samplerate())
        sdowncount.append(1)            # force each to read initially.
    # }}}
    # print an address line as column headings: {{{2
    for i in range(numsensors):
        print('sensor #%d' %(i+1),' - i2c adr: %#04x' % sensor[i].get_address(),'      ',sep='',end='')
        datalog.write(hex(sensor[i].get_address()))
        if i < numsensors-1:
            print(' | ',sep='',end='')
            datalog.write(str(','))
            if raw == True and cooked == True:
                datalog.write(str(','))
        else:
            print('\n',end='')
            datalog.write(str('\n'))
    # }}}
    # take the keyboard out of canonical mode, & define an exit command {{{2
    fd = sys.stdin.fileno()
    orig_attr = make_term_raw(fd)   # returns unmodified terminal attribute structure.
    exit_cmd = ('q','Q')
    # }}}
    # main try/except block {{{2
    # keyboard is now out of canonical mode, so use a try/except block to exit cleanly on kbint.
    try:
        # Discard the first few samples to allow settling; log the rest.
        totalsamples = samples + discard
        scount = 0                  # Counter for logging samples
        # main execution loop {{{3 
        while scount < totalsamples:
            time.sleep(1/sfreq)             # sleep between reads.
    
            for i in range(numsensors):
                # determine if a sensor needs to be read:
                if sdowncount[i] == 1:
                    sdowncount[i] = sdowncountini[i]
                    sensor[i].read_sensor() # Fetch data from the sensor (physically read it, don't just grab the number from the object).
    
                    # this runs at the rate of the sensor with the highest sample rate:
                    #print('raw: %#07x' % sensor[i].get_tempraw(),', cooked: %7.3f' % sensor[i].get_tempC(),u'\u00b0','C',sep='',end='')
                    if scount < discard:
                        print('raw: %#07x' % sensor[i].get_tempraw(),', cooked: %7.3f' % sensor[i].get_tempC(),u'\u00b0','C',sep='',end='')
                    if scount >= discard:
                        if raw == True and cooked == False:
                            print('raw: %#07x                   ' % sensor[i].get_tempraw(),end='')
                            datalog.write(str(sensor[i].get_tempraw()))
                        elif raw == False and cooked == True:
                            print('              cooked: %7.3f' % sensor[i].get_tempC(),u'\u00b0','C',sep='',end='')
                            datalog.write('{:#7.3f}'.format(sensor[i].get_tempC()))
                        elif raw == True and cooked == True:
                            print('raw: %#07x' % sensor[i].get_tempraw(),', cooked: %7.3f' % sensor[i].get_tempC(),u'\u00b0','C',sep='',end='')
                            datalog.write('{},{:#7.3f}'.format(sensor[i].get_tempraw(),sensor[i].get_tempC()))
                    if i < numsensors-1:
                        print(' | ',sep='',end='')
                        if scount >= discard:
                            datalog.write(str(','))
                    else:
                        if scount >= discard:
                            print('\n',end='')
                            datalog.write(str('\n'))
                        else:
                            print(' *')
                else:
                    sdowncount[i] -= 1
                    # pad the output to keep everything aligned on the screen.
                    print('raw:          cooked:        ',u'\u00b0','C',sep='',end='')
                    if i < numsensors-1:
                        print(' | ',sep='',end='')
                        if scount >= discard:
                            datalog.write(str(','))
                    else:
                        if scount >= discard:
                            print('\n',end='')
                            datalog.write(str('\n'))
                        else:
                            print(' *')
    
            if sys.stdin.read() in exit_cmd:
                raise KeyboardInterrupt

            scount += 1
        # }}}
        # log complete; exit through the keyboard exception
        # to restore input functionality & close log file.
        raise KeyboardInterrupt
    except (KeyboardInterrupt,OSError) as error:
        termios.tcsetattr(fd,termios.TCSADRAIN,orig_attr)   # restore canonical mode.
        if error == OSError:
            if error.errno == os.errno.EREMOTEIO:
                print('\nRemote I/O Error: it\'s likely an I2C device, probably one or more',
                      '\nti2c modules, has/have become unavailable. Verify connections & cables.')
        print('\nend.\n')
    # }}}
# }}}
if(__name__ == '__main__'):
    main(sys.argv[1:])
