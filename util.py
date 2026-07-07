# MN Analysis of Sentencing Trends
# Programming By:
# Sidney D. Allen
# Special Thanks:
# Dr. Lindsey Vigesaa
# Dr. Mary Clifford
# David Hudson
#
# util.py
# miscellaneous utilities

import html

import bcrypt

ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])
# taken from StackOverflow - https://stackoverflow.com/questions/9647202/ordinal-numbers-replacement


def normalize_password(plain_text_password):
    # The ONE normalization applied to a password before it touches bcrypt — used by BOTH
    # account creation (/new, before get_hashed_password) and login verification (/login,
    # before check_password) so the two can never drift apart.
    #
    # !!! DO NOT CHANGE THIS FUNCTION without a migration plan. Every stored hash was
    # computed over html.escape(password); altering the normalization (even dropping the
    # escape) makes every existing account's password stop verifying. The html.escape is
    # a historical artifact of form sanitization, kept deliberately for hash compatibility.
    return html.escape(plain_text_password)


def get_hashed_password(plain_text_password):
    # Hash a password for the first time
    #   (Using bcrypt, the salt is saved into the hash itself)
    return bcrypt.hashpw(plain_text_password.encode(), bcrypt.gensalt())


def check_password(plain_text_password, hashed_password):
    # Check hashed password. Using bcrypt, the salt is saved into the hash itself
    return bcrypt.checkpw(plain_text_password.encode(), hashed_password)
