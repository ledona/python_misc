"""
read and write to google sheets
"""

from __future__ import print_function
import httplib2
import os

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage


SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
                         'https://www.googleapis.com/auth/drive.metadata.readonly']


class GSheetManager(object):
    """
    Some limited functionality to support writing to google sheets
    """

    def __init__(self, application_name, client_secret_file, args,
                 scopes=SCOPES, verbose=False, credential_path=None,
                 reset_creds=False):
        """
        Based on python quickstart documentation at
        https://developers.google.com/sheets/api/quickstart/python


        Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        cred_path - if None then default to ~/.credentials

        Returns:
            Credentials, the obtained credential.
        """
        self.verbose = verbose

        if credential_path is None:
            home_dir = os.path.expanduser('~')
            credential_dir = os.path.join(home_dir, '.credentials')
            if not os.path.exists(credential_dir):
                os.makedirs(credential_dir)
            credential_path = os.path.join(credential_dir,
                                           'sheets.googleapis.com-python-quickstart.json')

        store = Storage(credential_path)
        credentials = store.get()
        if reset_creds or not credentials or credentials.invalid:
            flow = client.flow_from_clientsecrets(client_secret_file, scopes)
            flow.user_agent = application_name
            credentials = tools.run_flow(flow, store, args)

            if verbose:
                print('Storing credentials to ' + credential_path)
        self._credentials = credentials

    def find_sheets(self, name_starts_with=None, max_to_return=100, next_page_token=None):
        """
        Find sheets in google drive. Returns a dict with keys
        files - list of tuples of (name, id)
        complete - True if there are no other results
        next_page_token - token to use to get more results
        """

        query = ["mimeType = 'application/vnd.google-apps.spreadsheet'"]
        if name_starts_with is not None:
            query.append("name contains '{}'".format(name_starts_with))
        http = self._credentials.authorize(httplib2.Http())
        service = discovery.build('drive', 'v3', http=http)
        results = service.files().list(
            q=" ".join(query),
            corpora="user",
            pageSize=max_to_return,
            pageToken=next_page_token,
            fields="nextPageToken, incompleteSearch, files(id, name)").execute()

        return {'files': [(_f['name'], _f['id']) for _f in results['files']],
                'complete': not results['incompleteSearch'],
                'next_page_token': results.get('nextPageToken')}

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


def _list_sheets(manager, args):
    return manager.find_sheets(name_starts_with=args.sheet_name)


if __name__ == '__main__':
    import pprint
    import argparse
    parser = argparse.ArgumentParser(parents=[tools.argparser])
    parser.add_argument('--app_name', default="TEST", help="default = TEST")
    parser.add_argument('--reset_creds', default=False, action="store_true",
                        help="Reset all previously granted credentials")
    parser.add_argument('--verbose', default=False, action="store_true")
    parser.add_argument('secret_file',
                        help="Project credentials file. Instructions on creation found at https://developers.google.com/sheets/api/quickstart/python")

    subparsers = parser.add_subparsers(title="cmd")

    # Test command
    subparser_test = subparsers.add_parser(
        "test", description="Test to ensure credentials and access works")
    subparser_test.set_defaults(func=_run_test)

    # list sheets
    subparser_list = subparsers.add_parser(
        "list", description="list sheets")
    subparser_list.set_defaults(func=_list_sheets)
    subparser_list.add_argument('sheet_name', nargs='?', help="Name starts with")

    args = parser.parse_args()
    manager = GSheetManager(args.app_name, args.secret_file, args,
                            verbose=args.verbose, reset_creds=args.reset_creds)

    if not hasattr(args, 'func'):
        parser.error("choose a command to execute")

    pprint.pprint(args.func(manager, args))
