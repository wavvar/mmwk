from pathlib import Path
import unittest
from unittest import mock

import downloads.generate_module_pdfs as module_pdfs


class CoverMetaLinesTest(unittest.TestCase):
    def test_cover_meta_lines_for_english(self) -> None:
        self.assertEqual(
            module_pdfs.cover_meta_lines("en", "1.0.2", "2026-04-09"),
            ["Version: 1.0.2", "Updated: 2026-04-09"],
        )

    def test_cover_meta_lines_for_chinese(self) -> None:
        self.assertEqual(
            module_pdfs.cover_meta_lines("zh-cn", "1.0.2", "2026-04-09"),
            ["版本：1.0.2", "更新时间：2026-04-09"],
        )


class ParseArgsTest(unittest.TestCase):
    def test_parse_args_reads_required_release_metadata(self) -> None:
        args = module_pdfs.parse_args(
            [
                "--display-version",
                "1.0.2",
                "--built-date",
                "2026-04-09",
                "--out-dir",
                "dist/release/pdfs",
            ]
        )

        self.assertEqual(args.display_version, "1.0.2")
        self.assertEqual(args.built_date, "2026-04-09")
        self.assertEqual(args.out_dir, Path("dist/release/pdfs"))


class DisplayPathTest(unittest.TestCase):
    def test_display_path_falls_back_to_absolute_path(self) -> None:
        external = Path("/tmp/mmwk-release-assets/demo.pdf")
        self.assertEqual(module_pdfs.display_path(external), str(external))


class RegisterFontsTest(unittest.TestCase):
    def test_register_fonts_uses_reportlab_cid_font_name_for_fallback(self) -> None:
        with mock.patch.object(module_pdfs.Path, "exists", return_value=False):
            body_font, bold_font = module_pdfs.register_fonts("zh-cn")

        self.assertEqual(body_font, module_pdfs.ZH_FONT_FALLBACK)
        self.assertEqual(bold_font, module_pdfs.ZH_FONT_FALLBACK)
