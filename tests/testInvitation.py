from unittest import TestCase

from pymongo import MongoClient

from slugify import slugify

from tests.app.app import create_app

class TestInvitation(TestCase):
  def setUp(self):
    self.app = create_app()
    self.client = MongoClient(self.app.config["MONGO_URI"])
    self.table = self.client.tests.tests
    _, resp = self.app.test_client.get("/")

  def tearDown(self):
    self.client.close()

  def testGetInvitation(self):
    email = "getinvitation@ysanic.net"
    data = {"type": "Invitation", "email": email, "slug": slugify(email), "path": "/"}
    result = self.table.insert_one(data)
    data["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"invitations": data["_id"]}})

    _, resp = self.app.test_client.get("/{}".format(data["slug"]))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    expected = data.copy()
    expected["_id"] = str(expected["_id"])
    self.assertDictEqual(expected, resp.json["result"])

    self.table.delete_one({"_id": data["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"invitations": data["_id"]}})

  def testGetInvitations(self):
    data = [
      {"type": "Invitation", "email": "getinvitations1@ysanic.net", "path": "/"},
      {"type": "Invitation", "email": "getinvitations2@ysanic.net", "path": "/"},
      {"type": "Invitation", "email": "getinvitations3@ysanic.net", "path": "/"},
    ]

    ids = []
    for invitation in data:
      invitation["slug"] = slugify(invitation["email"])
      result = self.table.insert_one(invitation)
      invitation["_id"] = result.inserted_id
      ids.append(invitation["_id"])
    self.table.update_one({"type": "Community"}, {"$addToSet": {"invitations": {"$each": ids}}})

    _, resp = self.app.test_client.get("/get_invitations")
    
    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    actual = [invitation["_id"] for invitation in resp.json["result"]]
    expected = [str(invitation["_id"]) for invitation in data]
    self.assertListEqual(sorted(actual), sorted(expected))

    for _id in ids:
      result = self.table.delete_one({"_id": _id})
    self.table.update_one({"type": "Community"}, {"$pull": {"invitations": {"$in": ids}}})
