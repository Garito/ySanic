from pymongo import ASCENDING
from sanic_mongo import Mongo, GridFS

from yModel.mongo import NotFound
from ySanic import MongoySanic

from tests.app import models
from tests.app.config import Config

class ySanicServer(MongoySanic):
  pass

def create_app(config = None):
  app = ySanicServer(models = models, name = "app")
  app.config.from_object(config or Config)

  URI = app.config.get("MONGO_URI")
  Mongo.SetConfig(app, test = URI)
  Mongo(app)
  GridFS.SetConfig(app, test_fs = (URI, "fs"))
  GridFS(app)

  @app.listener("before_server_start")
  async def setup_db(app, loop):
    table = app.mongo["test"][app.config.get("MONGO_TABLE")]

    await table.create_index([("path", ASCENDING), ("slug", ASCENDING)])

    root = app.models.Community(table)
    try:
      await root.get(path = "", name = "")
    except NotFound:
      root.load({"path": "", "name": "", "description": "The community object is the root of the site"})
      await root.create()

      admin = app.models.User(table)
      admin.load({"path": "/", "name": "Garito", "email": "garito@gmail.com"})
      await admin.create()

      await root.update({"users": [admin._id]})

  app.register_middleware(app.set_table, "request")

  if app.config.get("DEBUG", False):
    app.register_middleware(app.allow_origin, "response")

  return app

if __name__ == "__main__":
  app = create_app()
  app.run(host = app.config.get("HOST", "localhost"), port = app.config.get("PORT", 8000))
