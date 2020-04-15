# jtlog and jtlogc

High-precision measurement and logging of temperature:

* __jtlog__ - command-line, intended for higher-speed logging.
* __jtlogc__ - menu driven (curses), intended low-speed synchronized sampling, and monitoring.

# Synopsis

Originally developed for monitoring process temperature in a small pysical plant, several wired temperature sensors are connected to a Raspberry Pi, which can, in turn, connect to a network and be used to monitor the plant. Logging temperature allows traceability of the process, so it can be verified as having run as designed. Both applications run on a Raspberry Pi in a bash shell, either directly on the pi, or through an ssh session.

# Contents
* [Description](#description)
  * [Hardware Requirements](#hwreq)
  * [Application Details](#appdetails)
    * [jtlogc](#jtlogc)
      * [Sensor Configuration](#sensorcfg)
      * [Logging Configuration](#loggingcfg)
      * [Actions](#actions)
      * [Help](#help)
	* [jtlog](#jtlog)
      * [Examples](#examples)
* [Requirements](#requirements)
* [Installation](#installation)
* [Issues](#issues)
* [Credits](#credits)
  
# Description

Before discussing features & benefits of the software, a few words about hardware:

## Hardware Requirements

It's a little unusual to start with a _hardware_ requirements in a document providing information about a software application, but there's little point in digging into the minutia of the software if the user doesn't understand the system requirements first, and at least possess the required hardware. To that end, there are two required pieces of hardware:

1. Raspberry Pi - can be any version with the J8 header, as connections to this header are required, and the software has very modest processing requirements.
2. TI2C - temerature sensing module (developed by, and available from, [J-Tech Engineering, Ltd.](http://jtecheng.com). The sensor uses a Pt-RTD element to sense temperature, coupled through an amplifier and a Microchip MCP3421 18-bit Sigma-Delta ADC. The device uses an I2C interface to communicate with a host. I2C addresses are 8-bits wide, and devices are available with addresses ranging from 0x68-0x6b. An additional four addresses are mentioned in Microchip's datasheet, but these do not appear to be available for purchase as of this writing. A final note about the sensing element: The sensors can be ordered with either surface-mounted sensing elements, or through-hole elements on wires. The SMD version is compact and convenient as compared with the wired sensor, however the wired unit is more accurate as it does not experience any self-heating from the TI2C PCB itself.

### Physical Connections

The Raspberry Pi requires a hard-wired connection to the TI2C modules. The connections from the Raspberry Pi to the TI2C are as follows:

   | Raspberry Pi(J8) | TI2C  | description |
   | ---------------: | :---: | :---------- |
   |                1 |   1   | 3.3V        |
   |                3 |   2   | SDA         |
   |                5 |   3   | SCL         |
   |                6 |   4   | GND         |

TI2C modules can be daisy-chained together; for example:

	Rapberry Pi J8 pin 1 ---- TI2C #1 pin 1 ---- TI2C #2 pin 1 ---- TI2C #3 pin 1 ---- TI2C #4 pin 1
	Rapberry Pi J8 pin 3 ---- TI2C #1 pin 2 ---- TI2C #2 pin 2 ---- TI2C #3 pin 2 ---- TI2C #4 pin 2
	Rapberry Pi J8 pin 5 ---- TI2C #1 pin 3 ---- TI2C #2 pin 3 ---- TI2C #3 pin 3 ---- TI2C #4 pin 3
	Rapberry Pi J8 pin 6 ---- TI2C #1 pin 4 ---- TI2C #2 pin 4 ---- TI2C #3 pin 4 ---- TI2C #4 pin 4

The header on the TI2C is 1x4 0.100" (2.54mm) pitch. Pin 1 is labelled, and also has a square solder pad on the PCB for easy identification. Connectors are ***not keyed***, and only minimally protected from static discharge, so care should be taken making connections. Power requirements are very light for these devices, so nearly any wire can be used; four-wire satin telephone wire (AWG28) was used during development. Please visit [Raspberry Pi - Python V3 MCP3421 Support](http://jtecheng.com/?p=1004) for information about connecting to the Raspberry Pi.

**Note:** There is no reason the sensor can't be connected directly to _any_ device supporting the I2C standard, though this will doubtless lead to further software development.

## Application Details
Coming (finally) to the point about what the applications do:

#### Continuous vs. Single Conversion Modes
The MCP3421 can either sample continuously or in single-conversion mode. Sampling temperature at high-speed is an unusual requirement, so in the case of **jtlogc**, ADCs run in one-shot mode, and are triggered directly by the Raspberry Pi. If there is a preference for higher speed continuous sampling, the command line application, **jtlog** is able to sample all devices continuously at their maximum rates. The maximum rate changes with bit-resolution: whereas 18-bit data can only be captured at 3.75Hz, 12-bit data can be captured at 240Hz. Users are encouraged to use the command line application in this case. It will also create log files, much like the curses-based application does. If scheduled high speed logging is required, the linux's cron daemon can be configured to launch the application at the required moment.

### jtlogc

The application will open with self-explanatory information in various locations on the screen.

#### Sensor Configuration
The first step is to configure the sensors connected using the sensor menu. This menu allows setting the following:
-I2C address of the device
-Operating mode(0-3): These modes correspond to 12, 14, 16, and 18 bit resolution, with the caveat the higher resolution results in slower sampling. Resolution and bit-rate are displayed on the menu underneath the mode setting.
-Units: The sensor can return temperature in different unit sizes: Celsius, Fahrenheit, and Kelvin. The raw sample data from the sensor is always the same; the arithmetic used to convert between units is handled in the TI2C python module.
-slope & intercept: PtRTD sensors are extremely linear, so raw ADC data is converted with a simple linear equation: y = mx + b. Note the values used for m and b are displayed above the status window at the bottom of the screen. The values shown initially are determined by simple calculation of gain stages through the TI2C module, and are based on the assumption that there are no offset or gain errors in the amplifier stage, and that all resistors have 0% tolerance. This is obviously never true, and the slope/intercept numbers can be used to calibrate all sensor output.
-The sensor configuration menu allows direct selection of up to eight different sensors, and once in the sensor configuration screen, the 'n' and 'p' keys can be used to switch between sensors.
-The same sensor can be addressed more than once in the list. If it's desirable to have one read in °C, °F, and K all at once, set three sensors to the same I2C address. This creates a lot more I2C traffic, and it may be neccessary to increase the sample period to give the display windows sufficient time to refresh.

#### Logging Configuration
**jtlogc** places data in a log file using standard **csv** format, and can be imported into any spreadsheet for further analysis. Start time, stop time, sample period, raw converter data, and converted temperature in the requested units (°C/°F/K) are all included in the log.

The second step is to configure how log files are to be generated:
- **start time**: the previously entered start time will be pre-loaded into the field entry window. Note that if a time in the past is entered into this field, it will not be possible to trigger sampling in the future. When a future time is entered, the stop time will be filled with the start time, as it is not possible to stop before one starts sampling.
- **stop time**: if a start time has not been already entered, the stop time will be the previously entered value. If a time before the programmed start time is entered, but still in the future, the start time will be adjusted to match the stop time.
- sample period: This is entered in seconds, and can be a decimal. In practice, sample times lower than 0.5 seconds, i.e. Fs > 2Hz, will cause the logger to not display data properly; however, data will still be written to the log file. If maximum possible sample rates are required, please use the command line executable, jtlog.py. It runs all ADCs in continuous mode, creates logs, and can handle unusual configurations such as different bit resolutions/speeds for different sensors. The sample period is displayed in the lower right corner of the window, above the log file.
- **log file prefix**: This is the name of the log file. The prefix will be used as the first part of the file name, and will have the time: yyyymmddhhmmss.csv appended to the prefix. The time used for the file name is the start time of sampling. If sampling is stopped and restarted, the log file currently being written will be closed, and a new file will be started when sampling recommences.
- **log file location**: Specify the path to the log files. Shortcuts can be used such as ~, or ~/logs, but fully specified paths work too. Please ensure the path supports writing by the current user. **jtlogc** is not graceful on this point. The chosen log location will be displayed in the lower right corner above the status window. The date and time will be completed when logging commences; note that the filename is not live; it does not update when logging is underway.

#### Actions
- **start/stop**: Immediate start/stop of sampling. If you just want data right away, and don't need a schedule, select this.
- **await start**: Uses the programmed start time, as set in the logging configuration menu. If the current time is between the start and stop times, and this item is selected, logging will commence immediately and stop at the specified stop time. Note that the local, start, and stop times are all displayed in the lower left corner of the window, right above the status window.

#### Help
All help actions simply provide instructions in the status window:
- **user manual**: there are man pages for both the cli and curses versions; 'man jtlog' or 'man jtlogc' should bring up the appropriate page.
check for updates: this will work only if running a local X session on the Raspberry Pi. If using a remote window, the program does not check, wait a minute, this could work, but only if you create a github repository.
- **check for updates**: directs user to J-Tech's [github repository](https://github.com/JTechEng)
- **web**: directs user to J-Tech's [web](http://jtecheng.com) page.
- **about j-tech**: directs user to our [about](http://jtecheng.com?page_id=74) page

### jtlog

This is a command-line version, and comes with both a man page, and a help screen. Run 'jtlog -h' or 'jtlog --help' for simple instructions on how to use the application. The help screen is as follows:

    J-Tech Engineering, Ltd. - Sigma Delta ADC Analyser & Logger

    jtlog  -h -s <mode-sensor#1> [-r] [-c] [-s <mode-sensor#2> ... <mode-sensor#8>] [-d <duration>] [-f filename]

    -h,--help
            display this message.

    -s<mode>,--sensor-mode=<mode>
            where <mode> is 0-4; up to 8 -s<mode> pairs can be supplied;
    
            <mode> is one of:
                    0 - no sensor
                    1 - 12-bit samples, sample rate 240.00 Hz
                    2 - 14-bit samples, sample rate 60.00 Hz
                    3 - 16-bit samples, sample rate 15.00 Hz
                    4 - 18-bit samples, sample rate 3.75 Hz

            max. # of sensors: 8:
                    sensor 0 I2C addr: 0x68
                    sensor 1 I2C addr: 0x69
                    sensor 2 I2C addr: 0x6a
                    sensor 3 I2C addr: 0x6b
                    sensor 4 I2C addr: 0x6c
                    sensor 5 I2C addr: 0x6d
                    sensor 6 I2C addr: 0x6e
                    sensor 7 I2C addr: 0x6f

            Sensors must be specified in ascending order of address.
            If a sensor is absent, use a 0 as a place holder. There
            is no need to pad remaining addresses with 0s after the
            last sensor parameter.

    -r,--raw
            Include only raw ADC data in hex format in output to stdout & file.

    -c,--cook
            Include cooked (converted) data in °C in output to stdout or file.

    -d<duration>,--duration=<duration>
            duration of data collection in seconds; 0 means collect for one year.

    -f<filename>,--logfile=<filename>
            Prefix of file name to which collected data will be written; csv
            format. All file output will be written to ~/jtlogs. If no filename
            is specified, the default log file name is 'jtlog_nnnn.csv', where
            nnnn is a unique number depending on what files already exist. If
            filename is specified, '_nnnn.csv' will be appended.

If using the cli version, jtlog, there are options to discard either the converted temperatures, or the raw data, but the default is to include both.

#### Examples
       jtlog.py -s4 -s4 -s4 -s4 -ftemplog
Configure sensors at addresses 0x68, 0x69, 0x6a, and 0x6b on the I2C bus to sample at 18-bit resolution, 3.75 samples/sec, for one year, and write all log data to *~/jtlogs/templog_nnnn.csv* where *_nnnn* will increment each time the program is run.

       jtlog.py -s4 -s0 -s0 -s4 -d300
Configure sensors at addresses 0x68, and 0x6b on the I2C bus to sample at 18-bit resolution, 3.75 samples/sec, for five minutes, and write all log data to *~/jtlogs/jtlog_nnnn.csv* where *_nnnn* will increment each time the program is run.

       jtlog.py -s4 -s1 -d3600 -ftemplog
Configure the sensor at address 0x68 to sample at 18-bit resolution, 3.75 samples/sec, and the sensor at 0x69 to sample at 12-bit resolution, 240 samples/sec for one hour, and write all log data to *~/jtlogs/templog_nnnn.csv* where *_nnnn* will increment each time the program is run.

# Requirements

- **jtlogc.py** and **jtlog.py** the curses, and command line apps, respectively.
- **ti2c.py** - the sensor configuration module; does all the talking & listening to the hardware. Note this is used by _both_ **jtlog** and **jtlogc**.
- **Python 3.5.9** or later - if using a different version, please upgrade python 3 before making support requests.
- **Python 3 modules** - sys, os, time, curses, curses.textpad, json, threading, queue, webbrowser. Python will complain if any of these are missing, but all should be included in the standard installation through raspian.

# Installation

Pull the files from the repository, and from the project directory, run './install' as root, or run 'sudo ./install'. You may have first to change file permissions to make install executable: 'chmod 755 install'.

If your Raspberry Pi is not configured to enable the SMBus, you will need to make a few small changes to the operating environment. See the man pages and/or [Raspberry Pi - Python V3 I2C Support](http://www.jtecheng.com/?p=959). Please be aware that at the time of creating the web page, modifications to the SMBus module were required for use in Python 3; this is no longer the case, and is noted on the page, but enabling the kernel modules and verifying TI2C devices are visible is still necessary.

# Issues

## Clock

**jtlogc** keeps a real-time-clock in the lower left corner, above the status window. This clock does not update consistently entering data into any of the subwindows, or when a pull-down menu is open. The clock does keep the time correctly, but fails to update consistently.

## SMBus vs I2C

In order to communicate with the sensors, the SMBus protocol is used. This protocol was _not_ designed for this purpose, and does have at least one quirk: when sending commands to a device, a command byte will always be included in the data packet. This can be confusing when attempting to simply read conversion results from the ADCs, as they do not expect this byte. The MCP3421 datasheet does specify that a 0 transmitted in this byte position will be ignored by the device; therefore the issue can be ignored.


# Credits

[Lawrence Johnson](mailto:lawrence@jtecheng.com)

[J-Tech Engineering, Ltd.](http://jtecheng.com)
