#!/usr/bin/env python

# Cylc suite-specific configuration data. The awesome ConfigObj and
# Validate modules do almost everything we need. This just adds a 
# method to check the few things that can't be automatically validated
# according to the spec, $CYLC_DIR/conf/suite-config.spec, such as
# cross-checking some items.

import taskdef
import re, os, sys
from validate import Validator
from configobj import ConfigObj

class SuiteConfigError( Exception ):
    """
    Attributes:
        message - what the problem is. 
        TO DO: element - config element causing the problem
    """
    def __init__( self, msg ):
        self.msg = msg
    def __str__( self ):
        return repr(self.msg)


class config( ConfigObj ):
    allowed_modifiers = ['dummy', 'contact', 'oneoff', 'sequential', 'catchup', 'catchup_contact']

    def __init__( self, file=None, spec=None ):
        if file:
            self.file = file
        else:
            self.file = os.path.join( os.environ[ 'CYLC_SUITE_DIR' ], 'suite.rc' ),

        if spec:
            self.spec = spec
        else:
            self.spec = os.path.join( os.environ[ 'CYLC_DIR' ], 'conf', 'suite-config.spec')

        # load config
        ConfigObj.__init__( self, self.file, configspec=self.spec )

        # validate and convert to correct types
        val = Validator()
        test = self.validate( val )
        if test != True:
            # TO DO: elucidate which items failed
            # (easy - see ConfigObj and Validate documentation)
            print test
            raise SuiteConfigError, "Suite Config Validation Failed"
        
        # check cylc-specific self consistency
        self.__check()

    def __check( self ):
        pass
        #for task in self['tasks']:
        #    # check for illegal type modifiers
        #    for modifier in self['tasks'][task]['type modifier list']:
        #        if modifier not in self.__class__.allowed_modifiers:
        #            raise SuiteConfigError, 'illegal type modifier for ' + task + ': ' + modifier

    def get_task_name_list( self ):
        return self['tasks'].keys()

    def get_task_shortname_list( self ):
        return self['tasks'].keys()

    def generate_task_classes( self, dir ):
        taskdefs = {}
        for cycle_list in self['dependency graph']:
            cycles = re.split( '\s*,\s*', cycle_list )

            for label in self['dependency graph'][ cycle_list ]:
                line = self['dependency graph'][cycle_list][label]

                sequence = re.split( '\s*->\s*', line )
                count = 0
                tasks = {}
                for name in sequence:
                    if name not in taskdefs:
                        # first time seen; define everything except for
                        # possible additional prerequisites.
                        if name not in self['tasks']:
                            raise SuiteConfigError, 'task ' + name + ' not defined'
                        taskconfig = self['tasks'][name]
                        taskd = taskdef.taskdef( name )
                        for item in taskconfig[ 'type list' ]:
                            if item == 'coldstart':
                                taskd.modifiers.append( 'oneoff' )
                                taskd.coldstart = True
                                continue
                            if item == 'free':
                                taskd.type = 'free'
                                continue
                            if item == 'oneoff' or \
                                item == 'sequential' or \
                                item == 'dummy' or \
                                item == 'catchup':
                                taskd.modifiers.append( item )
                                continue
                            
                            m = re.match( 'model\(\s*restarts\s*=\s*(\d+)\s*\)', item )
                            if m:
                                taskd.type = 'tied'
                                taskd.n_restart_outputs[ cycle_list ] = m.groups()[0]
                                continue

                            m = re.match( 'clock\(\s*offset\s*=\s*(\d+)\s*hour\s*\)', item )
                            if m:
                                taskd.modifiers.append( 'contact' )
                                taskd.contact_offset[ cycle_list ] = m.groups()[0]
                                continue

                            m = re.match( 'catchup clock\(\s*offset\s*=\s*(\d+)\s*hour\s*\)', item )
                            if m:
                                taskd.modifiers.append( 'catchup_contact' )
                                taskd.contact_offset[ cycle_list ] = m.groups()[0]
                                continue

                            raise SuiteConfigError, 'illegal task type: ' + item

                        taskd.logfiles = []
                        taskd.commands[ cycle_list ] = taskconfig[ 'command list' ]
                        taskd.environment[ cycle_list ] = taskconfig[ 'environment' ]

                        taskdefs[ name ] = taskd

                    for hour in cycles:
                        if hour not in taskdefs[name].hours:
                            taskdefs[name].hours.append( hour )

                    if count > 0:
                        if taskdefs[prev].coldstart:
                            if cycle_list not in taskdefs[prev].outputs:
                                taskdefs[prev].outputs[cycle_list] = []
                            taskdefs[prev].outputs[ cycle_list ].append( "'" + name + " restart files ready for ' + self.c_time" )
                        else:
                            if cycle_list not in taskdefs[name].prerequisites:
                                taskdefs[name].prerequisites[cycle_list] = []
                            taskdefs[name].prerequisites[ cycle_list ].append( "'" + prev + "%' + self.c_time + ' finished'" )
                    count += 1
                    prev = name

        for name in taskdefs:
            taskdefs[name].hours.sort( key=int ) 
            print name, taskdefs[name].type, taskdefs[name].hours
            taskdefs[name].write_task_class( dir )

