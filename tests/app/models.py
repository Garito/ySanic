import bson

from marshmallow import fields

from yModel import OkSchema, consumes, produces, can_crash
from yModel.mongo import ObjectId, MongoSchema, MongoTree

class OkResult(OkSchema):
  result = fields.Str(required = True)

class OkListResult(OkSchema):
  result = fields.List(fields.Dict, required = True)

class OkDictResult(OkSchema):
  result = fields.Dict(required = True)

class NameRequest(OkSchema):
  name = fields.Str(required = True)

class DescriptionRequest(OkSchema):
  description = fields.Str(required = True)

class Todo(MongoSchema):
  _id = ObjectId()
  type_ = fields.Str(attribute = "type", missing = "Todo")
  description = fields.Str(required = True)
  finished = fields.DateTime()

  @classmethod
  @produces(OkResult, as_ = "result")
  @consumes("Todo")
  async def factory(cls, request, model):
    model.table = request.app.table
    await model.create()
    return str(model._id)

  @classmethod
  @produces(OkListResult, as_ = "result")
  async def get_all(cls, request):
    model = cls(table = request.app.table, many = True)
    await model.get(type = "Todo", many = True)
    return model.to_plain_dict()

  @classmethod
  @produces(OkDictResult, as_ = "result")
  async def get_one(cls, request, _id):
    model = cls(table = request.app.table)
    await model.get(_id = bson.ObjectId(_id))
    return model.to_plain_dict()

  @classmethod
  @consumes(DescriptionRequest)
  @produces(OkResult, as_ = "result")
  async def find_and_update(cls, request, _id, model):
    todo = cls(table = request.app.table)
    await todo.get(_id = bson.ObjectId(_id))
    description = model.description
    await todo.update({"description": description})
    return description

  @classmethod
  @produces(OkResult, as_ = "result")
  async def find_and_remove(cls, request, _id):
    todo = cls(table = request.app.table)
    todo.__data__["_id"] = bson.ObjectId(_id)
    await todo.delete()
    return _id

  @produces(OkResult, as_ = "result")
  async def __call__(self, request):
    return self.to_plain_dict()

class Node(MongoTree):
  _id = ObjectId()
  type_ = fields.Str(attribute = "type", missing = "Node")
  name = fields.Str(required = True)
  slug = fields.Str(required = True)
  path = fields.Str(required = True)
  nodes = fields.List(fields.Str, missing = [])

  children_models = {"nodes": "Node"}

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

  @consumes(NameRequest)
  @produces(OkDictResult, as_ = "result")
  async def update_field(self, request, field, model):
    result = await super().update_field(field, getattr(model, field), request.app.models)
    return result.to_plain_dict()

  @produces(OkResult, as_ = "result")
  async def delete(self, request):
    _id = str(self._id)
    result = await super().delete()
    return _id
