import unittest
from updater import is_newer_version, parse_version, select_platform_asset, UpdateReleaseInfo


class TestUpdater(unittest.TestCase):
    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("v12.0"), (12, 0))
        self.assertEqual(parse_version("12.1.4"), (12, 1, 4))
        self.assertEqual(parse_version("v1.0.0-rc1"), (1, 0, 0, 1))
        self.assertEqual(parse_version(""), (0,))

    def test_is_newer_version(self) -> None:
        # Strettamente più recente
        self.assertTrue(is_newer_version("v12.1", "v12.0"))
        self.assertTrue(is_newer_version("v13.0", "v12.0"))
        self.assertTrue(is_newer_version("12.0.1", "v12.0"))
        self.assertTrue(is_newer_version("v12.0.1", "12.0.0"))

        # Uguale o precedente
        self.assertFalse(is_newer_version("v12.0", "v12.0"))
        self.assertFalse(is_newer_version("v11.9", "v12.0"))
        self.assertFalse(is_newer_version("12.0.0", "v12.0"))

    def test_release_info(self) -> None:
        info = UpdateReleaseInfo(
            version="v12.1",
            tag_name="v12.1",
            title="George v12.1",
            release_notes="- Nuove feature\n- Bug fix",
            html_url="https://github.com/mazzoccantelorenzo/george/releases/tag/v12.1",
            download_url="https://github.com/mazzoccantelorenzo/george/releases/download/v12.1/George.zip",
            asset_name="George.zip",
            asset_size=1024 * 1024 * 15,
        )
        self.assertEqual(info.version, "v12.1")
        self.assertEqual(info.asset_name, "George.zip")

    def test_select_platform_asset_windows_and_mac(self) -> None:
        assets: list[dict[str, object]] = [
            {
                "name": "George-Installer.dmg",
                "browser_download_url": "https://example.com/George-Installer.dmg",
                "size": 50000,
            },
            {
                "name": "George.zip",
                "browser_download_url": "https://example.com/George.zip",
                "size": 45000,
            },
            {
                "name": "George-Windows.zip",
                "browser_download_url": "https://example.com/George-Windows.zip",
                "size": 48000,
            },
        ]

        # Su Windows deve scegliere George-Windows.zip e NON George.zip (che è per Mac)
        win_url, win_name, win_size = select_platform_asset(assets, platform="win32")
        self.assertEqual(win_name, "George-Windows.zip")
        self.assertEqual(win_url, "https://example.com/George-Windows.zip")
        self.assertEqual(win_size, 48000)

        # Su macOS deve scegliere George.zip e NON George-Windows.zip
        mac_url, mac_name, mac_size = select_platform_asset(assets, platform="darwin")
        self.assertEqual(mac_name, "George.zip")
        self.assertEqual(mac_url, "https://example.com/George.zip")
        self.assertEqual(mac_size, 45000)


if __name__ == "__main__":
    unittest.main()
