from setuptools import setup, find_packages

long_description = '''Yet another tool for extracting source from PyInstaller archives.

Unlike several (all?) other options, this one supports binaries for non-Windows platforms.
'''.strip()

setup(
	name='pydeinstaller',
	version='0.0.2',
	author='Charles Duffy',
	author_email='charles@dyfis.net',
	url='https://github.com/charles-dyfis-net/pydeinstaller',
	package_dir={'': 'src'},
	packages=find_packages('src'),
	license='GPLv3',
	long_description=long_description,
	entry_points={
		'console_scripts': [
			'pydeinstaller = pydeinstaller:main'
		],
	},
	install_requires=[
		'pyinstaller',
		'uncompyle6',
		'xdis',
	],
)
