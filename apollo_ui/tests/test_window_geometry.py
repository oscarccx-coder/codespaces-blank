"""Window startup regression tests; pure geometry does not require Qt."""
import unittest
from apollo_window_geometry import centered_window_geometry as center


class StartupGeometryTests(unittest.TestCase):
    def test_centre_on_primary_screen(self):
        self.assertEqual(center((0, 0, 1920, 1080), (1500, 900)),
                         (210, 90, 1500, 900))

    def test_centre_on_secondary_monitor_with_negative_coordinates(self):
        self.assertEqual(center((-1920, 0, 1920, 1080), (1100, 700)),
                         (-1510, 190, 1100, 700))

    def test_clamp_oversized_saved_window_to_available_area(self):
        x, y, w, h = center((0, 0, 1366, 728), (4000, 1800))
        self.assertEqual((w, h), (1334, 696))
        self.assertEqual((x, y), (16, 16))

    def test_accept_monitor_not_starting_at_zero(self):
        self.assertEqual(center((1920, -240, 2560, 1400), (1500, 900)),
                         (2450, 10, 1500, 900))

    def test_reject_bad_screen(self):
        with self.assertRaises(ValueError):
            center((0, 0, 0, 0), (800, 600))


if __name__ == "__main__":
    unittest.main()
