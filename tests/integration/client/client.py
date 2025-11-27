#!/usr/bin/env python3
"""
Client for Astrometry.net API.
Extracted from net/client/client.py for integration testing.

This file is part of the Astrometry.net suite.
Copyright 2009 Dustin Lang
Licensed under a 3-clause BSD style license - see LICENSE
https://github.com/dstndstn/astrometry.net
"""

from __future__ import print_function
import json

try:
    # py3
    from urllib.parse import urlencode, quote
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
except ImportError:
    # py2
    from urllib import urlencode, quote
    from urllib2 import urlopen, Request, HTTPError


def json2python(data):
    """Parse JSON string to Python object."""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


python2json = json.dumps


class RequestError(Exception):
    """Exception raised for API request errors."""
    pass


class Client(object):
    """Client for Astrometry.net API."""
    
    default_url = 'https://nova.astrometry.net/api/'

    def __init__(self, apiurl=default_url):
        """Initialize client with API URL."""
        self.session = None
        self.apiurl = apiurl

    def get_url(self, service):
        """Get full URL for a service endpoint."""
        return self.apiurl + service

    def send_request(self, service, args={}, file_args=None):
        """
        Send a request to the API.
        
        Args:
            service: string endpoint name
            args: dict of request parameters
            file_args: tuple of (filename, file_content) for file uploads
        """
        if self.session is not None:
            args.update({'session': self.session})
        
        json_data = python2json(args)
        url = self.get_url(service)

        # If we're sending a file, format a multipart/form-data
        if file_args is not None:
            import random
            boundary_key = ''.join([random.choice('0123456789') for i in range(19)])
            boundary = '===============%s==' % boundary_key
            headers = {'Content-Type':
                       'multipart/form-data; boundary="%s"' % boundary}
            data_pre = (
                '--' + boundary + '\n' +
                'Content-Type: text/plain\r\n' +
                'MIME-Version: 1.0\r\n' +
                'Content-disposition: form-data; name="request-json"\r\n' +
                '\r\n' +
                json_data + '\n' +
                '--' + boundary + '\n' +
                'Content-Type: application/octet-stream\r\n' +
                'MIME-Version: 1.0\r\n' +
                'Content-disposition: form-data; name="file"; filename="%s"' % file_args[0] +
                '\r\n' + '\r\n')
            data_post = (
                '\n' + '--' + boundary + '--\n')
            data = data_pre.encode() + file_args[1] + data_post.encode()
        else:
            # Else send x-www-form-encoded
            data = {'request-json': json_data}
            data = urlencode(data)
            data = data.encode('utf-8')
            headers = {}

        request = Request(url=url, headers=headers, data=data)

        try:
            f = urlopen(request)
            txt = f.read()
            result = json2python(txt)
            stat = result.get('status')
            if stat == 'error':
                errstr = result.get('errormessage', '(none)')
                raise RequestError('server error message: ' + errstr)
            return result
        except HTTPError as e:
            txt = e.read()
            raise RequestError(f'HTTP error {e.code}: {txt.decode("utf-8", errors="ignore")}')

    def login(self, apikey):
        """Login with API key and store session."""
        args = {'apikey': apikey}
        result = self.send_request('login', args)
        sess = result.get('session')
        if not sess:
            raise RequestError('no session in result')
        self.session = sess

    def _get_upload_args(self, **kwargs):
        """Get upload arguments from kwargs."""
        args = {}
        for key, default, typ in [('allow_commercial_use', 'd', str),
                                  ('allow_modifications', 'd', str),
                                  ('publicly_visible', 'y', str),
                                  ('scale_units', None, str),
                                  ('scale_type', None, str),
                                  ('scale_lower', None, float),
                                  ('scale_upper', None, float),
                                  ('scale_est', None, float),
                                  ('scale_err', None, float),
                                  ('center_ra', None, float),
                                  ('center_dec', None, float),
                                  ('parity', None, int),
                                  ('radius', None, float),
                                  ('downsample_factor', None, int),
                                  ('positional_error', None, float),
                                  ('tweak_order', None, int),
                                  ('crpix_center', None, bool),
                                  ('invert', None, bool),
                                  ('use_sextractor', None, bool),
                                  ('image_width', None, int),
                                  ('image_height', None, int),
                                  ('x', None, list),
                                  ('y', None, list),
                                  ('album', None, str),
                                  ]:
            if key in kwargs:
                val = kwargs.pop(key)
                val = typ(val)
                args.update({key: val})
            elif default is not None:
                args.update({key: default})
        return args

    def url_upload(self, url, **kwargs):
        """Upload an image from URL."""
        args = dict(url=url)
        args.update(self._get_upload_args(**kwargs))
        result = self.send_request('url_upload', args)
        return result

    def upload(self, fn=None, **kwargs):
        """Upload an image file."""
        args = self._get_upload_args(**kwargs)
        file_args = None
        if fn is not None:
            try:
                f = open(fn, 'rb')
                file_args = (fn, f.read())
                f.close()
            except IOError:
                raise RequestError(f'File {fn} does not exist')
        return self.send_request('upload', args, file_args)

    def submission_images(self, subid):
        """Get image IDs for a submission."""
        result = self.send_request('submission_images', {'subid': subid})
        return result.get('image_ids')

    def myjobs(self):
        """Get list of my jobs."""
        result = self.send_request('myjobs/')
        return result['jobs']

    def job_status(self, job_id, justdict=False):
        """Get job status."""
        result = self.send_request('jobs/%s' % job_id)
        if justdict:
            return result
        return result.get('status')

    def annotate_data(self, job_id):
        """Get annotation data for a job."""
        result = self.send_request('jobs/%s/annotations' % job_id)
        return result

    def sub_status(self, sub_id, justdict=False):
        """Get submission status."""
        result = self.send_request('submissions/%s' % sub_id)
        if justdict:
            return result
        return result.get('status')

    def jobs_by_tag(self, tag, exact):
        """Get jobs by tag."""
        exact_option = 'exact=yes' if exact else ''
        result = self.send_request(
            'jobs_by_tag?query=%s&%s' % (quote(tag.strip()), exact_option),
            {},
        )
        return result

