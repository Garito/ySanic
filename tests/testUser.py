from unittest import TestCase

from bson import ObjectId
from pymongo import MongoClient

from slugify import slugify

from tests.app.app import create_app

class TestUser(TestCase):
  def setUp(self):
    self.app = create_app()
    self.client = MongoClient(self.app.config["MONGO_URI"])
    self.table = self.client.tests.tests
    _, resp = self.app.test_client.get("/")

  def tearDown(self):
    self.client.close()

  def testGetUser(self):
    name = "Get User"
    data = {"type": "User", "name": name, "email": "getuser@ysanic.net", "slug": slugify(name), "path": "/"}
    result = self.table.insert_one(data)
    data["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"users": data["_id"]}})

    _, resp = self.app.test_client.get("/{}".format(data["slug"]))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    expected = data.copy()
    expected["_id"] = str(expected["_id"])
    expected["trees"] = []
    self.assertDictEqual(expected, resp.json["result"])

    self.table.delete_one({"_id": data["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"users": data["_id"]}})

  def testGetUsers(self):
    data = [
      {"type": "User", "name": "Get Users 1", "email": "getusers1@ysanic.net", "path": "/"},
      {"type": "User", "name": "Get Users 2", "email": "getusers2@ysanic.net", "path": "/"},
      {"type": "User", "name": "Get Users 3", "email": "getusers3@ysanic.net", "path": "/"},
    ]

    ids = []
    for user in data:
      user["slug"] = slugify(user["email"])
      result = self.table.insert_one(user)
      user["_id"] = result.inserted_id
      ids.append(user["_id"])
    self.table.update_one({"type": "Community"}, {"$addToSet": {"users": {"$each": ids}}})

    _, resp = self.app.test_client.get("/get_users")
    
    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    actual = [user["_id"] for user in resp.json["result"]]
    expected = [str(user["_id"]) for user in data]
    garito = self.table.find_one({"name": "Garito"})
    expected.append(str(garito["_id"]))
    self.assertListEqual(sorted(actual), sorted(expected))

    for _id in ids:
      result = self.table.delete_one({"_id": _id})
    self.table.update_one({"type": "Community"}, {"$pull": {"users": {"$in": ids}}})

  def testCreateTree(self):
    name = "Create Tree"
    user = {"type": "User", "name": name, "email": "createtree@ysanic.net", "slug": slugify(name), "path": "/"}
    result = self.table.insert_one(user)
    user["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"users": user["_id"]}})

    data = {"name": "Tree 1"}
    _, resp = self.app.test_client.post("/{}/new/trees".format(user["slug"]), json = data)

    self.assertEqual(resp.status, 201)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    self.assertEqual(data["name"], resp.json["result"]["name"])

    self.table.delete_one({"_id": ObjectId(resp.json["result"]["_id"])})
    self.table.delete_one({"_id": user["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"users": user["_id"]}})

  def testCreateTreeBadUser(self):
    slug = "idontexists"
    _, resp = self.app.test_client.post("/{}/new/trees".format(slug), json = {"name": "Not important since the user doesn't exists"})

    self.assertEqual(resp.status, 404)
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual(resp.json["message"], '/{} not found'.format(slug))

  def testCreateTreeValidationError(self):
    name = "Create Tree Validation Error"
    user = {"type": "User", "name": name, "email": "createtreevalidationerror@ysanic.net", "slug": slugify(name), "path": "/"}
    result = self.table.insert_one(user)
    user["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"users": user["_id"]}})

    data = {"badproperty": "Tree 1"}
    _, resp = self.app.test_client.post("/{}/new/trees".format(user["slug"]), json = data)

    self.assertEqual(resp.status, 400)
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual(resp.json["message"], "{'name': ['Missing data for required field.']}")

    self.table.delete_one({"_id": user["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"users": user["_id"]}})
