"""
read and write to google sheets
"""

import httplib2
import os
import argparse

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage


_SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive']


class GSheetManager(object):
    """
    Some limited functionality to support writing to google sheets
    """
    _FIELDS = "nextPageToken, incompleteSearch, files(id, name)"

    def __init__(self, credential_path=None, reset_creds=False, app_name='Test',
                 verbose=False, secret_file=None, run_flow_flags=None,
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
        self.verbose = verbose

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

    def _find(self, name_contains=None, name_is=None, max_to_return=100, next_page_token=None,
              mime_type=None, fields=None, parent_id=None, order_by=None):
        """
        path: list of folder names
        """
        if name_contains is not None and name_is is not None:
            raise ValueError("name_contains and name_is cannot bot be not None")

        query = []
        if parent_id is not None:
            query.append("'{}' in parents".format(parent_id))
        if mime_type is not None:
            query.append("mimeType = '{}'".format(mime_type))
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

    def find_sheets(self, order_by_name=False, **kwargs):
        """
        Find sheets in google drive. Returns a dict with keys
        files - list of tuples of (name, id)
        complete - True if there are no other results
        next_page_token - token to use to get more results
        """
        results = self._find(mime_type='application/vnd.google-apps.spreadsheet',
                             fields=self._FIELDS,
                             order_by='name' if order_by_name else None,
                             **kwargs)

        return {'files': [(_f['name'], _f['id']) for _f in results['files']],
                'complete': not results['incompleteSearch'],
                'next_page_token': results.get('nextPageToken')}

    def find_folders(self, order_by_name=False, **kwargs):
        """
        Find folders in google drive. Returns a dict with keys
        folders - list of tuples of (name, id)
        complete - True if there are no other results
        next_page_token - token to use to get more results
        """
        results = self._find(mime_type='application/vnd.google-apps.folder',
                             fields="nextPageToken, incompleteSearch, files(id, name)",
                             order_by='name' if order_by_name else None,
                             **kwargs)

        return {'folders': [(_f['name'], _f['id']) for _f in results['files']],
                'complete': not results['incompleteSearch'],
                'next_page_token': results.get('nextPageToken')}

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
        return the id of the last folder in the path

        path: list of folder names

        raises: FileNotFoundError is the path does not exist
        """
        # if verbose print search results for steps on the path
        raise NotImplementedError()

    def create_sheet(self, title, parent_id=None):
        """
        returns: sheet id
        """
        new_sheet = {
            'properties': {"title": title}
        }

        service = self.get_sheets_service(self._credentials)

        request = service.spreadsheets().create(body=new_sheet)
        response = request.execute()
        sheet_id = response['spreadsheetId']
        if parent_id is not None:
            response = self._move_file(sheet_id, parent_id)
        return sheet_id

    def test_sheets_access(self):
        """
        Shows basic usage of Sheets API.

        Creates a Sheets API service object and prints the names and majors of
        students in a sample spreadsheet:
        https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit
        """
        http = self._credentials.authorize(httplib2.Http())
        discoveryUrl = ('https://sheets.googleapis.com/$discovery/rest?'
                        'version=v4')
        service = discovery.build('sheets', 'v4', http=http,
                                  discoveryServiceUrl=discoveryUrl)

        spreadsheetId = '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
        rangeName = 'Class Data!A2:E'
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheetId, range=rangeName).execute()
        values = result.get('values', [])

        if self.verbose:
            if values:
                print('No data found.')
            else:
                print('Name, Major:')
                for row in values:
                    # Print columns A and E, which correspond to indices 0 and 4.
                    print('%s, %s' % (row[0], row[4]))

    def test_drive_access(self):
        http = self._credentials.authorize(httplib2.Http())
        service = discovery.build('drive', 'v3', http=http)

        results = service.files().list(
            pageSize=10, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])
        if self.verbose:
            if not items:
                print('No files found.')
            else:
                print('Files:')
                for item in items:
                    print('{0} ({1})'.format(item['name'], item['id']))


def _run_test(manager, args):
    try:
        manager.test_sheets_access()
        manager.test_drive_access()
    except Exception:
        print("\nTest Failed...")
        raise
    if args.verbose:
        print("\n")
    return("Success, all looks good")


BASE_ARGPARSER = argparse.ArgumentParser(parents=[tools.argparser], add_help=False)


if __name__ == '__main__':
    import pprint
    parser = argparse.ArgumentParser(parents=[BASE_ARGPARSER])
    parser.add_argument('--app_name', default="TEST", help="default = TEST")
    parser.add_argument('--reset_creds', default=False, action="store_true",
                        help="Reset all previously granted credentials")
    parser.add_argument('--verbose', default=False, action="store_true")
    parser.add_argument('--secret_file',
                        help="Project credentials file. Instructions on creation found at https://developers.google.com/sheets/api/quickstart/python")

    subparsers = parser.add_subparsers(title="cmd")

    # Test command
    subparser = subparsers.add_parser(
        "test", description="Test to ensure credentials and access works")
    subparser.set_defaults(func=_run_test)

    # list sheets
    subparser = subparsers.add_parser(
        "sheets", description="list sheets")
    subparser.add_argument('sheet_name', nargs='?', help="Sheet name contains ...")
    subparser.add_argument('--order_by_name', default=False, action="store_true")
    subparser.add_argument('--parent_id', help="the parent folder id")
    subparser.set_defaults(
        func=(lambda manager, args:
              manager.find_sheets(parent_id=args.parent_id, name_contains=args.sheet_name,
                                  order_by_name=args.order_by_name)))

    # list folders
    subparser = subparsers.add_parser(
        "folders", description="list folders")
    subparser.add_argument('parent_id', default="root", nargs='?', help="ID of the parent folder")
    subparser.add_argument('--order_by_name', default=False, action="store_true")
    subparser.set_defaults(
        func=(lambda manager, args:
              manager.find_folders(parent_id=args.parent_id, order_by_name=args.order_by_name)))

    # find path
    subparser = subparsers.add_parser(
        "path", description="find path")
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

    args = parser.parse_args()
    manager = GSheetManager(**vars(args))

    if not hasattr(args, 'func'):
        parser.error("choose a command to execute")
    pprint.pprint(args.func(manager, args))
