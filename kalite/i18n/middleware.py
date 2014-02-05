"""
i18n/middleware:

Here, we have three major pieces of code:
1. Set the language for the request (request.session["django_language"], copied to request.language),
  using some cached data (see code below) or the "lang" GET parameter
2. (optional) Set the language for this user (facility users only) via "set_language" GET parameter
3. (optional) Set the default language for this installation (teacher or superuser rights required)
  via the "set_default_language" GET parameter

Other values set here:
  request.session["default_language"] - if no "lang" GET parameter is specified, this is the language to use on the current request.
  request.session["language_choices"] - available languages (based on language pack metadata)

"""
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.utils import translation
from django.utils.translation import ugettext_lazy as _

import settings
from config.models import Settings
from settings import LOG as logging
from shared.i18n import lcode_to_django_lang, lcode_to_ietf, get_installed_language_packs


def set_default_language(request, lang_code, global_set=False):
    """
    global_set has different meanings for different users.
    For students, it means their personal default language
    For teachers, it means their personal default language
    For django users, it means the server language.
    """
    lang_code = lcode_to_django_lang(lang_code)

    if lang_code != request.session.get("default_language"):
        logging.debug("setting session language to %s" % lang_code)
        request.session["default_language"] = lang_code

    if global_set:
        if request.is_django_user and lang_code != Settings.get("default_language"):
            logging.debug("setting server default language to %s" % lang_code)
            Settings.set("default_language", lang_code)
        elif not request.is_django_user and request.is_logged_in and lang_code != request.session["facility_user"].default_language:
            logging.debug("setting user default language to %s" % lang_code)
            request.session["facility_user"].default_language = lang_code
            request.session["facility_user"].save()

    set_request_language(request, lang_code)

def set_request_language(request, lang_code, persist=True):
    # each request can get the language from the querystring, or from the currently set session language

    lang_code = lcode_to_django_lang(lang_code)
    if lang_code != request.session.get(settings.LANGUAGE_COOKIE_NAME) and persist:
        logging.debug("setting session language to %s" % lang_code)
        # Just in case we have a db-backed session, don't write unless we have to.
        request.session[settings.LANGUAGE_COOKIE_NAME] = lang_code

    request.language = lcode_to_ietf(lang_code)

def set_language_choices(request, force=False):
    """
    Read available languages from language pack metadata, if needed
    """
    if force or "language_choices" not in request.session:
        # Set the set of available languages
        request.session["language_choices"] = get_installed_language_packs()
    return request.session["language_choices"]

def set_language_data(request):
    """
    Process requests to set language, redirect to the same URL to continue processing
    without leaving the "set" in the browser history.
    """
    set_language_choices(request)

    if "set_default_language" in request.GET:
        # Set the current server default language, and redirect (to clean browser history)
        if not request.is_admin:
            raise PermissionDenied(_("You don't have permissions to set the server's default language."))

        set_default_language(request, lang_code=request.GET["set_default_language"], global_set=True)

        # Redirect to the same URL, but without the GET param,
        #   to remove the language setting from the browser history.
        redirect_url = request.get_full_path().replace("set_default_language=" + request.GET["set_default_language"], "")
        return HttpResponseRedirect(redirect_url)

    elif "set_language" in request.GET:
        # Set the current user's session language, and redirect (to clean browser history)
        set_default_language(request, request.GET["set_language"], global_set=(request.is_logged_in and not request.is_django_user))

        # Redirect to the same URL, but without the GET param,
        #   to remove the language setting from the browser history.
        redirect_url = request.get_full_path().replace("set_language=" + request.GET["set_language"], "")
        return HttpResponseRedirect(redirect_url)

    if not "default_language" in request.session:
        # default_language has the following priority:
        #   facility user's individual setting
        #   config.Settings object's value
        #   settings' value
        request.session["default_language"] = getattr(request.session.get("facility_user"), "default_language", None) \
            or Settings.get("default_language") \
            or settings.LANGUAGE_CODE

    # Set this request's language based on the listed priority
    cur_lang = request.GET.get("lang") \
        or request.session.get(settings.LANGUAGE_COOKIE_NAME) \
        or request.session.get("default_language")

    set_request_language(request, lang_code=cur_lang, persist=False)


class SessionLanguage:
    def process_request(self, request):
        return set_language_data(request)
