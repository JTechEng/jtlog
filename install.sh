#!/bin/bash
# install script for the jtlog and jtlogc programs; run with root privileges.
# Copyright © 2020 - J-Tech Engineering, Ltd.
# {{{ licensing & permissions 
# install.sh is free software: you can redistribute it and/or modify
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
# }}}

echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo installing applications in /usr/local/bin...
#cp -v jtlog.py jtlogc.py ti2c.py /usr/local/bin
install --verbose --backup --target-directory=/usr/local/bin jtlog.py 
install --verbose --backup --target-directory=/usr/local/bin jtlogc.py 
install --verbose --backup --target-directory=/usr/local/bin ti2c.py 

# skip symbolic link creation if they exist; they're unlikely to change.
echo creating symbolic links if required...
if ! [[ -L /usr/local/bin/jtlog ]] ; then
	ln -s /usr/local/bin/jtlog.py /usr/local/bin/jtlog
fi
if ! [[ -L /usr/local/bin/jtlogc ]] ; then
	ln -s /usr/local/bin/jtlogc.py /usr/local/bin/jtlogc
fi

echo installing man pages...
if ! [[ -e /usr/local/man/man1 ]] ; then
	echo /usr/local/man/man1 does not exist\; creating...
	mkdir /usr/local/man/man1
	chmod 755 /usr/local/man/man1
	echo done.
fi

#cp -v jtlog.1.gz jtlogc.1.gz /usr/local/man/man1
install --verbose --backup --target-directory=/usr/local/man/man1 jtlog.1.gz 
install --verbose --backup --target-directory=/usr/local/man/man1 jtlogc.1.gz 
echo done.
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo If there are errors, re-run this script as root, or put sudo in front of it. If
echo there are no errors, all should be in place. Type man jtlog \&/or man jtlogc for
echo further details\; also, see README.md for general info.
