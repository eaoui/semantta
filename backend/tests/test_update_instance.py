import sys
from pathlib import Path
import unittest

from fastapi import HTTPException

# Make backend modules importable when tests are run from the repository root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import main


TEST_URI = "urn:test:instance"
TEST_CLASS = "http://example.org/Book"
TEST_PROPERTY = "http://example.org/title"


class FakeStore:
    def __init__(self):
        self.updates = []

    async def update(self, sparql: str) -> None:
        self.updates.append(sparql)


class FakeSHACL:
    def __init__(self, error: HTTPException | None = None):
        self.error = error

    async def get_active_classes(self):
        return [TEST_CLASS]

    async def get_active_properties(self):
        return [TEST_PROPERTY]

    async def validate_instance(self, class_uris, properties):
        if self.error is not None:
            raise self.error
        return True


class UpdateInstanceTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.original_store = main.store
        self.original_shacl = main.shacl
        self.original_check_disjoint = main.check_disjoint_classes
        self.original_invalidate_profile = main.invalidate_profile

        self.store = FakeStore()
        main.store = self.store
        main.shacl = FakeSHACL()
        main.check_disjoint_classes = self._check_disjoint
        main.invalidate_profile = lambda: None

        main.state["created_instances"].discard(TEST_URI)

    async def _check_disjoint(self, class_uris):
        return None

    def tearDown(self):
        main.store = self.original_store
        main.shacl = self.original_shacl
        main.check_disjoint_classes = self.original_check_disjoint
        main.invalidate_profile = self.original_invalidate_profile

    async def test_validation_failure_does_not_modify_store(self):
        main.shacl = FakeSHACL(
            HTTPException(
                status_code=400,
                detail="SHACL validation failed",
            )
        )

        with self.assertRaises(HTTPException):
            await main.update_instance(
                TEST_URI,
                {
                    "class_uris": [TEST_CLASS],
                    "properties": {
                        TEST_PROPERTY: ["New title"],
                    },
                },
            )

        self.assertEqual(
            self.store.updates,
            [],
            "A failed validation must not modify persistent RDF data.",
        )

    async def test_successful_update_uses_one_store_update(self):
        result = await main.update_instance(
            TEST_URI,
            {
                "class_uris": [TEST_CLASS],
                "properties": {
                    TEST_PROPERTY: ["New title"],
                },
            },
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(
            len(self.store.updates),
            1,
            "The replacement should be sent as one SPARQL update request.",
        )

        update = self.store.updates[0]

        self.assertIn("DELETE", update)
        self.assertIn("INSERT DATA", update)
        self.assertIn(TEST_URI, update)
        self.assertIn(TEST_CLASS, update)
        self.assertIn(TEST_PROPERTY, update)


if __name__ == "__main__":
    unittest.main()