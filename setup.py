from setuptools import setup

setup(
    name='ncli',
    version='0.1',
    packages=["ncli", "ncli.cloudformation"],
    install_requires=[
        'Click',
        'boto3',
        'PyYAML',
        'colorama'
    ],
    entry_points='''
        [console_scripts]
        ncli=ncli.ncli:ncli
    ''',
)