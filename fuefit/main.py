#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2013-2014 ankostis@gmail.com
#
# This file is part of fuefit.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.
"""The command-line entry-point for using all functionality of fuefit tool. """

import sys, os
import traceback
import logging
import argparse
from argparse import RawTextHelpFormatter
from textwrap import dedent
import re
import functools
import json
import jsonschema as jsons
import jsonpointer as jsonp

from . import model, _version


DEBUG   = True
TESTRUN = False
PROFILE = False

log = None

## When option `-m MODEL_PATH=VALUE` contains a relative path the following is preppended.
_model_default_prefix = '/engine/'

_key_value_regex = re.compile(r'^\s*([A-Za-z]\w*)\s*=\s*(.*)$')
def key_value_pair(arg):
    """Argument-type for -I and -O, syntaxed like: KEY=VALUE."""

    m = _key_value_regex.match(arg)
    if m:
        return m.groups()
    else:
        raise argparse.ArgumentTypeError("Not a KEY=VALUE syntax: %s"%arg)


_column_specifier_regex = re.compile(r'^\s*([^(]+)\s*(\(([^)]+)\))?\s*$')
def column_specifier(arg):
    """Argument-type for --icolumns, syntaxed like: COL_NAME [(UNITS)]."""

    m = _column_specifier_regex.match(arg)
    if m:
        return m.groups()
    else:
        raise argparse.ArgumentTypeError("Not a COLUMN_SPEC syntax: %s"%arg)


def main(argv=None):
    """Calculates an engine-map by fitting data-points vectors.

    REMARKS:
    --------
        * All string-values are case-sensitive.

    EXAMPLES:
    ---------
        Assuming a CSV-file 'engine_fc.csv' like this:
            CM,PMF,PME
            12,0.14,180
            ...

        then the next command  calculates and writes the fitted engine map's parameters
        as JSON into 'engine_map.json' file:
            %(prog)s -m fuel=PETROL --in-file engine_fc.csv -out-file engine_map
        and if header-row did not exist, it should become:
            %(prog)s -m fuel=DIESEL -i engine_fc.csv -o engine_map --icolumns CM PMF PME
        and if instead of PME we had a column with normalized-Power in Watts (instead of kW):
            %(prog)s -m fuel=PETROL -i engine_fc.csv -o engine_map  -c CM  PMF 'Pnorm (w)'

        Now, if input vectors are in 2 separate files, the 1st, 'engine_1.xlsx',
        having 5 columns with different headers than expected, like this:
            OTHER1    OTHER2       N        "Fuel waste"     OTHER3
            0        -1            12         0.14           "some text"
            ...

        and the 2nd having 2 columns with no headers at all and the 1st one being 'Pnorm',
        then it would take the following to read them:
            %(prog)s -o engine_map -m fuel=PETROL \
                    -i=engine_1.xlsx \
                    -c X   X   N   'Fuel consumption'  X \
                    -r X   X   RPM 'FC(g/s)'           X \
                    -i=engine_2.csv \
                    -c Pnorm X

        To explicitly specify the encoding, the file-type and the separator character:
            %(prog)s -o engine_map.txt -O encoding=UTF-8 -i=engine_data -f csv -I 'sep=;' -I encoding=UTF-8
    """

    global log, DEBUG

    program_name    = 'fuefit' #os.path.basename(sys.argv[0])

    if argv is None:
        argv = sys.argv[1:]

    parser = setup_args_parser(program_name)
    try:

        opts = parser.parse_args(argv)

        DEBUG = bool(opts.debug)

        if (DEBUG):
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)
        log = logging.getLogger(__file__)
        log.info("opts: %s", opts)

        if opts.verbose > 0:
            log.info("verbosity level = %d", opts.verbose)

        opts = validate_opts(opts)
        mdl = build_and_validate_model(opts)

        if (DEBUG):
            log.info("Input Model: %s", json.dumps(mdl, indent=2))

    except (SystemExit) as ex:
        if DEBUG:
            traceback.print_exception()
        raise
    except (ValueError) as ex:
        if DEBUG:
            raise
        indent = len(program_name) * " "
        parser.exit(3, "%s: %s\n%s  for help use --help\n"%(program_name, ex, indent))
    except jsons.ValidationError as ex:
        if DEBUG:
            raise
        indent = len(program_name) * " "
        parser.exit(4, "%s: Model validation failed due to: %s\n%s  for help use --help\n"%(program_name, ex, indent))


