"""
read and write to google sheets
"""

import httplib2
import os
import argparse
from pprint import pprint

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage


_SCOPES = ['https://www.googleapis.com/auth/drive']


class GSheetManager(object):
    """
    Some limited functionality for managing google drive and updating google sheets
    """
    _FIELDS = "nextPageToken, incompleteSearch, files(id, name)"

    def __init__(self, credential_path=None, reset_creds=False, app_name='Test',
                 verbose=False, debug=False, secret_file=None, run_flow_flags=None,
                 **kwargs):
        """
        Based on python quickstart documentation at
        https://developers.google.com/sheets/api/quickstart/python


        Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        cred_path: if None then default to ~/.credentials
        args: an object with attributed

        Returns:
            Credentials, the obtained credential.
        """
        self.debug = debug
        self.verbose = verbose or debug

        if credential_path is None:
            home_dir = os.path.expanduser('~')
            credential_dir = os.path.join(home_dir, '.credentials')
            if not os.path.exists(credential_dir):
                os.makedirs(credential_dir)
            credential_path = os.path.join(credential_dir, 'googleapis.com-python.json')

        store = Storage(credential_path)
        credentials = store.get()
        if reset_creds or not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(secret_file, _SCOPES)
            flow.user_agent = app_name
            credentials = tools.run_flow(flow, store, run_flow_flags)

            if self.verbose:
                print('Storing credentials to ' + credential_path)
        self._credentials = credentials

    @staticmethod
    def get_service(name, version, credentials):
        http = credentials.authorize(httplib2.Http())
        service = discovery.build(name, version, http=http)
        return service

    @classmethod
    def get_drive_service(cls, credentials):
        return cls.get_service('drive', 'v3', credentials)

    @classmethod
    def get_sheets_service(cls, credentials):
        return cls.get_service('sheets', 'v4', credentials)

    def find(self, name_contains=None, name_is=None, max_to_return=100, next_page_token=None,
             mime_type_contains=None, fields=None, parent_id=None, order_by=None):
        """
        returns: see https://developers.google.com/drive/v3/reference/files/list
        """
        if name_contains is not None and name_is is not None:
            raise ValueError("name_contains and name_is cannot bot be not None")

        query = []
        if parent_id is not None:
            query.append("'{}' in parents".format(parent_id))
        if mime_type_contains is not None:
            query.append("mimeType contains '{}'".format(mime_type_contains))
        if name_contains is not None:
            query.append("name contains '{}'".format(name_contains))
        elif name_is is not None:
            query.append("name = '{}'".format(name_is))

        service = self.get_drive_service(self._credentials)

        return service.files().list(
            q=" and ".join(query),
            corpora="user",
            pageSize=max_to_return,
            orderBy=order_by,
            pageToken=next_page_token,
            fields=fields).execute()

    def _move_file(self, file_id, folder_id):
        service = self.get_drive_service(self._credentials)

        # Retrieve the existing parents to remove
        _file = service.files().get(fileId=file_id,
                                    fields='parents').execute()
        previous_parents = ",".join(_file.get('parents'))
        # Move the file to the new folder
        return service.files().update(fileId=file_id,
                                      addParents=folder_id,
                                      removeParents=previous_parents,
                                      fields='id, parents').execute()

    def find_path(self, path):
        """
        find the requested path starting at the root

        path: list of folder names

        return: the list of ids for folders and the id of the final file/folder
        raises: FileNotFoundError is the path does not exist
        """
        assert isinstance(path, (tuple, list))

        path_ids = []
        # id, name
        parent = ('root', 'root')
        for name in path[:-1]:
            resp = self.find(name_is=name, parent_id=parent[0],
                             mime_type_contains='folder')
            if self.verbose:
                print(resp)
            if len(resp['files']) == 0:
                raise FileNotFoundError("Could not find folder '{}' in '{}'".format(name, parent[1]))
            path_ids.append((name, resp['files'][0]['id']))
            parent = (path_ids[-1][1], name)

        # find the last item in the path
        resp = self.find(name_is=path[-1], parent_id=parent[0])
        if self.verbose:
            print(resp)
        if len(resp['files']) == 0:
            raise FileNotFoundError("Could not find final item '{}' in '{}'".format(path[-1], parent[1]))

        path_ids.append((path[-1], resp['files'][0]['id']))
        return tuple(path_ids)

    def sort(self, sheet_id, subsheet_id, sort_cols, start_col_idx, start_row_idx,
             end_col_idx=None, end_row_idx=None):
        """
        all indices are zero based

        sort_cols: list of tuples of (sort_col_idx, "asc"|"desc"), or just a list of sort_col_idx
          former then sort defaults to asc
        """
        sort_specs = ([{'dimensionIndex': col, 'sortOrder': ordering} for col, ordering in sort_cols]
                      if isinstance(sort_cols[0], tuple) else
                      [{'dimensionIndex': col, 'sortOrder': "DESCENDING"} for col in sort_cols])

        sort_request = {'sortRange': {
            'range': {
                'sheet_id': subsheet_id,
                'startRowIndex': start_row_idx,
                'startColumnIndex': start_col_idx,
                'endRowIndex': end_row_idx,
                'endColumnIndex': end_col_idx
            },
            'sortSpecs': sort_specs
        }}

        service = self.get_sheets_service(self._credentials)
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={'requests': [sort_request]}
        ).execute()
        return response

    def set_dimension_visibility(self, sheet_id, ranges, visible, subsheet_id, dim='COLS'):
        """
        Each requested range's visibility will be set to 'visible'

        subsheet_id: can be retrieved using get_subsheet_id
        dim: COLS or ROWS
        ranges: Zero indexed list of ints or tuples. For tuples, they must each be of length 2 indicated the bounds
          of the range. All rows/columns inclusive of the low and exclusive of the high will be updated.
          If a range is an int, just that row/column will be updated
        """
        # TODO: add tests
        assert isinstance(visible, bool)
        assert subsheet_id is not None
        assert dim in ('COLS', 'ROWS')

        request_body = {'requests': []}
        for _range in ranges:
            request = {
                'updateDimensionProperties': {
                    "range": {
                        "sheetId": subsheet_id,
                        "dimension": 'COLUMNS' if dim == 'COLS' else 'ROWS',
                        "startIndex": _range if isinstance(_range, int) else _range[0],
                        "endIndex": (_range + 1) if isinstance(_range, int) else _range[1],
                    },
                    "properties": {
                        "hiddenByUser": not visible,
                    },
                    "fields": 'hiddenByUser',
                }
            }
            request_body['requests'].append(request)

        service = self.get_sheets_service(self._credentials)
        response = service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body=request_body
        ).execute()
        return response

    def create_sheet(self, title, subsheet_titles=None, parent_id=None):
        """
        returns: sheet id
        """
        new_sheet = {
            'properties': {"title": title}
        }

        if subsheet_titles is not None:
            new_sheet['sheets'] = [{'properties': {'title': ss_title}}
                                   for ss_title in subsheet_titles]

        service = self.get_sheets_service(self._credentials)

        request = service.spreadsheets().create(body=new_sheet)
        response = request.execute()
        sheet_id = response['spreadsheetId']
        if parent_id is not None:
            response = self._move_file(sheet_id, parent_id)
        return sheet_id

    def get_subsheets_info(self, sheet_id):
        """ return a list of tuples of (subsheet_id, subsheet_title) """
        # TODO: need a test for this
        service = self.get_sheets_service(self._credentials)
        request = service.spreadsheets().get(spreadsheetId=sheet_id,
                                             includeGridData=False)
        response = request.execute()
        subsheets = tuple((sheet_info['properties']['sheetId'],
                           sheet_info['properties']['title'])
                          for sheet_info in response['sheets'])
        return subsheets

    def get_subsheet_id(self, sheet_id, subsheet_title):
        """
        subsheet_title: if None the get the id of the first subsheet

        return the ID of the subsheet, or None if there is no
        subsheet with the requested title
        """
        # TODO: need a test for this
        for ss_id, ss_title in self.get_subsheets_info(sheet_id):
            if ss_title == subsheet_title:
                return ss_id
        return None

    def create_subsheet(self, sheet_id, subsheet_title):
        """ return the subsheet ID """
        # TODO: need a test for this
        request_body = {'requests': [{
            'addSheet': {
                'properties': {
                    'title': subsheet_title
                }
            }
        }]}
        service = self.get_sheets_service(self._credentials)
        request = service.spreadsheets().batchUpdate(spreadsheetId=sheet_id,
                                                     body=request_body)
        response = request.execute()
        return response['replies'][0]['addSheet']['properties']['sheetId']

    def get_sheet_data(self, sheet_id, _range, major_dim="ROWS", values_only=False):
        """
        values_only: if True just return the list of lists with values found on the sheet

        _range: The range of cells to get data for, in A1 notation
        """
        assert major_dim in ('ROWS', 'COLUMNS')
        service = self.get_sheets_service(self._credentials)
        request = service.spreadsheets().values().get(spreadsheetId=sheet_id,
                                                      range=_range,
                                                      majorDimension=major_dim)
        response = request.execute()
        if values_only:
            response = response.get('values', [])
        return response

    def update_sheet(self, sheet_id, _range, data, major_dim="ROWS", append=False, respond=False):
        assert major_dim in ('ROWS', 'COLUMNS')
        if self.verbose:
            print("{} sheet '{}' at range \"{}\" with {} rows."
                  .format('Appending to' if append else 'Updating', sheet_id, _range, len(data)))
            if self.debug:
                pprint(data)
        body = {'range': _range,
                'majorDimension': major_dim,
                'values': data}

        service = self.get_sheets_service(self._credentials)

        kwargs = {'spreadsheetId': sheet_id,
                  'valueInputOption': "USER_ENTERED",
                  'range': _range,
                  'includeValuesInResponse': respond,
                  'body': body}

        request = (service.spreadsheets().values().append(**kwargs)
                   if append else
                   service.spreadsheets().values().update(**kwargs))
        response = request.execute()
        return response


