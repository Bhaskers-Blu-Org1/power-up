#!/usr/bin/env python
# Copyright 2018 IBM Corp.
#
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import nested_scopes, generators, division, absolute_import, \
    with_statement, print_function, unicode_literals

import argparse
import glob
import os
import re
from shutil import copy2, copytree, rmtree, Error

import lib.logger as logger
from lib.utilities import sub_proc_display, sub_proc_exec, heading1, rlinput, \
    get_url, get_dir, get_yesno, get_selection, get_file_path, get_src_path, bold
from lib.exception import UserException


def setup_source_file(name, src_glob, url='', alt_url='http://',
                      dest_dir=None):
    """Interactive selection of a source file and copy it to the /srv/<dest>
    directory. The source file can include file globs and can come from a URL
    or the local disk. Local disk searching starts in the
    /home directory and then expands to the entire file system if no matches
    found in any home directory. URLs must point to the directory with the file.
    Inputs:
        src_glob (str): Source file name to look for. Can include file globs
        dest (str) : destination directory. Will be created if necessary under
            /srv/
        url (str): url for the public web site where the file can be obtained.
            leave empty to prevent prompting for a public url option.
        alt_url (str): Alternate url where the file can be found. Usually this
            is an intranet web site.
        name (str): Name for the source. Used for prompts and dest dir (/srv/{name}).
    Returns:
        state (bool) : state is True if a file matching the src_name exists
            in the dest directory or was succesfully copied there. state is
            False if there is no file matching src_name in the dest directory
            OR if the attempt to copy a new file to the dest directory failed.
        src_path (str) : The path for the file found / chosen by the user. If
            only a single match is found it is used without choice and returned.
        dest_path (str)
    """
    state = False
    src_path = None
    dest_path = None
    log = logger.getlogger()
    name_src = get_name_dir(name)
    exists = glob.glob(f'/srv/{name_src}/**/{src_glob}', recursive=True)
    if exists:
        dest_path = exists[0]
        state = True
    ch, item = get_selection('Copy from URL\nSearch local Disk', 'U\nD', allow_none=True)
    if ch == 'U':
        if url:
            ch, item = get_selection('Public mirror.Alternate web site', 'P.A',
                                     'Select source: ', '.')
        if ch == 'P':
            _url = url
        else:
            _url = alt_url if alt_url else 'http://'
        rc = -9
        while _url is not None and rc != 0:
            _url = get_url(_url, fileglob=src_glob)
            if _url:
                dest_dir = f'/srv/{name_src}'
                if not os.path.exists(dest_dir):
                    os.mkdir(dest_dir)
                cmd = f'wget -r -l 1 -nH -np --cut-dirs=1 -P {dest_dir} {_url}'
                rc = sub_proc_display(cmd)
                if rc != 0:
                    log.error(f'Failed downloading {name} source to'
                              f' /srv/{name_src}/ directory. \n{rc}')
                else:
                    src_path = _url
                    dest_path = os.path.join(dest_dir, os.path.basename(_url))
                    state = True
    elif ch == 'D':
        src_path = get_src_path(src_glob)
        if src_path:
            dest_dir = f'/srv/{name_src}'
            if not os.path.exists(dest_dir):
                os.mkdir(dest_dir)
            try:
                copy2(src_path, dest_dir)
            except Error as err:
                log.debug(f'Failed copying {name} source file to /srv/{name_src}/ '
                          f'directory. \n{err}')
            else:
                log.info(f'Successfully installed {name} source file '
                         'into the POWER-Up software server.')
                dest_path = os.path.join(dest_dir, os.path.basename(src_path))
                state = True
    else:
        log.info(f'No {name.capitalize()} source file copied to POWER-Up '
                 'server directory')

    return src_path, dest_path, state


def get_name_dir(name):
    """Construct a reasonable directory name from a descriptive name. Replace
    spaces with dashes, convert to lower case and remove 'content' and 'Repository'
    if present.
    """
    return name.lower().replace(' ', '-').replace('-content', '')\
        .replace('-repository', '')