def validate_opts(opts):
    ## Check number of input-files <--> related-opts
    #
    dopts = vars(opts)

    if (not opts.ifile):
        n_infiles = 1
    else:
        n_infiles = len(opts.ifile)
    rel_opts = ['icolumns', 'irenames', 'iformat', 'I']
    for ropt in rel_opts:
        opt_val = dopts[ropt]
        if (opt_val):
            n_ropt = len(opt_val)
            if( n_ropt > 1 and n_ropt != n_infiles):
                raise ValueError("Number of --%s(%i) mismatches number of --infile(%i)!"%(ropt, n_ropt, n_infiles))

    return opts

def build_and_validate_model(opts):
    mdl = model.base_model()

#     ## TODO: Merge models.
#     if (opts.model):
#         model.merge(mdl, opts.model)

    model_overrides = opts.m
    if (model_overrides):
        model_overrides = functools.reduce(lambda x,y: x+y, model_overrides)
        for (json_path, value) in model_overrides:
            if (not json_path.startswith('/')):
                json_path = _model_default_prefix + json_path
            jsonp.set_pointer(mdl, json_path, value)

    validator = model.model_validator()
    validator.validate(mdl)

    return mdl

def setup_args_parser(program_name):
    version_string  = '%%prog %s' % (_version)
    doc_lines       = main.__doc__.splitlines()
    desc            = doc_lines[0]
    epilog          = dedent('\n'.join(doc_lines[1:]))

    parser = argparse.ArgumentParser(prog=program_name, description=desc, epilog=epilog, add_help=False,
                                     formatter_class=RawTextHelpFormatter)


    grp_input = parser.add_argument_group('Input', 'Options controlling reading of input-file(s) and for specifying model values.')
    grp_input.add_argument('-i', '--ifile', help=dedent("""\
            the input-file(s) with the data-points (vectors).
            If more than one --ifile given, the number --iformat, --icolumns, --irenames and -I options
            must either match it, be 1 (meaning use them for all files), or be totally absent
            (meaning use defaults for all files); the order is important only within same options.
            The number of data-points (i.e. rows excluding header) for all data-files must be equal.
            Use '-' to specify reading <stdin>.
            Default: %(default)s"""),
                        action='append',
                        type=argparse.FileType('r'), required=True,
                        metavar='FILE')
