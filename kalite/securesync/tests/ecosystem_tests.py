import copy
import os
import platform
import requests
import shutil
import tempfile

from django.utils import unittest

import settings
from central.tests.browser_tests import KALiteCentralBrowserTestCase
from main.tests.browser_tests import KALiteDistributedBrowserTestCase
from playground.test_tools.mount_branch import KaLiteServer, KaLiteSelfZipProject
from securesync.models import Device, DeviceZone, Zone
#from shared.testing.base import create_test_admin
from shared.testing.browser import BrowserTestCase
from utils.django_utils import call_command_with_output


class KALiteEcosystemTestCase(KALiteCentralBrowserTestCase, KALiteDistributedBrowserTestCase):
    """
    A utility class for implementing testcases involving an "ecosystem" of KA Lite servers:
    1 central server and two distributed servers, on the same zone.
    
    Subclasses could look at complex syncing scenarios, using the setup provided here.
    """
    
    # TODO(bcipolli) move setup and teardown code to class (not instance);
    #   not sure how to tear down in this case, though...............
        
    def __init__(self, *args, **kwargs):
        self.log = settings.LOG
        self.zip_files = {
            "central": tempfile.mkstemp()[1],
            "local": tempfile.mkstemp()[1],
        }
        self.temp_dir = tempfile.mkdtemp()
        self.zone_name = kwargs.get("zone_name", "Syncing test zone")
        self.servers = {}

        KALiteCentralBrowserTestCase.__init__(self, *args, **kwargs)
        KALiteDistributedBrowserTestCase.__init__(self, *args, **kwargs)

    def reverse(self, url_name):
        if url_name == "auth_url":
            absolute_url = "/securesync/login"
        else:
            import pdb; pdb.set_trace()
        return "http://%s:%d%s" % (self.active_server.hostname, self.active_server.port, absolute_url)
        
    def setup_ports(self):
        """Get the live server port (self), plus three more ports (remotes)"""
        self.port = int(self.live_server_url.split(":")[2])

        assert os.environ.get("DJANGO_LIVE_TEST_SERVER_ADDRESS",""), "This testcase can only be run running under the liveserver django test option.  For KA Lite, this should be set up by our TestRunner (which is set up in settings.py)"
        
        # Parse the open ports
        self.open_ports = [int(p) for p in os.environ['DJANGO_LIVE_TEST_SERVER_ADDRESS'].split(":")[1].split("-")]
        if len(self.open_ports) != 2:
            raise Exception("Unable to parse ports. Use a simple range (8000-8080). Used: '%s'" % os.environ['DJANGO_LIVE_TEST_SERVER_ADDRESS'])
            
        # Choose some (but not one that's used for this liveserver)
        self.open_ports = set(range(self.open_ports[0], self.open_ports[1]+2)) - {self.port,}

    def setUp(self):
        KALiteCentralBrowserTestCase.setUp(self)
        #KALiteDistributedBrowserTestCase.setUp(self)

        self.setUpManual()
    
    
    def register_via_browser(self, distributed_server, central_server):
        self.active_server = distributed_server
        self.browser_login_admin()  # total hack, but I avoid multiple inheritance or major refactoring :)

        self.active_server = distributed_server
        import pdb; pdb.set_trace()


    def setUpManual(self):
        """
        Set up three servers--central and two distributed--and register
        the machiens to a zone.
        """
        self.log.info("Setting up ecosystem")

        self.setup_ports()
        server_types = ["central", "local", "local2"]
        port_map = dict(zip(server_types, self.open_ports))  # this works as wished, due to niceties of zip

        # Create a zip file package FROM THIS CODEBASE for a central server
        self.log.info("Creating zip package from your server; please wait.")
        out = call_command_with_output("zip_kalite", server_type="central", platform=platform.system(), locale='en', file=self.zip_files['central'])

        # Install the central server
        self.log.info("Installing the central server; please wait.")
        kap = KaLiteSelfZipProject(base_dir=self.temp_dir, zip_file=self.zip_files["central"], persistent_ports=False)
        kap.mount_project(server_types=["central"], host="127.0.0.1", port_map=port_map)
        self.servers["central"] = copy.copy(kap.servers["central"])

        # Create a zip file package FROM THIS CODEBASE for a distributed server
        self.log.info("Creating zip package from your server; please wait.")
        out = call_command_with_output("zip_kalite", server_type="local", platform=platform.system(), locale='en', file=self.zip_files['local'])

        # Install the central server
        self.log.info("Installing the first distributed server; please wait.")
        kap = KaLiteSelfZipProject(base_dir=self.temp_dir, zip_file=self.zip_files["local"], persistent_ports=False)
        kap.mount_project(server_types=["local"], host="127.0.0.1", port_map=port_map)
        self.servers["local"] = copy.copy(kap.servers["local"])

        # Register the distributed server with the central server
        self.register_via_browser(self.servers["local"], self.servers["central"])

        #
        # Log in to the central server

        # Create a zone on the central server
        out = self.shell_plus("central", "Zone(name='%s').save()" % self.zone_name)
        zone_id = eval(self.shell_plus("central", "Zone.objects.all()[0].id"))
        
        # Create a zip file package from the central codebase.
        self.log.info("Creating zip package from installed central server; please wait.")
        zoned_zip_file = self.shell_plus("central", "import utils.packaging\nutils.packaging.package_offline_install_zip(platform='%s', locale='en', zone=Zone.objects.all()[0], num_certificates=2, central_server='http://127.0.0.1:%d')" % (platform.system(), port_map["central"]))

        zoned_zip_file = zoned_zip_file[5:-1] # prune cruft (leading ">>> '" and trailing "'")

        # Install the other two servers
        ncservers = set(server_types)-{"central",}
        self.log.info("Installing the other servers (%s); please wait." % ncservers)
        kap = KaLiteSelfZipProject(base_dir=self.temp_dir, zip_file=zoned_zip_file, persistent_ports=False)
        kap.mount_project(server_types=ncservers, host="127.0.0.1", port_map=port_map)
        for server in ncservers:
            self.servers[server] = kap.servers[server]

        # Now start all the servers
        for server in self.servers.values():
            server.start_server()
            
        return super(KALiteEcosystemTestCase, self).setUp(*args, **kwargs)

    def tearDown(self):
        self.log.info("Tearing down ecosystem test servers")
        shutil.rmtree(self.temp_dir)
        os.remove(self.zip_file)


    def call_command(self, server, command, params_string="", expect_success=True):
        """Utility function for calling out to call_command, then repackaging the output."""
        out = self.servers[server].call_command(command=command, params_string=params_string)
        if expect_success:
            self.assertEqual(out['exit_code'], 0, "Check exit code.")
            self.assertEqual(out['stderr'], None, "Check stderr")
            return out['stdout']
        else:
            return out
        
    def shell_plus(self, server, commands, expect_success=True):
        """Utility function for calling out to shell_plus, then repackaging the output."""
        out = self.servers[server].shell_plus(commands=commands)
        if expect_success:
            self.assertIn('exit_code', out.keys(), "Check exit code.")
            self.assertEqual(out['exit_code'], 0, "Check exit code.")
            self.assertEqual(out['stderr'], None, "Check stderr")
            return out['stdout']
        else:
            return out


