"""
These will be run when you run "manage.py test [main].
These require a test server to be running, and multiple ports
  need to be available.  Run like this:
./manage.py test main --liveserver=localhost:8004-8010
".
"""

import logging
import re
import time
import unittest
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions, ui

from django.test import TestCase
from django.core.urlresolvers import reverse

import settings
from kalite.utils.django_utils import call_command_with_output
from securesync.models import Facility, FacilityGroup, FacilityUser
from utils.testing.browser import BrowserTestCase
from utils.testing.decorators import distributed_only


class KALiteDistributedBrowserTestCase(BrowserTestCase):
    """Base class for main server test cases.
    They will have different functions in here, for sure.
    """

    def register_user(self, username, password, first_name="firstname", last_name="lastname", stay_logged_in=False, expect_success=True):
        """Tests that a user can register"""

        # Expected results vary based on whether a user is logged in or not.
        if not stay_logged_in:
            self.logout_user()

        register_url = self.reverse("add_facility_student")
        self.browse_to(register_url) # Load page
        self.assertIn("Sign up", self.browser.title, "Register page title %s") # this depends on who is logged in.
        
        # Part 1: REGISTER
        self.browser_activate_element(id="id_username") # explicitly set the focus, to start
        self.browser_send_keys(username + Keys.TAB) # first name
        self.browser_send_keys(first_name + Keys.TAB) # first name
        self.browser_send_keys(last_name + Keys.TAB) # last name
        self.browser_send_keys(password + Keys.TAB) #password
#        self.browser_send_keys(password + Keys.TAB) #password (again)

        self.browser_send_keys(Keys.RETURN)
        
        
        # Make sure that the page changed to the admin homepage
        if expect_success:
            self.assertTrue(self.wait_for_page_change(register_url), "RETURN causes page to change")
            self.assertIn(reverse("login"), self.browser.current_url, "Register browses to login page" )
            #self.check_django_message(message_type="success", contains="You successfully registered.")
            # uncomment message check when that code gets checked in

    def login_user(self, username, password, expect_success=True):
        """
        Tests that an existing admin user can log in.
        """

        login_url = self.reverse("login")
        self.browse_to(login_url) # Load page
        self.assertIn("Log in", self.browser.title, "Login page title")
        
        # Focus should be on username, pasword and submit
        #   should be accessible through keyboard only.
        self.browser.find_element_by_id("id_username").clear() # explicitly set the focus, to start
        self.browser.find_element_by_id("id_username").click() # explicitly set the focus, to start
        self.browser.switch_to_active_element().send_keys(username + Keys.TAB)
        self.browser.switch_to_active_element().send_keys(password + Keys.TAB)
        self.browser.switch_to_active_element().send_keys(Keys.RETURN)
        
        # Make sure that the page changed to the admin homepage
        if expect_success:
            self.assertTrue(self.wait_for_page_change(login_url), "RETURN causes page to change")


    def login_admin(self, username=None, password=None, expect_success=True):
        if username is None:
            username = self.admin_user.username
        if password is None:
            password = self.admin_pass
            
        self.login_user(username=username, password=password, expect_success=expect_success)
        if expect_success:
            self.assertIn(reverse("easy_admin"), self.browser.current_url, "Login browses to easy_admin page" )

    def login_teacher(self, username, password, expect_success=True):
        self.login_user(username=username, password=password, expect_success=expect_success)
        if expect_success:
            self.assertIn(reverse("coach_reports"), self.browser.current_url, "Login browses to coach reports page" )
            self.check_django_message("success", contains="You've been logged in!")
    
    def login_student(self, username, password, expect_success=True):
        self.login_user(username=username, password=password, expect_success=expect_success)
        time.sleep(self.max_wait_time/10) # allow time for async messages to load
        if expect_success:
            self.assertIn(reverse("homepage"), self.browser.current_url, "Login browses to homepage" )
            self.check_django_message("success", contains="You've been logged in!")
    
    
    def logout_user(self):
        if self.is_logged_in():
            # Since logout redirects to the homepage, browse_to will fail (with no good way to avoid).
            #   so be smarter in that case.
            if self.reverse("homepage") in self.browser.current_url:
                self.browser.get(self.reverse("logout"))
            else:
                self.browse_to(self.reverse("logout"))
            self.assertIn(reverse("homepage"), self.browser.current_url, "Logout browses to homepage" )
            self.assertFalse(self.is_logged_in(), "Make sure that user is no longer logged in.")


    def is_logged_in(self, expected_username=None):
        # Two ways to be logged in:
        # 1. Student: #logged-in-name is username
        # 2. Admin: #logout contains username
        logged_in_name_text = self.browser.find_element_by_id("logged-in-name").text
        logout_text = self.browser.find_element_by_id("logout").text

        username =  logged_in_name_text or logout_text[0:len(" (LOGOUT)")]
        return username and (not expected_username or username == expected_username)


class KALiteRegisteredDistributedBrowserTestCase(KALiteDistributedBrowserTestCase):
    """Same thing, but do the setup steps to register a facility."""
    facility_name = "Test Facility"
    
    def setUp(self):
        """Add a facility, so users can begin registering / logging in immediately."""
        
        super(KALiteRegisteredDistributedBrowserTestCase,self).setUp() # sets up admin, etc
        
        self.add_facility(facility_name=self.facility_name)        
        #Facility(name=self.facility_name).save()
        self.logout_user()

    def add_facility(self, facility_name):
        """Add a facility"""
        
        # Login as admin
        self.login_admin()

        # Add the facility
        add_facility_url = self.reverse("add_facility", kwargs={"id": "new"})
        self.browse_to(add_facility_url)
        
        self.browser_activate_element(id="id_name") # explicitly set the focus, to start
        self.browser_send_keys(facility_name)
        self.browser.find_elements_by_class_name("submit")[0].click()
        self.wait_for_page_change(add_facility_url)
        
        self.check_django_message(message_type="success", contains="has been successfully saved!")
        


