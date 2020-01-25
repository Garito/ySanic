from inspect import getmembers, isclass, isfunction, ismethod, iscoroutinefunction
from time import perf_counter, process_time
from pathlib import PurePath
from logging import getLogger, INFO
from functools import wraps
from smtplib import SMTP_SSL
from email.mime.text import MIMEText

from sanic import Sanic, response
from sanic.blueprints import Blueprint
from sanic.log import logger
from sanic.exceptions import InvalidUsage, MethodNotSupported

from yModel import Schema, Tree, ErrorSchema
from yModel.mongo import NotFound, MongoJSONEncoder

from json import dumps

import re
if hasattr(re, '_pattern_type'):
  from re import _pattern_type as isPattern
else:
  from typing import Pattern as isPattern

from sanic.views import CompositionView
from typing import Type, Callable

class MyEncoder(MongoJSONEncoder):
  def default(self, obj):
    if isclass(obj) or ismethod(obj) or isfunction(obj) or isinstance(obj, (CompositionView, frozenset, isPattern, Type, Callable, set)):
      return str(obj)

    return MongoJSONEncoder.default(self, obj)

class ySanic(Sanic):
  log = logger

  def __init__(self, models, **kwargs):
    super().__init__(**kwargs)

    self.models = models

    if hasattr(self, "_add_openapi_route"):
      self._add_openapi_route()

    self._checkings = self._checks(models)
    self._permissions = self._checkings.pop("perms")

  def _is_recursive(self, model):
    return hasattr(model[1], "children_models") and model[0] in model[1].children_models.values()

  def _build(self, model, endpoint, routes, route, verb, code, path_param, models):
    schemas = {}
    perms = []
    if route not in routes:
      routes[route] = {}

    if path_param:
      if "parameters" not in routes[route]:
        routes[route]["parameters"] = []

      param = {"$ref": "#/components/parameters/{}_Path".format(model.__name__)}
      try:
        routes[route]["parameters"].index(param)
      except:
        routes[route]["parameters"].append(param)

    verb = verb.lower()
    if verb not in routes[route]:
      routes[route][verb] = {}

    endpoint_name = "call" if endpoint.__name__ == "__call__" else endpoint.__name__
    if path_param:
      routes[route][verb]["operationId"] = "{}/{}".format(model.__name__, endpoint_name)
    else:
      routes[route][verb]["operationId"] = "Root/{}".format(endpoint_name)
    if endpoint.__doc__:
      routes[route][verb]["summary"] = endpoint.__doc__

    keys = endpoint.__decorators__.keys()
    if "consumes" in keys:
      data = endpoint.__decorators__["consumes"]
      consumes_model = getattr(models, data["model"]) if isinstance(data["model"], str) else data["model"]
      routes[route][verb]["requestBody"] = {
        "content": {
          "application/json": {
            "schema": {"$ref": "#/components/schemas/{}".format(consumes_model.__name__)}
          }
        }
      }
      schemas[consumes_model.__name__] = consumes_model

    if "responses" not in routes[route][verb]:
      routes[route][verb]["responses"] = {}

    if code not in routes[route][verb]["responses"]:
      routes[route][verb]["responses"][code] = {}

    if "produces" in keys:
      data = endpoint.__decorators__["produces"]
      produces_model = getattr(models, data["model"]) if isinstance(data["model"], str) else data["model"]
      routes[route][verb]["responses"][code]["description"] = data["description"]
      routes[route][verb]["responses"][code]["content"] = {
        "application/json": {"schema": {"$ref": "#/components/schemas/{}".format(produces_model.__name__)}}
      }
      schemas[produces_model.__name__] = produces_model

    if "can_crash" in keys:
      data = endpoint.__decorators__["can_crash"]
      for error in data.values():
        if error["code"] not in routes[route][verb]["responses"]:
          routes[route][verb]["responses"][error["code"]] = {}
        routes[route][verb]["responses"][error["code"]]["description"] = error["description"] or ''
        routes[route][verb]["responses"][error["code"]]["content"] = {
          "application/json": {"schema": {"$ref": "#/components/schemas/{}".format(error["model"].__name__)}}
        }
        schemas[error["model"].__name__] = error["model"]

    if "permission" in keys and path_param:
      data = endpoint.__decorators__["permission"]
      ep_name = "call" if endpoint.__name__ == "__call__" else endpoint.__name__
      perm_dict = {"context": model.__name__, "name": ep_name, "roles": data["default"]}
      if "description" in data:
        perm_dict["description"] = data["description"]
      perms.append(perm_dict)

    #   routes[route][verb]["security"] =[{"$ref": "#/components/securitySchemes/{}_{}".format(model.__name__, ep_name)}]

    return schemas, perms

  def _check(self, model, models, is_root = False):
    routes = {}
    params = {}
    schemas = {}
    perms = []
    paths = {"no_path": [], "path": []}
    path_name = "{}_Path".format(model[0])
    path = "/{{{}}}/".format(path_name)
    real_path = "/<path:path>/"
    recursive = self._is_recursive(model)
    for endpoint in getmembers(model[1], lambda m: hasattr(m, "__decorators__")):
      keys = endpoint[1].__decorators__.keys()
      code = 200
      real_route = None
      real_endpoint = self.dispatcher
      path_param = False

      if endpoint[0] in ["__call__", "remove"]:
        verb = "DELETE" if endpoint[0] == "remove" else "GET"
        if is_root:
          root_route = "/"

        if not is_root or recursive:
          route = path
          real_route = ""
          path_param = True
      elif endpoint[0] == "update":
        verb = "PUT"
        if is_root:
          root_route = "/"

        if not is_root or recursive:
          route = path
          real_route = ""
          path_param = True
      elif "consumes" in keys:
        consumed = getattr(endpoint[1].__decorators__["consumes"]["model"], "__name__", endpoint[1].__decorators__["consumes"]["model"])

        if hasattr(model[1], "factories") and endpoint[0] in model[1].factories.values():
          idx = list(model[1].children_models.values()).index(consumed)
          oa_url = "new/{}".format(list(model[1].children_models.keys())[idx])

          verb, code, real_route = ("POST", 201, "new/<as_>")
          real_endpoint = self.factory
        else:
          oa_url = None
          verb, code, real_route = ("PUT", 200, endpoint[0])

        if is_root:
          root_route = "/{}".format(oa_url or real_route)

        if not is_root or recursive:
          route = "{}{}".format(path, oa_url or real_route)
          path_param = True
      elif "produces" in keys:
        verb = "GET"
        if is_root:
          root_route = "/{}".format(endpoint[0])

        if not is_root or recursive:
          route = "{}{}".format(path, endpoint[0])
          real_route = endpoint[0]
          path_param = True

      if is_root:
        if "notaroute" not in keys or endpoint[1].__decorators__["notaroute"]["when"] is None or "main" not in endpoint[1].__decorators__["notaroute"]["when"]:
          has_schemas, has_perms = self._build(model[1], endpoint[1], routes, root_route, verb, code, False, models)
          if has_schemas:
            schemas.update(has_schemas)
          if has_perms:
            perms += has_perms
          if root_route == "/":
            paths["no_path"].append((None, "/", verb, real_endpoint))
          elif real_route == "new/<as_>" and ("/", 'new/<as_>', "POST", real_endpoint) not in paths["no_path"]:
            paths["no_path"].append(("/", real_route, verb, real_endpoint))
        if "notaroute" not in keys or endpoint[1].__decorators__["notaroute"]["when"] is None or "recursive" not in endpoint[1].__decorators__["notaroute"]["when"]:
          has_schemas, has_perms = self._build(model[1], endpoint[1], routes, route, verb, code, path_param, models)
          if has_schemas:
            schemas.update(has_schemas)
          if has_perms:
            perms += has_perms
          paths["path"].append((real_path, real_route, verb, real_endpoint))
      elif "notaroute" not in keys or endpoint[1].__decorators__["notaroute"]["when"] is None or "main" not in endpoint[1].__decorators__["notaroute"]["when"]:
        has_schemas, has_perms = self._build(model[1], endpoint[1], routes, route, verb, code, path_param, models)
        if has_schemas:
          schemas.update(has_schemas)
        if has_perms:
            perms += has_perms
        paths["path"].append((real_path, real_route, verb, real_endpoint))

      if path_param:
        if path_name not in params:
          params[path_name] = {
            "name": path_name, "in": "path", "description": "The {}'s URI".format(model[0]), "required": True, "schema": {"type": "string"}
          }

    return {"recursive": recursive, "routes": routes, "params": params, "schemas": schemas, "perms": perms, "paths": paths}

  def _checks(self, models = None):
    if models is None:
      models = self.models

    root = None
    trees = []
    perms = []

    for model in getmembers(models, lambda m: isclass(m) and issubclass(m, Tree)):
      if hasattr(model[1], "auth") or hasattr(model, "get_global_context"):
        checks = self._check(model, models, True)
        has_perms = checks.pop("perms", False)
        if has_perms:
          perms.extend(has_perms)
        root = (model[0], model[1], checks)
      else:
        if "path" in model[1]._declared_fields:
          checks = self._check(model, models)
          has_perms = checks.pop("perms", False)
          if has_perms:
            perms.extend(has_perms)
          trees.append((model[0], model[1], checks))

    root_paths = root[2].pop("paths", {})
    if root_paths:
      if "no_path" in root_paths:
        for path in root_paths["no_path"]:
          self._route_adder(*path)
      if "path" in root_paths:
        for path in root_paths["path"]:
          self._route_adder(*path)
    for tree in trees:
      for path in tree[2].pop("paths", [])["path"]:
        self._route_adder(*path)

    return {"root": root, "trees": trees, "perms": perms}

  def _print_tree(self, models_types, models, model = None, indent = 0):
    if model is None:
      model = models_types["root"]

    print("{}{}".format("|  " * indent, model[0])) #, getattr(model[1], "children_models", {}).keys()))

    if hasattr(model[1], "children_models"):
      for child in model[1].children_models.values():
        theModel = (child, getattr(models, child))
        if self._is_recursive(theModel) and model[0] == theModel[0]:
          print("{}{}".format("|  " * (indent + 1), theModel[0]))
        else:
          self._print_tree(models_types, models, theModel, indent + 1)

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

  def _debug_endpoints(self):
    self._route_adder("", "/_declared_routes", "GET", self._declared_routes_endpoint)
    self._route_adder("", "/_models_tree", "GET", self._models_tree_endpoint)

  async def _declared_routes_endpoint(self, request):
    return response.text(self.router.routes_all)

  async def _models_tree_endpoint(self, request):
    self._print_tree(self._checkings, self.models)
    return response.text("Check your server's logs")

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
    elif resp:
      rest = request.raw_url.decode('utf-8').replace(resp["model"].get_url(), "")
      if rest:
        if rest.startswith("/"):
          rest = rest[1:]
        if "/" not in rest and rest:
          resp["args"] = rest

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

      # server = SMTP("{}:{}".format(self.config["SMTP_SERVER"], self.config.get("SMTP_PORT", 587)))

      server = SMTP_SSL(self.config["SMTP_SERVER"], self.config.get("SMTP_PORT", 587))
      if self.config.get("SMTP_TLS", False):
        server.starttls()
      else:
        server.ehlo()
      server.login(self.config.get("SMTP_SENDER_LOGIN", self.config["SMTP_SENDER"]), self.config["SMTP_SENDER_PASSWORD"])
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
    doc = await self.table.find_one({"path": ""})
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

    result = await self.table.find_one(purePaths[0]) if len(purePaths) == 1 else await self.table.find({"$or": purePaths}).to_list(None)
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

def notaroute(when = None, description = None):
  def decorator(func):
    if not hasattr(func, "__decorators__"):
      func.__decorators__ = {}
    func.__decorators__["notaroute"] = {"when": when, "description": description}

    @wraps(func)
    async def decorated(*args, **kwargs):
      result = await func(*args, **kwargs)
      return result

    return decorated
  return decorator