@unittest.skipIf("long" in settings.TESTS_TO_SKIP, "Skipping long test")
class CrossLocalServerSyncTestCase(KALiteEcosystemTestCase):
    """Basic sync test case."""
    
    def check_has_logs(self, server, log_type, count):
        """Check that given server has the number of logs expected, for the given type."""

        val = self.shell_plus(server, "%s.objects.all().count()" % log_type)
        self.assertEqual(count, int(val), "Checking that %s has %d %s logs." % (server, count, log_type))

    
    def check_has_device(self, server, device):
        """Check that device, zone, and devicezone data exist for the given device on the given server."""

        # Get the device and zone information
        device_id = eval(self.shell_plus(device, "Device.objects.filter(devicemetadata__is_own_device=True)[0].id"))
        zone_id = eval(self.shell_plus(device, "DeviceZone.objects.filter(device='%s')[0].zone.id" % device_id))

        # double eval is a bug to track down ... sometime.                
        self.assertEqual(device, eval(eval(self.shell_plus(server, "Device.objects.get(id='%s').name" % device_id))), "Device %s exists on %s" % (device, server))
        self.assertEqual(self.zone_name, eval(self.shell_plus(server, "Device.objects.get(id='%s').get_zone().name" % device_id)), "Zone for %s exists on %s" % (device, server))


    def test_one(self):
        ## Generate data on local2
        out = self.call_command("local2", "generatefakedata")
        n_elogs = int(self.shell_plus("local2", "ExerciseLog.objects.all().count()"))
        n_vlogs = int(self.shell_plus("local2", "VideoLog.objects.all().count()"))
        self.assertTrue(n_elogs > 0, "local2 has more than 0 exercise logs, after running 'generatefakedata'")

        ## Sync local2 to the central server            
        out = self.call_command("local2", "syncmodels")
        self.assertIn("Total errors: 0", out)
        
        # Validate data on central server
        self.check_has_logs(server="central", log_type="ExerciseLog", count=n_elogs)
        self.check_has_logs(server="central", log_type="VideoLog", count=n_vlogs)
        self.check_has_device(server="central", device="local2")
        
        # Validate no data on local
        self.check_has_logs(server="local", log_type="ExerciseLog", count=0)
        self.check_has_logs(server="local", log_type="VideoLog", count=0)


        ## Sync local to the central server (should get local2 data)
        out = self.call_command("local", "syncmodels")
        self.assertIn("Total errors: 0", out)
        
        # Validate data on local
        self.check_has_logs(server="local", log_type="ExerciseLog", count=n_elogs)
        self.check_has_logs(server="local", log_type="VideoLog", count=n_vlogs)
        self.check_has_device(server="local", device="local2")
        

        ## Last one: sync local2 to the central server (should get local device)
        out = self.call_command("local2", "syncmodels")
        self.assertIn("Total errors: 0", out)
        
        # Validate data on local2
        self.check_has_logs(server="local", log_type="ExerciseLog", count=n_elogs)
        self.check_has_logs(server="local", log_type="VideoLog", count=n_vlogs)
        self.check_has_device(server="local2", device="local")

        import pdb; pdb.set_trace()
