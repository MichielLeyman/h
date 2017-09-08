# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import sqlalchemy as sa

from h.models import User
from h.util.user import split_user
from h.util.db import on_transaction_end

UPDATE_PREFS_ALLOWED_KEYS = set(['show_sidebar_tutorial'])


class UserNotActivated(Exception):
    """Tried to log in to an unactivated user account."""


class UserService(object):

    """A service for retrieving and performing common operations on users."""

    def __init__(self, default_authority, session):
        """
        Create a new user service.

        :param default_authority: the default authority for users
        :param session: the SQLAlchemy session object
        """
        self.default_authority = default_authority
        self.session = session

        # Local cache of fetched users.
        self._cache = {}

        # But don't allow the cache to persist after the session is closed.
        @on_transaction_end(session)
        def flush_cache():
            self._cache = {}

    def fetch(self, userid_or_username, authority=None):
        """
        Fetch a user by userid or by username and authority.

        Takes *either* a userid *or* a username and authority as arguments.
        For example::

          user_service.fetch('acct:foo@example.com')

        or::

          user_service.fetch('foo', 'example.com')

        :returns: a user instance, if found
        :rtype: h.models.User or None

        """
        if authority is not None:
            username = userid_or_username
        else:
            userid = userid_or_username
            parts = split_user(userid)
            username = parts['username']
            authority = parts['domain']

        # The cache is keyed by (username, authority) tuples.
        cache_key = (username, authority)

        if cache_key not in self._cache:
            self._cache[cache_key] = (self.session.query(User)
                                      .filter_by(username=username)
                                      .filter_by(authority=authority)
                                      .one_or_none())

        return self._cache[cache_key]

    def fetch_for_login(self, username_or_email):
        """
        Fetch a user by data provided in the login field.

        This searches for a user by username in the default authority, or by
        email in the default authority if `username_or_email` contains an "@"
        character.

        When fetching by an email address we use a case-insensitive query.

        :returns: A user object if a user was found, None otherwise.
        :rtype: h.models.User or NoneType
        :raises UserNotActivated: When the user is not activated.
        """
        filters = [(User.authority == self.default_authority)]
        if '@' in username_or_email:
            filters.append(
                sa.func.lower(User.email) == username_or_email.lower())
        else:
            filters.append(User.username == username_or_email)

        user = (self.session.query(User)
                .filter(*filters)
                .one_or_none())

        if user is None:
            return None

        if not user.is_activated:
            raise UserNotActivated()

        return user

    def update_preferences(self, user, **kwargs):
        invalid_keys = set(kwargs.keys()) - UPDATE_PREFS_ALLOWED_KEYS
        if invalid_keys:
            keys = ', '.join(sorted(invalid_keys))
            raise TypeError("settings with keys %s are not allowed" % keys)

        if 'show_sidebar_tutorial' in kwargs:
            user.sidebar_tutorial_dismissed = not kwargs['show_sidebar_tutorial']


def user_service_factory(context, request):
    """Return a UserService instance for the passed context and request."""
    return UserService(default_authority=request.authority,
                       session=request.db)
