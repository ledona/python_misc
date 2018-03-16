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


_SCOPES = ['https://www.googleapis.com/auth/drive']


class GSheetManager(object):
    """
    Some limited functionality for managing google drive and updating google sheets
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

    def find(self, name_contains=None, name_is=None, max_to_return=100, next_page_token=None,
             mime_type_contains=None, fields=None, parent_id=None, order_by=None):
        """
        path: list of folder names
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

    args = parser.parse_args()
    manager = GSheetManager(**vars(args), run_flow_flags=args)

    if not hasattr(args, 'func'):
        parser.error("choose a command to execute")
    pprint.pprint(args.func(manager, args))
