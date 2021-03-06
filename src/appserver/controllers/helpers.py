import logging
import os
import sys
import json
import shutil
import cherrypy
import re
import time
import datetime
import urllib

#from splunk import AuthorizationFailed as AuthorizationFailed
import splunk.appserver.mrsparkle.controllers as controllers
import splunk.appserver.mrsparkle.lib.util as util
import splunk.bundle as bundle
import splunk.entity as entity
from splunk.appserver.mrsparkle.lib import jsonresponse
from splunk.appserver.mrsparkle.lib.util import make_splunkhome_path
import splunk.clilib.bundle_paths as bundle_paths
from splunk.util import normalizeBoolean as normBool
from splunk.appserver.mrsparkle.lib.decorators import expose_page
from splunk.appserver.mrsparkle.lib.routes import route
import splunk.rest as rest

dir = os.path.join(util.get_apps_dir(), 'alert_manager', 'bin', 'lib')
if not dir in sys.path:
    sys.path.append(dir)

from AlertManagerUsers import *
from AlertManagerLogger import *

logger = setupLogger('controllers')

from splunk.models.base import SplunkAppObjModel
from splunk.models.field import BoolField, Field



class Helpers(controllers.BaseController):

    @expose_page(must_login=True, methods=['GET'])
    def get_users(self, **kwargs):
        logger.info("Get users")

        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')

        users = AlertManagerUsers(sessionKey=sessionKey)
        user_list = users.getUserList()

        logger.debug("user_list: %s " % json.dumps(user_list))

        return json.dumps(user_list)

    @expose_page(must_login=True, methods=['GET'])
    def get_indexes(self, **kwargs):
        logger.info("Get indexes")

        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')


        uri = '/services/admin/indexes?output_mode=json'
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey, method='GET')
        #logger.debug("response: %s" % serverContent)
        entries = json.loads(serverContent)

        index_list = []
        if len(entries['entry']) > 0:
            for entry in entries['entry']:
                index_list.append(entry['name'])


        return json.dumps(index_list)

    @expose_page(must_login=True, methods=['GET'])
    def get_notification_schemes(self, **kwargs):
        logger.info("Get notification schemes")

        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')


        uri = '/servicesNS/nobody/alert_manager/storage/collections/data/notification_schemes?q=output_mode=json'
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey, method='GET')
        logger.debug("response: %s" % serverContent)
        entries = json.loads(serverContent)

        scheme_list = [ ]
        if len(entries) > 0:
            for entry in entries:
                scheme_list.append(entry['schemeName'])


        return json.dumps(scheme_list)

    @expose_page(must_login=True, methods=['GET'])
    def get_email_templates(self, **kwargs):
        logger.info("Get templates")

        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')


        uri = '/servicesNS/nobody/alert_manager/storage/collections/data/email_templates?q=&output_mode=json'
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey, method='GET')
        logger.debug("response: %s" % serverContent)
        entries = json.loads(serverContent)

        template_list = [ ]
        if len(entries) > 0:
            for entry in entries:
                template_list.append(entry['template_name'])


        return json.dumps(template_list)

    @expose_page(must_login=True, methods=['GET'])
    def get_email_template_files(self, **kwargs):
        logger.info("Get templates files")

        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')

        file_list = []

        file_default_dir = os.path.join(os.environ.get('SPLUNK_HOME'), "etc", "apps", "alert_manager", "default", "templates")
        if os.path.exists(file_default_dir):
            for f in os.listdir(file_default_dir):
                if re.match(r'.*\.html', f):
                    if f not in file_list:
                        file_list.append(f)

        file_local_dir = os.path.join(os.environ.get('SPLUNK_HOME'), "etc", "apps", "alert_manager", "local", "templates")
        if os.path.exists(file_local_dir):
            for f in os.listdir(file_local_dir):
                if re.match(r'.*\.html', f):
                    if f not in file_list:
                        file_list.append(f)

        return json.dumps(file_list)


    @expose_page(must_login=True, methods=['GET'])
    def get_savedsearch_description(self, savedsearch, app, **kwargs):
        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')

        uri = '/servicesNS/nobody/%s/admin/savedsearch/%s?output_mode=json' % \
              (app, urllib.quote(savedsearch.encode('utf8')))
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey, method='GET')

        savedSearchContent = json.loads(serverContent)

        if savedSearchContent["entry"][0]["content"]["description"]:
            return savedSearchContent["entry"][0]["content"]["description"]
        else:
            return ""

    ## var url = splunkUtil.make_url('/custom/alert_manager/helpers/get_drilldown_search?field='+e.data['row.Key']+'&value='+e.data['row.Value']);
    @expose_page(must_login=True, methods=['GET'])
    def get_drilldown_search(self, field, value, **kwargs):
        logger.info('Get search drilldown. field=%s, value=%s' % (field, value))
        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')

        # create a query to return kvstore values for this single field
        # sample query:
        # query={"field":{"$eq":"src"},"enabled":"1"}&output_mode=json
        q = {'query': '{"field":"' + str(field) + '"}'}

        uri = '/servicesNS/nobody/alert_manager/storage/collections/data/alert_drilldowns?' + urllib.urlencode(q) + '&output_mode=json'

        logger.info('get_drilldown_search uri is %s' % str(uri))
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey)

        logger.info('get_drilldown_search server response is %s' % json.dumps(serverContent))
        entries = json.loads(serverContent)

        # parse the return value for enabled search entries
        try:
            mysearch = []
            if len(entries) > 0:
                for entry in entries:
                    if 'enabled' in entry:
                        if normBool(entry['enabled']):
                            # Basic string replacement is done for value substitution...
                            tmp = str(entry['search'])
                            tmp = tmp.replace('$field$', field)
                            tmp = tmp.replace('$value$', value)
                            logger.info('Found search. Returning search value: %s' % str(tmp))
                            mysearch.append(tmp)

            else:
                mysearch.append('not_found')

            return json.dumps(mysearch)
        except:
            logger.info('Caught an exception when trying to get the search string. Defaulting to no action.')
            return json.dumps(['not_found'])


    @expose_page(must_login=True, methods=['GET'])
    def get_status_list(self, **kwargs):
        logger.info("Get status list")

        user = cherrypy.session['user']['name']
        sessionKey = cherrypy.session.get('sessionKey')

        uri = '/servicesNS/nobody/alert_manager/storage/collections/data/alert_status?output_mode=json'
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey)

        logger.info("server_response: %s" % json.dumps(serverResponse))
        entries = json.loads(serverContent)

        status_list = []
        if len(entries) > 0:
            for entry in entries:
                if int(entry['internal_only']) == 0:
                    se = {'status_description': entry['status_description'], 'status': entry['status']}
                    status_list.append(se)

        logger.info("status_list: %s " % json.dumps(status_list))

        return json.dumps(status_list)
