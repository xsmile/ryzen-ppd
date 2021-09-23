#!/usr/bin/env python

from setuptools import find_packages, setup

import ryzen_ppd


def file(path: str):
    with open(path) as f:
        return f.read()


setup(
    # metadata
    name=ryzen_ppd.__name__,
    version=ryzen_ppd.__version__,
    description=ryzen_ppd.__description__,
    long_description=file('README.md'),
    long_description_content_type='text/markdown',
    author=ryzen_ppd.__author__,
    author_email=ryzen_ppd.__author_email__,
    url=ryzen_ppd.__url__,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Topic :: System :: Hardware'
    ],
    license=ryzen_ppd.__license__,
    keywords=ryzen_ppd.__keywords__,
    # options
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=file('requirements.txt').split(),
    entry_points={
        'console_scripts': [f'{ryzen_ppd.__pkgname__} = ryzen_ppd.main:main']
    }
)
