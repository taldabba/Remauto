import distutils.core
import Cython.Build
import os
distutils.core.setup(
    ext_modules = Cython.Build.cythonize(os.path.dirname(os.path.abspath(__file__)) + "\\comms.pyx",
    compiler_directives={'language_level': 3}))