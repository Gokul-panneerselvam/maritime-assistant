import unittest
from pathlib import Path
from knowledge_graph.config import DataConfig
from knowledge_graph.kg_loader.normalizers import (
    convert_local_to_utc,
    parse_utc_iso,
    compute_duration_hours,
    slugify,
    normalize_type_id,
    extract_rolled_voyage,
)
from knowledge_graph.kg_loader.loaders.ports_loader import load_ports
from knowledge_graph.kg_loader.loaders.vessels_loader import load_vessels
from knowledge_graph.kg_loader.loaders.voyages_loader import load_voyages
from knowledge_graph.kg_loader.loaders.port_calls_loader import load_port_calls
from knowledge_graph.kg_loader.loaders.incidents_loader import load_incidents
from knowledge_graph.kg_loader.loaders.congestion_loader import load_congestion
from knowledge_graph.kg_loader.loaders.bookings_loader import load_bookings
from knowledge_graph.kg_loader.pipeline import IngestionPipeline

class TestNormalizers(unittest.TestCase):
    def test_convert_local_to_utc_rotterdam(self):
        # Summer daylight saving time (CEST is UTC+2)
        utc_ts = convert_local_to_utc("2026-07-18 12:00", "Europe/Amsterdam")
        self.assertEqual(utc_ts, "2026-07-18T10:00:00Z")

    def test_convert_local_to_utc_singapore(self):
        # Singapore is SGT (UTC+8)
        utc_ts = convert_local_to_utc("2026-09-30 06:00", "Asia/Singapore")
        self.assertEqual(utc_ts, "2026-09-29T22:00:00Z")

    def test_parse_utc_iso(self):
        self.assertEqual(parse_utc_iso("2026-10-06T06:00Z"), "2026-10-06T06:00:00Z")
        self.assertEqual(parse_utc_iso("2026-10-06T06:00:00Z"), "2026-10-06T06:00:00Z")
        self.assertIsNone(parse_utc_iso(""))
        self.assertIsNone(parse_utc_iso(None))

    def test_compute_duration_hours(self):
        hours = compute_duration_hours("2026-08-14T11:00Z", "2026-08-14T16:00Z")
        self.assertEqual(hours, 5.0)

        # Null or missing timestamp returns None
        self.assertIsNone(compute_duration_hours(None, "2026-08-14T16:00Z"))
        self.assertIsNone(compute_duration_hours("2026-08-14T11:00Z", None))

    def test_slugify(self):
        self.assertEqual(slugify("Halden Retail"), "halden-retail")
        self.assertEqual(slugify("Sulamar Gestão Naval"), "sulamar-gest-o-naval")

    def test_normalize_type_id(self):
        self.assertEqual(normalize_type_id("Container ship"), "CONTAINER_SHIP")
        self.assertEqual(normalize_type_id("Bulk carrier"), "BULK_CARRIER")
        self.assertEqual(normalize_type_id("Feeder"), "FEEDER")

    def test_extract_rolled_voyage(self):
        self.assertEqual(extract_rolled_voyage("Rolled to VG-1107"), "VG-1107")
        self.assertIsNone(extract_rolled_voyage("Rolled to next sailing"))
        self.assertIsNone(extract_rolled_voyage("Confirmed"))

class TestLoadersDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_config = DataConfig()

    def test_ports_loader(self):
        timezones = load_ports(self.data_config.ports_csv, dry_run=True)
        self.assertEqual(len(timezones), 15)
        self.assertIn("SGSIN", timezones)
        self.assertEqual(timezones["SGSIN"], "Asia/Singapore")
        self.assertEqual(timezones["NLRTM"], "Europe/Amsterdam")

    def test_vessels_loader(self):
        count = load_vessels(self.data_config.vessels_csv, dry_run=True)
        self.assertEqual(count, 40)

    def test_voyages_loader(self):
        timezones = load_ports(self.data_config.ports_csv, dry_run=True)
        count = load_voyages(self.data_config.voyages_csv, port_timezones=timezones, dry_run=True)
        self.assertEqual(count, 121)

    def test_port_calls_loader(self):
        count = load_port_calls(self.data_config.port_calls_csv, dry_run=True)
        self.assertEqual(count, 231)

    def test_incidents_loader(self):
        count = load_incidents(self.data_config.incidents_csv, dry_run=True)
        self.assertEqual(count, 90)

    def test_congestion_loader(self):
        count = load_congestion(self.data_config.congestion_csv, dry_run=True)
        self.assertEqual(count, 578)

    def test_bookings_loader(self):
        count = load_bookings(self.data_config.bookings_csv, dry_run=True)
        self.assertEqual(count, 400)

    def test_full_pipeline_dry_run(self):
        pipeline = IngestionPipeline(data_config=self.data_config)
        stats = pipeline.run(dry_run=True)
        self.assertTrue(stats["dry_run"])
        self.assertEqual(stats["ports_processed"], 15)
        self.assertEqual(stats["vessels_processed"], 40)
        self.assertEqual(stats["voyages_processed"], 121)
        self.assertEqual(stats["port_calls_processed"], 231)
        self.assertEqual(stats["incidents_processed"], 90)
        self.assertEqual(stats["congestion_processed"], 578)
        self.assertEqual(stats["bookings_processed"], 400)

if __name__ == "__main__":
    unittest.main()