#                         type=argparse.FileType('r'), default=sys.stdin,
#                         action='append', metavar='FILE')
    grp_input.add_argument('-c', '--icolumns', help=dedent("""\
            describes the contents and the units of input file(s) (see --ifile).
            It must be followed either by an integer denoting the index of the header-row
            within the tabular data, or by a list of column-names specifications,
            obeying the following syntax:
                COL_NAME [(UNITS)]
            Accepted quantities and their default units are grouped in 3+1 quantity-types and
            on each run exactly one from each of the 3 first categories must be present:
            1. engine-speed:
                RPM      (rad/min)
                RPMnorm  (rad/min)  : normalized against RPMnorm * RPM_IDLE + (RPM_RATED - RPM_IDLE)
                Omega    (rad/sec)
                CM       (m/sec)    : Mean Piston speed
            2. work-capability:
                P        (kW)
                Pnorm    (kW)       : normalized against P_MAX
                T        (Nm)
                PME      (bar)
            3. fuel-consumption:
                FC       (g/h)
                FCnorm   (g/h)      : normalized against P_MAX
                PMF      (bar)
            4. Irellevant column:
                X
            Default when files include heqders is 0 (1st row), otherwise it is 'RPM,P,FC'."""),
                        action='append', nargs='+',
                        type=column_specifier, metavar='COLUMN_SPEC')
    grp_input.add_argument('-r', '--irenames', help=dedent("""\
            renames the columns of input-file(s)  (see --ifile).
            It must be followed by a list of column-names specifications like --columns,
            but without accepting integers.
            The number of renamed-columns for each input-file must match those in the --icolumns.
            Use 'X' for columns not to be renamed."""),
                        action='append', nargs='+',
                        type=column_specifier, metavar='COLUMN_SPEC')
    grp_input.add_argument('-f', '--iformat', help=dedent("""\
            sets the format of input data file(s).
            It can be one of: %(choices)s
            When AUTO, format deduced fro the filename's extension (ie use it with Excel files).
            Different JSON sub-formats are supported through the use of the 'orient' keyword of Pandas
            (use the -I option to pass it).
            For more infos read the documentation of the read_json() method:
                http://pandas.pydata.org/pandas-docs/stable/generated/pandas.io.json.read_json.html
            Default: %(default)s"""),
                        choices=[ 'AUTO', 'CSV', 'TXT', 'XLS', 'JSON'],
                        action='append', metavar='FORMAT')
    grp_input.add_argument('-I', help=dedent("""\
            pass option(s) directly to pandas when reading input-file(s)."""),
                        action='append', nargs='+',
                        type=key_value_pair, metavar='KEY=VALUE')
    grp_input.add_argument('-m', help=dedent("""\
            override a model scalar values using an absolute or relative path.
            Relative paths are resolved against '/engine', for instance,
              -Mrpm_idle=850   -M/engine/p_max=660
            would set the following model's property:
                {
                  "engine": {
                      "rpm_idle": 850,
                      "p_max": 660,
                      ...
                  }
                }
            For the path syntax, see json-pointer spec:
                https://python-json-pointer.readthedocs.org/en/latest/tutorial.html
            """),
                        action='append', nargs='+',
                        type=key_value_pair, metavar='MODEL_PATH=VALUE')
    grp_input.add_argument('-M', help=dedent("""\
            get help description for the specfied model path.
            If no path specified, gets the default model-base. """),
                        action='append', nargs='*',
                        type=key_value_pair, metavar='MODEL_PATH')


    grp_output = parser.add_argument_group('Output', 'Options controlling writting of output-file.')
    grp_output.add_argument('-o', '--ofile', help=dedent("""\
            the output-file to write results into.
            Default: %(default)s]"""),
                        default=sys.stdout,
                        metavar='FILE')
    grp_output.add_argument('-a', '--append', help=dedent("""\
            append results if output-file already exists.
            Default: %(default)s"""),
                        type=bool, default=True)
    grp_output.add_argument('-t', '--oformat', help=dedent("""\
            the file-format of the results (see --ofile).
            See documentation for -f option."""),
                        choices=[ 'AUTO', 'CSV', 'TXT', 'XLS', 'JSON'],
                        action='append', metavar='FORMAT')
    grp_output.add_argument('-O', help=dedent("""\
            Pass option(s) directly to pandas when writting output-file."""),
                        nargs='+', type=key_value_pair, metavar='KEY=VALUE')


    grp_various = parser.add_argument_group('Various', 'Options controlling various other aspects.')
    #parser.add_argument('--gui', help='start in GUI mode', action='store_true')
    grp_various.add_argument("--debug", action="store_true", help="set debug level [default: %(default)s]", default=False)
    grp_various.add_argument("--verbose", action="count", default=0, help="set verbosity level [default: %(default)s]")
    grp_various.add_argument("--version", action="version", version=version_string, help="prints version identifier of the program")
    grp_various.add_argument("--help", action="help", help='show this help message and exit')

    return parser


if __name__ == "__main__":
    if TESTRUN:
        import doctest
        doctest.testmod()
    if PROFILE:
        import cProfile
        import pstats
        profile_filename = 'twanky_profile.txt'
        cProfile.run('main()', profile_filename)
        statsfile = open("profile_stats.txt", "wb")
        p = pstats.Stats(profile_filename, stream=statsfile)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.close()
        sys.exit(0)
    sys.exit(main())
