#!/bin/bash
# an install script for the jtlog and jtlogc programs;
# run this as root or it will not work.

echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo installing applications in /usr/local/bin...
#cp -v jtlog.py jtlogc.py ti2c.py /usr/local/bin
install --verbose --backup --target-directory=/usr/local/bin jtlog.py 
install --verbose --backup --target-directory=/usr/local/bin jtlogc.py 

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
echo ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
echo if there are errors, re-run this script as root, or put sudo in front of it.
echo if you see no errors, all should be in place. type man jtlog \&/or man jtlogc for further details.
echo also, see README.md for general info.
