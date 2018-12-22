from unittest import TestCase

from bson import ObjectId
from pymongo import MongoClient

from slugify import slugify

from tests.app.app import create_app

class TestNode(TestCase):
  def setUp(self):
    self.app = create_app()
    self.client = MongoClient(self.app.config["MONGO_URI"])
    self.table = self.client.tests.tests

    self.app.test_client.get("/")
    
    name = "Test Node"
    self.user = {"type": "User", "name": name, "email": "testnode@ysanic.net", "slug": slugify(name), "path": "/", "trees": []}
    result = self.table.insert_one(self.user)
    self.user["_id"] = result.inserted_id
    self.table.update_one({"type": "Community"}, {"$addToSet": {"users": self.user["_id"]}})

  def tearDown(self):
    self.table.delete_one({"_id": self.user["_id"]})
    self.table.update_one({"type": "Community"}, {"$pull": {"users": self.user["_id"]}})

    self.client.close()

  def testGetTree(self):
    name = "Get Tree"
    data = {"type": "Node", "name": name, "path": "/{}".format(self.user["slug"]), "slug": slugify(name), "nodes": []}
    self.table.insert_one(data)
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": data["slug"]}})

    _, resp = self.app.test_client.get("/{}/{}".format(self.user["slug"], data["slug"]))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    expected = data.copy()
    expected["_id"] = str(expected["_id"])
    self.assertDictEqual(expected, resp.json["result"])

    self.table.delete_one({"_id": data["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": data["slug"]}})

  def testGetNode(self):
    grandpa = "Grandparent Get Node"
    grandpaslug = slugify(grandpa)
    parent = "Parent Get Node"
    parentslug = slugify(parent)
    node = "Get Node"
    nodeslug = slugify(node)
    data = [
      {"type": "Node", "name": grandpa, "path": "/{}".format(self.user["slug"]), "slug": grandpaslug, "nodes": [parentslug]},
      {"type": "Node", "name": parent, "path": "/{}/{}".format(self.user["slug"], grandpaslug), "slug": parentslug, "nodes": [nodeslug]},
      {"type": "Node", "name": node, "path": "/{}/{}/{}".format(self.user["slug"], grandpaslug, parentslug), "slug": nodeslug, "nodes": []}
    ]

    for tree in data:
      result = self.table.insert_one(tree)
      tree["_id"] = result.inserted_id
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": grandpaslug}})

    _, resp = self.app.test_client.get("/{}/{}/{}/{}".format(self.user["slug"], grandpaslug, parentslug, nodeslug))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    expected = data[2].copy()
    expected["_id"] = str(expected["_id"])
    self.assertDictEqual(expected, resp.json["result"])

    for tree in data:
      result = self.table.delete_one({"_id": tree["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": grandpaslug}})

  def testGetTrees(self):
    data = [
      {"type": "Node", "name": "Tree 1", "path": "/{}".format(self.user["slug"]), "nodes": []},
      {"type": "Node", "name": "Tree 2", "path": "/{}".format(self.user["slug"]), "nodes": []},
      {"type": "Node", "name": "Tree 3", "path": "/{}".format(self.user["slug"]), "nodes": []}
    ]
    slugs = []
    for tree in data:
      tree["slug"] = slugify(tree["name"])
      result = self.table.insert_one(tree)
      tree["_id"] = result.inserted_id
      slugs.append(tree["slug"])
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": {"$each": slugs}}})

    _, resp = self.app.test_client.get("/{}/get_trees".format(self.user["slug"]))
    
    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    actual = [tree["_id"] for tree in resp.json["result"]]
    expected = [str(tree["_id"]) for tree in data]
    self.assertListEqual(sorted(actual), sorted(expected))

    for tree in data:
      result = self.table.delete_one({"_id": tree["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": {"$in": slugs}}})

  def testGetTreeAncestors(self):
    name = "Get Tree Ancestors"
    data = {"type": "Node", "name": name, "path": "/{}".format(self.user["slug"]), "slug": slugify(name), "nodes": []}
    self.table.insert_one(data)
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": data["slug"]}})

    _, resp = self.app.test_client.get("/{}/{}/get_ancestors".format(self.user["slug"], data["slug"]))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    expected = self.user.copy()
    expected["_id"] = str(expected["_id"])
    expected["trees"].append(data["slug"])
    self.assertListEqual([expected], resp.json["result"])

    self.table.delete_one({"_id": data["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": data["slug"]}})

  def testGetAncestors(self):
    grandpa = "Grandparent node"
    grandpaslug = slugify(grandpa)
    parent = "Parent node"
    parentslug = slugify(parent)
    node = "Node Ancestors"
    nodeslug = slugify(node)
    data = [
      {"type": "Node", "name": grandpa, "path": "/{}".format(self.user["slug"]), "slug": grandpaslug, "nodes": [parentslug]},
      {"type": "Node", "name": parent, "path": "/{}/{}".format(self.user["slug"], grandpaslug), "slug": parentslug, "nodes": [nodeslug]},
      {"type": "Node", "name": node, "path": "/{}/{}/{}".format(self.user["slug"], grandpaslug, parentslug), "slug": nodeslug, "nodes": []}
    ]

    for tree in data:
      result = self.table.insert_one(tree)
      tree["_id"] = result.inserted_id
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": grandpaslug}})

    _, resp = self.app.test_client.get("/{}/{}/{}/{}/get_ancestors".format(self.user["slug"], grandpaslug, parentslug, nodeslug))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    user = self.user.copy()
    user["_id"] = str(user["_id"])
    user["trees"] = [data[0]["slug"]]
    gp = data[0].copy()
    gp["_id"] = str(gp["_id"])
    p = data[1].copy()
    p["_id"] = str(p["_id"])
    expected = [user, gp, p]
    self.assertListEqual(expected, resp.json["result"])

    for tree in data:
      result = self.table.delete_one({"_id": tree["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": grandpaslug}})

  def testGetChildren(self):
    nodename = "Node Children"
    nodeslug = slugify(nodename)
    node = {"type": "Node", "name": nodename, "path": "/{}".format(self.user["slug"]), "slug": nodeslug, "nodes": []}
    data = [
      {"type": "Node", "name": "Child 1", "path": "/{}/{}".format(self.user["slug"], nodeslug), "nodes": []},
      {"type": "Node", "name": "Child 2", "path": "/{}/{}".format(self.user["slug"], nodeslug), "nodes": []},
      {"type": "Node", "name": "Child 3", "path": "/{}/{}".format(self.user["slug"], nodeslug), "nodes": []}
    ]
    slugs = []
    for child in data:
      child["slug"] = slugify(child["name"])
      slugs.append(child["slug"])
      result = self.table.insert_one(child)
      child["_id"] = result.inserted_id
    node["nodes"] = slugs
    self.table.insert_one(node)
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"nodes": nodeslug}})

    _, resp = self.app.test_client.get("/{}/{}/get_children".format(self.user["slug"], nodeslug))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)

    expected = []
    for child in data:
      childnode = child.copy()
      childnode["_id"] = str(childnode["_id"])
      expected.append(childnode)
    self.assertListEqual(expected, resp.json["result"])

    for child in data:
      self.table.delete_one({"_id": child["_id"]})
    self.table.delete_one({"_id": node["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"nodes": nodeslug}})

  def testUpdateTreeName(self):
    name = "Update node"
    data = {"type": "Node", "name": name, "path": "/{}".format(self.user["slug"]), "slug": slugify(name), "nodes": []}
    self.table.insert_one(data)
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": data["slug"]}})

    newName = "Updated node"
    newSlug = slugify(newName)
    _, resp = self.app.test_client.put("/{}/{}".format(self.user["slug"], data["slug"]), json = {"name": newName})

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    self.assertDictEqual({"name": newName, "slug": newSlug}, resp.json["result"])

    user = self.table.find_one({"_id": self.user["_id"]})
    self.assertEqual(user["trees"], [newSlug])

    self.table.delete_one({"_id": data["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": data["slug"]}})

  def testUpdateNodeName(self):
    parent = "Parent node"
    parentslug = slugify(parent)
    node = "Updated Node"
    nodeslug = slugify(node)
    child = "Child node"
    childslug = slugify(child)
    data = [
      {"type": "Node", "name": parent, "path": "/{}".format(self.user["slug"]), "slug": parentslug, "nodes": [nodeslug]},
      {"type": "Node", "name": node, "path": "/{}/{}".format(self.user["slug"], parentslug), "slug": nodeslug, "nodes": [childslug]},
      {"type": "Node", "name": child, "path": "/{}/{}/{}".format(self.user["slug"], parentslug, nodeslug), "slug": childslug, "nodes": []},
    ]

    for tree in data:
      result = self.table.insert_one(tree)
      tree["_id"] = result.inserted_id
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": parentslug}})

    newName = "Updated node"
    newSlug = slugify(newName)
    _, resp = self.app.test_client.put("/{}/{}/{}".format(self.user["slug"], parentslug, nodeslug), json = {"name": newName})

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    self.assertDictEqual({"name": newName, "slug": newSlug}, resp.json["result"])

    parentdoc = self.table.find_one({"_id": data[0]["_id"]})
    self.assertEqual(parentdoc["nodes"], [newSlug])
    childdoc = self.table.find_one({"_id": data[2]["_id"]})
    self.assertEqual(childdoc["path"], "/{}/{}/{}".format(self.user["slug"], parentslug, newSlug))

    for tree in data:
      result = self.table.delete_one({"_id": tree["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": parentslug}})

  def testDeleteNode(self):
    parent = "Parent node"
    parentslug = slugify(parent)
    node = "Deleted Node"
    nodeslug = slugify(node)
    child = "Child node"
    childslug = slugify(child)
    data = [
      {"type": "Node", "name": parent, "path": "/{}".format(self.user["slug"]), "slug": parentslug, "nodes": [nodeslug]},
      {"type": "Node", "name": node, "path": "/{}/{}".format(self.user["slug"], parentslug), "slug": nodeslug, "nodes": [childslug]},
      {"type": "Node", "name": child, "path": "/{}/{}/{}".format(self.user["slug"], parentslug, nodeslug), "slug": childslug, "nodes": []},
    ]

    for tree in data:
      result = self.table.insert_one(tree)
      tree["_id"] = result.inserted_id
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": parentslug}})

    _, resp = self.app.test_client.delete("/{}/{}/{}".format(self.user["slug"], parentslug, nodeslug))

    self.assertEqual(resp.status, 200)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
    self.assertEqual(str(data[1]["_id"]), resp.json["result"])
    
    parentdoc = self.table.find_one({"_id": data[0]["_id"]})
    self.assertEqual(parentdoc["nodes"], [])
    childdoc = self.table.find_one({"_id": data[2]["_id"]})
    self.assertIsNone(childdoc)

    self.table.delete_one({"_id": data[0]["_id"]})

  def testCreateChildNode(self):
    name = "Create Child Node"
    tree = {"type": "Node", "name": name, "path": "/{}".format(self.user["slug"]), "slug": slugify(name), "nodes": []}
    self.table.insert_one(tree)
    self.table.update_one({"_id": self.user["_id"]}, {"$addToSet": {"trees": tree["slug"]}})

    data = {"name": "Create Child Node Child"}
    _, resp = self.app.test_client.post("/{}/{}/new/nodes".format(self.user["slug"], tree["slug"]), json = data)

    self.assertEqual(resp.status, 201)
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json)
  
    expected = tree.copy()
    expected = {'type': 'Node', 'name': data["name"], 'slug': slugify(data["name"]), 'path': '/{}/{}'.format(self.user["slug"], tree["slug"]), 
      'nodes': []}
    actual = resp.json["result"].copy()
    del actual["_id"]
    self.assertDictEqual(expected, actual)

    self.table.delete_one({"_id": ObjectId(resp.json["result"]["_id"])})
    self.table.delete_one({"_id": tree["_id"]})
    self.table.update_one({"_id": self.user["_id"]}, {"$pull": {"trees": tree["slug"]}})
