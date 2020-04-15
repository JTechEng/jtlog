#!/usr/bin/python3
# ti2c.py - a class to communicate over I2C bus with
#           sensors from J-Tech Engineering, Ltd. 
# Copyright © 2020 - J-Tech Engineering, Ltd.
#
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
# Now that that's out of the way...
# Class definition for TI2C sensors.
# Sensors have one of eight addresses, as shown below.
# Each physical IC has a marking corresponding to its address.
# the 'nn' below is a traceability code; it's mentioned here so as to 
# aleviate confusion over the extra numbers:
#
# marking | I2C address
# --------+------------
#    CAnn | 0x68
#    CBnn | 0x69
#    CCnn | 0x6a
#    CDnn | 0x6b
#    CEnn | 0x6c *
#    CFnn | 0x6d *
#    CGnn | 0x6e *
#    CHnn | 0x6f *
#
# * not available, though listed in product datasheet.
#   product datasheet: ds22003e - http://microchip.com
#
# __doc__
"""ti2c python module; defines class tempsensor."""

import smbus

# There are a few commands that talk to all mcp3421 devices on the SMBus.
# Since they aren't specific to tempsensor objects, they're in a class of their own.
# The trigger function is useful if performing conversions slower than the 18-bit conversion rate.
class tempsensorglobal(object):
    bus = smbus.SMBus(1)
    def __init__(self):
        self.gen_call_address = 0
        self.gen_reset = 0x06
        self.gen_convert = 0x08

    def reset(self):
        """reset all mcp3421 devices by writing the global reset command to location 0."""
        self.bus.write_byte(self.gen_call_address,self.gen_reset)

    def trigger(self):
        """trigger all mcp3421 devices to simultaneously perform a conversion; will put all devices in one-shot mode."""
        self.bus.write_byte(self.gen_call_address,self.gen_convert)