def powerup_file_from_disk(name, file_glob):
        log = logger.getlogger()
        name_src = get_name_dir(name)
        dest_path = None
        src_path = get_src_path(file_glob)
        if src_path:
            if not os.path.exists(f'/srv/{name_src}'):
                os.mkdir(f'/srv/{name_src}')
            try:
                copy2(src_path, f'/srv/{name_src}/')
            except Error as err:
                log.debug(f'Failed copying {name} source file to /srv/{name_src}/ '
                          f'directory. \n{err}')
            else:
                log.info(f'Successfully installed {name} source file '
                         'into the POWER-Up software server.')
                dest_path = os.path.join(f'/srv/{name_src}/',
                                         os.path.basename(src_path))
        return src_path, dest_path


class PowerupRepo(object):
    """Base class for creating a yum repository for access by POWER-Up software
     clients.
    """
    def __init__(self, repo_id, repo_name, arch='ppc64le', rhel_ver='7'):
        self.repo_id = repo_id
        self.repo_name = repo_name
        self.arch = arch
        self.repo_type = 'yum'
        self.rhel_ver = str(rhel_ver)
        self.repo_base_dir = '/srv'
        self.repo_dir = f'/srv/repos/{self.repo_id}/rhel{self.rhel_ver}/{self.repo_id}'
        self.anarepo_dir = f'/srv/repos/{self.repo_id}'
        self.pypirepo_dir = f'/srv/repos/{self.repo_id}'
        self.log = logger.getlogger()

    def get_repo_dir(self):
        return self.repo_dir

    def get_action(self, exists, exists_prompt_yn=False):
        if exists:
            print(f'\nDo you want to sync the local {self.repo_name}\nrepository'
                  ' at this time?\n')
            print('This can take a few minutes.\n')
            if exists_prompt_yn:
                ch = 'Y' if get_yesno(prompt='Sync Repo? ', yesno='Y/n') else 'n'
            else:
                items = 'Yes,no,Sync repository and Force recreation of metadata files'
                ch, item = get_selection(items, 'Y,n,F', sep=',')
        else:
            print(f'\nDo you want to create a local {self.repo_name}\n repository'
                  ' at this time?\n')
            print('This can take a significant amount of time')
            ch = 'Y' if get_yesno(prompt='Create Repo? ', yesno='Y/n') else 'n'
        return ch

    def get_repo_url(self, url, alt_url=None, name=''):
        """Allows the user to choose the default url or enter an alternate
        Inputs:
            repo_url: (str) URL or metalink for the external repo source
        """
        if name:
            print(f'\nChoice for source of {name} repository:')
        ch, item = get_selection('Public mirror.Alternate web site', 'P.A',
                                 'Select source: ', '.')
        if ch == 'A':
            if not alt_url:
                alt_url = f'http://host/repos/{self.repo_id}/'
            tmp = get_url(alt_url, prompt_name=self.repo_name, repo_chk=self.repo_type)
            if tmp is None:
                return None
            else:
                if tmp[-1] != '/':
                    tmp = tmp + '/'
                alt_url = tmp
        url = alt_url if ch == 'A' else url
        return url

    def copy_to_srv(self, src_path, dst):
        dst_dir = f'{self.repo_base_dir}/{dst}'
        if not os.path.exists(dst_dir):
            os.mkdir(dst_dir)
        copy2(src_path, dst_dir)

    def copytree_to_srv(self, src_dir, dst):
        """Copy a directory recursively to the POWER-Up server base directory.
        Note that if the directory exists already under the /srv durectory, it
        will be recursively erased before the copy begins.
        """
        dst_dir = f'{self.repo_base_dir}/{dst}'
        if os.path.exists(dst_dir):
            os.removedirs(dst_dir)
        copytree(src_dir, dst_dir)

    def get_yum_dotrepo_content(self, url=None, repo_dir=None, gpgkey=None, gpgcheck=1,
                                metalink=False, local=False, client=False):
        """creates the content for a yum '.repo' file. To create content for a POWER-Up
        client, set client=True. To create content for this node (the POWER-Up node),
        set local=True. If neither client or local is true, content is created for this
        node to access a remote URL. Note: client and local should be considered
        mutually exclusive. If repo_dir is not included, self.repo_dir is used as the
        baseurl for client and local .repo content.
        """
        self.log.debug(f'Creating yum ". repo" file for {self.repo_name}')
        if not repo_dir:
            repo_dir = self.repo_dir
        content = ''
        # repo id
        if client:
            content += f'[{self.repo_id}-powerup]\n'
        elif local:
            content += f'[{self.repo_id}-local]\n'
        else:
            content = f'[{self.repo_id}]\n'

        # name
        content += f'name={self.repo_name}\n'

        # repo url
        if local:
            content += f'baseurl=file://{repo_dir}/\n'
        elif client:
            d = repo_dir.lstrip('/')
            d = d.lstrip('srv')
            content += 'baseurl=http://{{ host_ip.stdout }}' + f'{d}/\n'
        elif metalink:
            content += f'metalink={url}\n'
            content += 'failovermethod=priority\n'
        elif url:
            content += f'baseurl={url}\n'
        else:
            self.log.error('No ".repo" link type was specified')
        content += 'enabled=1\n'
        content += f'gpgcheck={gpgcheck}\n'
        if gpgcheck:
            content += f'gpgkey={gpgkey}'
        return content

    def write_yum_dot_repo_file(self, content, repo_link_path=None):
        """Writes '.repo' files to /etc/yum.repos.d/. If the .repo file already
        exists and the new content is different than the existing content, any
        existing yum cache data and any repodata for that repository is erased.
        """
        if repo_link_path is None:
            if f'{self.repo_id}-local' in content:
                repo_link_path = f'/etc/yum.repos.d/{self.repo_id}-local.repo'
            else:
                repo_link_path = f'/etc/yum.repos.d/{self.repo_id}.repo'
                if os.path.exists(repo_link_path):
                    with open(repo_link_path, 'r') as f:
                        curr_content = f.read()
                        if curr_content != content:
                            self.log.info(f'Sync source for repository {self.repo_id} '
                                          'has changed')
                            cache_dir = (f'/var/cache/yum/{self.arch}/7Server/'
                                         f'{self.repo_id}')
                            if os.path.exists(cache_dir):
                                self.log.info(f'Removing existing cache directory '
                                              f'{cache_dir}')
                                rmtree(cache_dir)
                            if os.path.exists(cache_dir + '-local'):
                                self.log.info(f'Removing existing cache directory '
                                              f'{cache_dir}-local')
                                rmtree(cache_dir + '-local')
                            if os.path.exists(f'{self.repo_dir}/repodata'):
                                self.log.info(f'Removing existing repodata for '
                                              f'{self.repo_id}')
                                rmtree(f'{self.repo_dir}/repodata')
                            if os.path.isfile(f'/etc/yum.repos.d/{self.repo_id}-local.repo'):
                                self.log.info(f'Removing existing local .repo for'
                                              f' {self.repo_id}-local')
                                os.remove(f'/etc/yum.repos.d/{self.repo_id}-local.repo')
        with open(repo_link_path, 'w') as f:
            f.write(content)

    def create_meta(self, update=False):
        action = ('update', 'Updating') if update else ('create', 'Creating')
        self.log.info(f'{action[1]} repository metadata and databases')
        print('This may take a few minutes.')
        if not update:
            cmd = f'createrepo -v {self.repo_dir}'
        else:
            cmd = f'createrepo -v --update {self.repo_dir}'
        resp, err, rc = sub_proc_exec(cmd)
        if rc != 0:
            self.log.error(f'Repo creation error: rc: {rc} stderr: {err}')
        else:
            self.log.info(f'Repo {action[0]} process for {self.repo_id} finished'
                          ' succesfully')


