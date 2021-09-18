#!/usr/bin/env python3

from __future__ import print_function

import os
import sys
import time
import logging
import tempfile
import traceback
import subprocess

from shutil import disk_usage, rmtree
from base64 import b64decode

try:
    import pathlib
    import importlib.util
except ImportError:
    pass


class GIT(object):
    @classmethod
    def works(cls):
        try:
            return bool(subprocess.check_output('git --version', shell=True))
        except:
            return False


class PIP(object):
    @classmethod
    def run(cls, command, check_output=False):
        if not cls.works():
            raise RuntimeError("Could not import pip.")

        try:
            return PIP.run_python_m(*command.split(), check_output=check_output)
        except subprocess.CalledProcessError as e:
            return e.returncode
        except:
            traceback.print_exc()
            print("Error using -m method")

    @classmethod
    def run_python_m(cls, *args, **kwargs):
        check_output = kwargs.pop('check_output', False)
        check = subprocess.check_output if check_output else subprocess.check_call
        return check([sys.executable, '-m', 'pip'] + list(args))

    @classmethod
    def run_pip_main(cls, *args, **kwargs):
        import pip

        args = list(args)
        check_output = kwargs.pop('check_output', False)

        if check_output:
            from io import StringIO

            out = StringIO()
            sys.stdout = out

            try:
                pip.main(args)
            except:
                traceback.print_exc()
            finally:
                sys.stdout = sys.__stdout__

                out.seek(0)
                pipdata = out.read()
                out.close()

                print(pipdata)
                return pipdata
        else:
            return pip.main(args)

    @classmethod
    def run_install(cls, cmd, quiet=False, check_output=False):
        return cls.run("install %s%s" % ('-q ' if quiet else '', cmd), check_output)

    @classmethod
    def run_show(cls, cmd, check_output=False):
        return cls.run("show %s" % cmd, check_output)

    @classmethod
    def works(cls):
        try:
            import pip
            return True
        except ImportError:
            return False

    # noinspection PyTypeChecker
    @classmethod
    def get_module_version(cls, mod):
        try:
            out = cls.run_show(mod, check_output=True)

            if isinstance(out, bytes):
                out = out.decode()

            datas = out.replace('\r\n', '\n').split('\n')
            expectedversion = datas[3]

            if expectedversion.startswith('Version: '):
                return expectedversion.split()[1]
            else:
                return [x.split()[1] for x in datas if x.startswith("Version: ")][0]
        except:
            pass

    @classmethod
    def get_requirements(cls, file='requirements.txt'):
        from pip.req import parse_requirements
        return list(parse_requirements(file))


# Setup initial loggers

tmpfile = tempfile.TemporaryFile('w+', encoding='utf8')
log = logging.getLogger('launcher')
log.setLevel(logging.DEBUG)

sh = logging.StreamHandler(stream=sys.stdout)
sh.setFormatter(logging.Formatter(
    fmt="[%(levelname)s] %(name)s: %(message)s"
))

sh.setLevel(logging.INFO)
log.addHandler(sh)

tfh = logging.StreamHandler(stream=tmpfile)
tfh.setFormatter(logging.Formatter(
    fmt="[%(relativeCreated).9f] %(asctime)s - %(levelname)s - %(name)s: %(message)s"
))
tfh.setLevel(logging.DEBUG)
log.addHandler(tfh)


def finalize_logging():
    if os.path.isfile("logs/musicbot.log"):
        log.info("Moving old musicbot log")
        try:
            if os.path.isfile("logs/musicbot.log.last"):
                os.unlink("logs/musicbot.log.last")
            os.rename("logs/musicbot.log", "logs/musicbot.log.last")
        except:
            pass

    with open("logs/musicbot.log", 'w', encoding='utf8') as f:
        tmpfile.seek(0)
        f.write(tmpfile.read())
        tmpfile.close()

        f.write('\n')
        f.write(" PRE-RUN SANITY CHECKS PASSED ".center(80, '#'))
        f.write('\n\n')

    global tfh
    log.removeHandler(tfh)
    del tfh

    fh = logging.FileHandler("logs/musicbot.log", mode='a')
    fh.setFormatter(logging.Formatter(
        fmt="[%(relativeCreated).9f] %(name)s-%(levelname)s: %(message)s"
    ))
    fh.setLevel(logging.DEBUG)
    log.addHandler(fh)

    sh.setLevel(logging.INFO)

    dlog = logging.getLogger('discord')
    dlh = logging.StreamHandler(stream=sys.stdout)
    dlh.terminator = ''
    dlh.setFormatter(logging.Formatter('.'))
    dlog.addHandler(dlh)


def bugger_off(msg="Press enter to continue . . .", code=1):
    input(msg)
    sys.exit(code)

def opt_check_disk_space(warnlimit_mb=200):
    if disk_usage('.').free < warnlimit_mb*1024*2:
        log.warning("Less than %sMB of free space remains on this device" % warnlimit_mb)


#################################################

def pyexec(pycom, *args, pycom2=None):
    pycom2 = pycom2 or pycom
    os.execlp(pycom, pycom2, *args)


def main():
    # TODO: *actual* argparsing

    if '--no-checks' not in sys.argv:
        sanity_checks()

    finalize_logging()

    import asyncio

    if sys.platform == 'win32':
        loop = asyncio.ProactorEventLoop()  # needed for subprocesses
        asyncio.set_event_loop(loop)

    tried_requirementstxt = False
    tryagain = True

    loops = 0
    max_wait_time = 60

    while tryagain:
        # Maybe I need to try to import stuff first, then actually import stuff
        # It'd save me a lot of pain with all that awful exception type checking

        m = None
        try:
            from musicbot import MusicBot
            m = MusicBot()

            sh.terminator = ''
            sh.terminator = '\n'

            m.run()

        except SyntaxError:
            log.exception("Syntax error (this is a bug, not your fault)")
            break

        except ImportError:
            # TODO: if error module is in pip or dpy requirements...

            if not tried_requirementstxt:
                tried_requirementstxt = True

                log.exception("Error starting bot")
                log.info("Attempting to install dependencies...")

                err = PIP.run_install('--upgrade -r requirements.txt')

                if err: # TODO: add the specific error check back as not to always tell users to sudo it
                    print()
                    log.critical("You may need to %s to install dependencies." %
                                 ['use sudo', 'run as admin'][sys.platform.startswith('win')])
                    break
                else:
                    print()
                    log.info("Ok lets hope it worked")
                    print()
            else:
                log.exception("Unknown ImportError, exiting.")
                break

        except Exception as e:
            if hasattr(e, '__module__') and e.__module__ == 'musicbot.exceptions':
                if e.__class__.__name__ == 'HelpfulError':
                    log.info(e.message)
                    break

                elif e.__class__.__name__ == "TerminateSignal":
                    break

                elif e.__class__.__name__ == "RestartSignal":
                    loops = 0
                    pass
            else:
                log.exception("Error starting bot")

        finally:
            if not m or not m.init_ok:
                if any(sys.exc_info()):
                    # How to log this without redundant messages...
                    traceback.print_exc()
                break

            asyncio.set_event_loop(asyncio.new_event_loop())
            loops += 1

        sleeptime = min(loops * 2, max_wait_time)
        if sleeptime:
            log.info("Restarting in {} seconds...".format(loops*2))
            time.sleep(sleeptime)

    print()
    log.info("All done.")


if __name__ == '__main__':
    main()
