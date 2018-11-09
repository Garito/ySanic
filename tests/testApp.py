from unittest import TestCase

from random import choice

from bson import ObjectId

from pymongo import MongoClient

from slugify import slugify

from tests.app.app import create_app

class TestTodos(TestCase):
  def setUp(self):
    self.app = create_app()
    self.client = MongoClient(self.app.config["MONGO_URI"])
    self.table = self.client.tests.tests

    self.todos = [
      {"type": "Todo", "description": "Todo 1"},
      {"type": "Todo", "description": "Todo 2"},
      {"type": "Todo", "description": "Todo 3"},
      {"type": "Todo", "description": "Todo 4"},
      {"type": "Todo", "description": "Todo 5"}
    ]

    for todo in self.todos:
      result = self.table.insert_one(todo)
      todo["_id"] = result.inserted_id

  def tearDown(self):
    for todo in self.todos:
      self.table.delete_one({"_id": todo["_id"]})

    self.client.close()

  def testNotFound(self):
    _id = ObjectId()
    req, resp = self.app.test_client.get("/todos/{}".format(str(_id)))

    self.assertEqual(resp.status, 404)
    self.assertIn("ok", resp.json.keys())
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json.keys())
    self.assertEqual(resp.json["message"], str({"_id": _id}))

  def testCreateTodo(self):
    data = {"description": "Todo's description"}
    req, resp = self.app.test_client.post("/todos", json = data)

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())

    doc = self.table.find_one({"_id": ObjectId(resp.json["result"])})
    self.assertEqual(doc["description"], data["description"])

    self.table.delete_one({"_id": ObjectId(resp.json["result"])})

  def testGetTodos(self):
    req, resp = self.app.test_client.get("/todos")

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())

    retrieved_ids = [todo["_id"] for todo in resp.json["result"]]
    expected_ids = [str(todo["_id"]) for todo in self.todos]

    self.assertListEqual(sorted(retrieved_ids), sorted(expected_ids))

  def testGetTodo(self):
    todo = choice(self.todos).copy()
    todo["_id"] = str(todo["_id"])
    req, resp = self.app.test_client.get("/todos/{}".format(todo["_id"]))

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())

    self.assertDictEqual(resp.json["result"], todo)

  def testGetTodoNotFound(self):
    _id = ObjectId()
    req, resp = self.app.test_client.get("/todos/{}".format(_id))

    self.assertEqual(resp.status, 404)
    self.assertIn("ok", resp.json.keys())
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json.keys())

    self.assertEqual(resp.json["message"], str({"_id": _id}))

  def testUpdateTodo(self):
    todo = choice(self.todos)
    data = {"description": "{} edited".format(todo["description"])}
    req, resp = self.app.test_client.post("/todos/{}".format(todo["_id"]), json = data)

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())

    self.assertEqual(resp.json["result"], data["description"])

  def testDeleteTodo(self):
    todo = choice(self.todos)
    req, resp = self.app.test_client.delete("/todos/{}".format(todo["_id"]))

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())
    self.assertEqual(resp.json["result"], str(todo["_id"]))

    doc = self.table.find_one({"_id": todo["_id"]})

    self.assertIsNone(doc)

