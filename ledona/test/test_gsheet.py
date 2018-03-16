import json
import os
import unittest
from unittest.mock import patch
from apiclient.http import HttpMockSequence
from apiclient.discovery import build

from ..gsheet import GSheetManager


_CREATE_RESPONSE = json.dumps(
    {"properties": {"autoRecalc": "ON_CHANGE",
                    "defaultFormat": {"backgroundColor": {"blue": 1,
                                                          "green": 1,
                                                          "red": 1},
                                      "padding": {"bottom": 2,
                                                  "left": 3,
                                                  "right": 3,
                                                  "top": 2},
                                      "textFormat": {"bold": False,
                                                     "fontFamily": "arial,sans,sans-serif",
                                                     "fontSize": 10,
                                                     "foregroundColor": {},
                                                     "italic": False,
                                                     "strikethrough": False,
                                                     "underline": False},
                                      "verticalAlignment": "BOTTOM",
                                      "wrapStrategy": "OVERFLOW_CELL"},
                    "locale": "en_US",
                    "timeZone": "Etc/GMT",
                    "title": "%s"},
     "sheets": [{"properties": {"gridProperties": {"columnCount": 26,
                                                   "rowCount": 1000},
                                "index": 0,
                                "sheetId": 0,
                                "sheetType": "GRID",
                                "title": "Sheet1"}}],
     "spreadsheetId": "%s",
     "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/1n6KalojT91K-IX6I9GAIpCokXFsQ1qa0ajdWcSX-_ac/edit"}
)

_MOVE_RESPONSE = json.dumps(
    {"id": "%s",
     "parents": ["0BxSHVIWmmaymNmZjWGFqZnBBY28"]}
)


_SERVICE_VERSIONS = {'sheets': 'v4',
                     'drive': 'v3'}


def create_service_mock(service, http):
    # needed to establish the cache
    api_key = 'your_api_key'

    def get_func(credentials):
        return build(service, _SERVICE_VERSIONS[service], http=http, developerKey=api_key,
                     cache_discovery=False)
    return get_func


class TestGSheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(__file__), 'drive_discovery.json'), 'r') as dd:
            cls._drive_discovery = dd.read()
        with open(os.path.join(os.path.dirname(__file__), 'sheets_discovery.json'), 'r') as sd:
            cls._sheets_discovery = sd.read()

    def test_create_sheet(self):
        title = "xyz"
        _id = '123'

        http = HttpMockSequence([
            ({'status': '200'}, self._sheets_discovery),
            ({'status': '200'}, _CREATE_RESPONSE % (title, _id)),
            ({'status': '200'}, _MOVE_RESPONSE % _id)])
        gsheet = GSheetManager()
        with patch.object(gsheet, 'get_sheets_service', create_service_mock('sheets', http)):
            sheet_id = gsheet.create_sheet(title)
        self.assertEqual(_id, sheet_id)

    def test_find_sheets(self):
        raise NotImplementedError()

    def test_find_folders(self):
        raise NotImplementedError()

    def test_find_path(self):
        raise NotImplementedError()