BASE_ARGPARSER = argparse.ArgumentParser(parents=[tools.argparser], add_help=False)


def _update_sheet(manager, sheet_id, _range, csv_str, major_dim, append, respond):
    """ parser the csv string and then call the manager """
    data = []
    for row in csv_str.split("\n"):
        data.append([value.strip() for value in row.strip().split(",")])
    return manager.update_sheet(sheet_id, _range, data,
                                major_dim=major_dim, append=append, respond=respond)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(parents=[BASE_ARGPARSER])
    parser.add_argument('--app_name', default="TEST", help="default = TEST")
    parser.add_argument('--reset_creds', default=False, action="store_true",
                        help="Reset all previously granted credentials")
    parser.add_argument('--verbose', default=False, action="store_true")
    parser.add_argument('--secret_file',
                        help=("Project credentials file. Instructions on creation found at "
                              "https://developers.google.com/sheets/api/quickstart/python"))

    subparsers = parser.add_subparsers(title="cmd")

    # list sheets
    subparser = subparsers.add_parser(
        "find", description="find stuff on your drive")
    subparser.add_argument('name', nargs='?', help="Name contains ...")
    subparser.add_argument('--order_by_name', default=False, action="store_true")
    subparser.add_argument('--parent_id', help="the parent folder id")
    subparser.add_argument('--mime', help="mime type contains...")
    subparser.set_defaults(
        func=(lambda manager, args:
              manager.find(parent_id=args.parent_id, name_contains=args.name,
                           mime_type_contains=args.mime,
                           order_by='name' if args.order_by_name else None)))

    # find path
    subparser = subparsers.add_parser(
        "find_path", description="find path")
    subparser.add_argument('path', help="Path to find. Folder names should be seperated by '/'")
    subparser.set_defaults(
        func=(lambda manager, args:
              manager.find_path(args.path.split("/"))))

    subparser = subparsers.add_parser(
        "create", description="create sheet")
    subparser.add_argument('sheet_name', help="Name of new sheet")
    subparser.add_argument('--parent_id', help="the folder id to save the sheet to")
    subparser.set_defaults(
        func=(lambda manager, args:
              manager.create_sheet(args.sheet_name, parent_id=args.parent_id)))

    subparser = subparsers.add_parser(
        "get", description="get sheet data")
    subparser.add_argument('sheet_id')
    subparser.add_argument('range', help="Sheet range in A1 notation")
    subparser.add_argument('--major_dim', choices=('ROWS', 'COLUMNS'), default='ROWS',
                           help="Major dimension to use in retrieving data. Default=ROWS")
    subparser.add_argument('--values_only', action="store_true", default=False)
    subparser.set_defaults(
        func=(lambda manager, args:
              manager.get_sheet_data(args.sheet_id, args.range,
                                     values_only=args.values_only, major_dim=args.major_dim)))

    subparser = subparsers.add_parser(
        "update", description="update sheet data")
    subparser.add_argument('--major_dim', choices=('ROWS', 'COLUMNS'), default='ROWS',
                           help="Major dimension to use in retrieving data. Default=ROWS")
    subparser.add_argument('--append', default=False, action="store_true",
                           help="Append data to the table defined by the range")
    subparser.add_argument('--respond', default=False, action="store_true",
                           help="Request a response with the new values. Default success has no response")
    subparser.add_argument('sheet_id')
    subparser.add_argument('range', help="Sheet range in A1 notation")
    subparser.add_argument('values', help="csv data as a single string")
    subparser.set_defaults(
        func=(lambda manager, args:
              _update_sheet(manager, args.sheet_id, args.range, args.values, args.major_dim,
                            args.append, args.respond)))

    args = parser.parse_args()
    manager = GSheetManager(run_flow_flags=args, **vars(args))

    if not hasattr(args, 'func'):
        parser.error("choose a command to execute")
    pprint(args.func(manager, args))
