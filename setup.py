from setuptools import setup

def readme():
  with open("README.md") as f:
    return f.read()

setup(
  name = "ySanic",
  version = "0.0.1",
  description = "ySanic subclass with some addons to sanic",
  long_description = readme(),
  classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Plugins",
    "Framework :: sanic",
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
  packages = ["ySanic"],
  install_requires = ["sanic"],
  dependency_links = [
    "git+https://github.com/Garito/sanic-mongo#egg=sanic-mongo",
    "git+https://github.com/Garito/yModel#egg=yModel"
  ],
  test_suite = "unittest"
)