class tempsensor(object):
    # create an object able to access the I2C bus:
    bus = smbus.SMBus(1)

    # possible addresses:
    # note: as of this writing, only the first four are available.
    i2caddress = (0x68,0x69,0x6a,0x6b,0x6c,0x6d,0x6e,0x6f)
    i2caddrind = -1

    # create a list of tuples to hold each possible configuration of the sigma-delta converter:
    # definition: (bit resolution, sample rate, sample data mask, configuration byte)
    mcp3421 = [(12,240.0,0x7ff,0x10),(14,60.0,0x1fff,0x14),(16,15.0,0x7fff,0x18),(18,3.75,0x1ffff,0x1c)]
    mode = 3        # default mode is 18 bit resolution, lowest sample rate.

    # for slower operation, sampling below 3.75Hz:
    one_shot_cfg = 0x0c
    one_shot_trig = 0x8c


    # constants used in mapping temperature (by mode, not by individual sensor.)
    # the following slope,intercept pairs are based on perfect conditions, i.e. 0% tolerance on resistors,
    # 0V offset in the sensor amplifiers, 0 error in the ADC conversion, etc.
    slope_intercept = [(62.85027E-3,70.64385),(15.71257E-3,70.64385),(3.928142E-3,70.64385),(982.0354E-6,70.64385)]

    # an afterthought... add the symbols for C/K/F (assuming your world has utf-8 fonts:
    unit = (u'\u00b0' + 'C',' K',u'\u00b0' + 'F') 

    def __init__(self,address,mode,units):
        """tempsensor __init__; pass address (0..7) and mode (0..3) - see set_address() & set_mode() for details."""
        self.i2caddrind = address
        self.set_address(address)                       # map the requested address to a physical I2C address.
        self.set_mode(mode)                             # select the converter mode.
        self.cfgbyte = self.mcp3421[self.mode][3]       # 
        self.status = self.cfgbyte                      #
        self.slope = self.slope_intercept[mode][0]      # slope of temperature line; calibration means adjusting this value.
        self.intercept = self.slope_intercept[mode][1]  # intercept of temperature line; calibration means adjusting this value.
        self.units = units                              # 0 = celsius, 1 = kelvin, 2 = fahrenheit
        if self.units < 0:
            self.units = 0
        elif self.units > 2:
            self.units = 2
        self.raw = 0                                    # raw data from sensor.
        self.cooked = 0                                 # formatted data from sensor; Celsius by default.

    def set_address(self,address):
        """set ti2c module address: 0=0x68, 1=0x69... 7=0x6f."""
        if address in range(len(self.i2caddress)):
            self.i2caddrind = address
            self.address = self.i2caddress[self.i2caddrind]
        elif address in self.i2caddress:
            self.i2caddrind = self.i2caddress.index(address)
            self.address = self.i2caddress[self.i2caddrind]
        else:
            self.i2caddrind = -1
            self.address = 0
    def set_mode(self,mode):
        """set ti2c module mode: 0=12-bit/240Hz; 1=14-bit/60Hz; 2=16-bit/15Hz; 3=18-bit/3.75Hz"""
        if self.mode < 0:           # set the mode
            self.mode = 0
        elif self.mode > len(self.mcp3421)-1:
            self.mode = len(self.mcp3421)-1
        else:
            self.mode = mode
    def set_slope(self,slope):
        """set ti2c module slope: for converting sample data to temperature; for calibration."""
        self.slope = slope
    def set_intercept(self,intercept):
        """set ti2c module intercept: for converting sample data to temperature; for calibration. """
        self.intercept = intercept

    def get_address(self):
        """get ti2c's I2C address."""
        return self.address
    def get_mode(self):
        """get ti2c operating mode; see set_mode() for details."""
        return self.mode
    def get_resolution(self):
        """get ti2c sample resolution; see set_mode() for details."""
        return self.mcp3421[self.mode][0]
    def get_samplerate(self):
        """get ti2c sample rate; see set_mode() for details."""
        return self.mcp3421[self.mode][1]
    def get_samplemask(self):
        """get ti2c sample mask; used for removing sign-extension bits during sample-to-temperature conversion."""
        return self.mcp3421[self.mode][2]
    def get_config(self):
        """get ti2c adc configuration programming byte."""
        return self.cfgbyte # self.mcp3421[self.mode][3]
    
    def get_slope(self):
        """get ti2c module slope variable; see set_slope() for details."""
        return self.slope
    def get_intercept(self):
        """get ti2c module intercept variable; see set_intercept() for details."""
        return self.intercept

    def get_tempraw(self):
        """get ti2c module raw temperature sample data."""
        return self.raw
    def get_tempcooked(self):
        """get ti2c module temperature in temp specified during initialisation"""
        if self.units == 0:
            return self.get_tempC()
        elif self.units == 1:
            return self.get_tempK()
        elif self.units == 2:
            return self.get_tempF()
    def get_tempC(self):
        """get ti2c module temperature in Celsius."""
        return self.cooked
    def get_tempF(self):
        """get ti2c module temperature in Fahrenheit."""
        return self.cooked * 9 / 5 + 32
    def get_tempK(self):
        """get ti2c module temperature in Kelvin."""
        return self.cooked + 273.15

    def stop_sampling(self):
        """stop sensor sampling by clearing the nO/C bit in its config. register."""
        # a subtlety of the mcp3421: writing the config byte with the /RDY & /O/C bits set low 
        # tells the device to keep doing; it will not put it in one-shot mode; the only way to
        # get the device to stop sampling.
        self.cfgbyte &= 0x6f
        self.bus.write_byte(self.address,self.cfgbyte | 0x80)

    def start_sampling(self):
        """start sensor sampling by setting the nO/C bit in its config. register."""
        self.cfgbyte |= 0x10
        self.bus.write_byte(self.address,self.cfgbyte)

    def trigger(self):
        """trigger a data conversion; one-shot mode only; will fail if sensor does not respond."""
        self.bus.write_byte(self.address,self.cfgbyte | 0x80)   # negate nRDY

    def write_config_oneshot(self):
        """write the config byte to the ti2c module; will fail if sensor does not respond."""
        self.cfgbyte &= 0x6f
        self.bus.write_byte(self.address,self.cfgbyte)  # configure ADC

    def write_config(self):
        """write the config byte to the ti2c module; will fail if sensor does not respond."""
        self.bus.write_byte(self.address,self.cfgbyte)   # configure ADC

    def read_status(self):
        """Read the module, and check the status of the ready bit; return True if data is ready, False otherwise."""
        # there's an extra byte to read if the mcp3421 is in 18-bit mode:
        if self.mcp3421[self.mode][0] == 18:
            mcpdata = self.bus.read_i2c_block_data(self.address,self.cfgbyte,4)
            self.raw = mcpdata[2] + (mcpdata[1] << 8) + (mcpdata[0] << 16)
            self.status = mcpdata[3]
        else:
            mcpdata = self.bus.read_i2c_block_data(self.address,self.cfgbyte,3)
            self.raw = mcpdata[1] + (mcpdata[0] << 8)
            self.status = mcpdata[2]
        # the conversion results precede the status byte.
        if self.status & 0x80:
            return False
        else:
            self.raw &= self.mcp3421[self.mode][2]          # mask off sign-extension bits
            if mcpdata[0] & 0x80:                           # if the data was negative, 
                self.raw -= self.mcp3421[self.mode][2] + 1  # subtract off the sign extension bit
            # cook the data:
            self.cooked = self.raw * self.slope + self.intercept
            return True

    def read_sensor(self):
        """get ti2c module raw temperature from the sensor itself; must call this function to update temperature."""
        # there's an extra byte to read if the mcp3421 is in 18-bit mode:
        if self.mcp3421[self.mode][0] == 18:
            mcpdata = self.bus.read_i2c_block_data(self.address,self.cfgbyte,4)
            self.raw = mcpdata[2] + (mcpdata[1] << 8) + (mcpdata[0] << 16)
        else:
            mcpdata = self.bus.read_i2c_block_data(self.address,self.cfgbyte,3)
            self.raw = mcpdata[1] + (mcpdata[0] << 8)

        self.raw &= self.mcp3421[self.mode][2]          # mask off sign-extension bits
        if mcpdata[0] & 0x80:                           # if the data was negative, 
            self.raw -= self.mcp3421[self.mode][2] + 1  # subtract off the sign extension bit
        # cook the data:
        self.cooked = self.raw * self.slope + self.intercept
        return self.raw

