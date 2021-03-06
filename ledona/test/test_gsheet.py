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

_FIND_RESPONSE_DICT = {
    'files': [{'id': '1WjIrRBsfUMrwThsnWJFxnVEvssQp2aUDYAqx1vsLIt8',
               'kind': 'drive#file',
               'mimeType': 'application/vnd.google-apps.spreadsheet',
               'name': 'Fantasy Scoring Tests'},
              {'id': '1i7mfK5zNEXAlp943ccpVIPESKH9R3EYC',
               'kind': 'drive#file',
               'mimeType': 'application/vnd.google-apps.folder',
               'name': 'TEST'},
              {'id': '1G8BmlcBLBowUY5LOPCgIqL_u2J8Rw32QKPU6pUonHtQ',
               'kind': 'drive#file',
               'mimeType': 'application/vnd.google-apps.spreadsheet',
               'name': 'Knapsack Testing'},
              {'id': '1yUdMEAWEA8m3WqCdGX9ZNjxUacIw-6Y_Wt56QL7Ek3A',
               'kind': 'drive#file',
               'mimeType': 'application/vnd.google-apps.spreadsheet',
               'name': 'fantasy 2016-8 test'}],
    'incompleteSearch': False,
    'kind': 'drive#fileList'}

_FIND_RESPONSE = json.dumps(_FIND_RESPONSE_DICT)

_PATH_RESPONSES = [
    {'files': [{'id': '1',
                'kind': 'drive#file',
                'mimeType': 'application/vnd.google-apps.folder',
                'name': 't1'}],
     'incompleteSearch': False,
     'kind': 'drive#fileList'},
    {'files': [{'id': '2',
                'kind': 'drive#file',
                'mimeType': 'application/vnd.google-apps.folder',
                'name': 't2'}],
     'incompleteSearch': False,
     'kind': 'drive#fileList'},
    {'files': [{'id': '3',
                'kind': 'drive#file',
                'mimeType': 'application/vnd.google-apps.spreadsheet',
                'name': 'sheet'}],
     'incompleteSearch': False,
     'kind': 'drive#fileList'}
]

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

    def test_find(self):
        http = HttpMockSequence([
            ({'status': '200'}, self._drive_discovery),
            ({'status': '200'}, _FIND_RESPONSE)])
        gsheet = GSheetManager()
        with patch.object(gsheet, 'get_drive_service', create_service_mock('drive', http)):
            self.assertEqual(_FIND_RESPONSE_DICT, gsheet.find(name_contains='test'))

    @patch.object(GSheetManager, 'find')
    def test_find_path(self, mock_find):
        def find_side_effect(name_is=None, mime_type_contains=None, parent_id=None, **kwargs):
            self.assertIn(name_is, ('t1', 't2', 'sheet'))

            if name_is == 't1':
                self.assertEqual('root', parent_id)
                self.assertEqual('folder', mime_type_contains)
                return _PATH_RESPONSES[0]
            elif name_is == 't2':
                self.assertEqual('1', parent_id)
                self.assertEqual('folder', mime_type_contains)
                return _PATH_RESPONSES[1]
            else:
                # name_is == 'sheet'
                self.assertEqual('2', parent_id)
                return _PATH_RESPONSES[2]

        mock_find.side_effect = find_side_effect
        gsheet = GSheetManager()
        search_path = ['t1', 't2', 'sheet']
        path_ids = gsheet.find_path(search_path)
        self.assertEqual(tuple(zip(search_path, ('1', '2', '3'))), path_ids)

    def test_get_sheet_data(self):
        ref_dict = {'majorDimension': 'ROWS',
                    'range': 'TEST!A1:B2',
                    'values': [['Texas', 'Providence'], ['4', '0']]}
        http = HttpMockSequence([
            ({'status': '200'}, self._sheets_discovery),
            ({'status': '200'}, json.dumps(ref_dict))])
        gsheet = GSheetManager()
        with patch.object(gsheet, 'get_sheets_service', create_service_mock('sheets', http)):
            resp = gsheet.get_sheet_data('x', "TEST!A1:B2")
        self.assertEqual(ref_dict, resp)

    def test_update_sheet_data(self):
        sheet_id = 'xyz'
        ref_dict = {'spreadsheetId': sheet_id,
                    'updatedCells': 2,
                    'updatedColumns': 2,
                    'updatedRange': 'TEST!A1:B1',
                    'updatedRows': 1}
        http = HttpMockSequence([
            ({'status': '200'}, self._sheets_discovery),
            ({'status': '200'}, json.dumps(ref_dict))])
        gsheet = GSheetManager()
        with patch.object(gsheet, 'get_sheets_service', create_service_mock('sheets', http)):
            resp = gsheet.update_sheet(sheet_id, "TEST!A1:B2", ['2', '3'])
        self.assertEqual(ref_dict, resp)

    def test_append_sheet_data(self):
        sheet_id = 'xyz'
        ref_dict = {'spreadsheetId': sheet_id,
                    'updatedCells': 2,
                    'updatedColumns': 2,
                    'updatedRange': 'TEST!A3:B3',
                    'updatedRows': 1}
        http = HttpMockSequence([
            ({'status': '200'}, self._sheets_discovery),
            ({'status': '200'}, json.dumps(ref_dict))])
        gsheet = GSheetManager()
        with patch.object(gsheet, 'get_sheets_service', create_service_mock('sheets', http)):
            resp = gsheet.update_sheet(sheet_id, "TEST!A1:B2", ['2', '3'], append=True)
        self.assertEqual(ref_dict, resp)
