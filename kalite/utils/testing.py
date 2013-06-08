import decorator
import logging
import time
import os
import shutil
import sys
import platform
import tempfile
import unittest
from selenium import webdriver
from StringIO import StringIO

from django.contrib.auth.models import User
from django.test.client import Client
from django.core.urlresolvers import reverse
from django.core.management import call_command
from django.test import TestCase, LiveServerTestCase
from django_snippets._mkdir import _mkdir

import settings
from kalite.utils.django_utils import call_command_with_output


def x_only(f, cond, msg):
    """Decorator"""

    if f.__class__.__name__ == "type":
        @unittest.skipIf(cond, msg)
        class wrapped_class(f):
            pass
        return wrapped_class
        
    else:
        @unittest.skipIf(cond, msg)
        def wrapped_fn(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapped_fn

def main_only(f):
    return x_only(f, settings.CENTRAL_SERVER, "Distributed server test")

def central_only(f):
    return x_only(f, not settings.CENTRAL_SERVER, "Central server test")
    
         
def add_to_local_settings(var, val):
    fh = open(settings.PROJECT_PATH + "/local_settings.py","a")
    fh.write("\n%s = %s" % (var,str(val)))
    fh.close()
        
def create_test_user(username, password, email):
    """Create a test user.
    Taken from http://stackoverflow.com/questions/3495114/how-to-create-admin-user-in-django-tests-py"""
    
    test_admin = User.objects.create_superuser(username, email, password)
    logging.debug('Created user "%s"' % username)

    # You'll need to log him in before you can send requests through the client
    client = Client()
    assert client.login(username=test_admin.username, password=password)

    # set dummy password, so it can be passed around
    test_admin.password = password
    assert client.login(username=test_admin.username, password=password)
    
    return test_admin
    
    
browser = None
def setup_test_env(browser_type="Firefox", test_user="test", test_password="test", test_email="test@learningequality.org", persistent_browser=False):
    """Create a django superuser, and connect to the specified browser.
    peristent_browser: keep a static handle to the browser, rather than 
      re-launch for every testcase.  True currently doesn't work well, so just do False :("""
      
    global browser
        
    # Add the test user
    admin_user = create_test_user(username=test_user, password=test_password, email=test_email)
    
    # Launch the browser
    if not persistent_browser or (persistent_browser and not browser):
        local_browser = getattr(webdriver, browser_type)() # Get local session of firefox
        if persistent_browser: # share browser across tests
            browser = local_browser
    else:
        local_browser = browser
       
    return (local_browser,admin_user)
            


def wait_for_page_change(browser, source_url, max_retries=10):
    """Given a selenium browser, wait until the browser has completed.
    Code taken from: https://github.com/dragoon/django-selenium/blob/master/django_selenium/testcases.py"""

    for i in range(max_retries):
        if browser.current_url == source_url:
            time.sleep(100)
        else:
            break;

    return browser.current_url != source_url
    
    

class KALiteTestCase(LiveServerTestCase):
    def reverse(self, url_name):
        """Given a URL name, returns the full central URL to that URL"""

        return self.live_server_url + reverse(url_name)

    
class BrowserTestCase(KALiteTestCase):
    """
    A base test case for Selenium, providing helper methods for generating
    clients and logging in profiles.
    """
    persistent_browser = False
    
    def setUp(self):
        (self.browser,self.admin_user) = setup_test_env(persistent_browser=self.persistent_browser)
        
    def tearDown(self):
        if not self.persistent_browser:
            self.browser.quit()
        
    def wait_for_page_change(self, source_url, max_retries=10):
        return wait_for_page_change(self.browser, source_url, max_retries)
    
    def browser_activate_element(self, elem=None, id=None, name=None, tag_name=None):
        """Given the identifier to a page element, make it active.
        Currently done by clicking TODO(bcipolli): this won't work for buttons, 
        so find another way when that becomes an issue."""
        
        if not elem:
            if id:
                elem = self.browser.find_element_by_id(id)
            elif name:
                elem = self.browser.find_element_by_name(name)
            elif tag_name:
                elem = self.browser.find_element_by_tag_name(tag_name)
        elem.click()
            
    def browser_send_keys(self, keys):
        """Convenience method to send keys to active_element in the browser"""
        self.browser.switch_to_active_element().send_keys(keys)
    
    def capture_stdout(self, cmdargs):
        """Captures output to stdout when a particular test command is run.
        cmdargs: first arg is the function, all other args are positional args.
           there should be a better way to do this, but I'm not sure what it is yet."""
        
        # Parse out function and args
        fn = cmdargs[0]
        args = cmdargs[1:]
        
        # Save old stdout stream.  Save stdout string.  Restore old stdout stream
        saved_stdout = sys.stdout
        try:
            out = StringIO()
            sys.stdout = out
            fn(args)
            output = out.getvalue().strip()
        except Exception as e:
            output = e.message
        finally:
            sys.stdout = saved_stdout        

        return output

   
class KALiteCentralBrowserTestCase(BrowserTestCase):
    """Base class for central server test cases"""
    pass
    
    
class KALiteLocalBrowserTestCase(BrowserTestCase):
    pass

class KALiteEcosystemTestCase(KALiteTestCase):

    def setUp(self):
        # Make sure the setup is 2 local, 1 central
        server1 = {'zip_filename': tempfile.mkstemp(), 'type': 'local'}
        server2 = {'zip_filename': tempfile.mkstemp(), 'type': 'local' if settings.CENTRAL_SERVER else 'central' }

#        out = call_command_with_output("package_for_download", platform=platform.system(), locale='en', server_type=server1['type'], file=server1['zip_filename'])
        out = call_command_with_output("package_for_download", platform=platform.system(), locale='en', server_type=server2['type'], file=server2['zip_filename'])

        from main.management.commands.package_for_download import recursively_add_files
        files_dict = recursively_add_files(settings.PROJECT_PATH+"/../")
        import pdb; pdb.set_trace()
        server1_dir = tempfile.mkdtemp()
        server2_dir = tempfile.mkdtemp()
        for src_path,props in files_dict.items():
            dest_path = server1_dir+props['dest_path']
            _mkdir(os.path.split(dest_path)[0])
            shutil.copyfile(src_path, dest_path)
        
        #import pdb; pdb.set_trace()
        
    
    def tearDown(self):
        import pdb; pdb.set_trace()
        
        