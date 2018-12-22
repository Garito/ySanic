from inspect import getmembers, isclass, isfunction, ismethod, iscoroutinefunction, getmro
from time import perf_counter, process_time
from pathlib import PurePath
from logging import getLogger, INFO
from functools import wraps
from smtplib import SMTP
from email.mime.text import MIMEText

from sanic import Sanic, response
from sanic.blueprints import Blueprint
from sanic.log import logger
from sanic.exceptions import InvalidUsage, MethodNotSupported

from yModel import Schema, Tree, ErrorSchema
from yModel.mongo import NotFound

from json import dumps, JSONEncoder
from re import _pattern_type
from sanic.views import CompositionView
from typing import Type, Callable

class MyEncoder(JSONEncoder):
  def default(self, obj):
    if isclass(obj) or ismethod(obj) or isfunction(obj) or isinstance(obj, (CompositionView, frozenset, _pattern_type, Type, Callable, set)):
      return str(obj)

    return JSONEncoder.default(self, obj)

class ySanic(Sanic):
  log = logger

  def __init__(self, models, **kwargs):
    add_routes = kwargs.pop("add_routes", False)
    super().__init__(**kwargs)

    self.models = models
    self._models_by_type = self._models_types()
    self._inspected = self._inspect()

    if "yOpenSanic" in [class_.__name__ for class_ in getmro(self.__class__)]:
      self._route_adder("", "/openapi", "GET", self.openapi)

    # self.log.info(dumps(self._models_by_type, indent = 2))
    # self.log.info(dumps(self._inspected, indent = 2, cls = MyEncoder))
    # self.log.info(dumps(self.router.routes_all, indent = 2, cls = MyEncoder))

  def _models_types(self, models = None):
    trees = getmembers(models or self.models, lambda m: isclass(m) and issubclass(m, Tree))
    not_trees = getmembers(models or self.models, lambda m: isclass(m) and issubclass(m, Schema) and not issubclass(m, Tree))
    root = [name for name, model in trees]
    not_root = []
    inout = [name for name, model in not_trees]
    leafs = []

    for name, model in trees:
      for child in getattr(model, "children_models", {}).values():
        if child in root and child != model.__name__:
          del root[root.index(child)]
          not_root.append(child)
        elif child in inout:
          del inout[inout.index(child)]
          leafs.append(child)

    independent = []
    for name, model in not_trees:
      if name in inout and getmembers(model, lambda m: (ismethod(m) or isfunction(m)) and m.__module__ == model.__module__):
        del inout[inout.index(name)]
        independent.append(name)

    return {"root": root[0] if len(root) > 0 else None, "trees": not_root, "leafs": leafs, "independent": independent, "inout": inout}

  def _inspect(self, models = None, add_routes = False):
    data = {}
    for name, model in getmembers(models or self.models, lambda m: isclass(m) and not m.__module__.startswith("yModel")):
      model_methods = getmembers(model, lambda m: (isfunction(m) or ismethod(m)) and hasattr(m, "__decorators__"))
      if model_methods:
        data[name] = {}
        if name == self._models_by_type["root"]:
          data[name]["type"] = "root"
        elif name in self._models_by_type["trees"]:
          data[name]["type"] = "tree"
        elif name in self._models_by_type["independent"]:
          data[name]["type"] = "independent"
        else:
          data[name]["type"] = "leaf"

        if data[name]["type"] in ["root", "tree"]:
          data[name]["recursive"] = model.__name__ in getattr(model, "children_models", {}).values()

        for method_name, method in model_methods:
          if "consumes" in method.__decorators__:
            if "in" not in data[name]:
              data[name]["in"] = {}

            if (hasattr(model, "factories") and method_name in model.factories.values()) or method.__decorators__["consumes"]["model"] == model.__name__:
              if "factories" not in data[name]["in"]:
                data[name]["in"]["factories"] = {}

              data[name]["in"]["factories"][method_name] = {"method": method, "decorators": method.__decorators__}

              if not method.__decorators__.get("notaroute", False):
                self._add_route(model, "factory", data[name]["type"], data[name]["in"]["factories"][method_name])
                if data[name]["type"] == "root" and data[name]["recursive"] and not self._models_by_type["trees"]:
                  self._add_route(model, "factory", "tree", data[name]["in"]["factories"][method_name])
            else:
              if "updaters" not in data[name]["in"]:
                data[name]["in"]["updaters"] = {}

              data[name]["in"]["updaters"][method_name] = {"method": method, "decorators": method.__decorators__}

              if not method.__decorators__.get("notaroute", False):
                self._add_route(model, "updater", data[name]["type"], data[name]["in"]["updaters"][method_name])
                if data[name]["type"] == "root" and data[name]["recursive"] and not self._models_by_type["trees"]:
                  self._add_route(model, "updater", "tree", data[name]["in"]["updaters"][method_name])
          else:
            if "out" not in data[name]:
              data[name]["out"] = {}

            if method_name in ["remove", "find_and_remove"]:
              if "remover" not in data[name]["out"]:
                data[name]["out"]["removers"] = {}

              data[name]["out"]["removers"][method_name] = {"method": method, "decorators": method.__decorators__}

              if not method.__decorators__.get("notaroute", False):
                self._add_route(model, "remover", data[name]["type"], data[name]["out"]["removers"][method_name])
                if data[name]["type"] == "root" and data[name]["recursive"] and not self._models_by_type["trees"]:
                  self._add_route(model, "remover", "tree", data[name]["out"]["removers"][method_name])
            else:
              if "views" not in data[name]["out"]:
                data[name]["out"]["views"] = {}

              data[name]["out"]["views"][method_name] = {"method": method, "decorators": method.__decorators__}

              if not method.__decorators__.get("notaroute", False):
                self._add_route(model, "view", data[name]["type"], data[name]["out"]["views"][method_name])
                if data[name]["type"] == "root" and data[name]["recursive"] and not self._models_by_type["trees"]:
                  self._add_route(model, "view", "tree", data[name]["out"]["views"][method_name])

    return data

  def _route_adder(self, prefix, url, verb, endpoint):
    if prefix:
      url = "{}{}".format(prefix, url)

    if url not in self.router.routes_all or verb not in list(self.router.routes_all[url][1]):
      self.add_route(endpoint, url, methods = [verb])

    if url not in self.router.routes_all or "OPTIONS" not in list(self.router.routes_all[url][1]):
      self.add_route(self.generic_options, url, methods = ["OPTIONS"])

  def _add_route(self, model, type_, is_, data):
    prefix = getattr(model, "url_prefix", False)

    if type_ == "factory":
      verb = "POST"
      if is_ == "independent":
        url = "/"
        endpoint = data["method"]
      else:
        url = "/new/<as_>" if is_ == "root" else "/<path:path>/new/<as_>"
        endpoint = self.factory
    elif type_ == "updater":
      verb = "PUT"
      if is_ == "independent":
        url = "/<_id>"
        endpoint = data["method"]
      else:
        url = "/" if is_ == "root" else "/<path:path>"
        endpoint = self.dispatcher
    elif type_ == "remover":
      verb = "DELETE"
      if is_ == "independent":
        url = "/<_id>"
        endpoint = data["method"]
      else:
        url = "/<path:path>"
        endpoint = self.dispatcher
    else:
      verb = "GET"
      if is_ == "independent":
        if data["method"].__name__ == "__call__":
          url = "/<_id>"
        elif data["method"].__name__ == "get_all":
          url = "/"
        else:
          url = "/<_id>/{}".format(data["method"].__name__)
        endpoint = data["method"]
      else:
        url = "/" if data["method"].__name__ == "__call__" else "/<path:path>"
        endpoint = self.dispatcher

    self._route_adder(prefix, url, verb, endpoint)

  async def factory(self, request, path = "/", as_ = None):
    """
    The user will ask for /path/to/the/parent/new/member-list
    Where member-list is the list where the parent saves the children order
    So in the test model MinimalMongoTree the only factory will be /new/children
    """
    counter, time = perf_counter(), process_time()
    if not path.startswith("/"):
      path = "/{}".format(path)

    resp = await self.resolve_path(path)
    if resp:
      if "path" not in request.json:
        request.json["path"] = path

      method = getattr(resp["model"], resp["model"].factories[as_] if hasattr(resp["model"], "factories") and as_ in resp["model"].factories else "create_child")
      result = await method(request, as_)
      code = result.code if issubclass(result.__class__, ErrorSchema) else 201
      result = result.to_plain_dict()

      result['pref_counter'] = (perf_counter() - counter) * 1000
      result['process_time'] = (process_time() - time) * 1000
      return response.json(result, code)
    else:
      error = self.models.ErrorSchema()
      error.load({"message": "{} not found".format(path), "code": 404})
      return response.json(error.to_plain_dict(), 404)

  async def dispatcher(self, request, path = "/"):
    counter, time = perf_counter(), process_time()
    if not path.startswith("/"):
      path = "/{}".format(path)

    resp = await self.resolve_path(path, 1)

    parts = path.split("/")
    if not resp and len(parts) == 2:
      root = await self.get_root()
      resp = {"model": root, "args": parts[1]}

    if resp:
      paper = resp["model"]
      default_methods = {"GET": "__call__", "PUT": "update", "DELETE": "remove"}
      member = resp["args"] if "args" in resp else default_methods[request.method]

      method = getattr(paper, member, None)
      if method is not None and not method.__decorators__.get("notaroute", False):
        result = await method(request) if iscoroutinefunction(method) else method(request)
        code = result.code if issubclass(result.__class__, ErrorSchema) else 200
        result = result.to_plain_dict()

        result['pref_counter'] = (perf_counter() - counter) * 1000
        result['process_time'] = (process_time() - time) * 1000
        return response.json(result, code)

    error = self.models.ErrorSchema()
    error.load({"message": "{} not found".format(path), "code": 404})
    return response.json(error.to_plain_dict(), 404)

  async def openapi(self, request):
    return response.json(self.openapi_v3())

  async def generic_options(self, request, *args, **kwargs):
    return response.text("", status = 204)

  async def notify(self, notification, request, data):
    if hasattr(self, notification):
      func = getattr(self, notification)
      return await func(request, data) if iscoroutinefunction(func) else func(request, data)
    else:
      self.log.info("{}: {}".format(notification, data))

  def send_mail(self, to, subject, text = None, html = None):
    if self.config.get("DEBUG_EMAILS", False):
      self.log.info(f"to: {to}")
      self.log.info(f"subject: {subject}")
      self.log.info(f"text: {text}")
      self.log.info(f"html: {html}")
    else:
      msg = MIMEText(html, 'html')
      msg["From"] = self.config["SMTP_SENDER"]
      msg["To"] = to
      msg["Subject"] = subject

      server = SMTP("{}:{}".format(self.config["SMTP_SERVER"], self.config.get("SMTP_PORT", 587)))
      server.starttls()
      server.login(self.config["SMTP_SENDER"], self.config["SMTP_SENDER_PASSWORD"])
      server.sendmail(self.config["SMTP_SENDER"], to, msg.as_string())
      server.quit()

  async def allow_origin(self, request, response):
      response.headers["Access-Control-Allow-Origin"] = "*"
      response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
      response.headers["Access-Control-Allow-Headers"] = "Access-Control-Allow-Origin, Access-Control-Allow-Headers, Origin, X-Requested-With, Content-Type, Authorization"