@distributed_only
class DeviceUnregisteredTest(KALiteDistributedBrowserTestCase):
    """Validate all the steps of registering a device.
    
    Currently, only testing that the device is not registered works.
    """

    def test_device_unregistered(self):
        """
        Tests that a device is initially unregistered, and that it can
        be registered through automatic means.
        """

        home_url = self.reverse("homepage")

        # First, get the homepage without any automated information.
        self.browser.get(home_url) # Load page
        self.check_django_message(message_type="warning", contains="complete the setup.")
        self.assertFalse(self.is_logged_in(), "Not (yet) logged in")
        
        # Now, log in as admin
        self.login_admin()


@distributed_only
class ChangeLocalUserPassword(unittest.TestCase):
    """Tests for the changelocalpassword command"""
    
    def setUp(self):
        """Create a new facility and facility user"""
        self.facility = Facility(name="Test Facility")
        self.facility.save()
        self.group = FacilityGroup(facility=self.facility, name="Test Class")
        self.group.full_clean()
        self.group.save()
        self.user = FacilityUser(facility=self.facility, username="testuser", first_name="Firstname", last_name="Lastname", group=self.group)
        self.user.clear_text_password = "testpass" # not used anywhere but by us, for testing purposes
        self.user.set_password(self.user.clear_text_password)
        self.user.full_clean()
        self.user.save()
    
    
    def test_change_password(self):
        """Change the password on an existing user."""
        
        # Now, re-retrieve the user, to check.
        (out,err,val) = call_command_with_output("changelocalpassword", self.user.username, noinput=True)
        self.assertEquals(err, "", "no output on stderr")
        self.assertNotEquals(out, "", "some output on stderr")
        self.assertEquals(val, 0, "Exit code is zero")

        match = re.match(r"^.*Error: user '([^']+)' does not exist$", err.replace("\n",""), re.M)
        self.assertFalse(match is None, "could not parse stderr")
        self.assertEquals(match.groups()[0], fake_username, "Verify printed fake username")
        self.assertNotEquals(val, 0, "Verify exit code is non-zero")


@distributed_only
class UserRegistrationCaseTest(KALiteRegisteredDistributedBrowserTestCase):
    username   = "user1"
    password   = "password"

    def test_register_login_exact(self):
        """Tests that a user can login with the exact same email address as registered"""

        # Register user in one case
        self.register_user(username=self.username.lower(), password=self.password)

        # Login in the same case
        self.login_student(username=self.username.lower(), password=self.password)
        self.logout_user()


    def test_login_mixed(self):
        """Tests that a user can login with the uppercased version of the email address that was registered"""

        # Register user in one case
        self.register_user(username=self.username.lower(), password=self.password)

        # Login in the same case
        self.login_student(username=self.username.upper(), password=self.password)
        self.logout_user()


    def test_register_mixed(self):
        """Tests that a user cannot re-register with the uppercased version of an email address that was registered"""
         
        # Register user in one case
        self.register_user(username=self.username.lower(), password=self.password)

        # Try to register again in a different case
        self.register_user(username=self.username.upper(), password=self.password, expect_success=False)

        text_box = self.browser.find_element_by_id("id_username") # form element        
        error    = text_box.parent.find_elements_by_class_name("errorlist")[-1]
        self.assertIn("A user with this username at this facility already exists.", error.text, "Check 'username is taken' error.")


    def test_login_two_users_different_cases(self):
        """Tests that a user cannot re-register with the uppercased version of an email address that was registered"""
        
        user1_uname = self.username.lower()
        user2_uname = "a"+self.username.lower()
        user1_password = self.password
        user2_password = "a"+self.password
        user1_fname = "User1"
        user2_fname = "User2"
        
        # Register & activate two users with different usernames / emails
        self.register_user(username=user1_uname, password=user1_password, first_name=user1_fname)
        self.login_student(username=user1_uname, password=user1_password)
        self.logout_user()
        
        self.register_user(username=user2_uname, password=user2_password, first_name=user2_fname)
        self.login_student(username=user2_uname, password=user2_password)
        self.logout_user()
        
        # Change the second user to be a case-different version of the first user
        user2 = FacilityUser.objects.get(username=user2_uname)
        user2_uname = user1_uname.upper()
        user2.username = user2_uname
        user2.email = user2_uname
        user2.save()
        
        # First, make sure that user 1 can only log in with user 1's email/password
        self.login_student(username=user1_uname, password=user1_password) # succeeds
        self.logout_user()
        self.login_student(username=user2_uname, password=user1_password, expect_success=False) # fails
        self.check_django_message("error", contains="There was an error logging you in.")
        
        # Now, check the same in the opposite direction.
        self.login_student(username=user2_uname, password=user2_password) # succeeds
        self.logout_user()

        self.login_student(username=user1_uname, password=user2_password, expect_success=False) # fails
        self.check_django_message("error", contains="There was an error logging you in.")
