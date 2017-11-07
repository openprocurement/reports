from setuptools import setup

NAME = 'reports'
VERSION = '1.0.0'
AUTHOR = 'Quintagroup, Ltd.'
LICENSE = 'Apache License 2.0'
REQUIRES = [
    'couchdb',
    'dateparser',
    'pbkdf2',
    'requests',
    'requests_cache',
    'pytz',
    'iso8601',
    'pyminizip',
    'arrow',
    'boto3',
    'Jinja2',
    'systemd-python',
    'PyYaml',
    'ExtendedJournalHandler==1.0.0',
    'repoze.lru'
]

TEST_REQUIRES = REQUIRES + [
    'mock'
]

setup(
    name=NAME,
    version=VERSION,
    packages=[
        'reports',
    ],
    author=AUTHOR,
    author_email='info@quintagroup.com',
    license=LICENSE,
    url='https://github.com/openprocurement/reports',
    entry_points={
        'console_scripts': [
            'bids = reports.utilities.bids:run',
            'tenders = reports.utilities.tenders:run',
            'refunds = reports.utilities.refunds:run',
            'invoices = reports.utilities.invoices:run',
            'init = reports.db_init:run',
            'zip = reports.utilities.zip:run',
            'send = reports.utilities.send:run',
        ]
    },
    include_package_data=True,
    zip_safe=False,
    install_requires=REQUIRES,
    tests_require=TEST_REQUIRES,
    test_suite='reports.tests.main.suite',
    extras_require={'test': TEST_REQUIRES},
)