class PowerupRepoFromRpm(PowerupRepo):
    """Sets up a yum repository for access by POWER-Up software clients.
    The repo is created from an rpm file selected interactively by the user.
    """
    def __init__(self, repo_id, repo_name, arch='ppc64le', rhel_ver='7'):
        super(PowerupRepoFromRpm, self).__init__(repo_id, repo_name, arch, rhel_ver)

    def get_rpm_path(self, filepath='/home/**/*.rpm'):
        """Interactive search for the rpm path.
        Returns: Path to file or None
        """
        while True:
            self.rpm_path = get_file_path(filepath)
            # Check for .rpm files in the chosen file
            cmd = 'rpm -qlp self.rpm_path'
            resp, err, rc = sub_proc_exec(cmd)
            if self.rpm_path:
                if '.rpm' not in resp:
                    print('There are no ".rpm" files in the selected path')
                    if get_yesno('Use selected path? ', default='n'):
                        return self.rpm_path
            else:
                return None

    def copy_rpm(self, src_path):
        """copy the selected rpm file (self.rpm_path) to the /srv/{self.repo_id}
        directory.
        The directory is created if it does not exist.
        """
        self.rpm_path = src_path
        dst_dir = f'/srv/{self.repo_id}'
        if not os.path.exists(dst_dir):
            os.mkdir(dst_dir)
        copy2(self.rpm_path, dst_dir)
        dest_path = os.path.join(dst_dir, os.path.basename(src_path))
        print(dest_path)
        return dest_path

    def extract_rpm(self, src_path):
        """Extracts files from the selected rpm file to a repository directory
        under /srv/repoid/rhel7/repoid. If a repodata directory is included in
        the extracted data, then the path to repodata directory is returned
        Inputs: Uses self.repo_dir and self.repo_id
        Outputs:
            repodata_dir : absolute path to repodata directory if one exists
        """
        extract_dir = self.repo_dir
        if not os.path.exists(extract_dir):
            os.makedirs(extract_dir)
        os.chdir(extract_dir)
        cmd = f'rpm2cpio {src_path} | sudo cpio -div'
        resp, err, rc = sub_proc_exec(cmd, shell=True)
        if rc != 0:
            self.log.error(f'Failed extracting {src_path}')

        repodata_dir = glob.glob(f'{extract_dir}/**/repodata', recursive=True)
        if repodata_dir:
            return os.path.dirname(repodata_dir[0])
        else:
            return None