class TestNodes(TestCase):
  def setUp(self):
    self.app = create_app()
    self.client = MongoClient(self.app.config["MONGO_URI"])
    self.table = self.client.tests.tests

    self.nodes = [
      # {"type": "Node", "path": "/", "name": "", "slug": "", "nodes": ["parent-1"]},
      {"type": "Node", "path": "/", "name": "Parent 1", "slug": "parent-1", "nodes": ["parent-2", "paper-2"]},
      {"type": "Node", "path": "/parent-1", "name": "Parent 2", "slug": "parent-2", "nodes": ["paper"]},
      {"type": "Node", "path": "/parent-1", "name": "Paper 2", "slug": "paper-2", "nodes": []},
      {"type": "Node", "path": "/parent-1/parent-2", "name": "Paper", "slug": "paper", "nodes": []}
    ]

    for node in self.nodes:
      result = self.table.insert_one(node)
      node["_id"] = result.inserted_id

  def tearDown(self):
    for node in self.nodes:
      self.table.delete_one({"_id": node["_id"]})

    self.client.close()

  def testMethodNotFound(self):
    node = self.nodes[1]
    url = "{}/{}/idontexist".format(node["path"], node["slug"])
    req, resp = self.app.test_client.get("/nodes{}".format(url))

    self.assertEqual(resp.status, 404)
    self.assertIn("ok", resp.json.keys())
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json.keys())
    self.assertEqual(resp.json["message"], "{} not found".format(url))

  def testGetNode(self):
    node = choice(self.nodes)
    url = "/nodes{}/{}".format(node["path"], node["slug"]) if node["path"] != "/" else "/nodes/{}".format(node["slug"])
    req, resp = self.app.test_client.get(url)

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())
    self.assertEqual(resp.json["result"]["_id"], str(node["_id"]))

  def testGetWrongNode(self):
    wrong_path = "/one/that/doesnt/exist"
    req, resp = self.app.test_client.get("/nodes{}".format(wrong_path))

    self.assertEqual(resp.status, 404)
    self.assertIn("ok", resp.json.keys())
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json.keys())
    self.assertEqual(resp.json["message"], "{} not found".format(wrong_path))

  def testGetChildren(self):
    node = self.nodes[0]
    req, resp = self.app.test_client.get("/nodes/{}/get_children".format(node["slug"]))

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())

    self.assertEqual(resp.json["result"][0]["_id"], str(self.nodes[1]["_id"]))
    self.assertEqual(resp.json["result"][1]["_id"], str(self.nodes[2]["_id"]))

  def testGetAncestors(self):
    node = self.nodes[-1]
    req, resp = self.app.test_client.get("/nodes{}/{}/get_ancestors".format(node["path"], node["slug"]))

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())

    self.assertEqual(resp.json["result"][0]["_id"], str(self.nodes[0]["_id"]))
    self.assertEqual(resp.json["result"][1]["_id"], str(self.nodes[1]["_id"]))

  def testCreateChild(self):
    node = self.nodes[-1]
    data = {"type": "Node", "name": "Child node"}
    req, resp = self.app.test_client.post("/nodes{}/{}/new/nodes".format(node["path"], node["slug"]), json = data)

    self.assertEqual(resp.status, 201)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())

    result = self.table.delete_one({"_id": ObjectId(resp.json["result"]["_id"])})
    self.assertEqual(result.deleted_count, 1)

  def testCreateChildWrongParent(self):
    wrong_path = "/one/that/doesnt/exist"
    data = {"type": "Node", "name": "Child node with wrong parent"}
    req, resp = self.app.test_client.post("/nodes{}/new/nodes".format(wrong_path), json = data)

    self.assertEqual(resp.status, 404)
    self.assertIn("ok", resp.json.keys())
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json.keys())
    self.assertEqual(resp.json["message"], "{} not found".format(wrong_path))

  def testUpdateNodeName(self):
    nodes = [
      {"type": "Node", "path": "/parent-1", "name": "Updated node", "slug": "updated-node", "nodes": ["subnode-1", "subnode-2"]},
      {"type": "Node", "path": "/parent-1/updated-node", "name": "Subnode 1", "slug": "subnode-1", "nodes": []},
      {"type": "Node", "path": "/parent-1/updated-node", "name": "Subnode 2", "slug": "subnode-2", "nodes": ["sub-subnode-1", "sub-subnode-2"]},
      {"type": "Node", "path": "/parent-1/updated-node/subnode-1", "name": "Sub subnode 1", "slug": "sub-subnode-1", "nodes": ["sub-sub-subnode"]},
      {"type": "Node", "path": "/parent-1/updated-node/subnode-1/sub-subnode-1", "name": "Sub sub subnode", "slug": "sub-sub-subnode", "nodes": []}
    ]

    for node in nodes:
      result = self.table.insert_one(node)
      node["_id"] = result.inserted_id

    node_url = "/parent-1/updated-node"
    data = {"name": "Updated updated node"}
    req, resp = self.app.test_client.put("/nodes{}/update/name".format(node_url), json = data)
    data["slug"] = slugify(data["name"])
    new_url = "/parent-1/{}".format(data["slug"])

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())
    self.assertDictEqual(resp.json["result"], data)

    docs_old = list(self.table.find({"path": {"$regex": "^{}".format(node_url)}}))
    docs_new = list(self.table.find({"path": {"$regex": "^{}".format(new_url)}}))

    self.assertFalse(docs_old)
    ids = sorted([str(doc["_id"]) for doc in docs_new])
    actual_ids = sorted([str(node["_id"]) for node in nodes[1:]])

    self.assertListEqual(ids, actual_ids)

    for node in nodes:
      self.table.delete_one({"_id": node["_id"]})

  def testUpdateWrongParent(self):
    wrong_path = "/path/that/doesnt/exists"
    req, resp = self.app.test_client.put("/nodes{}/update/nane".format(wrong_path), json = {"name": "will not work"})

    self.assertEqual(resp.status, 404)
    self.assertIn("ok", resp.json.keys())
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json.keys())
    self.assertEqual(resp.json["message"], "{} not found".format(wrong_path))

  def testDeleteNode(self):
    nodes = [
      {"type": "Node", "path": "/parent-1", "name": "Deleted node", "slug": "deleted-node", "nodes": ["subnode-1", "subnode-2"]},
      {"type": "Node", "path": "/parent-1/deleted-node", "name": "Subnode 1", "slug": "subnode-1", "nodes": []},
      {"type": "Node", "path": "/parent-1/deleted-node", "name": "Subnode 2", "slug": "subnode-2", "nodes": ["sub-subnode-1", "sub-subnode-2"]},
      {"type": "Node", "path": "/parent-1/deleted-node/subnode-1", "name": "Sub subnode 1", "slug": "sub-subnode-1", "nodes": ["sub-sub-subnode"]},
      {"type": "Node", "path": "/parent-1/deleted-node/subnode-1/sub-subnode-1", "name": "Sub sub subnode", "slug": "sub-sub-subnode", "nodes": []}
    ]

    for node in nodes:
      result = self.table.insert_one(node)
      node["_id"] = result.inserted_id

    node_url = "/parent-1/deleted-node"
    req, resp = self.app.test_client.delete("/nodes{}".format(node_url))

    children = list(self.table.find({"path": {"$regex": "^{}".format(node_url)}}))

    self.assertEqual(resp.status, 200)
    self.assertIn("ok", resp.json.keys())
    self.assertTrue(resp.json["ok"])
    self.assertIn("result", resp.json.keys())
    self.assertEqual(resp.json["result"], str(nodes[0]["_id"]))

    self.assertFalse(children)

  def testDeleteWrongParent(self):
    wrong_path = "/path/that/doesnt/exists"
    req, resp = self.app.test_client.delete("/nodes{}".format(wrong_path))

    self.assertEqual(resp.status, 404)
    self.assertIn("ok", resp.json.keys())
    self.assertFalse(resp.json["ok"])
    self.assertIn("message", resp.json.keys())
    self.assertEqual(resp.json["message"], "{} not found".format(wrong_path))
