from setuptools import setup, find_packages


def desc():
    with open("README.md") as f:
        return f.read()


setup(
    name='frasco-angular',
    version='0.1',
    url='http://github.com/frascoweb/frasco-angular',
    license='MIT',
    author='Maxime Bouroumeau-Fuseau',
    author_email='maxime.bouroumeau@gmail.com',
    description="Angular integration for Frasco",
    long_description=desc(),
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=[
        'frasco',
        'frasco-assets'
    ]
)