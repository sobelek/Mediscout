from setuptools import setup

setup(
    name='mediscout',
    version='0.2',
    py_modules=['mediscout'],
    include_package_data=True,
    install_requires=[
        'fake-useragent',
        'click',
        'requests',
        'beautifulsoup4',
        'python-pushover',
        'notifiers',
        'xmpppy',
        'python-dotenv',
        'appdirs',
        'xmpppy',
        'lxml'
    ],
    entry_points='''
        [console_scripts]
        mediscout=mediscout:mediscout
    ''',
)
