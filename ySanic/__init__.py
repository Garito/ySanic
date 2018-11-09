from inspect import iscoroutinefunction
from time import perf_counter, process_time
from json import dumps
from pathlib import PurePath
from logging import getLogger, INFO
from functools import wraps
from smtplib import SMTP
from email.mime.text import MIMEText

from sanic import Sanic, response
from sanic.blueprints import Blueprint
from sanic.log import logger
from sanic.exceptions import InvalidUsage, MethodNotSupported

from yModel import ErrorSchema
from yModel.mongo import NotFound

class ySanic(Sanic):
  log = logger

  def __init__(self, models, **kwargs):
    self.models = models
    super().__init__(**kwargs)

  def notify(self, notification, data):
    if hasattr(self, notification) and not self.config.get("DEBUG_EMAILS", False):
      return getattr(self, notification)(data)
    else:
      self.log.info("{}: {}".format(notification, data))

  def load_email_templates(self, templates, path = './emails/'):
    templates_dict = {}
    for template in templates:
      with open("{}{}.html".format(path, template)) as f:
        templates_dict[template] = f.read()
    return templates_dict

  def send_mail(self, to, subject, text = None, html = None):
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

  async def factory(self, request, path, as_ = None):
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
      result = result.to_plain_dict()

      result['pref_counter'] = (perf_counter() - counter) * 1000
      result['process_time'] = (process_time() - time) * 1000
      return result
    else:
      raise NotFound("{} not found".format(path))

  async def dispatcher(self, request, path):
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
      member = resp["args"] if "args" in resp else "__call__"

      method = getattr(paper, member, None)
      if method is None:
        raise NotFound("{} not found".format(path))

      result = await method(request) if iscoroutinefunction(method) else method(request)
      result = result.to_plain_dict()

      result['pref_counter'] = (perf_counter() - counter) * 1000
      result['process_time'] = (process_time() - time) * 1000
      return result
    else:
      raise NotFound("{} not found".format(path))

  async def updater(self, request, path, field):
    counter, time = perf_counter(), process_time()
    if not path.startswith("/"):
      path = "/{}".format(path)

    resp = await self.resolve_path(path)
    if resp:
      result = await resp["model"].update_field(request, field)
      result = result.to_plain_dict()

      result["pref_counter"] = (perf_counter() - counter) * 1000
      result['process_time'] = (process_time() - time) * 1000
      return result
    else:
      raise NotFound("{} not found".format(path))

  async def deleter(self, request, path):
    counter, time = perf_counter(), process_time()
    if not path.startswith("/"):
      path = "/{}".format(path)

    resp = await self.resolve_path(path)
    if resp:
      result = await resp["model"].delete(request)
      result = result.to_plain_dict()

      result["pref_counter"] = (perf_counter() - counter) * 1000
      result['process_time'] = (process_time() - time) * 1000
      return result
    else:
      raise NotFound("{} not found".format(path))

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

class yBlueprint(Blueprint):
  def produces(self, type_ = "json", code = 200, description = None):
    def decorator(func):
      if not hasattr(func, "__decorators__"):
        func.__decorators__ = {}
      func.__decorators__["produces"] = {"type": type_, "code": code, "description": description}

      @wraps(func)
      async def decorated(*args, **kwargs):
        result = await func(*args, **kwargs)
        return getattr(response, type_)(result, code)

      return decorated
    return decorator

  def can_crash(self, exc, model = ErrorSchema, code = 400, description = None):
    def decorator(func):
      if not hasattr(func, "__decorators__"):
        func.__decorators__ = {}
      if "can_crash" not in func.__decorators__:
        func.__decorators__["can_crash"] = {}

      func.__decorators__["can_crash"][exc.__name__] = {"model": model, "exc": exc, "code": code, "description": description}

      @wraps(func)
      async def decorated(*args, **kwargs):
        try:
          result = await func(*args, **kwargs)
          return result
        except exc as e:
          modelObj = model()
          modelObj.load({"message": str(e), "code": code})
          return response.json(modelObj.to_plain_dict(), code)

      return decorated
    return decorator

  @classmethod
  def generate_tree_blueprint(cls, name, url_prefix = None, host = None, version = None, strict_slashes = False):
    bp = yBlueprint(name, url_prefix, host, version, strict_slashes)

    @bp.options("/<path:path>/new/<as_>")
    def factory_options(request, *args, **kwargs):
      return response.text("", status = 204)

    @bp.post("/<path:path>/new/<as_>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces(code = 201)
    async def factory(request, path, as_):
      return await request.app.factory(request, path, as_)

    @bp.options("/new/<as_>")
    def factory_options(request, *args, **kwargs):
      return response.text("", status = 204)

    @bp.post("/new/<as_>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces(code = 201)
    async def root_factory(request, as_):
      return await request.app.factory(request, "/", as_)

    @bp.options("/<path:path>")
    def dispatcher_options(request, *args, **kwargs):
      return response.text("", status = 204)

    @bp.get("/<path:path>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces()
    async def dispatcher(request, path):
      return await request.app.dispatcher(request, path)

    @bp.get("/")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces()
    async def root_dispatcher(request):
      return await request.app.dispatcher(request, "/")

    @bp.options("/<path:path>/update/<field>")
    def factory_options(request, *args, **kwargs):
      return response.text("", status = 204)

    @bp.put("/<path:path>/update/<field>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces()
    async def updater(request, path, field):
      return await request.app.updater(request, path, field)

    @bp.delete("/<path:path>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces()
    async def deleter(request, path):
      return await request.app.deleter(request, path)

    return bp

  @classmethod
  def generate_files_blueprint(cls, name, url_prefix = None, host = None, version = None, strict_slashes = False):
    bp = yBlueprint(name, url_prefix, host, version, strict_slashes)

    @bp.get("/<filename:path>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces("raw")
    async def get_file(request, filename):
      return await request.app.get_file(filename)

    return bp

  @classmethod
  def generate_crud_blueprint(cls, name, model, url_prefix = None, host = None, version = None, strict_slashes = False):
    bp = yBlueprint(name, url_prefix, host, version, strict_slashes)

    @bp.post("/")
    @bp.produces()
    async def add(request):
      result = await model.factory(request)
      return result.to_plain_dict()

    @bp.get("/")
    @bp.produces()
    async def get_all(request):
      result = await model.get_all(request)
      return result.to_plain_dict()

    @bp.get("/<_id>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces()
    async def get(request, _id):
      result = await model.get_one(request, _id)
      return result.to_plain_dict()

    @bp.post("/<_id>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces()
    async def update(request, _id):
      result = await model.find_and_update(request, _id)
      return result.to_plain_dict()

    @bp.delete("/<_id>")
    @bp.can_crash(NotFound, code = 404)
    @bp.produces()
    async def delete(request, _id):
      result = await model.find_and_remove(request, _id)
      return result.to_plain_dict()

    return bp
