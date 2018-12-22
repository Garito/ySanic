from unittest import TestCase

from bson import ObjectId
from pymongo import MongoClient

from slugify import slugify

from tests.app.app import create_app

class TestCommunity(TestCase):
  def setUp(self):
    self.app = create_app()
    self.client = MongoClient(self.app.config["MONGO_URI"])
    self.table = self.client.tests.tests

  def tearDown(self):
    self.client.close()

  def testGetCommunity(self):
    _, resp = self.app.test_client.get("/")

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)

    self.assertEqual(resp.json["result"]["path"], "")
    self.assertEqual(resp.json["result"]["slug"], "")
    self.assertEqual(resp.json["result"]["name"], "")
    self.assertEqual(len(resp.json["result"]["users"]), 1)

  def testCreateInvitation(self):
    data = {"email": "testcreateinvitation@ysanic.net"}
    _, resp = self.app.test_client.post("/new/invitations", json = data)

    self.assertEqual(resp.status, 201)
    self.assertTrue(resp.json["ok"])

    invitation = self.table.find_one({"type": "Invitation", "email": data["email"]})
    self.assertIsNotNone(invitation)

    self.table.delete_one({"_id": invitation["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"invitations": invitation["_id"]}})

  def testAlreadyInvited(self):
    email = "testalreadyinvited@ysanic.net"
    invitation = {"type": "Invitation", "email": email, "slug": slugify(email), "path": "/"}
    result = self.table.insert_one(invitation)
    invitation["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"invitations": invitation["_id"]}})

    _, resp = self.app.test_client.post("/new/invitations", json = {"email": email})

    self.assertEqual(resp.status, 409)
    self.assertTrue(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual("Already invited", resp.json["message"])

    self.table.delete_one({"_id": invitation["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"invitations": invitation["_id"]}})

  def testCreateInvitationNotEmail(self):
    _, resp = self.app.test_client.post("/new/invitations", json = {"name": "CreateInvitationNotEmail"})

    self.assertEqual(resp.status, 400)
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual("{'email': ['Missing data for required field.']}", resp.json["message"])

  def testCreateInvitationBadEmail(self):
    _, resp = self.app.test_client.post("/new/invitations", json = {"email": "createinvitationbademail.ysanic.net"})

    self.assertEqual(resp.status, 400)
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual("{'email': ['Not a valid email address.']}", resp.json["message"])

  def testCreateUser(self):
    email = "createuser@ysanic.net"
    invitation = {"type": "Invitation", "email": email, "slug": slugify(email), "path": "/"}
    result = self.table.insert_one(invitation)
    invitation["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"invitations": invitation["_id"]}})

    data = {"name": "Create User", "email": email, "code": str(invitation["_id"])}
    _, resp = self.app.test_client.post("/new/users", json = data)

    self.assertEqual(resp.status, 201)
    self.assertTrue(resp.json["ok"])

    invit = self.table.find_one({"_id": invitation["_id"]})
    self.assertIsNone(invit)
    user = self.table.find_one({"type": "User", "email": email})
    self.assertIsNotNone(user)

    self.table.delete_one({"_id": user["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"users": user["_id"], "invitations": invitation["_id"]}})

  def testCreateUserNoInvitation(self):
    code = str(ObjectId())
    data = {"name": "Create User Not Invitation", "email": "createusernotinvitation@ysanic.net", "code": code}
    _, resp = self.app.test_client.post("/new/users", json = data)
    
    self.assertEqual(resp.status, 404)
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual(resp.json["message"], "{{'_id': ObjectId('{}')}}".format(code))

  def testCreateUserValidationError(self):
    email = "createuservalidationerror@ysanic.net"
    invitation = {"type": "Invitation", "email": email, "slug": slugify(email), "path": "/"}
    result = self.table.insert_one(invitation)
    invitation["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"invitations": invitation["_id"]}})

    data = {"name": "Create User Validation Error"}
    _, resp = self.app.test_client.post("/new/users", json = data)

    self.assertEqual(resp.status, 400)
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual(resp.json["message"], "{'email': ['Missing data for required field.']}")

    self.table.delete_one({"_id": invitation["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"invitations": invitation["_id"]}})
  
  def testNotARoute(self):
    _, resp = self.app.test_client.get("/notaroute")

    self.assertEqual(resp.status, 404)
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json)
    self.assertEqual(resp.json["message"], "/notaroute not found")