class PowerupYumRepoFromRepo(PowerupRepo):
    """Sets up a yum repository for access by POWER-Up software clients.
    The repo is first sync'ed locally from the internet or a user specified
    URL which could reside on another host or from a local directory. (ie
    a file based URL pointing to a mounted disk. eg file:///mnt/my-mounted-usb)
    """
    def __init__(self, repo_id, repo_name, arch='ppc64le', rhel_ver='7'):
        super(PowerupYumRepoFromRepo, self).__init__(repo_id, repo_name, arch, rhel_ver)

    def sync(self):
        self.log.info(f'Syncing {self.repo_name}')
        self.log.info('This can take many minutes or hours for large repositories\n')
        cmd = (f'reposync -a {self.arch} -r {self.repo_id} -p'
               f'{os.path.dirname(self.repo_dir)} -l -m')
        rc = sub_proc_display(cmd)
        if rc != 0:
            self.log.error(bold(f'\nFailed {self.repo_name} repo sync. {rc}'))
            raise UserException
        else:
            self.log.info(f'{self.repo_name} sync finished successfully')


class PowerupAnaRepoFromRepo(PowerupRepo):
    """Sets up an Anaconda repository for access by POWER-Up software clients.
    The repo is first sync'ed locally from the internet or a user specified
    URL which could reside on another host or from a local directory. (ie
    a file based URL pointing to a mounted disk. eg file:///mnt/my-mounted-usb)
    To download the entire repository, leave the accept list (acclist) and rejlist
    empty. Note that the accept list and reject list are mutually exclusive.
    inputs:
        acclist (str): Accept list. List of files to download. If specified,
            only the listed files will be downloaded.
        rejlist (str): Reject list. List of files to reject. If specified,
            the entire repository except the files in the rejlist will be downloaded.
    """
    def __init__(self, repo_id, repo_name, arch='ppc64le', rhel_ver='7'):
        super(PowerupAnaRepoFromRepo, self).__init__(repo_id, repo_name, arch, rhel_ver)
        self.repo_type = 'ana'

    def sync_ana(self, url, rejlist='', acclist=''):
        """Syncs an Anaconda repository using wget or copy?. The corresponding
        'noarch' repo is also synced.
        """
        if 'http:' in url or 'https:' in url:
            dest_dir = f'/srv/repos/{self.repo_id}' + url[url.find('/pkgs/'):]
            self.log.info(f'Syncing {self.repo_name}')
            self.log.info('This can take many minutes or hours for large repositories\n')

            # remove directory path components up to '/pkgs'
            cd_cnt = url[3 + url.find('://'):url.find('/pkgs')].count('/')

            if acclist:
                ctrl = '--accept'
                _list = acclist
                if 'index.html' not in _list:
                    _list += ',index.html'
                if 'repodata.json' not in _list:
                    _list += ',repodata.json'
                if 'repodata.json.bz2' not in _list:
                    _list += ',repodata.json.bz2'
            else:
                ctrl = '--reject'
                _list = rejlist
            cmd = (f"wget -m -nH --cut-dirs={cd_cnt} {ctrl} '{_list}' "
                   f"-P /srv/repos/{self.repo_id} {url}")
            rc = sub_proc_display(cmd, shell=True)
            if rc != 0:
                self.log.error(f'Error downloading {url}.  rc: {rc}')
        elif 'file:///' in url:
            src_dir = url[7:]
            if '/pkgs/' in url:
                dest_dir = self.anarepo_dir + url[url.find('/pkgs/'):]
            elif self.anarepo_dir in url:
                dest_dir = url[url.find(self.anarepo_dir):]
            else:
                dest_dir = self.anarepo_dir + url
            if not os.path.isdir(dest_dir):
                os.makedirs(dest_dir)
            cmd = f'rsync -uaPv {src_dir} {dest_dir}'
            rc = sub_proc_display(cmd)
            if rc != 0:
                self.log.error('Sync of {self.repo_id} failed. rc: {rc}')
            else:
                self.log.info(f'{self.repo_name} sync finished successfully')

        filelist = os.listdir(dest_dir)
        filecnt = 0
        dest = dest_dir + 'index.html'
        src = dest_dir + 'index-src.html'
        os.rename(dest, src)
        with open(src, 'r') as s, open(dest, 'w') as d:
            while True:
                line = s.readline()
                if not line:
                    break
                if '<tr>' not in line:
                    line = re.sub(r'Files:\s+\d+', f'Files: {filecnt-2}', line)
                    d.write(line)
                else:
                    # start of html table row
                    row, filename = self._get_table_row(s)
                    if filename in filelist:
                        line += row
                        filecnt += 1
                        d.write(line)
        return dest_dir

    def _get_table_row(self, file_handle):
        """read lines from file handle until end of table row </tr> found
        return:
            row: (str) with the balance of the table row.
            filename: (str) with the name of the file referenced.
        """
        row = ''
        filename = ''
        while '</tr>' not in row:
            line = file_handle.readline()
            name = re.search(r'href="(.+)"', line)
            row += line
            if name:
                filename = name.group(1)
        return row, filename


