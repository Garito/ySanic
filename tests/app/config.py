class Config:
  DEBUG = True
  DEBUG_EMAILS = True
  TESTING = True

  HOST = "localhost"
  PUBLIC_HOST = HOST
  PORT = 8000
  SERVER_NAME = "http://{}:{}".format(PUBLIC_HOST, PORT)

  MONGO_TABLE = "tests"
  MONGO = {"host": PUBLIC_HOST, "port": 27017, "db": MONGO_TABLE}
  MONGO_URI = "mongodb://{host}:{port}/{db}".format(**MONGO)
