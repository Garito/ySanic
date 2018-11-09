from sanic_mongo import Mongo, GridFS

from ySanic import MongoySanic, yBlueprint

from tests.app import models
from tests.app.config import Config

def create_app():
  app = MongoySanic(models = models)
  app.config.from_object(Config)

  URI = app.config.get("MONGO_URI")
  Mongo.SetConfig(app, test = URI)
  Mongo(app)
  GridFS.SetConfig(app, test_fs = (URI, "fs"))
  GridFS(app)

  app.blueprint(yBlueprint.generate_crud_blueprint("todos", models.Todo, "/todos"))
  app.blueprint(yBlueprint.generate_files_blueprint("files", "/files"))
  app.blueprint(yBlueprint.generate_tree_blueprint("nodes", "/nodes"))

  app.register_middleware(app.set_table, "request")

  if app.config.get("DEBUG", False):
    app.register_middleware(app.allow_origin, "response")

  return app

if __name__ == "__main__":
  app = create_app()
  app.run(host = app.config.get("HOST", "localhost"), port = app.config.get("PORT", 8000))