class PowerupPypiRepoFromRepo(PowerupRepo):
    """Sets up a Pypi (pip) repository for access by POWER-Up software clients.
    The repo is first sync'ed locally from the internet or a user specified
    URL which could reside on another host or from a local directory. (ie
    a file based URL pointing to a mounted disk. eg file:///mnt/my-mounted-usb)
    """
    def __init__(self, repo_id, repo_name, arch='ppc64le', rhel_ver='7'):
        super(PowerupPypiRepoFromRepo, self).__init__(repo_id, repo_name, arch, rhel_ver)
        self.repo_type = 'pypi'

    def sync(self, pkg_list, alt_url=None):
        """
        inputs:
            pkg_list (str): list of packages separated by space(s). Packages can
                include versions. ie Keras==2.0.5
        """
        if not os.path.isdir(self.pypirepo_dir):
            os.mkdir(self.pypirepo_dir)
        pkg_cnt = len(pkg_list.split())
        print(f'Downloading {pkg_cnt} python packages plus dependencies:\n{pkg_list}\n')

        if alt_url:
            host = re.search(r'http://([^/]+)', alt_url).group(1)
            cmd = ('source ' + os.path.expanduser('~/anaconda2/bin/activate') +
                   f'pkgdl &&  pip download --index-url={alt_url} -d '
                   f'{self.pypirepo_dir} {pkg} --trusted-host {host}')
            resp, err, rc = sub_proc_exec(cmd, shell=True)
            if rc != 0:
                self.log.error('Error occured while downloading python package: '
                               f'{pkg}. \nResp: {resp} \nRet code: {rc} \nerr: {err}')
        else:
            cmd = ('source ' + os.path.expanduser('~/anaconda2/bin/activate') +
                   f' pkgdl && pip download -d {self.pypirepo_dir} {pkg_list}')
            resp, err, rc = sub_proc_exec(cmd, shell=True)
            if rc != 0:
                self.log.error('Error occured while downloading python package: '
                               f'{pkg}. \nResp: {resp} \nRet code: {rc} \nerr: {err}')
        if not os.path.isdir(self.pypirepo_dir + '/simple'):
            os.mkdir(self.pypirepo_dir + '/simple')
        dir_list = os.listdir(self.pypirepo_dir)
        cnt = 0

        for item in dir_list:
            if item[0] != '.' and os.path.isfile(self.pypirepo_dir + '/' + item):
                res = re.search(r'([-_+\w\.]+)(?=-(\d+\.\d+){1,3}).+', item)
                if res:
                    cnt += 1
                    name = res.group(1)
                    name = name.replace('.', '-')
                    name = name.replace('_', '-')
                    name = name.lower()
                    if not os.path.isdir(self.pypirepo_dir + f'/simple/{name}'):
                        os.mkdir(self.pypirepo_dir + f'/simple/{name}')
                    if not os.path.islink(self.pypirepo_dir + f'/simple/{name}/{item}'):
                        os.symlink(self.pypirepo_dir + f'/{item}',
                                   self.pypirepo_dir + f'/simple/{name}/{item}')
                else:
                    self.log.error(f'mismatch: {item}. There was a problem entering '
                                   f'{item}\ninto the python package index')
        self.log.info(f'A total of {cnt} packages exist or were added to the python '
                      'package repository')