class MongoySanic(ySanic):
  def __init__(self, models, **kwargs):
    table = kwargs.pop("table", None)
    if table is not None:
      self.table = table
    super().__init__(models, **kwargs)

  async def get_root(self):
    doc = await self.table.find_one({"path": "", "name": ""})
    if doc:
      model = getattr(self.models, doc["type"])(self.table)
      model.load(doc)
      errors = model.get_errors()
      if errors:
        raise InvalidUsage(errors)
      else:
        return model
    else:
      raise NotFound("root not found")

  async def get_path(self, path):
    result = await self.get_paths([path])
    return result[0] if isinstance(result, list) else result

  async def get_paths(self, paths):
    purePaths = []
    for path in paths:
      path = PurePath(path)
      purePaths.append({"path": str(path.parent), "slug": path.name})

    if len(purePaths) == 1:
      result = await self.table.find_one(purePaths[0])
    else:
      result = await self.table.find({"$or": purePaths}).to_list(None)

    return result

  async def get_paper(self, path):
    doc = await self.get_path(path)
    if doc:
      model = getattr(self.models, doc["type"])(self.table)
      model.load(doc)
      errors = model.get_errors()
      if errors:
        raise InvalidUsage(errors)
      else:
        return model
    else:
      raise NotFound("{} not found".format(path))

  async def resolve_path(self, path, max_args = 0):
    path = PurePath(path)
    args = []
    if path.name == "":
      paper = await self.get_root()
      return {"model": paper}
    else:
      while path.name != "":
        try:
          paper = await self.get_paper(path)
        except NotFound:
          if len(args) >= max_args:
            return None
          args.append(path.name)

          path = path.parent
          continue

        if paper:
          result = {"model": paper}
          if args:
            result["args"] = args[0] if max_args == 1 and len(args) > 0 else args
          return result
        else:
          if len(args) >= max_args:
            return None
          args.append(path.name)

        path = path.parent

  async def get_file(self, filename):
    cursor = self.GridFS["test_fs"].find({"filename": filename})

    stream = None
    content_type = None
    async for file in cursor:
      content_type = file.metadata["contentType"]
      stream = await file.read()

    if stream is None and content_type is None:
      raise NotFound(filename)

    return {"stream": stream, "contentType": content_type}

  async def set_file(self, filename, data, contentType):
    await self.GridFS["test_fs"].upload_from_stream(filename, data, metadata = {"contentType": contentType})

  async def set_table(self, request):
    request.app.table = request.app.mongo["test"][request.app.config.get("MONGO_TABLE")]

def notaroute(func):
  if not hasattr(func, "__decorators__"):
    func.__decorators__ = {}
  func.__decorators__["notaroute"] = True

  @wraps(func)
  async def decorated(*args, **kwargs):
    result = await func(*args, **kwargs)
    return result

  return decorated
