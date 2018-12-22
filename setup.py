from setuptools import setup, find_packages

def readme():
  with open("README.md") as f:
    return f.read()

setup(
  name = "ySanic",
  version = "0.1.0",
  description = "ySanic subclass with some addons to sanic",
  long_description = readme(),
  long_description_content_type='text/markdown',
  classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Plugins",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Topic :: Internet :: WWW/HTTP :: WSGI :: Server"
  ],
  keywords = "sanic",
  url = "https://github.com/Garito/ySanic",
  author = "Garito",
  author_email = "garito@gmail.com",
  license = "MIT",
  packages = find_packages(),
  python_requires=">=3.6",
  install_requires = [
    "sanic",
    "yModel"
  ],
  dependency_links = [
    "git+https://github.com/Garito/sanic-mongo#egg=sanic-mongo"
  ],
  test_suite = "unittest"
)