# dir2pi changes underscores to dashes in the links it creates which caused some
# packages to fail to install. In particular python_heatclient and other python
# openstack packages
#        cmd = f'dir2pi -N {self.pypirepo_dir}'
#        resp, err, rc = sub_proc_exec(cmd)
#        if rc != 0:
#            self.log.error('An error occured while creating python package index: \n'
#                           f'dir2pi utility results: \nResp: {resp} \nRet code: '
#                           f'{rc} \nerr: {err}')


class PowerupRepoFromDir(PowerupRepo):
    def __init__(self, repo_id, repo_name, arch='ppc64le', rhel_ver='7'):
        super(PowerupRepoFromDir, self).__init__(repo_id, repo_name, arch, rhel_ver)

    def copy_dirs(self, src_dir=None):
        if os.path.exists(self.repo_dir):
            r = get_yesno(f'Directory {self.repo_dir} already exists. OK to replace it? ')
            if r == 'yes':
                rmtree(os.path.dirname(self.repo_dir), ignore_errors=True)
            else:
                self.log.info('Directory not created')
                return None, None

        src_dir = get_dir(src_dir)
        if not src_dir:
            return None, None

        try:
            dest_dir = self.repo_dir
            copytree(src_dir, dest_dir)
        except Error as exc:
            print(f'Copy error: {exc}')
            return None, dest_dir
        else:
            return src_dir, dest_dir


