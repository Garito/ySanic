import bson

from marshmallow import fields, pre_load
from marshmallow.validate import ValidationError

from yModel import Schema, OkSchema, ErrorSchema, OkResult, OkDictResult, OkListResult, consumes, produces, can_crash
from yModel.mongo import ObjectId, MongoTree, NotFound
from ySanic import notaroute

class ExistsException(Exception):
  pass

class SilentErrorSchema(ErrorSchema):
  ok = fields.Bool(required = True, missing = True)

class NameRequest(Schema):
  name = fields.Str(required = True)
  slug = fields.Str(required = True)

class Node(MongoTree):
  _id = ObjectId()
  type_ = fields.Str(attribute = "type", missing = "Node")
  name = fields.Str(required = True)
  slug = fields.Str(required = True)
  path = fields.Str(required = True)
  nodes = fields.List(fields.Str, missing = [])

  children_models = {"nodes": "Node"}
  factories = {"nodes": "create_child"}

  @can_crash(ValidationError, code = 400, description = "Returns the fields that don't validate")
  @produces(OkDictResult, as_ = "result")
  @consumes("Node")
  async def create_child(self, request, as_, model):
    return await super().create_child(model, as_)

  @produces(OkListResult, as_ = "result")
  async def get_children(self, request):
    result = await self.children("nodes", request.app.models)
    return result.to_plain_dict()

  @produces(OkListResult, as_ = "result")
  async def get_ancestors(self, request):
    nodes = await self.ancestors(request.app.models)
    return [node.to_plain_dict() for node in nodes]

  @produces(OkDictResult, as_ = "result")
  async def __call__(self, request):
    return self.to_plain_dict()

  @can_crash(ValidationError, code = 400, description = "Returns the fields that don't validate")
  @consumes(NameRequest)
  @produces(OkDictResult, as_ = "result")
  async def update(self, request, model):
    result = await super().update(model.get_data(), request.app.models)
    return result.to_plain_dict()

  @produces(OkResult, as_ = "result")
  async def remove(self, request):
    _id = str(self._id)
    result = await self.delete(request.app.models)
    return _id

class User(MongoTree):
  _id = ObjectId()
  type_ = fields.Str(attribute = "type", missing = "User")
  path = fields.Str(required = True, missing = "/")
  name = fields.Str(required = True)
  slug = fields.Str(required = True)
  email = fields.Email(required = True)
  trees = fields.List(fields.Str, required = True, missing = [])

  children_models = {"trees": "Node"}
  factories = {"trees": "create_tree"}

  @classmethod  
  async def exists(cls, table, email, get_model = False):
    model = cls(table = table)
    try:
      await model.get(email = email)
      return model if get_model else True
    except Exception:
      return False

  @produces(OkDictResult, as_ = "result", description = "Returns a dictionary with the user's content")
  async def __call__(self, request):
    return self.to_plain_dict()

  @can_crash(ValidationError, code = 400, description = "Returns the fields that don't validate")
  @produces(OkDictResult, as_ = "result", description = "Returns a dictionary with the new tree's content")
  @consumes(Node)
  async def create_tree(self, request, as_, model):
    return await super().create_child(model, as_)

  @produces(OkListResult, as_ = "result", description = "Returns a list of the user's trees")
  async def get_trees(self, request):
    result = await self.children("trees", request.app.models)
    return result.to_plain_dict()

class Invitation(MongoTree):
  _id = ObjectId()
  type_ = fields.Str(attribute = "type", missing = "Invitation")
  email = fields.Email(required = True)
  slug = fields.Str(required = True)
  path = fields.Str(required = True, missing = "/")

  slugable = "email"

  @classmethod
  async def exists(cls, table, email, get_model = False):
    model = cls(table)
    try:
      await model.get(email = email)
      return model if get_model else True
    except NotFound:
      return False

  @produces(OkDictResult, as_ = "result", description = "Returns a dictionary with the invitation's content")
  async def __call__(self, request):
    return self.to_plain_dict()

class Community(MongoTree):
  _id = ObjectId()
  type_ = fields.Str(attribute = "type", missing = "Community")
  path = fields.Str(required = True)
  name = fields.Str(required = True)
  slug = fields.Str(required = True)
  description = fields.Str()
  users = fields.List(ObjectId, required = True, missing = [])
  invitations = fields.List(ObjectId, required = True, missing = [])

  children_models = {"users": "User", "invitations": "Invitation"}
  factories = {"users": "create_user", "invitations": "create_invitation"}

  @produces(OkDictResult, as_ = "result", description = "Returns a dictionary with the community's data")
  async def __call__(self, request):
    return self.to_plain_dict()

  @can_crash(ExistsException, SilentErrorSchema, code = 409, description = "Returns ok = True even if the invitation is not found")
  @can_crash(ValidationError, code = 400, description = "Returns the fields that don't validate")
  @produces(OkSchema, description = "Returns ok = True if the invitation has been created successfuly")
  @consumes(Invitation)
  async def create_invitation(self, request, as_, model):
    """Creates a new invitation"""
    if await model.__class__.exists(self.table, model.email):
      raise ExistsException("Already invited")

    model.table = self.table
    await self.create_child(model, as_)

  @produces(OkListResult, as_ = "result", description = "Returns a list of invitations in the community in the key result")
  async def get_invitations(self, request):
    """Returns the list of invitations in the community"""
    result = await self.children("invitations", request.app.models)
    return result.to_plain_dict()

  @can_crash(NotFound, code = 404, description = "Returns not found if there is no invitation for that user")
  @can_crash(ValidationError, code = 400, description = "Returns the fields that don't validate")
  @produces(OkSchema, description = "Returns ok = True if the user has been created successfuly")
  @consumes(User)
  async def create_user(self, request, as_, model):
    """Creates a new user from a previous invitation"""
    invitation = Invitation(self.table)
    await invitation.get(_id = bson.ObjectId(request.json.get("code", None)))
    await invitation.delete()
    await self.create_child(model, as_)

  @produces(OkListResult, as_ = "result", description = "Returns a list of users in the community in the key result")
  async def get_users(self, request):
    """Returns the list of users in the community"""
    result = await self.children("users", request.app.models)
    return result.to_plain_dict()

  @notaroute
  @can_crash(ValidationError, code = 400, description = "Returns the fields that don't validate")
  @produces(User)
  @consumes(User)
  async def notaroute(self, request, model):
    return model.to_plain_dict()
