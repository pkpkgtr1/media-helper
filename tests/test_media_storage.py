"""Storage regression tests using temporary, neutral local media fixtures only.

Run from the project root: python -m unittest discover -s tests -p test_media_storage.py
No crawler imports, browser sessions, or network access are needed.
"""
from __future__ import annotations

import copy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import media_storage as storage


class CategoryRulesTests(unittest.TestCase):
    def test_default_catalog_is_complete_grouped_and_explicit_only(self):
        settings = storage.default_settings()
        rows = settings["categories"]
        self.assertEqual(240, len(rows))
        self.assertEqual(7, len({r["group"] for r in rows}))
        self.assertEqual(240, len({r["name"] for r in rows}))
        self.assertFalse(any(r["checked"] for r in rows))
        self.assertEqual("exclude", settings["unseenDefault"])
        self.assertEqual([], storage.filter_categories(["Studio", "1080p"], settings))

    def test_migration_discards_custom_and_fills_complete_catalog(self):
        settings = storage.validate_settings({"categories": [
            {"name": "1080p", "checked": True}, {"name": "Studio", "checked": True}],
            "writeTags": False, "unseenDefault": "keep"})
        self.assertEqual(240, len(settings["categories"]))
        self.assertEqual(["1080p"], [r["name"] for r in settings["categories"] if r["checked"]])
        self.assertTrue(settings["writeTags"] and settings["writeGenres"])
        self.assertEqual(["1080p"], storage.filter_categories(["1080p", "Studio", "ASMR"], settings))

    def test_nfkc_case_and_full_name_matching_never_keeps_unknown(self):
        settings = {"categories": [{"name": "ASMR", "checked": True}], "unseenDefault": "keep"}
        self.assertEqual(["ASMR"], storage.filter_categories([" ＡＳＭＲ ", "asmr", "ASMR notes", "Studio"], settings))

    def test_traditional_aliases_share_one_selection_and_output_name(self):
        row = next(r for r in storage.official_categories() if len(set(r["aliases"])) > 1)
        settings = storage.validate_settings({"categories": [{"name": row["aliases"][0], "checked": True}]})
        self.assertEqual([row["name"]], storage.filter_categories(row["aliases"], settings))
        self.assertEqual([], storage.filter_categories(row["aliases"], {"categories": []}))

    def test_validation_rejects_normalized_duplicate_rules_and_boolean_numbers(self):
        with self.assertRaises(ValueError):
            storage.validate_settings({"categories": [
                {"name": "Field Recording", "checked": True},
                {"name": "ＦＩＥＬＤ　ＲＥＣＯＲＤＩＮＧ", "checked": False},
            ]})
        for name in ("retries", "downloadInterval", "requestTimeout"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                storage.validate_settings({name: True})


class TemporaryLibraryTests(unittest.TestCase):
    def test_resolution_refresh_preserves_newer_record_and_nfo(self):
        item = self.record()
        current = {**item, "title": "Newer title", "custom": "keep"}
        self.write_records([current])
        nfo = self.write_nfo()
        old_bytes = nfo.read_bytes()
        storage.publish_month_resolution(str(self.root), 2026, 4, item, [1080, 720])
        rows = json.loads((self.directory / "2026-04.json").read_text(encoding="utf-8"))
        self.assertEqual([{**current, "available_resolutions": [1080, 720]}], rows)
        self.assertEqual(old_bytes, nfo.read_bytes())
        result = storage.library_entries(str(self.root), 2026, 4, self.settings)
        self.assertEqual("1080p", result["entries"][0]["resolution"])

    def test_publish_each_item_preserves_old_records_and_survives_interruption(self):
        self.write_records([self.record(stem="Previous", id="old")])
        record = self.record()
        storage.publish_month_item(str(self.root), 2026, 4, record)
        first = storage.library_entries(str(self.root), 2026, 4, self.settings)
        self.assertEqual(2, len(first["entries"]))
        record["tags"] = ["New"]
        storage.publish_month_item(str(self.root), 2026, 4, record)
        rows = json.loads((self.directory / "2026-04.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(rows))
        self.assertEqual(["New"], next(r for r in rows if r["id"] == record["id"])["tags"])

    def test_current_metadata_item_is_visible_before_nfo_exists(self):
        task = dict(id="job", outputDir=str(self.directory), state="downloading", type="NFO",
                    currentCode="local-river", currentTitle="River Study")
        result = storage.library_entries(str(self.root), 2026, 4, self.settings, [task])
        self.assertTrue(result["entries"][0]["isProcessingPlaceholder"])
        storage.publish_month_item(str(self.root), 2026, 4, self.record())
        result = storage.library_entries(str(self.root), 2026, 4, self.settings, [task])
        self.assertEqual(1, len(result["entries"]))
        self.assertEqual("downloading", result["entries"][0]["nfo"])
        self.write_nfo()
        result = storage.library_entries(str(self.root), 2026, 4, self.settings, [task])
        self.assertEqual("ready", result["entries"][0]["nfo"])
        task["outputDir"] = str(self.root / "2026-05")
        result = storage.library_entries(str(self.root), 2026, 4, self.settings, [task])
        self.assertNotEqual("downloading", result["entries"][0]["status"])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="media-storage-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "媒体资料"
        self.directory = self.root / "2026-04"
        self.directory.mkdir(parents=True)
        self.state_directory = self.base / "settings"
        # Use a small neutral catalog for file and backup regression fixtures.
        catalog_patch = patch.object(storage, "official_categories", return_value=[
            dict(name=name, group="Fixture", aliases=[name])
            for name in ["Archive", "Field Recording", "New", "Landscape"]])
        catalog_patch.start()
        self.addCleanup(catalog_patch.stop)
        self.settings = storage.validate_settings({
            "outputRoot": str(self.root),
            "categories": [{"name": name, "checked": name != "Archive"}
                           for name in ["Archive", "Field Recording", "New", "Landscape"]],
        })
        self.store = storage.Storage(self.state_directory)

    def record(self, stem="River Study", **extra):
        result = {
            "id": "local-river",
            "title_fs": stem,
            "title": "River Study from JSON",
            "tags": ["Field Recording"],
            "original_tags": ["Field Recording", "Archive", "New"],
        }
        result.update(extra)
        return result

    def write_records(self, records):
        path = self.directory / "2026-04.json"
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        return path

    def nfo_bytes(self, title="River Study from NFO", tags=("Archive", "Legacy")):
        node = ET.Element("movie", {"custom": "preserved"})
        ET.SubElement(node, "title").text = title
        ET.SubElement(node, "id").text = "local-nfo"
        ET.SubElement(node, "uniqueid", {"type": "local", "default": "true"}).text = "local-unique"
        ET.SubElement(node, "plot").text = "A neutral study of river flow & light."
        ET.SubElement(node, "runtime").text = "12"
        ET.SubElement(node, "thumb", {"aspect": "poster"}).text = "River Study-poster.jpg"
        actor = ET.SubElement(node, "actor")
        ET.SubElement(actor, "name").text = "Sample Narrator"
        ET.SubElement(actor, "role").text = "Narration"
        node.append(ET.Comment("Keep this local note"))
        for tag in tags:
            ET.SubElement(node, "genre").text = tag
            ET.SubElement(node, "tag").text = tag
        return ET.tostring(node, encoding="utf-8", xml_declaration=True)

    def write_nfo(self, stem="River Study", **kwargs):
        path = self.directory / f"{stem}.nfo"
        path.write_bytes(self.nfo_bytes(**kwargs))
        return path

    def request(self, **extra):
        value = {
            "outputRoot": str(self.root), "year": 2026, "month": 4,
            "settings": copy.deepcopy(self.settings), "backup": True,
        }
        value.update(extra)
        return value

    def apply_preview(self, request):
        preview = self.store.preview_nfo(request)
        return self.store.apply_nfo({**request, "token": preview["token"]})

    def snapshot(self):
        return {
            str(path.relative_to(self.base)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.base.rglob("*") if path.is_file()
        }

    def test_json_and_nfo_merge_retains_original_metadata_and_current_nfo_categories(self):
        self.write_records([self.record()])
        self.write_nfo()
        self.write_nfo("Harbor Walk", title="Harbor Walk", tags=("Landscape",))
        items, warnings = storage.read_month(str(self.root), 2026, 4)
        self.assertEqual([], warnings)
        self.assertEqual(["Harbor Walk", "River Study"], [item["title_fs"] for item in items])
        river = items[1]
        self.assertEqual("local-river", river["id"])
        self.assertEqual("River Study from JSON", river["title"])
        self.assertEqual(["Field Recording"], river["tags"])
        self.assertEqual(["Field Recording", "Archive", "New"], river["original_tags"])
        self.assertEqual(["Archive", "Legacy"], river["_nfo_categories"])
        self.assertEqual("A neutral study of river flow & light.", river["description"])
        self.assertEqual("local-nfo", items[0]["id"])
        self.assertEqual(["Landscape"], items[0]["tags"])
        self.assertNotEqual(river["_entry_id"], items[0]["_entry_id"])
        self.assertEqual(items, storage.read_month(str(self.root), 2026, 4)[0])

    def test_invalid_json_recovers_local_nfo_without_rewriting_the_json(self):
        record_path = self.directory / "2026-04.json"
        record_path.write_text("{ unfinished", encoding="utf-8")
        self.write_nfo()
        before = self.snapshot()
        items, warnings = storage.read_month(str(self.root), 2026, 4)
        self.assertEqual(["River Study"], [item["title_fs"] for item in items])
        self.assertTrue(warnings)
        self.assertEqual(before, self.snapshot())

    def test_readonly_load_and_preview_leave_all_bytes_and_modification_times_unchanged(self):
        self.write_records([self.record()])
        self.write_nfo()
        (self.directory / "River Study.mp4").write_bytes(b"neutral local media fixture")
        (self.directory / "River Study-poster.jpg").write_bytes(b"neutral local poster fixture")
        self.store.save_settings(self.settings)
        for path in self.base.rglob("*"):
            if path.is_file():
                os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
        before = self.snapshot()
        reopened = storage.Storage(self.state_directory)
        storage.read_month(str(self.root), 2026, 4)
        result = storage.library_entries(str(self.root), 2026, 4, reopened.settings)
        preview = reopened.preview_nfo(self.request())
        self.assertEqual(1, preview["affected"])
        self.assertEqual("completed", result["entries"][0]["status"])
        self.assertEqual(before, self.snapshot())

    def test_loading_missing_month_does_not_create_directories(self):
        missing_root = self.base / "never-created"
        self.assertEqual(([], []), storage.read_month(str(missing_root), 2025, 12))
        result = storage.library_entries(str(missing_root), 2025, 12, self.settings)
        self.assertEqual([], result["entries"])
        self.assertFalse(missing_root.exists())

    def test_missing_or_empty_assets_are_not_reported_ready(self):
        self.write_records([self.record()])
        self.write_nfo()
        (self.directory / "River Study.mp4").write_bytes(b"")
        (self.directory / "River Study-poster.jpg").write_bytes(b"")
        entry = storage.library_entries(str(self.root), 2026, 4, self.settings)["entries"][0]
        self.assertEqual("missing", entry["video"])
        self.assertEqual("missing", entry["image"])
        self.assertEqual("ready", entry["nfo"])
        self.assertEqual("", entry["cover"])

    def test_completed_retry_supersedes_an_older_failure_for_the_same_entry(self):
        self.write_records([self.record()])
        self.write_nfo()
        (self.directory / "River Study.mp4").write_bytes(b"neutral local media fixture")
        (self.directory / "River Study-poster.jpg").write_bytes(b"neutral local poster fixture")
        entry_id = storage.read_month(str(self.root), 2026, 4)[0][0]["_entry_id"]
        tasks = [
            {"id": "old", "entryId": entry_id, "type": "视频", "state": "failed", "error": "Old failure", "progress": 20},
            {"id": "retry", "entryId": entry_id, "type": "视频", "state": "completed", "progress": 100},
        ]
        entry = storage.library_entries(str(self.root), 2026, 4, self.settings, tasks)["entries"][0]
        self.assertEqual("completed", entry["status"])
        self.assertEqual("ready", entry["video"])
        self.assertFalse(entry.get("error"))

    def test_invalid_record_path_does_not_discard_subsequent_safe_records(self):
        self.write_records([
            self.record("First"), self.record("../outside"), self.record("Last"),
        ])
        items, warnings = storage.read_month(str(self.root), 2026, 4)
        self.assertEqual(["First", "Last"], [item["title_fs"] for item in items])
        self.assertTrue(warnings)
        self.assertFalse((self.root / "outside.nfo").exists())

    def test_safe_base_rejects_traversal_and_absolute_or_special_paths(self):
        for name in ("", ".", "..", "../outside", "..\\outside", "sub/entry", "sub\\entry",
                     "/absolute", "C:\\outside", "entry:stream", "entry\nname", "entry\0name"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                storage.safe_base(self.directory, name)
        self.assertEqual(self.directory / "中性样片", storage.safe_base(self.directory, "中性样片"))

    def test_period_validation_rejects_non_integer_and_out_of_range_values(self):
        for year, month in ((2026, 0), (2026, 13), (2026, True), (True, 4), (1899, 4), (2201, 4), (2026, "4")):
            with self.subTest(year=year, month=month), self.assertRaises(ValueError):
                storage.month_directory(str(self.root), year, month)
        with self.assertRaises(ValueError):
            storage.month_directory(" ", 2026, 4)

    def test_nfo_symlink_outside_month_is_not_read(self):
        outside = self.base / "outside.nfo"
        outside.write_bytes(self.nfo_bytes(title="Outside fixture"))
        linked = self.directory / "Escaped.nfo"
        try:
            linked.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("This host lacks permission to create filesystem symlinks")
        before = outside.read_bytes()
        items, warnings = storage.read_month(str(self.root), 2026, 4)
        self.assertEqual([], items)
        self.assertTrue(warnings)
        self.assertEqual(before, outside.read_bytes())

    def test_resolved_nfo_target_outside_month_is_rejected_without_reading_it(self):
        nfo = self.write_nfo()
        outside = self.base / "outside.nfo"
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            return outside if path == nfo else original_resolve(path, *args, **kwargs)

        # Covers the caller's boundary check on hosts without symlink privileges.
        with patch.object(Path, "resolve", new=resolve), patch.object(storage, "xml_tree", wraps=storage.xml_tree) as parser:
            items, warnings = storage.read_month(str(self.root), 2026, 4)
        self.assertEqual([], items)
        self.assertTrue(warnings)
        parser.assert_not_called()

    def test_resolved_month_record_outside_month_is_rejected(self):
        record_path = self.write_records([self.record("Escaped")])
        outside = self.base / "outside.json"
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            return outside if path == record_path else original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", new=resolve):
            items, warnings = storage.read_month(str(self.root), 2026, 4)
        self.assertEqual([], items)
        self.assertTrue(warnings)

    def test_resolved_month_directory_outside_root_is_rejected(self):
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            return self.base / "outside" if path == self.directory else original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", new=resolve), self.assertRaises(ValueError):
            storage.read_month(str(self.root), 2026, 4)

    def test_preview_filters_original_categories_without_touching_nfo(self):
        self.write_records([self.record()])
        nfo = self.write_nfo()
        before = nfo.read_bytes()
        preview = self.store.preview_nfo(self.request())
        self.assertEqual(1, preview["affected"])
        self.assertEqual(0, preview["unrecoverable"])
        self.assertEqual(64, len(preview["token"]))
        fragment = ET.fromstring(f"<movie>{preview['preview'][0]['after']}</movie>")
        self.assertEqual(["Field Recording", "New"], [node.text for node in fragment.findall("genre")])
        self.assertEqual(["Field Recording", "New"], [node.text for node in fragment.findall("tag")])
        self.assertEqual(before, nfo.read_bytes())
        self.assertEqual([], list(self.directory.glob("*.bak")))

    def test_stale_preview_rejects_changed_nfo_before_any_writes(self):
        self.write_records([self.record()])
        nfo = self.write_nfo()
        request = self.request()
        preview = self.store.preview_nfo(request)
        nfo.write_bytes(self.nfo_bytes(title="Edited after preview"))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.store.apply_nfo({**request, "token": preview["token"]})
        self.assertEqual(before, self.snapshot())

    def test_stale_preview_rejects_changed_rules_and_original_json_categories(self):
        self.write_records([self.record()])
        self.write_nfo()
        request = self.request()
        preview = self.store.preview_nfo(request)
        changed_rules = copy.deepcopy(request)
        changed_rules["settings"]["categories"][0]["checked"] = True
        with self.assertRaises(ValueError):
            self.store.apply_nfo({**changed_rules, "token": preview["token"]})
        self.write_records([self.record(original_tags=["Landscape"])])
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.store.apply_nfo({**request, "token": preview["token"]})
        self.assertEqual(before, self.snapshot())

    def test_apply_preserves_non_category_fields_attributes_comments_and_source_json(self):
        record_path = self.write_records([self.record()])
        original_json = record_path.read_bytes()
        nfo = self.write_nfo()
        original_nfo = nfo.read_bytes()
        before = storage.xml_tree(nfo)
        non_category_fields = [ET.tostring(node) for node in before if node.tag not in ("tag", "genre")]
        result = self.apply_preview(self.request())
        after = storage.xml_tree(nfo)
        self.assertEqual({"updated": 1, "backups": 1}, result)
        self.assertEqual(before.attrib, after.attrib)
        self.assertEqual(non_category_fields, [ET.tostring(node) for node in after if node.tag not in ("tag", "genre")])
        self.assertEqual(original_json, record_path.read_bytes())
        self.assertEqual(original_nfo, Path(str(nfo) + ".bak").read_bytes())
        self.assertEqual(["Field Recording", "New"], [node.text for node in after.findall("genre")])
        self.assertEqual(["Field Recording", "New"], [node.text for node in after.findall("tag")])
        self.assertEqual(0, self.store.preview_nfo(self.request())["affected"])

    def test_existing_backup_is_preserved_and_each_apply_has_a_distinct_backup(self):
        self.write_records([self.record()])
        nfo = self.write_nfo()
        existing = Path(str(nfo) + ".bak")
        existing.write_bytes(b"An older backup that must remain untouched")
        original_nfo = nfo.read_bytes()
        result = self.apply_preview(self.request())
        backups = list(self.directory.glob("*.bak"))
        self.assertEqual(1, result["backups"])
        self.assertEqual(2, len(backups))
        self.assertEqual(b"An older backup that must remain untouched", existing.read_bytes())
        self.assertEqual(original_nfo, next(path for path in backups if path != existing).read_bytes())

    def test_backup_names_do_not_collide_even_when_clock_does_not_advance(self):
        self.write_records([self.record()])
        nfo = self.write_nfo()
        originals = []
        for title in ("First original", "Second original", "Third original"):
            nfo.write_bytes(self.nfo_bytes(title=title))
            originals.append(nfo.read_bytes())
            self.apply_preview(self.request())
        backups = list(self.directory.glob("*.bak"))
        self.assertEqual(3, len(backups), "A same-clock backup must receive a fresh filename")
        self.assertCountEqual(originals, [path.read_bytes() for path in backups])

    def test_nfo_selected_scope_leaves_unselected_files_unchanged(self):
        self.write_records([self.record(), self.record("Harbor Walk")])
        selected_nfo = self.write_nfo()
        other_nfo = self.write_nfo("Harbor Walk")
        other_bytes = other_nfo.read_bytes()
        items, _ = storage.read_month(str(self.root), 2026, 4)
        selected_id = next(item["_entry_id"] for item in items if item["title_fs"] == "River Study")
        self.assertEqual({"updated": 1, "backups": 1}, self.apply_preview(self.request(ids=[selected_id])))
        self.assertEqual(other_bytes, other_nfo.read_bytes())
        self.assertTrue(Path(str(selected_nfo) + ".bak").exists())
        self.assertFalse(Path(str(other_nfo) + ".bak").exists())
        with self.assertRaises(ValueError):
            self.store.preview_nfo(self.request(ids=[]))

    def test_nfo_both_fields_share_selection_even_with_legacy_switches(self):
        self.write_records([self.record()])
        nfo = self.write_nfo()
        request = self.request(backup=False)
        request["settings"].update(writeTags=False, writeGenres=False)
        self.assertEqual({"updated": 1, "backups": 0}, self.apply_preview(request))
        node = storage.xml_tree(nfo)
        for field in ("tag", "genre"):
            self.assertEqual(["Field Recording", "New"], [x.text for x in node.findall(field)])
        self.assertEqual("12", node.findtext("runtime"))
        for category in request["settings"]["categories"]:
            category["checked"] = False
        self.apply_preview(request)
        node = storage.xml_tree(nfo)
        self.assertEqual([], node.findall("tag") + node.findall("genre"))

    def test_nfo_only_records_report_that_original_categories_are_unavailable(self):
        self.write_nfo(tags=("Archive", "Landscape"))
        preview = self.store.preview_nfo(self.request())
        self.assertEqual(1, preview["unrecoverable"])
        self.assertEqual(1, preview["affected"])
        result = storage.library_entries(str(self.root), 2026, 4, self.settings)
        self.assertFalse(result["entries"][0]["originalCategoriesAvailable"])
        self.apply_preview(self.request())
        node = storage.xml_tree(self.directory / "River Study.nfo")
        self.assertEqual(["Landscape"], [field.text for field in node.findall("tag")])

    def test_invalid_existing_settings_are_reported_and_not_overwritten(self):
        self.state_directory.mkdir()
        path = self.state_directory / "settings.json"
        original = b"{ invalid saved configuration"
        path.write_bytes(original)
        instance = storage.Storage(self.state_directory)
        self.assertTrue(instance.error)
        self.assertEqual(original, path.read_bytes())
        self.assertEqual("exclude", instance.settings["unseenDefault"])


class ProxySettingsTests(unittest.TestCase):
    """Proxy switch semantics: validation, URL normalisation and env publication."""

    def test_disabled_or_blank_means_no_proxy(self):
        self.assertIsNone(storage.proxy_from_settings({"proxyEnabled": False, "proxyUrl": "http://h:1"}))
        self.assertIsNone(storage.proxy_from_settings({"proxyEnabled": True, "proxyUrl": "  "}))
        self.assertIsNone(storage.proxy_from_settings({}))

    def test_url_normalisation_and_schemes(self):
        url = storage.proxy_from_settings({"proxyEnabled": True, "proxyUrl": "http://Clash:bl9a2S5W@192.168.11.2:7893"})
        self.assertEqual(url, "http://Clash:bl9a2S5W@192.168.11.2:7893")
        self.assertEqual(storage.proxy_from_settings({"proxyEnabled": True, "proxyUrl": "192.168.11.2:7893"}),
                         "http://192.168.11.2:7893")
        self.assertEqual(storage.proxy_from_settings({"proxyEnabled": True, "proxyUrl": "socks5://10.0.0.1:1080"}),
                         "socks5://10.0.0.1:1080")

    def test_invalid_urls_rejected(self):
        for value in ("ftp://h:21", "http://", "http://host", "://x:1", "javascript:alert(1)"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    storage.proxy_from_settings({"proxyEnabled": True, "proxyUrl": value})

    def test_mask_proxy_hides_credentials(self):
        self.assertEqual(storage.mask_proxy("http://Clash:bl9a2S5W@192.168.11.2:7893"),
                         "http://***@192.168.11.2:7893")
        self.assertEqual(storage.mask_proxy("http://192.168.11.2:7893"), "http://192.168.11.2:7893")
        self.assertEqual(storage.mask_proxy(""), "")

    def test_validate_settings_requires_url_when_enabled(self):
        with self.assertRaises(ValueError):
            storage.validate_settings({"proxyEnabled": True, "proxyUrl": ""})
        with self.assertRaises(ValueError):
            storage.validate_settings({"proxyEnabled": True, "proxyUrl": "not a url:;;"})
        result = storage.validate_settings({"proxyEnabled": True, "proxyUrl": "http://h:1"})
        self.assertEqual(result["proxyUrl"], "http://h:1")
        # 关闭时保留已填地址，方便再次启用。
        result = storage.validate_settings({"proxyEnabled": False, "proxyUrl": "http://h:1"})
        self.assertEqual(result["proxyUrl"], "http://h:1")

    def test_validate_settings_rejects_non_boolean_switch(self):
        with self.assertRaises(ValueError):
            storage.validate_settings({"proxyEnabled": "yes", "proxyUrl": "http://h:1"})

    def test_playwright_proxy_splits_auth_and_bypass(self):
        option = storage.playwright_proxy("http://Clash:bl9a2S5W@192.168.11.2:7893")
        self.assertEqual(option["server"], "http://192.168.11.2:7893")
        self.assertEqual(option["username"], "Clash")
        self.assertEqual(option["password"], "bl9a2S5W")
        self.assertIn("127.0.0.1", option["bypass"])
        plain = storage.playwright_proxy("socks5://10.0.0.1:1080")
        self.assertEqual(plain, {"server": "socks5://10.0.0.1:1080", "bypass": plain["bypass"]})
        self.assertNotIn("username", plain)

    def test_configure_proxy_env_sets_and_clears(self):
        keep = {k: v for k, v in os.environ.items()}
        try:
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "MEDIA_PROXY",
                         "http_proxy", "https_proxy", "MEDIA_PROXY_BYPASS"):
                os.environ.pop(name, None)
            url = storage.configure_proxy_env({"proxyEnabled": True, "proxyUrl": "http://p:8080"})
            self.assertEqual(url, "http://p:8080")
            self.assertEqual(os.environ["HTTPS_PROXY"], "http://p:8080")
            self.assertEqual(os.environ["https_proxy"], "http://p:8080")
            self.assertEqual(os.environ["MEDIA_PROXY"], "http://p:8080")
            self.assertIn("127.0.0.1", os.environ["NO_PROXY"])
            storage.configure_proxy_env({"proxyEnabled": False, "proxyUrl": "http://p:8080"})
            self.assertNotIn("HTTPS_PROXY", os.environ)
            self.assertNotIn("MEDIA_PROXY", os.environ)
        finally:
            os.environ.clear()
            os.environ.update(keep)

    def test_configure_proxy_env_removes_stale_values_on_enable(self):
        keep = {name: os.environ.get(name) for name in ("HTTP_PROXY", "http_proxy")}
        try:
            os.environ["http_proxy"] = "http://stale:1"
            storage.configure_proxy_env({"proxyEnabled": True, "proxyUrl": "http://new:2"})
            self.assertEqual(os.environ["http_proxy"], "http://new:2")
            self.assertEqual(os.environ["HTTP_PROXY"], "http://new:2")
        finally:
            for name, value in keep.items():
                os.environ.pop(name, None)
                if value is not None:
                    os.environ[name] = value


class BrowserInstallHintTests(unittest.TestCase):
    def test_hint_matches_platform_runtime(self):
        import unittest.mock as mock
        import media_storage as st
        with mock.patch.object(st.os, "name", "posix"):
            hint = st.browser_install_hint()
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH", hint)
        self.assertIn("playwright install chromium", hint)
        self.assertIn(".venv/bin/python", hint)
        with mock.patch.object(st.os, "name", "nt"):
            hint = st.browser_install_hint()
        self.assertIn("ms-playwright", hint)
        self.assertIn("playwright install chromium", hint)
        self.assertIn("Scripts", hint)  # Windows 用 Scripts 而不是 bin


class BrowserDiscoveryTests(unittest.TestCase):
    """Project bundle wins over HOME caches; detection covers linux and windows layouts."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app_root = self.root / "app"
        self.bundle = self.app_root / "ms-playwright"
        self.fake_home = self.root / "home"
        (self.fake_home / ".cache" / "ms-playwright").mkdir(parents=True)
        self.app_root.mkdir(parents=True, exist_ok=True)
        self.env = patch.dict(os.environ, {"HOME": str(self.fake_home), "USERPROFILE": str(self.fake_home)}, clear=True)
        self.paths = patch.object(storage, "APP_ROOT", self.app_root)

    def tearDown(self):
        self.paths.stop(); self.env.stop(); self.temp.cleanup()

    def _start(self):
        self.env.start(); self.paths.start()

    def _binary(self, directory, name="chrome"):
        directory.mkdir(parents=True, exist_ok=True)
        binary = directory / name
        binary.write_bytes(b"#!/bin/sh\n")
        binary.chmod(0o755)
        return binary

    def test_project_bundle_takes_priority(self):
        self._start()
        bundle_bin = self._binary(self.bundle / "chromium-1248" / "chrome-linux64")
        self._binary(self.fake_home / ".cache" / "ms-playwright" / "chromium-1248" / "chrome-linux64")
        self.assertEqual(storage.find_browser_executable(), bundle_bin)
        self.assertEqual(storage.configure_browser_env(), self.bundle.resolve())
        self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(self.bundle.resolve()))

    def test_headless_shell_and_windows_layouts_detected(self):
        self._start()
        expected = self._binary(self.bundle / "chromium_headless_shell-1248" / "chrome-headless-shell-linux64",
                                name="chrome-headless-shell")
        self.assertEqual(storage.find_browser_executable(), expected)
        # 换一套只有 Windows 布局的目录
        import shutil as _shutil
        _shutil.rmtree(self.bundle)
        expected = self._binary(self.bundle / "chromium-1248" / "chrome-win", name="chrome.exe")
        self.assertEqual(storage.find_browser_executable(), expected)

    def test_missing_or_empty_tree_is_not_ready(self):
        self._start()
        self.assertIsNone(storage.find_browser_executable())
        empty_dir = self.bundle / "chromium-1248" / "chrome-linux64"
        empty_dir.mkdir(parents=True)
        (empty_dir / "chrome").write_bytes(b"")
        self.assertIsNone(storage.find_browser_executable())
        self.assertIsNone(storage.configure_browser_env())
        self.assertNotIn("PLAYWRIGHT_BROWSERS_PATH", os.environ)

    def test_configured_path_used_when_bundle_missing(self):
        self._start()
        configured = self.root / "custom"
        expected = self._binary(configured / "chromium-1248" / "chrome-linux64")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(configured)
        self.assertEqual(storage.find_browser_executable(), expected)
        # 显式配置优先，configure 不改写它。
        self.assertIsNone(storage.configure_browser_env())
        self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(configured))

    def test_home_cache_found_without_bundle(self):
        self._start()
        expected = self._binary(self.fake_home / ".cache" / "ms-playwright" / "chromium-1248" / "chrome-linux64")
        self.assertEqual(storage.find_browser_executable(), expected)
        self.assertIsNone(storage.configure_browser_env())


if __name__ == "__main__":
    unittest.main()
