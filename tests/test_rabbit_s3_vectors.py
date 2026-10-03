import unittest
from unittest.mock import patch

from rabbit_s3_vectors import PublicVectorIndex


LIST_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Contents><Key>vectors/</Key></Contents>
  <Contents><Key>vectors/anchor-1.json</Key></Contents>
  <Contents><Key>vectors/anchor-2.json</Key></Contents>
</ListBucketResult>"""


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return LIST_RESPONSE


class PublicVectorIndexTest(unittest.TestCase):
    @patch("rabbit_s3_vectors.urlopen", return_value=_Response())
    def test_lists_objects_below_configured_prefix(self, urlopen_mock):
        index = PublicVectorIndex("example-bucket", "vectors")

        self.assertEqual(
            index.list_keys(),
            ["vectors/anchor-1.json", "vectors/anchor-2.json"],
        )
        self.assertIn("prefix=vectors/", urlopen_mock.call_args.args[0].full_url)

    @patch("rabbit_s3_vectors.urlopen", side_effect=OSError("network unavailable"))
    def test_status_returns_connection_error(self, _):
        status = PublicVectorIndex().status()

        self.assertFalse(status.reachable)
        self.assertEqual(status.object_count, 0)
        self.assertEqual(status.error, "network unavailable")


if __name__ == "__main__":
    unittest.main()
