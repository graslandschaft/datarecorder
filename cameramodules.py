"""
list_modules() and available_modules() let you query which audio modules
are installed and available.
"""

# probe for available camera modules:
camera_modules = dict()

try:
    from Camera_pointgrey import Camera
    camera_modules['pointgrey'] = True
except ImportError:
    camera_modules['pointgrey'] = False

try:
    from Camera import Camera
    camera_modules['opencv'] = True
except ImportError:
    camera_modules['opencv'] = False

try:
    from Camera_dummy import Camera
    camera_modules['dummy'] = True
except ImportError:
    camera_modules['dummy'] = False


def available_modules():
    """Returns:
         mods (list): list of installed audio modules.
    """
    mods = []
    for module, available in camera_modules.items():
        if available:
            mods.append(module)
    return mods


def disable_module(module):
    """
    Disable an audio module so that it is not used by the audioio functions and classes.
    
    Args:
      module (string): name of the module to be disabled as it appears in available_modules()
    """
    if module in camera_modules:
        camera_modules[module] = False


def list_modules(module=None):
    """Print list of all supported modules and whether they are available.

    Args:
      module (None or string): if None list all modules.
                         if string list only the specified module.
    """
    def print_module(module, available):
        if available:
            print('%-16s is installed' % module)
        else:
            print('%-16s is not installed' % module)

    if module is not None:
        print_module(module, camera_modules[module])
    else:
        for module, available in camera_modules.items():
            print_module(module, available)


if __name__ == "__main__":
    print("Checking camera-modules module ...")
    print('')
    list_modules()
    print('')
    print('available modules:')
    print('  %s' % '\n  '.join(available_modules()))
    print('')
    module = 'dummy'
    print('disable %s module:' % module)
    list_modules(module)
    disable_module(module)
    list_modules(module)
