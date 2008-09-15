"""
This is a makeapp.py script generated by py2applet

Usage:
    python makeapp.py py2app
"""

from setuptools import setup

APP = ['scripts/sip_rtp_audio_session.py']
DATA_FILES = []
OPTIONS = {'argv_emulation': True,
           'site_packages': True,
           'resources': ['scripts/ring_inbound.wav', 'scripts/ring_outbound.wav'],
           'includes': ['dns.*', 'application.*', 'pypjua.*'],
           'packages': ['dns', 'application', 'pypjua']}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