def create_repo_from_rpm_pkg(pkg_name, pkg_file, src_dir, dst_dir, web=None):
        heading1(f'Setting up the {pkg_name} repository')
        ver = ''
        src_installed, src_path = setup_source_file(cuda_src, cuda_dir, 'PowerAI')
        ver = re.search(r'\d+\.\d+\.\d+', src_path).group(0) if src_path else ''
        self.log.debug(f'{pkg_name} source path: {src_path}')
        cmd = f'rpm -ihv --test --ignorearch {src_path}'
        resp1, err1, rc = sub_proc_exec(cmd)
        cmd = f'diff /opt/DL/repo/rpms/repodata/ /srv/repos/DL-{ver}/repo/rpms/repodata/'
        resp2, err2, rc = sub_proc_exec(cmd)
        if 'is already installed' in err1 and resp2 == '' and rc == 0:
            repo_installed = True
        else:
            repo_installed = False

        # Create the repo and copy it to /srv directory
        if src_path:
            if not ver:
                self.log.error('Unable to find the version in {src_path}')
                ver = rlinput('Enter a version to use (x.y.z): ', '5.1.0')
            ver0 = ver.split('.')[0]
            ver1 = ver.split('.')[1]
            ver2 = ver.split('.')[2]
            # First check if already installed
            if repo_installed:
                print(f'\nRepository for {src_path} already exists')
                print('in the POWER-Up software server.\n')
                r = get_yesno('Do you wish to recreate the repository')

            if not repo_installed or r == 'yes':
                cmd = f'rpm -ihv  --force --ignorearch {src_path}'
                rc = sub_proc_display(cmd)
                if rc != 0:
                    self.log.info('Failed creating PowerAI repository')
                    self.log.info(f'Failing cmd: {cmd}')
                else:
                    shutil.rmtree(f'/srv/repos/DL-{ver}', ignore_errors=True)
                    try:
                        shutil.copytree('/opt/DL', f'/srv/repos/DL-{ver}')
                    except shutil.Error as exc:
                        print(f'Copy error: {exc}')
                    else:
                        self.log.info('Successfully created PowerAI repository')
        else:
            if src_installed:
                self.log.debug('PowerAI source file already in place and no '
                               'update requested')
            else:
                self.log.error('PowerAI base was not installed.')

        if ver:
            dot_repo = {}
            dot_repo['filename'] = f'powerai-{ver}.repo'
            dot_repo['content'] = (f'[powerai-{ver}]\n'
                                   f'name=PowerAI-{ver}-powerup\n'
                                   'baseurl=http://{host}}/repos/'
                                   f'DL-{ver}/repo/rpms\n'
                                   'enabled=1\n'
                                   'gpgkey=http://{host}/repos/'
                                   f'DL-{ver}/repo/mldl-public-key.asc\n'
                                   'gpgcheck=0\n')
            if dot_repo not in self.sw_vars['yum_powerup_repo_files']:
                self.sw_vars['yum_powerup_repo_files'].append(dot_repo)


if __name__ == '__main__':
    """ setup reposities. sudo env "PATH=$PATH" python repo.py
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('repo_name', nargs='?',
                        help='repository name')

    parser.add_argument('--print', '-p', dest='log_lvl_print',
                        help='print log level', default='info')

    parser.add_argument('--file', '-f', dest='log_lvl_file',
                        help='file log level', default='info')

    args = parser.parse_args()
    # args.repo_name = args.repo_name[0]

    if args.log_lvl_print == 'debug':
        print(args)

    logger.create(args.log_lvl_print, args.log_lvl_file)

    repo = local_epel_repo(args.repo_name)
    repo.yum_create_remote()
    repo.sync()
    repo.create()
    repo.yum_create_local()
    client_file = repo.get_yum_client_powerup()