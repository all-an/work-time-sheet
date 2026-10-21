import unittest

import worktime


class SmokeTest(unittest.TestCase):
    def test_package_has_version(self):
        self.assertRegex(worktime.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
