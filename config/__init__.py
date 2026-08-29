"""Register PyMySQL as the MySQLdb driver Django expects.

Avoids needing to compile mysqlclient (no pkg-config / build toolchain required
on either the Mac dev machine or the Windows server).
"""

import pymysql

pymysql.install_as_MySQLdb()
