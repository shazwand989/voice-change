# Install PyMySQL as MySQLdb fallback so MySQL works without binary mysqlclient.
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
